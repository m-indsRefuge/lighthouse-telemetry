"""
Tool registry for Lighthouse.

This module defines what Lighthouse is allowed to know about as a tool.

It does not execute tools.
It does not change the operating system.
It is a safety and planning layer for future agentic behavior.
"""

from dataclasses import dataclass


RISK_READ_ONLY = 0
RISK_CONVENIENCE = 1
RISK_REVERSIBLE_ACTION = 2
RISK_DISRUPTIVE_ACTION = 3
RISK_BLOCKED = 4


@dataclass(frozen=True)
class ToolDefinition:
    """
    Metadata describing a Lighthouse tool.

    The registry is used by future planning and permission layers to decide
    which tools can be suggested, planned, blocked, or executed.
    """

    name: str
    description: str
    category: str
    risk_level: int
    read_only: bool
    implemented: bool
    requires_confirmation: bool
    requires_target: bool
    allow_automatic_use: bool
    logs_action: bool
    notes: str = ""


_REGISTERED_TOOLS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="collect_snapshot",
        description="Collect a full read-only Lighthouse telemetry snapshot.",
        category="diagnostics",
        risk_level=RISK_READ_ONLY,
        read_only=True,
        implemented=True,
        requires_confirmation=False,
        requires_target=False,
        allow_automatic_use=True,
        logs_action=False,
    ),
    ToolDefinition(
        name="show_health_summary",
        description="Show a simple read-only system health summary.",
        category="diagnostics",
        risk_level=RISK_READ_ONLY,
        read_only=True,
        implemented=True,
        requires_confirmation=False,
        requires_target=False,
        allow_automatic_use=True,
        logs_action=False,
    ),
    ToolDefinition(
        name="list_top_processes",
        description="List the processes using the most memory.",
        category="diagnostics",
        risk_level=RISK_READ_ONLY,
        read_only=True,
        implemented=True,
        requires_confirmation=False,
        requires_target=False,
        allow_automatic_use=True,
        logs_action=False,
    ),
    ToolDefinition(
        name="read_recent_events",
        description="Read recent crash-relevant Windows System event evidence.",
        category="diagnostics",
        risk_level=RISK_READ_ONLY,
        read_only=True,
        implemented=True,
        requires_confirmation=False,
        requires_target=False,
        allow_automatic_use=True,
        logs_action=False,
    ),
    ToolDefinition(
        name="inspect_memory_usage",
        description="Inspect current memory usage from telemetry.",
        category="diagnostics",
        risk_level=RISK_READ_ONLY,
        read_only=True,
        implemented=True,
        requires_confirmation=False,
        requires_target=False,
        allow_automatic_use=True,
        logs_action=False,
    ),
    ToolDefinition(
        name="inspect_cpu_usage",
        description="Inspect current CPU usage from telemetry.",
        category="diagnostics",
        risk_level=RISK_READ_ONLY,
        read_only=True,
        implemented=True,
        requires_confirmation=False,
        requires_target=False,
        allow_automatic_use=True,
        logs_action=False,
    ),
    ToolDefinition(
        name="inspect_disk_usage",
        description="Inspect current disk usage from telemetry.",
        category="diagnostics",
        risk_level=RISK_READ_ONLY,
        read_only=True,
        implemented=True,
        requires_confirmation=False,
        requires_target=False,
        allow_automatic_use=True,
        logs_action=False,
    ),
    ToolDefinition(
        name="compare_snapshots",
        description="Compare two saved Lighthouse snapshots.",
        category="diagnostics",
        risk_level=RISK_READ_ONLY,
        read_only=True,
        implemented=False,
        requires_confirmation=False,
        requires_target=True,
        allow_automatic_use=False,
        logs_action=False,
        notes="Planned future read-only tool.",
    ),
    ToolDefinition(
        name="save_snapshot",
        description="Save a timestamped local Lighthouse snapshot file.",
        category="reporting",
        risk_level=RISK_CONVENIENCE,
        read_only=False,
        implemented=True,
        requires_confirmation=False,
        requires_target=False,
        allow_automatic_use=False,
        logs_action=True,
        notes="Writes a local report file but does not modify system settings.",
    ),
    ToolDefinition(
        name="export_report",
        description="Export a Lighthouse report for review.",
        category="reporting",
        risk_level=RISK_CONVENIENCE,
        read_only=False,
        implemented=False,
        requires_confirmation=False,
        requires_target=False,
        allow_automatic_use=False,
        logs_action=True,
        notes="Planned future reporting tool.",
    ),
    ToolDefinition(
        name="open_task_manager",
        description="Open Windows Task Manager for user inspection.",
        category="navigation",
        risk_level=RISK_CONVENIENCE,
        read_only=False,
        implemented=False,
        requires_confirmation=False,
        requires_target=False,
        allow_automatic_use=False,
        logs_action=True,
        notes="Convenience tool only. Does not close processes.",
    ),
    ToolDefinition(
        name="open_resource_monitor",
        description="Open Windows Resource Monitor for user inspection.",
        category="navigation",
        risk_level=RISK_CONVENIENCE,
        read_only=False,
        implemented=False,
        requires_confirmation=False,
        requires_target=False,
        allow_automatic_use=False,
        logs_action=True,
    ),
    ToolDefinition(
        name="open_windows_settings",
        description="Open a selected Windows Settings page.",
        category="navigation",
        risk_level=RISK_CONVENIENCE,
        read_only=False,
        implemented=False,
        requires_confirmation=False,
        requires_target=True,
        allow_automatic_use=False,
        logs_action=True,
    ),
    ToolDefinition(
        name="disable_selected_startup_app",
        description="Disable one selected startup app.",
        category="startup_management",
        risk_level=RISK_REVERSIBLE_ACTION,
        read_only=False,
        implemented=False,
        requires_confirmation=True,
        requires_target=True,
        allow_automatic_use=False,
        logs_action=True,
    ),
    ToolDefinition(
        name="enable_selected_startup_app",
        description="Enable one selected startup app.",
        category="startup_management",
        risk_level=RISK_REVERSIBLE_ACTION,
        read_only=False,
        implemented=False,
        requires_confirmation=True,
        requires_target=True,
        allow_automatic_use=False,
        logs_action=True,
    ),
    ToolDefinition(
        name="close_selected_process",
        description="Close one selected process by PID after confirmation.",
        category="process_management",
        risk_level=RISK_DISRUPTIVE_ACTION,
        read_only=False,
        implemented=False,
        requires_confirmation=True,
        requires_target=True,
        allow_automatic_use=False,
        logs_action=True,
        notes="Potentially disruptive because unsaved work may be lost.",
    ),
    ToolDefinition(
        name="clear_selected_temp_folder",
        description="Clear one selected temporary folder after confirmation.",
        category="disk_management",
        risk_level=RISK_DISRUPTIVE_ACTION,
        read_only=False,
        implemented=False,
        requires_confirmation=True,
        requires_target=True,
        allow_automatic_use=False,
        logs_action=True,
        notes="Deletes temporary files only after explicit confirmation.",
    ),
    ToolDefinition(
        name="delete_user_files",
        description="Delete user files.",
        category="blocked",
        risk_level=RISK_BLOCKED,
        read_only=False,
        implemented=False,
        requires_confirmation=True,
        requires_target=True,
        allow_automatic_use=False,
        logs_action=True,
        notes="Blocked for Lighthouse V1.",
    ),
    ToolDefinition(
        name="edit_registry",
        description="Edit the Windows registry.",
        category="blocked",
        risk_level=RISK_BLOCKED,
        read_only=False,
        implemented=False,
        requires_confirmation=True,
        requires_target=True,
        allow_automatic_use=False,
        logs_action=True,
        notes="Blocked for Lighthouse V1.",
    ),
    ToolDefinition(
        name="change_drivers",
        description="Install, remove, update, or change device drivers.",
        category="blocked",
        risk_level=RISK_BLOCKED,
        read_only=False,
        implemented=False,
        requires_confirmation=True,
        requires_target=True,
        allow_automatic_use=False,
        logs_action=True,
        notes="Blocked for Lighthouse V1.",
    ),
    ToolDefinition(
        name="change_services",
        description="Change Windows services.",
        category="blocked",
        risk_level=RISK_BLOCKED,
        read_only=False,
        implemented=False,
        requires_confirmation=True,
        requires_target=True,
        allow_automatic_use=False,
        logs_action=True,
        notes="Blocked for Lighthouse V1.",
    ),
    ToolDefinition(
        name="uninstall_software",
        description="Uninstall software from the device.",
        category="blocked",
        risk_level=RISK_BLOCKED,
        read_only=False,
        implemented=False,
        requires_confirmation=True,
        requires_target=True,
        allow_automatic_use=False,
        logs_action=True,
        notes="Blocked for Lighthouse V1.",
    ),
    ToolDefinition(
        name="run_raw_command",
        description="Run an arbitrary shell, PowerShell, or command-line command.",
        category="blocked",
        risk_level=RISK_BLOCKED,
        read_only=False,
        implemented=False,
        requires_confirmation=True,
        requires_target=True,
        allow_automatic_use=False,
        logs_action=True,
        notes="Blocked. Lighthouse tools must be explicit registered functions.",
    ),
)


