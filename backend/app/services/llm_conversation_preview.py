"""
Conversational preview bridge for Lighthouse LLM route proposals.

This module shows the Operator a side-by-side comparison between:
- deterministic Operator conversation routing
- model-proposed routing through LLM Contract V0
- deterministic route handoff and autorun-gate policy

It does not execute tools.
It does not mutate the operating system.
It does not hand model output to talk or talkrun.
It does not grant model output authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.llm_route_engine import (
    LLMRouteCallResult,
    ModelRouteCallable,
    build_llm_route_call,
)
from app.services.llm_preview_journal import record_llm_route_preview
from app.services.operator_conversation import (
    OperatorConversationResult,
    interpret_operator_input,
)
from app.services.operator_routes import validate_route_handoff_for_autorun


LLM_CONVERSATION_PREVIEW_STATUS_OK = "ok"
LLM_CONVERSATION_PREVIEW_STATUS_NEEDS_CLARIFICATION = "needs_clarification"


@dataclass(frozen=True)
class LLMConversationPreviewResult:
    """
    Stable result for an LLM conversational preview.
    """

    status: str
    message: str
    user_request: str
    deterministic_result: OperatorConversationResult | None
    llm_route_result: LLMRouteCallResult | None
    autorun_gate: Any | None
    preview_journal_result: dict[str, Any] | None
    executed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable LLM conversational preview result.
        """
        return {
            "status": self.status,
            "message": self.message,
            "user_request": self.user_request,
            "deterministic_result": (
                self.deterministic_result.to_dict()
                if self.deterministic_result is not None
                else None
            ),
            "llm_route_result": (
                self.llm_route_result.to_dict()
                if self.llm_route_result is not None
                else None
            ),
            "autorun_gate": (
                self.autorun_gate.to_dict()
                if self.autorun_gate is not None
                and hasattr(self.autorun_gate, "to_dict")
                else None
            ),
            "preview_journal_result": self.preview_journal_result,
            "executed": self.executed,
        }


def yes_no(value: bool) -> str:
    """
    Convert a boolean into a human-readable yes/no value.
    """
    return "yes" if value else "no"


def extract_preview_id(journal_result: dict[str, Any] | None) -> str | None:
    """
    Extract the preview id from a preview journal result.
    """
    if not isinstance(journal_result, dict):
        return None

    data = journal_result.get("data", {})

    if isinstance(data, dict):
        preview_id = data.get("preview_id")

        if isinstance(preview_id, str) and preview_id:
            return preview_id

    return None


def build_llm_conversation_preview(
    user_request: str,
    *,
    model_callable: ModelRouteCallable | None = None,
    memory_dir: Any | None = None,
) -> LLMConversationPreviewResult:
    """
    Build an LLM conversational preview.

    This is preview-only. It never executes the deterministic or model-proposed route.
    """
    cleaned_request = user_request.strip()

    if not cleaned_request:
        return LLMConversationPreviewResult(
            status=LLM_CONVERSATION_PREVIEW_STATUS_NEEDS_CLARIFICATION,
            message="Please provide a request after llm talk.",
            user_request="",
            deterministic_result=None,
            llm_route_result=None,
            autorun_gate=None,
            preview_journal_result=None,
            executed=False,
        )

    deterministic_result = interpret_operator_input(cleaned_request)
    llm_route_result = build_llm_route_call(
        cleaned_request,
        model_callable=model_callable,
    )

    handoff = {}

    if llm_route_result.validation is not None:
        handoff = llm_route_result.validation.route_handoff or {}

    autorun_gate = validate_route_handoff_for_autorun(handoff) if handoff else None

    preview_journal_result = record_llm_route_preview(
        user_request=cleaned_request,
        preview_result=llm_route_result,
        memory_dir=memory_dir,
    )

    return LLMConversationPreviewResult(
        status=LLM_CONVERSATION_PREVIEW_STATUS_OK,
        message="LLM conversational preview completed. No command was executed.",
        user_request=cleaned_request,
        deterministic_result=deterministic_result,
        llm_route_result=llm_route_result,
        autorun_gate=autorun_gate,
        preview_journal_result=preview_journal_result,
        executed=False,
    )


def format_deterministic_section(
    result: OperatorConversationResult | None,
) -> list[str]:
    """
    Format the deterministic talk section.
    """
    lines = [
        "DETERMINISTIC INTERPRETATION",
        "-" * 52,
    ]

    if result is None:
        lines.append("Status: not_available")
        return lines

    lines.extend(
        [
            f"Status: {result.status}",
            f"Intent: {result.intent}",
            f"Interpreted request: {result.interpreted_request}",
            f"Recommended command: {result.recommended_command}",
        ]
    )

    if result.clarifying_question:
        lines.append(f"Clarifying question: {result.clarifying_question}")

    return lines


