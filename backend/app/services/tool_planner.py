"""
Read-only tool planner for Lighthouse.

This module maps a user request to registered Lighthouse tools.

It does not execute tools.
It does not change the operating system.
It does not call the LLM.

The planner is intentionally conservative:
- read-only diagnostic tools may be planned safely
- OS-changing tools are never automatic
- blocked tools remain blocked
- unknown requests receive safe alternatives only
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from app.services.tool_registry import (
    RISK_BLOCKED,
    get_tool_by_name,
    is_tool_allowed_for_automatic_use,
)


PLAN_STATUS_OK = "ok"
PLAN_STATUS_BLOCKED = "blocked"
PLAN_STATUS_NEEDS_CONFIRMATION = "needs_confirmation"
PLAN_STATUS_NEEDS_CLARIFICATION = "needs_clarification"


@dataclass(frozen=True)
class PlannedTool:
    """
    A registered Lighthouse tool selected by the planner.
    """

    name: str
    reason: str
    category: str
    risk_level: int
    read_only: bool
    implemented: bool
    requires_confirmation: bool
    requires_target: bool
    allow_automatic_use: bool
    logs_action: bool

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable representation of the planned tool.
        """
        return {
            "name": self.name,
            "reason": self.reason,
            "category": self.category,
            "risk_level": self.risk_level,
            "read_only": self.read_only,
            "implemented": self.implemented,
            "requires_confirmation": self.requires_confirmation,
            "requires_target": self.requires_target,
            "allow_automatic_use": self.allow_automatic_use,
            "logs_action": self.logs_action,
        }