TOOL_REGISTRY: dict[str, ToolDefinition] = {
    tool.name: tool for tool in _REGISTERED_TOOLS
}


def normalize_tool_name(name: str) -> str:
    """
    Normalize a tool name for lookup.
    """
    return name.strip().lower()


def get_tool_registry() -> dict[str, ToolDefinition]:
    """
    Return a copy of the Lighthouse tool registry.
    """
    return dict(TOOL_REGISTRY)


def list_registered_tools() -> list[ToolDefinition]:
    """
    Return all registered tools sorted by name.
    """
    return sorted(TOOL_REGISTRY.values(), key=lambda tool: tool.name)


def get_tool_by_name(name: str) -> ToolDefinition | None:
    """
    Return a tool definition by name, or None if it is unknown.
    """
    normalized_name = normalize_tool_name(name)

    return TOOL_REGISTRY.get(normalized_name)


def is_known_tool(name: str) -> bool:
    """
    Return True if a tool is registered.
    """
    return get_tool_by_name(name) is not None


def list_tools_by_risk(risk_level: int) -> list[ToolDefinition]:
    """
    Return tools matching a specific risk level.
    """
    return sorted(
        [
            tool
            for tool in TOOL_REGISTRY.values()
            if tool.risk_level == risk_level
        ],
        key=lambda tool: tool.name,
    )