def format_model_section(result: LLMRouteCallResult | None) -> list[str]:
    """
    Format the model proposal section.
    """
    lines = [
        "MODEL PROPOSAL",
        "-" * 52,
    ]

    if result is None:
        lines.append("Status: not_available")
        return lines

    lines.extend(
        [
            f"Status: {result.status}",
            f"Message: {result.message}",
            f"Model used: {result.model_used or 'none'}",
            f"Used model: {yes_no(result.used_model)}",
        ]
    )

    validation = result.validation

    if validation is None:
        lines.append("Contract validation: not_available")
        return lines

    proposal = validation.normalized_proposal or {}

    lines.extend(
        [
            f"Contract status: {validation.status}",
            f"Contract valid: {yes_no(validation.valid)}",
            f"Contract message: {validation.message}",
            f"Proposed intent: {proposal.get('proposed_intent', 'unknown')}",
            f"Interpreted request: {proposal.get('interpreted_request')}",
            f"Confidence: {proposal.get('confidence')}",
        ]
    )

    if validation.errors:
        lines.append("Contract errors:")
        lines.extend(f"- {error}" for error in validation.errors)

    if validation.warnings:
        lines.append("Contract warnings:")
        lines.extend(f"- {warning}" for warning in validation.warnings)

    return lines


def format_handoff_section(
    result: LLMRouteCallResult | None,
    autorun_gate: Any | None,
) -> list[str]:
    """
    Format the deterministic route handoff derived from model proposal validation.
    """
    lines = [
        "ROUTE HANDOFF",
        "-" * 52,
    ]

    handoff = {}

    if result is not None and result.validation is not None:
        handoff = result.validation.route_handoff or {}

    if not handoff:
        lines.append("Route handoff: none")
        return lines

    lines.extend(
        [
            f"Route ready: {yes_no(bool(handoff.get('route_ready')))}",
            f"Route known: {yes_no(bool(handoff.get('route_known')))}",
            f"Intent: {handoff.get('intent')}",
            f"Safety class: {handoff.get('safety_class')}",
            f"Command family: {handoff.get('command_family')}",
            f"Recommended command: {handoff.get('recommended_command')}",
            f"Engine request: {handoff.get('engine_request')}",
            f"Autorun allowed by policy: {yes_no(bool(handoff.get('autorun_allowed')))}",
            "Manual review required: "
            f"{yes_no(bool(handoff.get('manual_review_required')))}",
        ]
    )

    if autorun_gate is not None:
        lines.extend(
            [
                f"Autorun gate allowed: {yes_no(bool(autorun_gate.allowed))}",
                f"Autorun gate status: {autorun_gate.status}",
                f"Autorun gate reason: {autorun_gate.reason}",
            ]
        )

    return lines


def format_execution_section(result: LLMConversationPreviewResult) -> list[str]:
    """
    Format the execution and feedback guidance section.
    """
    lines = [
        "EXECUTION",
        "-" * 52,
        "No command was executed by llm talk.",
        "Model output was not handed to talk or talkrun.",
        "Model output cannot bypass the route registry or autorun gate.",
    ]

    recommended_command = None

    if (
        result.llm_route_result is not None
        and result.llm_route_result.validation is not None
    ):
        handoff = result.llm_route_result.validation.route_handoff or {}
        recommended_command = handoff.get("recommended_command")

    if recommended_command:
        lines.append(f"To continue manually: {recommended_command}")

    preview_id = extract_preview_id(result.preview_journal_result)

    if preview_id:
        lines.append(f"Preview ID: {preview_id}")
        lines.append(
            "To review this preview: "
            f"llm preview feedback {preview_id} useful [note]"
        )

    return lines


def format_llm_conversation_preview_report(
    result: LLMConversationPreviewResult,
) -> str:
    """
    Format an LLM conversational preview for the CLI.
    """
    lines = [
        "LIGHTHOUSE LLM TALK PREVIEW",
        "=" * 52,
        "Mode: preview_only",
        "Execution: disabled",
        "Authority: deterministic route registry and autorun gate",
        "",
        f"Status: {result.status}",
        f"Message: {result.message}",
    ]

    if not result.user_request:
        lines.extend(
            [
                "",
                "Examples:",
                "- llm talk my laptop feels slow",
                "- llm talk why is chrome eating memory",
                "=" * 52,
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            f"Request: {result.user_request}",
            "",
            *format_deterministic_section(result.deterministic_result),
            "",
            *format_model_section(result.llm_route_result),
            "",
            *format_handoff_section(result.llm_route_result, result.autorun_gate),
            "",
            *format_execution_section(result),
            "=" * 52,
        ]
    )

    return "\n".join(lines)
