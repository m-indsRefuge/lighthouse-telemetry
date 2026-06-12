"""
Read-only tool executor for Lighthouse.

This module executes only safe, registered, read-only Lighthouse tools.

It does not execute OS-changing tools.
It does not run arbitrary commands.
It does not bypass the tool registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.collectors.event_logs import get_recent_system_events
from app.main import collect_telemetry
from app.services.insights import build_system_insight
from app.services.tool_planner import PLAN_STATUS_OK, ToolPlan, plan_tools_for_request
from app.services.tool_registry import (
    RISK_BLOCKED,
    RISK_READ_ONLY,
    get_tool_by_name,
    get_tool_safety_summary,
    is_tool_allowed_for_automatic_use,
)


TOOL_EXECUTION_EXECUTED = "executed"
TOOL_EXECUTION_REFUSED = "refused"
TOOL_EXECUTION_ERROR = "error"

PLAN_EXECUTION_COMPLETED = "completed"
PLAN_EXECUTION_PARTIAL = "partial"
PLAN_EXECUTION_REFUSED = "refused"


@dataclass
class ToolExecutionContext:
    """
    Shared execution context for one tool plan run.

    This caches telemetry, event evidence, and insight data so multiple tools
    in one plan use the same snapshot.
    """

    telemetry: dict[str, Any] | None = None
    event_report: dict[str, Any] | None = None
    insight: dict[str, Any] | None = None

    def get_telemetry(self) -> dict[str, Any]:
        """
        Return cached telemetry, collecting it once if needed.
        """
        if self.telemetry is None:
            self.telemetry = collect_telemetry()

        return self.telemetry

    def get_event_report(self) -> dict[str, Any]:
        """
        Return cached event evidence, collecting it once if needed.
        """
        if self.event_report is None:
            self.event_report = get_recent_system_events(limit=100)

        return self.event_report

    def get_insight(self) -> dict[str, Any]:
        """
        Return cached Lighthouse insight, building it once if needed.
        """
        if self.insight is None:
            self.insight = build_system_insight(
                telemetry=self.get_telemetry(),
                event_report=self.get_event_report(),
            )

        return self.insight


@dataclass(frozen=True)
class ToolExecutionResult:
    """
    Result of attempting to execute one registered tool.
    """

    tool_name: str
    status: str
    message: str
    data: dict[str, Any] | None
    safety_summary: dict[str, object]

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable result shape.
        """
        return {
            "tool_name": self.tool_name,
            "status": self.status,
            "message": self.message,
            "data": self.data,
            "safety_summary": self.safety_summary,
        }


