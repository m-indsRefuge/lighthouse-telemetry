"""
Tests for the Lighthouse tool registry.

The registry defines what Lighthouse may plan or use in future agentic flows.
These tests ensure the registry stays conservative before any execution layer
is added.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.tool_registry import (
    RISK_BLOCKED,
    RISK_CONVENIENCE,
    RISK_DISRUPTIVE_ACTION,
    RISK_READ_ONLY,
    RISK_REVERSIBLE_ACTION,
    get_tool_by_name,
    get_tool_registry,
    get_tool_safety_summary,
    is_known_tool,
    is_tool_allowed_for_automatic_use,
    list_automatic_tools,
    list_blocked_tools,
    list_implemented_tools,
    list_registered_tools,
    list_tools_by_category,
    list_tools_by_risk,
    list_unimplemented_tools,
    tool_requires_confirmation,
    validate_tool_registry,
)


def test_tool_registry_validates_without_errors() -> None:
    """
    The registry should satisfy Lighthouse safety rules.
    """
    assert validate_tool_registry() == []


def test_registry_contains_core_read_only_tools() -> None:
    """
    Core diagnostic tools should be registered as read-only tools.
    """
    registry = get_tool_registry()

    expected_tools = {
        "collect_snapshot",
        "show_health_summary",
        "list_top_processes",
        "read_recent_events",
        "inspect_memory_usage",
        "inspect_cpu_usage",
        "inspect_disk_usage",
    }

    assert expected_tools.issubset(set(registry.keys()))

    for tool_name in expected_tools:
        tool = registry[tool_name]

        assert tool.risk_level == RISK_READ_ONLY
        assert tool.read_only is True
        assert tool.implemented is True
        assert tool.requires_confirmation is False
        assert tool.allow_automatic_use is True


def test_registered_tool_names_are_unique() -> None:
    """
    Registered tool names should be unique.
    """
    tools = list_registered_tools()
    names = [tool.name for tool in tools]

    assert len(names) == len(set(names))


def test_get_tool_by_name_normalizes_input() -> None:
    """
    Tool lookup should tolerate surrounding whitespace and casing.
    """
    tool = get_tool_by_name("  COLLECT_SNAPSHOT  ")

    assert tool is not None
    assert tool.name == "collect_snapshot"


def test_unknown_tool_is_not_known() -> None:
    """
    Unknown tools should not be treated as registered.
    """
    assert is_known_tool("invented_tool") is False
    assert get_tool_by_name("invented_tool") is None


def test_automatic_tools_are_only_safe_read_only_tools() -> None:
    """
    Automatic tools must be read-only, implemented, and low risk.
    """
    automatic_tools = list_automatic_tools()

    assert automatic_tools

    for tool in automatic_tools:
        assert tool.risk_level == RISK_READ_ONLY
        assert tool.read_only is True
        assert tool.implemented is True
        assert tool.requires_confirmation is False
        assert tool.requires_target is False
        assert tool.allow_automatic_use is True


def test_is_tool_allowed_for_automatic_use_blocks_unknown_tools() -> None:
    """
    Unknown tools should never be allowed for automatic use.
    """
    assert is_tool_allowed_for_automatic_use("unknown_tool") is False


def test_is_tool_allowed_for_automatic_use_blocks_non_read_only_tools() -> None:
    """
    Non-read-only tools should not be allowed automatically.
    """
    assert is_tool_allowed_for_automatic_use("save_snapshot") is False
    assert is_tool_allowed_for_automatic_use("close_selected_process") is False


def test_save_snapshot_is_convenience_tool_not_automatic() -> None:
    """
    Saving a snapshot writes a local file, so it should not be automatic.
    """
    tool = get_tool_by_name("save_snapshot")

    assert tool is not None
    assert tool.risk_level == RISK_CONVENIENCE
    assert tool.implemented is True
    assert tool.read_only is False
    assert tool.allow_automatic_use is False
    assert tool.logs_action is True


def test_future_action_tools_require_confirmation_and_targets() -> None:
    """
    Future OS-changing tools must require confirmation and a specific target.
    """
    tool_names = [
        "disable_selected_startup_app",
        "enable_selected_startup_app",
        "close_selected_process",
        "clear_selected_temp_folder",
    ]

    for tool_name in tool_names:
        tool = get_tool_by_name(tool_name)

        assert tool is not None
        assert tool.risk_level in {
            RISK_REVERSIBLE_ACTION,
            RISK_DISRUPTIVE_ACTION,
        }
        assert tool.read_only is False
        assert tool.implemented is False
        assert tool.requires_confirmation is True
        assert tool.requires_target is True
        assert tool.allow_automatic_use is False
        assert tool.logs_action is True


def test_blocked_tools_are_not_implemented_or_automatic() -> None:
    """
    Blocked tools should exist only as explicit policy boundaries.
    """
    blocked_tools = list_blocked_tools()

    assert blocked_tools

    for tool in blocked_tools:
        assert tool.risk_level == RISK_BLOCKED
        assert tool.implemented is False
        assert tool.allow_automatic_use is False
        assert tool.requires_confirmation is True
        assert tool.logs_action is True


def test_specific_dangerous_tools_are_blocked() -> None:
    """
    Dangerous capabilities should be explicitly blocked for Lighthouse V1.
    """
    blocked_tool_names = {
        "delete_user_files",
        "edit_registry",
        "change_drivers",
        "change_services",
        "uninstall_software",
        "run_raw_command",
    }

    for tool_name in blocked_tool_names:
        tool = get_tool_by_name(tool_name)

        assert tool is not None
        assert tool.risk_level == RISK_BLOCKED
        assert is_tool_allowed_for_automatic_use(tool_name) is False


def test_tool_requires_confirmation_defaults_to_true_for_unknown_tools() -> None:
    """
    Unknown tools should be treated conservatively.
    """
    assert tool_requires_confirmation("unknown_tool") is True


def test_tool_requires_confirmation_for_disruptive_tools() -> None:
    """
    Disruptive future tools should require confirmation.
    """
    assert tool_requires_confirmation("close_selected_process") is True
    assert tool_requires_confirmation("clear_selected_temp_folder") is True


def test_read_only_tools_do_not_require_confirmation() -> None:
    """
    Read-only automatic tools should not require confirmation.
    """
    assert tool_requires_confirmation("collect_snapshot") is False
    assert tool_requires_confirmation("list_top_processes") is False


def test_list_tools_by_risk_returns_matching_tools() -> None:
    """
    Tools should be listable by risk level.
    """
    read_only_tools = list_tools_by_risk(RISK_READ_ONLY)
    blocked_tools = list_tools_by_risk(RISK_BLOCKED)

    assert read_only_tools
    assert blocked_tools
    assert all(tool.risk_level == RISK_READ_ONLY for tool in read_only_tools)
    assert all(tool.risk_level == RISK_BLOCKED for tool in blocked_tools)


def test_list_tools_by_category_returns_matching_tools() -> None:
    """
    Tools should be listable by category.
    """
    diagnostic_tools = list_tools_by_category("diagnostics")

    assert diagnostic_tools
    assert all(tool.category == "diagnostics" for tool in diagnostic_tools)


def test_implemented_and_unimplemented_tools_are_listed() -> None:
    """
    Registry should expose implemented and planned tools separately.
    """
    implemented_tools = list_implemented_tools()
    unimplemented_tools = list_unimplemented_tools()

    assert implemented_tools
    assert unimplemented_tools
    assert all(tool.implemented for tool in implemented_tools)
    assert all(not tool.implemented for tool in unimplemented_tools)


def test_get_tool_safety_summary_for_known_tool() -> None:
    """
    Safety summary should expose conservative policy metadata.
    """
    summary = get_tool_safety_summary("collect_snapshot")

    assert summary["name"] == "collect_snapshot"
    assert summary["known"] is True
    assert summary["allowed"] is True
    assert summary["risk_level"] == RISK_READ_ONLY
    assert summary["read_only"] is True
    assert summary["implemented"] is True
    assert summary["allow_automatic_use"] is True


def test_get_tool_safety_summary_for_unknown_tool_is_blocked() -> None:
    """
    Unknown tool summaries should be treated as blocked.
    """
    summary = get_tool_safety_summary("invented_fix_everything_tool")

    assert summary["name"] == "invented_fix_everything_tool"
    assert summary["known"] is False
    assert summary["allowed"] is False
    assert summary["risk_level"] == RISK_BLOCKED
    assert summary["requires_confirmation"] is True
    assert summary["requires_target"] is True
    assert summary["allow_automatic_use"] is False
    assert summary["reason"] == "Unknown tools are blocked."


def test_get_tool_registry_returns_copy() -> None:
    """
    get_tool_registry should return a shallow copy of the registry mapping.
    """
    registry = get_tool_registry()
    registry.pop("collect_snapshot")

    fresh_registry = get_tool_registry()

    assert "collect_snapshot" in fresh_registry