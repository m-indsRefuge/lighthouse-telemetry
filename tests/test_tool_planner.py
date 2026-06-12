"""
Tests for the Lighthouse read-only tool planner.

The planner maps user requests to registered tools.
It must never execute tools, invent tools, or automatically plan unsafe actions.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.tool_planner import (
    PLAN_STATUS_BLOCKED,
    PLAN_STATUS_NEEDS_CLARIFICATION,
    PLAN_STATUS_NEEDS_CONFIRMATION,
    PLAN_STATUS_OK,
    ToolPlan,
    contains_any,
    normalize_request,
    plan_tools_for_request,
)
from app.services.tool_registry import (
    RISK_BLOCKED,
    RISK_CONVENIENCE,
    RISK_DISRUPTIVE_ACTION,
    RISK_READ_ONLY,
    get_tool_by_name,
)


def assert_all_planned_tools_are_registered(plan: ToolPlan) -> None:
    """
    Every planned, blocked, or alternative tool should exist in the registry.
    """
    all_names = (
        plan.tool_names()
        + plan.blocked_tool_names()
        + plan.safe_alternative_names()
    )

    for tool_name in all_names:
        assert get_tool_by_name(tool_name) is not None


def test_normalize_request_collapses_spacing_and_casing() -> None:
    """
    Request normalization should be stable.
    """
    assert normalize_request("  My   LAPTOP   Feels Slow  ") == "my laptop feels slow"


def test_contains_any_uses_word_boundaries_for_single_words() -> None:
    """
    Single-word matching should not match partial words.
    """
    assert contains_any("please save this report", ["save"]) is True
    assert contains_any("show my saved reports", ["save"]) is False


def test_empty_request_needs_clarification() -> None:
    """
    Empty requests should not produce an executable plan.
    """
    plan = plan_tools_for_request("   ")

    assert plan.status == PLAN_STATUS_NEEDS_CLARIFICATION
    assert plan.intent == "empty_request"
    assert plan.tool_names() == []
    assert plan.safe_alternative_names() == ["collect_snapshot"]
    assert_all_planned_tools_are_registered(plan)


def test_health_request_plans_read_only_health_tools() -> None:
    """
    A health request should plan read-only diagnostic tools.
    """
    plan = plan_tools_for_request("Is my laptop healthy?")

    assert plan.status == PLAN_STATUS_OK
    assert plan.intent == "health_check"
    assert plan.tool_names() == [
        "collect_snapshot",
        "show_health_summary",
        "read_recent_events",
    ]
    assert plan.requires_confirmation is False
    assert_all_planned_tools_are_registered(plan)

    for tool in plan.tools:
        assert tool.risk_level == RISK_READ_ONLY
        assert tool.read_only is True
        assert tool.allow_automatic_use is True


def test_slow_laptop_request_plans_read_only_diagnostics() -> None:
    """
    Slow laptop requests should inspect CPU, memory, disk, processes, and events.
    """
    plan = plan_tools_for_request("My laptop feels slow, can you analyze it?")

    assert plan.status == PLAN_STATUS_OK
    assert plan.intent == "slow_laptop_diagnostics"
    assert plan.tool_names() == [
        "collect_snapshot",
        "inspect_cpu_usage",
        "inspect_memory_usage",
        "inspect_disk_usage",
        "list_top_processes",
        "read_recent_events",
    ]
    assert plan.requires_confirmation is False
    assert_all_planned_tools_are_registered(plan)


def test_memory_request_plans_memory_tools() -> None:
    """
    Memory requests should inspect memory and top processes.
    """
    plan = plan_tools_for_request("Please optimize RAM usage")

    assert plan.status == PLAN_STATUS_OK
    assert plan.intent == "slow_laptop_diagnostics"
    assert "collect_snapshot" in plan.tool_names()
    assert "inspect_memory_usage" in plan.tool_names()
    assert "list_top_processes" in plan.tool_names()
    assert plan.requires_confirmation is False
    assert_all_planned_tools_are_registered(plan)


def test_cpu_request_plans_cpu_tools() -> None:
    """
    CPU requests should inspect CPU and top processes.
    """
    plan = plan_tools_for_request("Is my CPU the problem?")

    assert plan.status == PLAN_STATUS_OK
    assert plan.intent == "cpu_diagnostics"
    assert plan.tool_names() == [
        "collect_snapshot",
        "inspect_cpu_usage",
        "list_top_processes",
    ]
    assert_all_planned_tools_are_registered(plan)


def test_disk_request_plans_disk_tools() -> None:
    """
    Disk requests should inspect disk usage only.
    """
    plan = plan_tools_for_request("Do I have enough storage space?")

    assert plan.status == PLAN_STATUS_OK
    assert plan.intent == "disk_diagnostics"
    assert plan.tool_names() == [
        "collect_snapshot",
        "inspect_disk_usage",
    ]
    assert_all_planned_tools_are_registered(plan)


def test_crash_request_plans_event_log_tools() -> None:
    """
    Crash requests should inspect recent event evidence.
    """
    plan = plan_tools_for_request("Did my laptop crash recently?")

    assert plan.status == PLAN_STATUS_OK
    assert plan.intent == "recent_crash_check"
    assert plan.tool_names() == [
        "collect_snapshot",
        "read_recent_events",
    ]
    assert_all_planned_tools_are_registered(plan)


def test_save_snapshot_request_plans_save_but_not_automatic() -> None:
    """
    Saving a snapshot writes a local file, so it should not be automatic.
    """
    plan = plan_tools_for_request("Save this report")

    assert plan.status == PLAN_STATUS_OK
    assert plan.intent == "save_snapshot"
    assert plan.tool_names() == ["save_snapshot"]
    assert plan.requires_confirmation is False
    assert_all_planned_tools_are_registered(plan)

    tool = plan.tools[0]

    assert tool.risk_level == RISK_CONVENIENCE
    assert tool.read_only is False
    assert tool.allow_automatic_use is False
    assert tool.logs_action is True


def test_open_task_manager_request_plans_convenience_tool() -> None:
    """
    Opening Task Manager should be planned as a convenience tool only.
    """
    plan = plan_tools_for_request("Open Task Manager")

    assert plan.status == PLAN_STATUS_OK
    assert plan.intent == "open_task_manager"
    assert plan.tool_names() == ["open_task_manager"]
    assert plan.safe_alternative_names() == ["list_top_processes"]
    assert_all_planned_tools_are_registered(plan)

    tool = plan.tools[0]

    assert tool.risk_level == RISK_CONVENIENCE
    assert tool.read_only is False
    assert tool.allow_automatic_use is False


def test_delete_files_request_is_blocked_with_safe_alternative() -> None:
    """
    User-file deletion should be blocked and redirected to disk inspection.
    """
    plan = plan_tools_for_request("Delete files to make space")

    assert plan.status == PLAN_STATUS_BLOCKED
    assert plan.intent == "blocked_file_deletion"
    assert plan.tool_names() == []
    assert plan.blocked_tool_names() == ["delete_user_files"]
    assert plan.safe_alternative_names() == [
        "collect_snapshot",
        "inspect_disk_usage",
    ]
    assert plan.has_blocked_tools is True
    assert_all_planned_tools_are_registered(plan)

    blocked_tool = plan.blocked_tools[0]

    assert blocked_tool.risk_level == RISK_BLOCKED


def test_registry_change_request_is_blocked() -> None:
    """
    Registry changes should be blocked.
    """
    plan = plan_tools_for_request("Edit the registry to make Windows faster")

    assert plan.status == PLAN_STATUS_BLOCKED
    assert plan.intent == "blocked_registry_change"
    assert plan.blocked_tool_names() == ["edit_registry"]
    assert plan.safe_alternative_names() == [
        "collect_snapshot",
        "show_health_summary",
    ]
    assert_all_planned_tools_are_registered(plan)


def test_driver_change_request_is_blocked() -> None:
    """
    Driver changes should be blocked.
    """
    plan = plan_tools_for_request("Update my drivers")

    assert plan.status == PLAN_STATUS_BLOCKED
    assert plan.intent == "blocked_driver_change"
    assert plan.blocked_tool_names() == ["change_drivers"]
    assert_all_planned_tools_are_registered(plan)


def test_service_change_request_is_blocked() -> None:
    """
    Windows service changes should be blocked.
    """
    plan = plan_tools_for_request("Disable services I do not need")

    assert plan.status == PLAN_STATUS_BLOCKED
    assert plan.intent == "blocked_service_change"
    assert plan.blocked_tool_names() == ["change_services"]
    assert_all_planned_tools_are_registered(plan)


def test_uninstall_request_is_blocked() -> None:
    """
    Software uninstall actions should be blocked for Lighthouse V1.
    """
    plan = plan_tools_for_request("Uninstall software I do not use")

    assert plan.status == PLAN_STATUS_BLOCKED
    assert plan.intent == "blocked_uninstall"
    assert plan.blocked_tool_names() == ["uninstall_software"]
    assert_all_planned_tools_are_registered(plan)


def test_raw_command_request_is_blocked() -> None:
    """
    Arbitrary command execution should be blocked.
    """
    plan = plan_tools_for_request("Run a PowerShell command to fix this")

    assert plan.status == PLAN_STATUS_BLOCKED
    assert plan.intent == "blocked_raw_command"
    assert plan.blocked_tool_names() == ["run_raw_command"]
    assert_all_planned_tools_are_registered(plan)


def test_close_process_request_requires_confirmation_and_target() -> None:
    """
    Closing a process should never be automatic.
    """
    plan = plan_tools_for_request("Close Chrome because it is using memory")

    assert plan.status == PLAN_STATUS_NEEDS_CONFIRMATION
    assert plan.intent == "close_process_request"
    assert plan.tool_names() == ["close_selected_process"]
    assert plan.safe_alternative_names() == [
        "collect_snapshot",
        "list_top_processes",
    ]
    assert plan.requires_confirmation is True
    assert_all_planned_tools_are_registered(plan)

    tool = plan.tools[0]

    assert tool.risk_level == RISK_DISRUPTIVE_ACTION
    assert tool.read_only is False
    assert tool.requires_confirmation is True
    assert tool.requires_target is True
    assert tool.allow_automatic_use is False


def test_clear_temp_request_requires_confirmation() -> None:
    """
    Clearing temporary folders should be gated.
    """
    plan = plan_tools_for_request("Clear temp files")

    assert plan.status == PLAN_STATUS_NEEDS_CONFIRMATION
    assert plan.intent == "clear_temp_request"
    assert plan.tool_names() == ["clear_selected_temp_folder"]
    assert plan.safe_alternative_names() == [
        "collect_snapshot",
        "inspect_disk_usage",
    ]
    assert plan.requires_confirmation is True
    assert_all_planned_tools_are_registered(plan)


def test_disable_startup_request_requires_confirmation() -> None:
    """
    Startup app changes should be gated.
    """
    plan = plan_tools_for_request("Disable startup apps")

    assert plan.status == PLAN_STATUS_NEEDS_CONFIRMATION
    assert plan.intent == "disable_startup_request"
    assert plan.tool_names() == ["disable_selected_startup_app"]
    assert plan.requires_confirmation is True
    assert_all_planned_tools_are_registered(plan)


def test_unknown_request_needs_clarification_and_safe_alternative() -> None:
    """
    Unknown requests should not invent tools.
    """
    plan = plan_tools_for_request("Make the laptop behave nicer please")

    assert plan.status == PLAN_STATUS_NEEDS_CLARIFICATION
    assert plan.intent == "unknown_request"
    assert plan.tool_names() == []
    assert plan.blocked_tool_names() == []
    assert plan.safe_alternative_names() == [
        "collect_snapshot",
        "show_health_summary",
    ]
    assert_all_planned_tools_are_registered(plan)


def test_tool_plan_to_dict_is_serializable_shape() -> None:
    """
    Plans should expose a stable dictionary shape for future CLI/API use.
    """
    plan = plan_tools_for_request("My laptop is slow")
    payload = plan.to_dict()

    assert payload["status"] == PLAN_STATUS_OK
    assert payload["intent"] == "slow_laptop_diagnostics"
    assert payload["requires_confirmation"] is False
    assert isinstance(payload["tools"], list)
    assert isinstance(payload["blocked_tools"], list)
    assert isinstance(payload["safe_alternatives"], list)
    assert payload["tools"][0]["name"] == "collect_snapshot"