@dataclass(frozen=True)
class ToolPlanExecutionResult:
    """
    Result of executing safe tools from a Lighthouse tool plan.
    """

    status: str
    message: str
    plan_status: str
    intent: str
    user_request: str
    executed_tools: tuple[ToolExecutionResult, ...]
    refused_tools: tuple[ToolExecutionResult, ...]
    blocked_tools: tuple[str, ...]
    safe_alternatives: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable plan execution result.
        """
        return {
            "status": self.status,
            "message": self.message,
            "plan_status": self.plan_status,
            "intent": self.intent,
            "user_request": self.user_request,
            "executed_tools": [
                result.to_dict() for result in self.executed_tools
            ],
            "refused_tools": [
                result.to_dict() for result in self.refused_tools
            ],
            "blocked_tools": list(self.blocked_tools),
            "safe_alternatives": list(self.safe_alternatives),
        }


def normalize_tool_name(tool_name: str) -> str:
    """
    Normalize tool names for lookup and dispatch.
    """
    return tool_name.strip().lower()


def get_tool_execution_safety(tool_name: str) -> dict[str, object]:
    """
    Decide whether a tool may be executed automatically.

    Only registered, implemented, read-only, risk-0, automatic tools are allowed.
    """
    normalized_name = normalize_tool_name(tool_name)
    tool = get_tool_by_name(normalized_name)
    safety_summary = get_tool_safety_summary(normalized_name)

    if tool is None:
        return {
            **safety_summary,
            "executable": False,
            "reason": "Unknown tools cannot be executed.",
        }

    if tool.risk_level == RISK_BLOCKED:
        return {
            **safety_summary,
            "executable": False,
            "reason": "Blocked tools cannot be executed.",
        }

    if not tool.implemented:
        return {
            **safety_summary,
            "executable": False,
            "reason": "Tool is registered but not implemented.",
        }

    if not tool.read_only:
        return {
            **safety_summary,
            "executable": False,
            "reason": "Only read-only tools can be executed by this executor.",
        }

    if tool.risk_level != RISK_READ_ONLY:
        return {
            **safety_summary,
            "executable": False,
            "reason": "Only risk level 0 tools can be executed automatically.",
        }

    if tool.requires_confirmation:
        return {
            **safety_summary,
            "executable": False,
            "reason": "Tools requiring confirmation cannot run automatically.",
        }

    if tool.requires_target:
        return {
            **safety_summary,
            "executable": False,
            "reason": "Tools requiring a target cannot run automatically.",
        }

    if not is_tool_allowed_for_automatic_use(normalized_name):
        return {
            **safety_summary,
            "executable": False,
            "reason": "Tool is not allowed for automatic use.",
        }

    return {
        **safety_summary,
        "executable": True,
        "reason": "Tool is safe for automatic read-only execution.",
    }


def _refused_tool_result(tool_name: str, message: str) -> ToolExecutionResult:
    """
    Build a refused tool result.
    """
    normalized_name = normalize_tool_name(tool_name)

    return ToolExecutionResult(
        tool_name=normalized_name,
        status=TOOL_EXECUTION_REFUSED,
        message=message,
        data=None,
        safety_summary=get_tool_execution_safety(normalized_name),
    )


def _execute_collect_snapshot(context: ToolExecutionContext) -> dict[str, Any]:
    """
    Execute the collect_snapshot tool.
    """
    return {
        "telemetry": context.get_telemetry(),
        "event_report": context.get_event_report(),
        "insight": context.get_insight(),
    }


def _execute_show_health_summary(context: ToolExecutionContext) -> dict[str, Any]:
    """
    Execute the show_health_summary tool.
    """
    return {
        "insight": context.get_insight(),
    }


def _execute_list_top_processes(context: ToolExecutionContext) -> dict[str, Any]:
    """
    Execute the list_top_processes tool.
    """
    return {
        "processes": context.get_telemetry().get("processes", {}),
    }


def _execute_read_recent_events(context: ToolExecutionContext) -> dict[str, Any]:
    """
    Execute the read_recent_events tool.
    """
    return {
        "event_report": context.get_event_report(),
    }


def _execute_inspect_memory_usage(context: ToolExecutionContext) -> dict[str, Any]:
    """
    Execute the inspect_memory_usage tool.
    """
    return {
        "memory": context.get_telemetry().get("memory", {}),
    }


def _execute_inspect_cpu_usage(context: ToolExecutionContext) -> dict[str, Any]:
    """
    Execute the inspect_cpu_usage tool.
    """
    return {
        "cpu": context.get_telemetry().get("cpu", {}),
    }


def _execute_inspect_disk_usage(context: ToolExecutionContext) -> dict[str, Any]:
    """
    Execute the inspect_disk_usage tool.
    """
    return {
        "disk": context.get_telemetry().get("disk", {}),
    }


_READ_ONLY_TOOL_EXECUTORS: dict[
    str,
    Callable[[ToolExecutionContext], dict[str, Any]],
] = {
    "collect_snapshot": _execute_collect_snapshot,
    "show_health_summary": _execute_show_health_summary,
    "list_top_processes": _execute_list_top_processes,
    "read_recent_events": _execute_read_recent_events,
    "inspect_memory_usage": _execute_inspect_memory_usage,
    "inspect_cpu_usage": _execute_inspect_cpu_usage,
    "inspect_disk_usage": _execute_inspect_disk_usage,
}


def execute_registered_tool(
    tool_name: str,
    context: ToolExecutionContext | None = None,
) -> ToolExecutionResult:
    """
    Execute one registered safe read-only tool.

    Unsafe, unknown, unimplemented, or non-automatic tools are refused.
    """
    normalized_name = normalize_tool_name(tool_name)
    safety_summary = get_tool_execution_safety(normalized_name)

    if not safety_summary.get("executable", False):
        return ToolExecutionResult(
            tool_name=normalized_name,
            status=TOOL_EXECUTION_REFUSED,
            message=str(safety_summary.get("reason", "Tool execution refused.")),
            data=None,
            safety_summary=safety_summary,
        )

    executor = _READ_ONLY_TOOL_EXECUTORS.get(normalized_name)

    if executor is None:
        return ToolExecutionResult(
            tool_name=normalized_name,
            status=TOOL_EXECUTION_REFUSED,
            message="No read-only executor is configured for this tool.",
            data=None,
            safety_summary={
                **safety_summary,
                "executable": False,
                "reason": "No read-only executor is configured for this tool.",
            },
        )

    execution_context = context or ToolExecutionContext()

    try:
        data = executor(execution_context)

        return ToolExecutionResult(
            tool_name=normalized_name,
            status=TOOL_EXECUTION_EXECUTED,
            message="Tool executed successfully.",
            data=data,
            safety_summary=safety_summary,
        )
    except Exception as error:
        return ToolExecutionResult(
            tool_name=normalized_name,
            status=TOOL_EXECUTION_ERROR,
            message=f"Tool execution failed: {error}",
            data=None,
            safety_summary=safety_summary,
        )


def execute_tool_plan(plan: ToolPlan) -> ToolPlanExecutionResult:
    """
    Execute safe read-only tools from a ToolPlan.

    Plans that are blocked, need confirmation, or need clarification are not
    executed. Their tools are returned as refused.
    """
    blocked_tool_names = tuple(plan.blocked_tool_names())
    safe_alternative_names = tuple(plan.safe_alternative_names())

    if plan.status != PLAN_STATUS_OK:
        refused_results = tuple(
            _refused_tool_result(
                tool.name,
                f"Tool was not executed because plan status is {plan.status}.",
            )
            for tool in (*plan.tools, *plan.blocked_tools)
        )

        return ToolPlanExecutionResult(
            status=PLAN_EXECUTION_REFUSED,
            message=(
                "Plan was not executed because it is not an automatic "
                "read-only plan."
            ),
            plan_status=plan.status,
            intent=plan.intent,
            user_request=plan.user_request,
            executed_tools=(),
            refused_tools=refused_results,
            blocked_tools=blocked_tool_names,
            safe_alternatives=safe_alternative_names,
        )

    if not plan.tools:
        return ToolPlanExecutionResult(
            status=PLAN_EXECUTION_REFUSED,
            message="Plan did not contain executable tools.",
            plan_status=plan.status,
            intent=plan.intent,
            user_request=plan.user_request,
            executed_tools=(),
            refused_tools=(),
            blocked_tools=blocked_tool_names,
            safe_alternatives=safe_alternative_names,
        )

    context = ToolExecutionContext()
    executed_results: list[ToolExecutionResult] = []
    refused_results: list[ToolExecutionResult] = []

    for planned_tool in plan.tools:
        result = execute_registered_tool(
            tool_name=planned_tool.name,
            context=context,
        )

        if result.status == TOOL_EXECUTION_EXECUTED:
            executed_results.append(result)
        else:
            refused_results.append(result)

    if executed_results and refused_results:
        status = PLAN_EXECUTION_PARTIAL
        message = "Some safe tools executed, but at least one tool was refused."
    elif executed_results:
        status = PLAN_EXECUTION_COMPLETED
        message = "All safe read-only tools executed successfully."
    else:
        status = PLAN_EXECUTION_REFUSED
        message = "No tools were executed."

    return ToolPlanExecutionResult(
        status=status,
        message=message,
        plan_status=plan.status,
        intent=plan.intent,
        user_request=plan.user_request,
        executed_tools=tuple(executed_results),
        refused_tools=tuple(refused_results),
        blocked_tools=blocked_tool_names,
        safe_alternatives=safe_alternative_names,
    )


def execute_tools_for_request(user_request: str) -> ToolPlanExecutionResult:
    """
    Plan a user request, then execute only safe read-only tools from the plan.
    """
    plan = plan_tools_for_request(user_request)

    return execute_tool_plan(plan)