def list_tools_by_category(category: str) -> list[ToolDefinition]:
    """
    Return tools matching a specific category.
    """
    normalized_category = category.strip().lower()

    return sorted(
        [
            tool
            for tool in TOOL_REGISTRY.values()
            if tool.category.lower() == normalized_category
        ],
        key=lambda tool: tool.name,
    )


def list_implemented_tools() -> list[ToolDefinition]:
    """
    Return tools that are currently implemented.
    """
    return sorted(
        [
            tool
            for tool in TOOL_REGISTRY.values()
            if tool.implemented
        ],
        key=lambda tool: tool.name,
    )


def list_unimplemented_tools() -> list[ToolDefinition]:
    """
    Return tools that are registered but not currently implemented.
    """
    return sorted(
        [
            tool
            for tool in TOOL_REGISTRY.values()
            if not tool.implemented
        ],
        key=lambda tool: tool.name,
    )


def list_automatic_tools() -> list[ToolDefinition]:
    """
    Return tools allowed for automatic use.

    Automatic tools must be implemented, read-only, low risk, and not require
    confirmation or a target.
    """
    return sorted(
        [
            tool
            for tool in TOOL_REGISTRY.values()
            if is_tool_allowed_for_automatic_use(tool.name)
        ],
        key=lambda tool: tool.name,
    )


