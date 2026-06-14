"""
Lighthouse Engine v1.

This module is the first unified orchestration layer for Lighthouse.

It coordinates the existing safe components:

- tool execution planning
- read-only execution
- target resolution
- confirmation preview generation
- action journaling
- confirmation preview journaling

It does not execute OS-changing tools.
It does not accept confirmation input.
It does not close processes, delete files, edit settings, or mutate the OS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.action_journal import record_plan_execution
from app.services.confirmation_gate import (
    ConfirmationRequest,
    build_confirmation_request,
)
from app.services.confirmation_journal import record_target_confirmation_preview
from app.services.target_resolver import (
    TARGET_STATUS_CANDIDATE_FOUND,
    TargetResolution,
    resolve_target_for_tool,
)
from app.services.tool_executor import (
    ToolPlanExecutionResult,
    execute_tools_for_request,
)


ENGINE_STATUS_OK = "ok"
ENGINE_STATUS_NEEDS_CLARIFICATION = "needs_clarification"
ENGINE_STATUS_ERROR = "error"

ENGINE_EXECUTION_STATUS_NOT_RUN = "not_run"


@dataclass(frozen=True)
class LighthouseConfirmationPreview:
    """
    A target-aware confirmation preview produced by the engine.

    This object represents what Lighthouse would show to the Operator before any
    future confirmation or action executor could run.
    """

    tool_name: str
    target_resolution: TargetResolution
    confirmation_request: ConfirmationRequest
    journal_result: Any | None

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable confirmation preview shape.
        """
        return {
            "tool_name": self.tool_name,
            "target_resolution": self.target_resolution.to_dict(),
            "confirmation_request": confirmation_request_to_dict(
                self.confirmation_request
            ),
            "journal_result": journal_result_to_dict(self.journal_result),
        }