@dataclass(frozen=True)
class ToolPlan:
    """
    A conservative plan for a user request.

    The plan describes what Lighthouse should consider doing later.
    It does not execute anything.
    """

    status: str
    intent: str
    user_request: str
    message: str
    tools: tuple[PlannedTool, ...]
    blocked_tools: tuple[PlannedTool, ...]
    safe_alternatives: tuple[PlannedTool, ...]

    @property
    def requires_confirmation(self) -> bool:
        """
        Return True if any planned tool requires confirmation.
        """
        return any(tool.requires_confirmation for tool in self.tools)

    @property
    def has_blocked_tools(self) -> bool:
        """
        Return True if the plan includes blocked tools.
        """
        return bool(self.blocked_tools)

    def tool_names(self) -> list[str]:
        """
        Return planned tool names in order.
        """
        return [tool.name for tool in self.tools]

    def blocked_tool_names(self) -> list[str]:
        """
        Return blocked tool names in order.
        """
        return [tool.name for tool in self.blocked_tools]

    def safe_alternative_names(self) -> list[str]:
        """
        Return safe alternative tool names in order.
        """
        return [tool.name for tool in self.safe_alternatives]

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable representation of the plan.
        """
        return {
            "status": self.status,
            "intent": self.intent,
            "user_request": self.user_request,
            "message": self.message,
            "requires_confirmation": self.requires_confirmation,
            "tools": [tool.to_dict() for tool in self.tools],
            "blocked_tools": [tool.to_dict() for tool in self.blocked_tools],
            "safe_alternatives": [
                tool.to_dict() for tool in self.safe_alternatives
            ],
        }


def normalize_request(user_request: str) -> str:
    """
    Normalize a user request for deterministic matching.
    """
    return " ".join(user_request.strip().lower().split())


def contains_any(text: str, phrases: list[str]) -> bool:
    """
    Return True if normalized text contains any phrase.

    Multi-word phrases use substring matching.
    Single words use word-boundary matching so "saved" does not match "save".
    """
    normalized_text = normalize_request(text)

    for phrase in phrases:
        normalized_phrase = normalize_request(phrase)

        if not normalized_phrase:
            continue

        if " " in normalized_phrase:
            if normalized_phrase in normalized_text:
                return True

            continue

        pattern = rf"\b{re.escape(normalized_phrase)}\b"

        if re.search(pattern, normalized_text):
            return True

    return False


def _dedupe_names(tool_names: list[str]) -> list[str]:
    """
    Preserve order while removing duplicate tool names.
    """
    seen: set[str] = set()
    unique_names: list[str] = []

    for tool_name in tool_names:
        normalized_name = tool_name.strip().lower()

        if normalized_name in seen:
            continue

        seen.add(normalized_name)
        unique_names.append(normalized_name)

    return unique_names


def _planned_tool(tool_name: str, reason: str) -> PlannedTool:
    """
    Convert a registered tool into a PlannedTool.

    Unknown tools are represented as blocked placeholders. In normal planner
    operation this should not happen because the planner only uses registered
    tool names.
    """
    normalized_name = tool_name.strip().lower()
    tool = get_tool_by_name(normalized_name)

    if tool is None:
        return PlannedTool(
            name=normalized_name,
            reason="Unknown tools are blocked.",
            category="blocked",
            risk_level=RISK_BLOCKED,
            read_only=False,
            implemented=False,
            requires_confirmation=True,
            requires_target=True,
            allow_automatic_use=False,
            logs_action=True,
        )

    return PlannedTool(
        name=tool.name,
        reason=reason,
        category=tool.category,
        risk_level=tool.risk_level,
        read_only=tool.read_only,
        implemented=tool.implemented,
        requires_confirmation=tool.requires_confirmation,
        requires_target=tool.requires_target,
        allow_automatic_use=is_tool_allowed_for_automatic_use(tool.name),
        logs_action=tool.logs_action,
    )


def _planned_tools(tool_names: list[str], reason: str) -> tuple[PlannedTool, ...]:
    """
    Convert registered tool names into planned tools.
    """
    return tuple(
        _planned_tool(tool_name, reason)
        for tool_name in _dedupe_names(tool_names)
    )


def _build_plan(
    *,
    status: str,
    intent: str,
    user_request: str,
    message: str,
    tool_names: list[str] | None = None,
    blocked_tool_names: list[str] | None = None,
    safe_alternative_names: list[str] | None = None,
) -> ToolPlan:
    """
    Build a ToolPlan from registered tool names.
    """
    return ToolPlan(
        status=status,
        intent=intent,
        user_request=user_request,
        message=message,
        tools=_planned_tools(
            tool_names or [],
            reason=f"Planned for intent: {intent}.",
        ),
        blocked_tools=_planned_tools(
            blocked_tool_names or [],
            reason=f"Blocked for intent: {intent}.",
        ),
        safe_alternatives=_planned_tools(
            safe_alternative_names or [],
            reason=f"Safe alternative for intent: {intent}.",
        ),
    )


def plan_tools_for_request(user_request: str) -> ToolPlan:
    """
    Create a conservative Lighthouse tool plan for a user request.

    This is the first agentic planning layer. It maps plain English requests
    to registered tools without executing anything.
    """
    cleaned_request = user_request.strip()
    normalized_request = normalize_request(cleaned_request)

    if not normalized_request:
        return _build_plan(
            status=PLAN_STATUS_NEEDS_CLARIFICATION,
            intent="empty_request",
            user_request=cleaned_request,
            message="No request was provided.",
            safe_alternative_names=["collect_snapshot"],
        )

    if _is_raw_command_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_BLOCKED,
            intent="blocked_raw_command",
            user_request=cleaned_request,
            message=(
                "Lighthouse does not plan arbitrary shell, PowerShell, "
                "or command-line execution."
            ),
            blocked_tool_names=["run_raw_command"],
            safe_alternative_names=["collect_snapshot", "show_health_summary"],
        )

    if _is_registry_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_BLOCKED,
            intent="blocked_registry_change",
            user_request=cleaned_request,
            message="Registry changes are blocked for Lighthouse V1.",
            blocked_tool_names=["edit_registry"],
            safe_alternative_names=["collect_snapshot", "show_health_summary"],
        )

    if _is_driver_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_BLOCKED,
            intent="blocked_driver_change",
            user_request=cleaned_request,
            message="Driver changes are blocked for Lighthouse V1.",
            blocked_tool_names=["change_drivers"],
            safe_alternative_names=["collect_snapshot", "show_health_summary"],
        )

    if _is_service_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_BLOCKED,
            intent="blocked_service_change",
            user_request=cleaned_request,
            message="Windows service changes are blocked for Lighthouse V1.",
            blocked_tool_names=["change_services"],
            safe_alternative_names=["collect_snapshot", "show_health_summary"],
        )

    if _is_uninstall_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_BLOCKED,
            intent="blocked_uninstall",
            user_request=cleaned_request,
            message="Software uninstall actions are blocked for Lighthouse V1.",
            blocked_tool_names=["uninstall_software"],
            safe_alternative_names=["collect_snapshot", "show_health_summary"],
        )

    if _is_delete_user_files_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_BLOCKED,
            intent="blocked_file_deletion",
            user_request=cleaned_request,
            message=(
                "Lighthouse does not plan user-file deletion. "
                "It can inspect disk usage first."
            ),
            blocked_tool_names=["delete_user_files"],
            safe_alternative_names=["collect_snapshot", "inspect_disk_usage"],
        )

    if _is_clear_temp_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_NEEDS_CONFIRMATION,
            intent="clear_temp_request",
            user_request=cleaned_request,
            message=(
                "Clearing a selected temporary folder is a future gated action. "
                "It requires a specific target and confirmation."
            ),
            tool_names=["clear_selected_temp_folder"],
            safe_alternative_names=["collect_snapshot", "inspect_disk_usage"],
        )

    if _is_close_process_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_NEEDS_CONFIRMATION,
            intent="close_process_request",
            user_request=cleaned_request,
            message=(
                "Closing a process is disruptive and cannot be automatic. "
                "Lighthouse should inspect processes first and require a "
                "specific target plus confirmation."
            ),
            tool_names=["close_selected_process"],
            safe_alternative_names=["collect_snapshot", "list_top_processes"],
        )

    if _is_disable_startup_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_NEEDS_CONFIRMATION,
            intent="disable_startup_request",
            user_request=cleaned_request,
            message=(
                "Changing startup apps is a future gated action. "
                "It requires a selected app and confirmation."
            ),
            tool_names=["disable_selected_startup_app"],
            safe_alternative_names=["collect_snapshot", "show_health_summary"],
        )

    if _is_enable_startup_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_NEEDS_CONFIRMATION,
            intent="enable_startup_request",
            user_request=cleaned_request,
            message=(
                "Changing startup apps is a future gated action. "
                "It requires a selected app and confirmation."
            ),
            tool_names=["enable_selected_startup_app"],
            safe_alternative_names=["collect_snapshot", "show_health_summary"],
        )

    if _is_save_snapshot_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_OK,
            intent="save_snapshot",
            user_request=cleaned_request,
            message="Lighthouse can plan a local snapshot save.",
            tool_names=["save_snapshot"],
            safe_alternative_names=["collect_snapshot"],
        )

    if _is_export_report_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_OK,
            intent="export_report",
            user_request=cleaned_request,
            message="Lighthouse can plan a future report export.",
            tool_names=["export_report"],
            safe_alternative_names=["collect_snapshot"],
        )

    if _is_open_task_manager_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_OK,
            intent="open_task_manager",
            user_request=cleaned_request,
            message="Lighthouse can plan opening Task Manager for inspection.",
            tool_names=["open_task_manager"],
            safe_alternative_names=["list_top_processes"],
        )

    if _is_open_resource_monitor_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_OK,
            intent="open_resource_monitor",
            user_request=cleaned_request,
            message="Lighthouse can plan opening Resource Monitor for inspection.",
            tool_names=["open_resource_monitor"],
            safe_alternative_names=["collect_snapshot"],
        )

    if _is_open_settings_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_OK,
            intent="open_windows_settings",
            user_request=cleaned_request,
            message="Lighthouse can plan opening a selected Windows Settings page.",
            tool_names=["open_windows_settings"],
            safe_alternative_names=["collect_snapshot"],
        )

    if _is_crash_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_OK,
            intent="recent_crash_check",
            user_request=cleaned_request,
            message="Lighthouse can inspect recent crash-relevant evidence.",
            tool_names=["collect_snapshot", "read_recent_events"],
        )

    if _is_slow_laptop_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_OK,
            intent="slow_laptop_diagnostics",
            user_request=cleaned_request,
            message="Lighthouse can inspect common read-only performance signals.",
            tool_names=[
                "collect_snapshot",
                "inspect_cpu_usage",
                "inspect_memory_usage",
                "inspect_disk_usage",
                "list_top_processes",
                "read_recent_events",
            ],
        )

    if _is_memory_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_OK,
            intent="memory_diagnostics",
            user_request=cleaned_request,
            message="Lighthouse can inspect read-only memory evidence.",
            tool_names=[
                "collect_snapshot",
                "inspect_memory_usage",
                "list_top_processes",
            ],
        )

    if _is_cpu_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_OK,
            intent="cpu_diagnostics",
            user_request=cleaned_request,
            message="Lighthouse can inspect read-only CPU evidence.",
            tool_names=[
                "collect_snapshot",
                "inspect_cpu_usage",
                "list_top_processes",
            ],
        )

    if _is_disk_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_OK,
            intent="disk_diagnostics",
            user_request=cleaned_request,
            message="Lighthouse can inspect read-only disk evidence.",
            tool_names=["collect_snapshot", "inspect_disk_usage"],
        )

    if _is_health_request(normalized_request):
        return _build_plan(
            status=PLAN_STATUS_OK,
            intent="health_check",
            user_request=cleaned_request,
            message="Lighthouse can run a read-only health check.",
            tool_names=[
                "collect_snapshot",
                "show_health_summary",
                "read_recent_events",
            ],
        )

    return _build_plan(
        status=PLAN_STATUS_NEEDS_CLARIFICATION,
        intent="unknown_request",
        user_request=cleaned_request,
        message=(
            "Lighthouse does not have a confident tool plan for this request. "
            "A read-only snapshot is the safest starting point."
        ),
        safe_alternative_names=["collect_snapshot", "show_health_summary"],
    )


def _is_raw_command_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "powershell",
            "command prompt",
            "cmd",
            "terminal",
            "shell",
            "run command",
            "run a command",
            "execute command",
            "execute script",
            "run script",
        ],
    )


def _is_registry_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "registry",
            "regedit",
            "edit registry",
            "change registry",
        ],
    )


def _is_driver_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "driver",
            "drivers",
            "update driver",
            "update drivers",
            "change driver",
            "change drivers",
        ],
    )


def _is_service_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "windows service",
            "windows services",
            "disable service",
            "disable services",
            "change service",
            "change services",
            "services.msc",
        ],
    )


def _is_uninstall_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "uninstall",
            "remove software",
            "remove program",
            "delete program",
        ],
    )


def _is_delete_user_files_request(text: str) -> bool:
    destructive_verbs = contains_any(
        text,
        [
            "delete",
            "remove",
            "erase",
            "wipe",
        ],
    )
    file_targets = contains_any(
        text,
        [
            "file",
            "files",
            "folder",
            "folders",
            "downloads",
            "documents",
            "desktop",
            "junk",
        ],
    )

    return destructive_verbs and file_targets


def _is_clear_temp_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "clear temp",
            "clear temporary",
            "delete temp",
            "delete temporary",
            "clean temp",
            "clean temporary",
        ],
    )


def _is_close_process_request(text: str) -> bool:
    close_words = contains_any(
        text,
        [
            "close",
            "kill",
            "end task",
            "force close",
            "stop process",
        ],
    )
    process_targets = contains_any(
        text,
        [
            "process",
            "processes",
            "app",
            "apps",
            "program",
            "programs",
            "chrome",
            "edge",
            "teams",
            "browser",
        ],
    )

    return close_words and process_targets


def _is_disable_startup_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "disable startup",
            "turn off startup",
            "stop startup",
            "startup app",
            "startup apps",
        ],
    )


def _is_enable_startup_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "enable startup",
            "turn on startup",
        ],
    )


def _is_save_snapshot_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "save snapshot",
            "save report",
            "save this report",
            "save this snapshot",
        ],
    )


def _is_export_report_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "export report",
            "export snapshot",
        ],
    )


def _is_open_task_manager_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "open task manager",
            "task manager",
        ],
    )


def _is_open_resource_monitor_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "open resource monitor",
            "resource monitor",
        ],
    )


def _is_open_settings_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "open settings",
            "windows settings",
            "settings page",
        ],
    )


def _is_crash_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "crash",
            "crashed",
            "blue screen",
            "bsod",
            "unexpected shutdown",
            "event log",
            "event logs",
            "recent events",
        ],
    )


def _is_slow_laptop_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "slow",
            "sluggish",
            "lag",
            "lagging",
            "freezing",
            "performance",
            "optimize",
            "optimise",
            "speed up",
            "feels slow",
        ],
    )


def _is_memory_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "memory",
            "ram",
        ],
    )


def _is_cpu_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "cpu",
            "processor",
        ],
    )


def _is_disk_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "disk",
            "storage",
            "space",
            "drive",
            "ssd",
            "hard drive",
        ],
    )


def _is_health_request(text: str) -> bool:
    return contains_any(
        text,
        [
            "health",
            "healthy",
            "wrong",
            "okay",
            "status",
            "check my laptop",
            "check my system",
            "is my laptop ok",
            "is my laptop okay",
        ],
    )