def list_blocked_tools() -> list[ToolDefinition]:
    """
    Return tools that are explicitly blocked.
    """
    return list_tools_by_risk(RISK_BLOCKED)


def is_tool_allowed_for_automatic_use(name: str) -> bool:
    """
    Return True if a tool can be used automatically by future planners.

    Unknown tools are never allowed.
    """
    tool = get_tool_by_name(name)

    if tool is None:
        return False

    return (
        tool.implemented
        and tool.read_only
        and tool.risk_level == RISK_READ_ONLY
        and not tool.requires_confirmation
        and not tool.requires_target
        and tool.allow_automatic_use
    )


def tool_requires_confirmation(name: str) -> bool:
    """
    Return True if a tool requires confirmation.

    Unknown tools are treated as requiring confirmation for safety.
    """
    tool = get_tool_by_name(name)

    if tool is None:
        return True

    return tool.requires_confirmation


def get_tool_safety_summary(name: str) -> dict[str, object]:
    """
    Return a compact safety summary for a tool.

    Unknown tools are reported as blocked.
    """
    tool = get_tool_by_name(name)

    if tool is None:
        return {
            "name": normalize_tool_name(name),
            "known": False,
            "allowed": False,
            "risk_level": RISK_BLOCKED,
            "read_only": False,
            "implemented": False,
            "requires_confirmation": True,
            "requires_target": True,
            "allow_automatic_use": False,
            "logs_action": True,
            "reason": "Unknown tools are blocked.",
        }

    return {
        "name": tool.name,
        "known": True,
        "allowed": tool.risk_level != RISK_BLOCKED,
        "risk_level": tool.risk_level,
        "read_only": tool.read_only,
        "implemented": tool.implemented,
        "requires_confirmation": tool.requires_confirmation,
        "requires_target": tool.requires_target,
        "allow_automatic_use": is_tool_allowed_for_automatic_use(tool.name),
        "logs_action": tool.logs_action,
        "reason": tool.notes,
    }


def validate_tool_registry() -> list[str]:
    """
    Validate the registry against Lighthouse safety rules.

    Returns a list of validation errors. An empty list means the registry is valid.
    """
    errors: list[str] = []
    seen_names: set[str] = set()

    for tool in _REGISTERED_TOOLS:
        if not tool.name:
            errors.append("A tool has an empty name.")
            continue

        if tool.name in seen_names:
            errors.append(f"Duplicate tool name found: {tool.name}")

        seen_names.add(tool.name)

        if tool.risk_level not in {
            RISK_READ_ONLY,
            RISK_CONVENIENCE,
            RISK_REVERSIBLE_ACTION,
            RISK_DISRUPTIVE_ACTION,
            RISK_BLOCKED,
        }:
            errors.append(f"{tool.name}: invalid risk level {tool.risk_level}")

        if tool.risk_level == RISK_READ_ONLY and not tool.read_only:
            errors.append(f"{tool.name}: risk 0 tools must be read-only.")

        if tool.risk_level == RISK_READ_ONLY and tool.requires_confirmation:
            errors.append(f"{tool.name}: risk 0 tools should not require confirmation.")

        if tool.risk_level >= RISK_REVERSIBLE_ACTION and tool.allow_automatic_use:
            errors.append(
                f"{tool.name}: risk {tool.risk_level} tools cannot be automatic."
            )

        if tool.risk_level == RISK_BLOCKED and tool.implemented:
            errors.append(f"{tool.name}: blocked tools cannot be implemented.")

        if tool.risk_level == RISK_BLOCKED and tool.allow_automatic_use:
            errors.append(f"{tool.name}: blocked tools cannot be automatic.")

        if tool.allow_automatic_use and not tool.implemented:
            errors.append(f"{tool.name}: automatic tools must be implemented.")

        if tool.allow_automatic_use and tool.requires_confirmation:
            errors.append(
                f"{tool.name}: automatic tools cannot require confirmation."
            )

        if tool.allow_automatic_use and tool.requires_target:
            errors.append(f"{tool.name}: automatic tools cannot require a target.")

    return errors