@dataclass(frozen=True)
class LighthouseEngineResult:
    """
    Unified result returned by Lighthouse Engine v1.
    """

    status: str
    message: str
    user_request: str
    execution_status: str
    plan_status: str
    intent: str
    execution_result: ToolPlanExecutionResult | None
    confirmation_previews: tuple[LighthouseConfirmationPreview, ...]
    plan_journal_result: Any | None
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable engine result shape.
        """
        return {
            "status": self.status,
            "message": self.message,
            "user_request": self.user_request,
            "execution_status": self.execution_status,
            "plan_status": self.plan_status,
            "intent": self.intent,
            "execution_result": execution_result_to_dict(self.execution_result),
            "confirmation_previews": [
                preview.to_dict()
                for preview in self.confirmation_previews
            ],
            "plan_journal_result": journal_result_to_dict(
                self.plan_journal_result
            ),
            "errors": list(self.errors),
        }


def journal_result_to_dict(journal_result: Any | None) -> dict[str, Any] | None:
    """
    Convert a journal write result into a compact serializable shape.
    """
    if journal_result is None:
        return None

    return {
        "status": getattr(journal_result, "status", "unknown"),
        "message": getattr(journal_result, "message", ""),
        "path": str(getattr(journal_result, "path", "")),
    }


def confirmation_request_to_dict(
    confirmation_request: ConfirmationRequest,
) -> dict[str, Any]:
    """
    Convert a confirmation request into a compact serializable shape.
    """
    return {
        "status": confirmation_request.status,
        "tool_name": confirmation_request.tool_name,
        "message": confirmation_request.message,
        "risk_level": confirmation_request.risk_level,
        "requires_confirmation": confirmation_request.requires_confirmation,
        "requires_target": confirmation_request.requires_target,
        "target": confirmation_request.target,
        "required_phrase": confirmation_request.required_phrase,
        "executable_after_confirmation": (
            confirmation_request.executable_after_confirmation
        ),
    }


def execution_result_to_dict(
    execution_result: ToolPlanExecutionResult | None,
) -> dict[str, Any] | None:
    """
    Convert a tool-plan execution result into a compact serializable shape.

    If the execution result already provides to_dict(), use it. Otherwise, fall
    back to the fields Lighthouse Engine v1 depends on.
    """
    if execution_result is None:
        return None

    to_dict = getattr(execution_result, "to_dict", None)

    if callable(to_dict):
        return to_dict()

    return {
        "user_request": getattr(execution_result, "user_request", ""),
        "status": getattr(execution_result, "status", "unknown"),
        "plan_status": getattr(execution_result, "plan_status", "unknown"),
        "intent": getattr(execution_result, "intent", "unknown"),
        "message": getattr(execution_result, "message", ""),
        "executed_tool_count": len(getattr(execution_result, "executed_tools", ())),
        "refused_tool_count": len(getattr(execution_result, "refused_tools", ())),
        "blocked_tools": list(getattr(execution_result, "blocked_tools", ())),
        "safe_alternatives": list(
            getattr(execution_result, "safe_alternatives", ())
        ),
    }


def get_confirmable_target(target_resolution: TargetResolution) -> str | None:
    """
    Return a target only when target resolution produced one clear candidate.

    Ambiguous or missing targets are not passed into the confirmation gate.
    """
    if target_resolution.status != TARGET_STATUS_CANDIDATE_FOUND:
        return None

    return target_resolution.target


def build_confirmation_previews(
    execution_result: ToolPlanExecutionResult,
) -> tuple[LighthouseConfirmationPreview, ...]:
    """
    Build target-aware confirmation previews for refused confirmation-gated tools.

    This does not execute tools.
    This does not accept confirmation input.
    """
    if execution_result.plan_status != "needs_confirmation":
        return ()

    previews: list[LighthouseConfirmationPreview] = []

    for refused_tool in execution_result.refused_tools:
        target_resolution = resolve_target_for_tool(
            tool_name=refused_tool.tool_name,
            user_request=execution_result.user_request,
        )

        confirmation_request = build_confirmation_request(
            tool_name=refused_tool.tool_name,
            target=get_confirmable_target(target_resolution),
        )

        journal_result = record_target_confirmation_preview(
            user_request=execution_result.user_request,
            tool_name=refused_tool.tool_name,
            target_resolution=target_resolution,
            confirmation_request=confirmation_request,
        )

        previews.append(
            LighthouseConfirmationPreview(
                tool_name=refused_tool.tool_name,
                target_resolution=target_resolution,
                confirmation_request=confirmation_request,
                journal_result=journal_result,
            )
        )

    return tuple(previews)


def run_lighthouse_engine(user_request: str) -> LighthouseEngineResult:
    """
    Run Lighthouse Engine v1 for a single Operator request.

    This currently supports the same safety boundary as runplan:
    safe read-only tools may execute, but confirmation-gated and blocked tools
    are not executed.
    """
    cleaned_request = user_request.strip()

    if not cleaned_request:
        return LighthouseEngineResult(
            status=ENGINE_STATUS_NEEDS_CLARIFICATION,
            message="Please provide an Operator request.",
            user_request=user_request,
            execution_status=ENGINE_EXECUTION_STATUS_NOT_RUN,
            plan_status="needs_clarification",
            intent="unknown",
            execution_result=None,
            confirmation_previews=(),
            plan_journal_result=None,
            errors=(),
        )

    errors: list[str] = []

    try:
        execution_result = execute_tools_for_request(cleaned_request)
    except Exception as error:  # pragma: no cover - defensive boundary
        return LighthouseEngineResult(
            status=ENGINE_STATUS_ERROR,
            message="Lighthouse Engine failed while executing the tool plan.",
            user_request=cleaned_request,
            execution_status=ENGINE_EXECUTION_STATUS_NOT_RUN,
            plan_status="error",
            intent="unknown",
            execution_result=None,
            confirmation_previews=(),
            plan_journal_result=None,
            errors=(str(error),),
        )

    try:
        plan_journal_result = record_plan_execution(execution_result)
    except Exception as error:  # pragma: no cover - defensive boundary
        plan_journal_result = None
        errors.append(f"Plan journal write failed: {error}")

    try:
        confirmation_previews = build_confirmation_previews(execution_result)
    except Exception as error:  # pragma: no cover - defensive boundary
        confirmation_previews = ()
        errors.append(f"Confirmation preview build failed: {error}")

    return LighthouseEngineResult(
        status=ENGINE_STATUS_OK,
        message=execution_result.message,
        user_request=execution_result.user_request,
        execution_status=execution_result.status,
        plan_status=execution_result.plan_status,
        intent=execution_result.intent,
        execution_result=execution_result,
        confirmation_previews=confirmation_previews,
        plan_journal_result=plan_journal_result,
        errors=tuple(errors),
    )