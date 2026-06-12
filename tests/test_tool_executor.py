"""
Tests for the Lighthouse read-only tool executor.

The executor must only run safe, registered, read-only tools.
It must refuse blocked, unknown, unimplemented, or OS-changing tools.
"""

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

import pytest

from app.services.tool_executor import (
    PLAN_EXECUTION_COMPLETED,
    PLAN_EXECUTION_REFUSED,
    TOOL_EXECUTION_EXECUTED,
    TOOL_EXECUTION_REFUSED,
    ToolExecutionContext,
    execute_registered_tool,
    execute_tool_plan,
    execute_tools_for_request,
    get_tool_execution_safety,
)
from app.services.tool_planner import plan_tools_for_request


@pytest.fixture
def fake_execution_environment(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """
    Patch telemetry, events, and insight building for deterministic tests.
    """
    calls = {
        "telemetry": 0,
        "events": 0,
        "insight": 0,
    }

    def fake_collect_telemetry() -> dict[str, Any]:
        calls["telemetry"] += 1

        return {
            "cpu": {
                "status": "ok",
                "usage_percent": 5.0,
            },
            "memory": {
                "status": "ok",
                "total_gb": 32.0,
                "used_gb": 13.5,
                "available_gb": 18.5,
                "usage_percent": 42.2,
            },
            "disk": {
                "status": "ok",
                "path": "C:\\",
                "total_gb": 512.0,
                "used_gb": 61.0,
                "free_gb": 451.0,
                "usage_percent": 12.0,
            },
            "processes": {
                "status": "ok",
                "processes": [
                    {
                        "pid": 1234,
                        "name": "chrome.exe",
                        "memory_mb": 1129.7,
                        "cpu_percent": 1.2,
                    }
                ],
            },
        }

    def fake_get_recent_system_events(limit: int = 100) -> dict[str, Any]:
        calls["events"] += 1

        return {
            "status": "ok",
            "events_checked": limit,
            "severity_summary": {
                "critical": 0,
                "warning": 0,
                "context": 20,
            },
            "possible_causes": [],
            "events": [],
        }

    def fake_build_system_insight(
        telemetry: dict[str, Any],
        event_report: dict[str, Any],
    ) -> dict[str, Any]:
        calls["insight"] += 1

        return {
            "status": "ok",
            "overall_status": "GOOD",
            "summary": "No obvious fault found.",
            "conclusion": "The system looks healthy based on this snapshot.",
            "metrics": {
                "cpu_status": "OK",
                "memory_status": "OK",
                "disk_status": "OK",
                "critical_events": 0,
                "warning_events": 0,
                "context_events": 20,
            },
            "findings": [
                "CPU usage is healthy.",
                "Memory usage is healthy.",
                "Disk usage is healthy.",
            ],
            "recommendations": [
                "No immediate action needed.",
            ],
        }

    monkeypatch.setattr(
        "app.services.tool_executor.collect_telemetry",
        fake_collect_telemetry,
    )
    monkeypatch.setattr(
        "app.services.tool_executor.get_recent_system_events",
        fake_get_recent_system_events,
    )
    monkeypatch.setattr(
        "app.services.tool_executor.build_system_insight",
        fake_build_system_insight,
    )

    return calls


def test_get_tool_execution_safety_allows_safe_read_only_tool() -> None:
    """
    Safe read-only automatic tools should be executable.
    """
    safety = get_tool_execution_safety("collect_snapshot")

    assert safety["known"] is True
    assert safety["executable"] is True
    assert safety["risk_level"] == 0
    assert safety["read_only"] is True


def test_get_tool_execution_safety_blocks_unknown_tool() -> None:
    """
    Unknown tools should never be executable.
    """
    safety = get_tool_execution_safety("invented_fix_tool")

    assert safety["known"] is False
    assert safety["executable"] is False
    assert safety["reason"] == "Unknown tools cannot be executed."


def test_execute_registered_tool_runs_collect_snapshot(
    fake_execution_environment: dict[str, int],
) -> None:
    """
    collect_snapshot should execute and return telemetry, events, and insight.
    """
    result = execute_registered_tool("collect_snapshot")

    assert result.status == TOOL_EXECUTION_EXECUTED
    assert result.tool_name == "collect_snapshot"
    assert result.data is not None
    assert "telemetry" in result.data
    assert "event_report" in result.data
    assert "insight" in result.data
    assert fake_execution_environment["telemetry"] == 1
    assert fake_execution_environment["events"] == 1
    assert fake_execution_environment["insight"] == 1


def test_execute_registered_tool_runs_memory_inspection(
    fake_execution_environment: dict[str, int],
) -> None:
    """
    inspect_memory_usage should execute and return memory telemetry.
    """
    result = execute_registered_tool("inspect_memory_usage")

    assert result.status == TOOL_EXECUTION_EXECUTED
    assert result.data is not None
    assert result.data["memory"]["usage_percent"] == 42.2
    assert fake_execution_environment["telemetry"] == 1


def test_execute_registered_tool_runs_process_listing(
    fake_execution_environment: dict[str, int],
) -> None:
    """
    list_top_processes should execute and return process telemetry.
    """
    result = execute_registered_tool("list_top_processes")

    assert result.status == TOOL_EXECUTION_EXECUTED
    assert result.data is not None
    assert result.data["processes"]["processes"][0]["name"] == "chrome.exe"


def test_execute_registered_tool_refuses_blocked_tool() -> None:
    """
    Blocked tools should not execute.
    """
    result = execute_registered_tool("delete_user_files")

    assert result.status == TOOL_EXECUTION_REFUSED
    assert result.tool_name == "delete_user_files"
    assert result.data is None
    assert result.safety_summary["executable"] is False
    assert "Blocked tools cannot be executed" in result.message


def test_execute_registered_tool_refuses_os_changing_tool() -> None:
    """
    OS-changing tools should not execute through the read-only executor.
    """
    result = execute_registered_tool("close_selected_process")

    assert result.status == TOOL_EXECUTION_REFUSED
    assert result.data is None
    assert result.safety_summary["executable"] is False


def test_execute_registered_tool_refuses_convenience_write_tool() -> None:
    """
    save_snapshot writes a file, so this read-only executor should refuse it.
    """
    result = execute_registered_tool("save_snapshot")

    assert result.status == TOOL_EXECUTION_REFUSED
    assert result.data is None
    assert result.safety_summary["executable"] is False
    assert "read-only" in result.message


def test_execute_registered_tool_refuses_unknown_tool() -> None:
    """
    Unknown tools should be refused.
    """
    result = execute_registered_tool("unknown_tool")

    assert result.status == TOOL_EXECUTION_REFUSED
    assert result.data is None
    assert result.safety_summary["known"] is False


def test_tool_execution_context_reuses_cached_telemetry(
    fake_execution_environment: dict[str, int],
) -> None:
    """
    A shared execution context should collect telemetry once.
    """
    context = ToolExecutionContext()

    first = execute_registered_tool("inspect_cpu_usage", context=context)
    second = execute_registered_tool("inspect_memory_usage", context=context)
    third = execute_registered_tool("inspect_disk_usage", context=context)

    assert first.status == TOOL_EXECUTION_EXECUTED
    assert second.status == TOOL_EXECUTION_EXECUTED
    assert third.status == TOOL_EXECUTION_EXECUTED
    assert fake_execution_environment["telemetry"] == 1


def test_execute_tool_plan_runs_safe_read_only_plan(
    fake_execution_environment: dict[str, int],
) -> None:
    """
    A safe read-only plan should execute all planned tools.
    """
    plan = plan_tools_for_request("please optimize RAM usage")
    result = execute_tool_plan(plan)

    assert result.status == PLAN_EXECUTION_COMPLETED
    assert result.plan_status == "ok"
    assert result.intent == "slow_laptop_diagnostics"
    assert result.refused_tools == ()
    assert result.blocked_tools == ()
    assert len(result.executed_tools) == 6

    executed_names = [tool.tool_name for tool in result.executed_tools]

    assert executed_names == [
        "collect_snapshot",
        "inspect_cpu_usage",
        "inspect_memory_usage",
        "inspect_disk_usage",
        "list_top_processes",
        "read_recent_events",
    ]

    assert fake_execution_environment["telemetry"] == 1
    assert fake_execution_environment["events"] == 1
    assert fake_execution_environment["insight"] == 1


def test_execute_tools_for_request_blocks_file_deletion(
    fake_execution_environment: dict[str, int],
) -> None:
    """
    Blocked plans should not execute safe alternatives automatically.
    """
    result = execute_tools_for_request("delete files to make space")

    assert result.status == PLAN_EXECUTION_REFUSED
    assert result.plan_status == "blocked"
    assert result.intent == "blocked_file_deletion"
    assert result.executed_tools == ()
    assert result.blocked_tools == ("delete_user_files",)
    assert result.safe_alternatives == (
        "collect_snapshot",
        "inspect_disk_usage",
    )
    assert fake_execution_environment["telemetry"] == 0
    assert fake_execution_environment["events"] == 0
    assert fake_execution_environment["insight"] == 0


def test_execute_tools_for_request_refuses_confirmation_plan(
    fake_execution_environment: dict[str, int],
) -> None:
    """
    Confirmation-required plans should not execute automatically.
    """
    result = execute_tools_for_request("close Chrome because it is using memory")

    assert result.status == PLAN_EXECUTION_REFUSED
    assert result.plan_status == "needs_confirmation"
    assert result.intent == "close_process_request"
    assert result.executed_tools == ()
    assert result.blocked_tools == ()
    assert result.safe_alternatives == (
        "collect_snapshot",
        "list_top_processes",
    )
    assert result.refused_tools[0].tool_name == "close_selected_process"
    assert fake_execution_environment["telemetry"] == 0


def test_execute_tools_for_request_handles_unknown_request(
    fake_execution_environment: dict[str, int],
) -> None:
    """
    Unknown plans should not execute automatically.
    """
    result = execute_tools_for_request("make it better somehow")

    assert result.status == PLAN_EXECUTION_REFUSED
    assert result.plan_status == "needs_clarification"
    assert result.executed_tools == ()
    assert result.safe_alternatives == (
        "collect_snapshot",
        "show_health_summary",
    )
    assert fake_execution_environment["telemetry"] == 0


def test_plan_execution_result_to_dict_shape(
    fake_execution_environment: dict[str, int],
) -> None:
    """
    Plan execution results should expose a stable serializable shape.
    """
    result = execute_tools_for_request("please optimize RAM usage")
    payload = result.to_dict()

    assert payload["status"] == PLAN_EXECUTION_COMPLETED
    assert payload["plan_status"] == "ok"
    assert payload["intent"] == "slow_laptop_diagnostics"
    assert isinstance(payload["executed_tools"], list)
    assert isinstance(payload["refused_tools"], list)
    assert isinstance(payload["blocked_tools"], list)
    assert isinstance(payload["safe_alternatives"], list)
    assert payload["executed_tools"][0]["tool_name"] == "collect_snapshot"