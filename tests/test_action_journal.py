"""
Tests for the Lighthouse action journal.

The journal records plan/execution decisions before Lighthouse gains
permission-gated OS-changing tools.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.action_journal import (
    EVENT_TYPE_TOOL_PLAN_EXECUTION,
    JOURNAL_SCHEMA_VERSION,
    JOURNAL_STATUS_OK,
    append_journal_entry,
    build_plan_execution_journal_entry,
    format_journal_report,
    read_journal_entries,
    record_plan_execution,
)


def build_fake_tool_result(tool_name: str) -> SimpleNamespace:
    """
    Build a fake tool execution result.
    """
    return SimpleNamespace(
        tool_name=tool_name,
        status="executed",
        message="Tool executed successfully.",
        data={},
        safety_summary={},
    )


def build_fake_plan_execution_result(
    *,
    status: str = "completed",
    plan_status: str = "ok",
    intent: str = "slow_laptop_diagnostics",
    user_request: str = "please optimize RAM usage",
    message: str = "All safe read-only tools executed successfully.",
    executed_tools: tuple[Any, ...] = (),
    refused_tools: tuple[Any, ...] = (),
    blocked_tools: tuple[str, ...] = (),
    safe_alternatives: tuple[str, ...] = (),
) -> SimpleNamespace:
    """
    Build a fake ToolPlanExecutionResult-like object.
    """
    return SimpleNamespace(
        status=status,
        plan_status=plan_status,
        intent=intent,
        user_request=user_request,
        message=message,
        executed_tools=executed_tools,
        refused_tools=refused_tools,
        blocked_tools=blocked_tools,
        safe_alternatives=safe_alternatives,
    )


def test_build_plan_execution_journal_entry_for_completed_run() -> None:
    """
    A completed runplan result should become a compact journal entry.
    """
    result = build_fake_plan_execution_result(
        executed_tools=(
            build_fake_tool_result("collect_snapshot"),
            build_fake_tool_result("inspect_memory_usage"),
        ),
    )

    entry = build_plan_execution_journal_entry(
        result,
        timestamp="2026-06-12T10:00:00Z",
    )

    assert entry["schema_version"] == JOURNAL_SCHEMA_VERSION
    assert entry["timestamp"] == "2026-06-12T10:00:00Z"
    assert entry["event_type"] == EVENT_TYPE_TOOL_PLAN_EXECUTION
    assert entry["user_request"] == "please optimize RAM usage"
    assert entry["intent"] == "slow_laptop_diagnostics"
    assert entry["plan_status"] == "ok"
    assert entry["execution_status"] == "completed"
    assert entry["executed_tools"] == [
        "collect_snapshot",
        "inspect_memory_usage",
    ]
    assert entry["refused_tools"] == []
    assert entry["blocked_tools"] == []
    assert entry["safe_alternatives"] == []
    assert entry["requires_confirmation"] is False
    assert entry["execution_allowed"] is True


def test_build_plan_execution_journal_entry_for_blocked_run() -> None:
    """
    A blocked result should preserve blocked tools and safe alternatives.
    """
    result = build_fake_plan_execution_result(
        status="refused",
        plan_status="blocked",
        intent="blocked_file_deletion",
        user_request="delete files to make space",
        message="This request contains a blocked action.",
        refused_tools=(build_fake_tool_result("delete_user_files"),),
        blocked_tools=("delete_user_files",),
        safe_alternatives=("collect_snapshot", "inspect_disk_usage"),
    )

    entry = build_plan_execution_journal_entry(
        result,
        timestamp="2026-06-12T10:01:00Z",
    )

    assert entry["plan_status"] == "blocked"
    assert entry["execution_status"] == "refused"
    assert entry["execution_allowed"] is False
    assert entry["requires_confirmation"] is False
    assert entry["refused_tools"] == ["delete_user_files"]
    assert entry["blocked_tools"] == ["delete_user_files"]
    assert entry["safe_alternatives"] == [
        "collect_snapshot",
        "inspect_disk_usage",
    ]


def test_build_plan_execution_journal_entry_for_confirmation_run() -> None:
    """
    Confirmation-required results should be marked clearly.
    """
    result = build_fake_plan_execution_result(
        status="refused",
        plan_status="needs_confirmation",
        intent="close_process_request",
        user_request="close Chrome because it is using memory",
        message="This request requires explicit Operator confirmation.",
        refused_tools=(build_fake_tool_result("close_selected_process"),),
        safe_alternatives=("collect_snapshot", "list_top_processes"),
    )

    entry = build_plan_execution_journal_entry(
        result,
        timestamp="2026-06-12T10:02:00Z",
    )

    assert entry["plan_status"] == "needs_confirmation"
    assert entry["execution_status"] == "refused"
    assert entry["requires_confirmation"] is True
    assert entry["execution_allowed"] is False
    assert entry["refused_tools"] == ["close_selected_process"]
    assert entry["safe_alternatives"] == [
        "collect_snapshot",
        "list_top_processes",
    ]


def test_append_journal_entry_creates_jsonl_file(tmp_path: Path) -> None:
    """
    Appending a journal entry should create the directory and JSONL file.
    """
    journal_path = tmp_path / "journal" / "lighthouse_actions.jsonl"

    entry = {
        "event_type": EVENT_TYPE_TOOL_PLAN_EXECUTION,
        "user_request": "check memory",
    }

    result = append_journal_entry(
        entry=entry,
        journal_path=journal_path,
    )

    assert result.status == JOURNAL_STATUS_OK
    assert journal_path.exists()

    lines = journal_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 1

    payload = json.loads(lines[0])

    assert payload["event_type"] == EVENT_TYPE_TOOL_PLAN_EXECUTION
    assert payload["user_request"] == "check memory"
    assert "timestamp" in payload


def test_record_plan_execution_writes_compact_entry(tmp_path: Path) -> None:
    """
    Recording a plan execution should write a compact journal entry.
    """
    journal_path = tmp_path / "journal" / "lighthouse_actions.jsonl"
    execution_result = build_fake_plan_execution_result(
        executed_tools=(build_fake_tool_result("inspect_cpu_usage"),),
    )

    result = record_plan_execution(
        execution_result=execution_result,
        journal_path=journal_path,
    )

    assert result.status == JOURNAL_STATUS_OK
    assert result.entry is not None
    assert result.entry["event_type"] == EVENT_TYPE_TOOL_PLAN_EXECUTION
    assert result.entry["executed_tools"] == ["inspect_cpu_usage"]

    lines = journal_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 1


def test_read_journal_entries_missing_file_returns_empty(tmp_path: Path) -> None:
    """
    Reading before the journal exists should return an empty ok result.
    """
    journal_path = tmp_path / "journal" / "missing.jsonl"

    result = read_journal_entries(
        journal_path=journal_path,
    )

    assert result.status == JOURNAL_STATUS_OK
    assert result.entries == []
    assert result.entry_count == 0
    assert result.malformed_count == 0


def test_read_journal_entries_returns_newest_first(tmp_path: Path) -> None:
    """
    Journal reads should return the newest records first.
    """
    journal_path = tmp_path / "journal" / "lighthouse_actions.jsonl"

    append_journal_entry(
        {
            "timestamp": "2026-06-12T10:00:00Z",
            "event_type": EVENT_TYPE_TOOL_PLAN_EXECUTION,
            "user_request": "first",
        },
        journal_path=journal_path,
    )
    append_journal_entry(
        {
            "timestamp": "2026-06-12T10:01:00Z",
            "event_type": EVENT_TYPE_TOOL_PLAN_EXECUTION,
            "user_request": "second",
        },
        journal_path=journal_path,
    )
    append_journal_entry(
        {
            "timestamp": "2026-06-12T10:02:00Z",
            "event_type": EVENT_TYPE_TOOL_PLAN_EXECUTION,
            "user_request": "third",
        },
        journal_path=journal_path,
    )

    result = read_journal_entries(
        limit=2,
        journal_path=journal_path,
    )

    assert result.status == JOURNAL_STATUS_OK
    assert result.entry_count == 2
    assert result.entries[0]["user_request"] == "third"
    assert result.entries[1]["user_request"] == "second"


def test_read_journal_entries_skips_malformed_lines(tmp_path: Path) -> None:
    """
    Malformed JSONL records should be skipped, not crash the reader.
    """
    journal_path = tmp_path / "journal" / "lighthouse_actions.jsonl"
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    journal_path.write_text(
        "\n".join(
            [
                '{"event_type": "tool_plan_execution", "user_request": "ok"}',
                "not valid json",
                '["not", "a", "dict"]',
            ]
        ),
        encoding="utf-8",
    )

    result = read_journal_entries(
        journal_path=journal_path,
    )

    assert result.status == JOURNAL_STATUS_OK
    assert result.entry_count == 1
    assert result.malformed_count == 2
    assert result.entries[0]["user_request"] == "ok"


def test_read_journal_entries_with_zero_limit_returns_empty(tmp_path: Path) -> None:
    """
    A zero read limit should return no entries.
    """
    journal_path = tmp_path / "journal" / "lighthouse_actions.jsonl"

    append_journal_entry(
        {
            "event_type": EVENT_TYPE_TOOL_PLAN_EXECUTION,
            "user_request": "check memory",
        },
        journal_path=journal_path,
    )

    result = read_journal_entries(
        limit=0,
        journal_path=journal_path,
    )

    assert result.status == JOURNAL_STATUS_OK
    assert result.entries == []
    assert result.entry_count == 0


def test_format_journal_report_handles_empty_result(tmp_path: Path) -> None:
    """
    Formatting an empty journal result should still produce a readable report.
    """
    journal_path = tmp_path / "journal" / "missing.jsonl"
    read_result = read_journal_entries(
        journal_path=journal_path,
    )

    report = format_journal_report(read_result)

    assert "LIGHTHOUSE ACTION JOURNAL" in report
    assert "Entries shown: 0" in report
    assert "No action journal found yet." in report


def test_format_journal_report_includes_entry_details(tmp_path: Path) -> None:
    """
    Formatting journal entries should include important audit fields.
    """
    journal_path = tmp_path / "journal" / "lighthouse_actions.jsonl"

    append_journal_entry(
        {
            "timestamp": "2026-06-12T10:00:00Z",
            "event_type": EVENT_TYPE_TOOL_PLAN_EXECUTION,
            "user_request": "check memory",
            "intent": "memory_diagnostics",
            "plan_status": "ok",
            "execution_status": "completed",
            "message": "All safe read-only tools executed successfully.",
            "executed_tools": ["inspect_memory_usage"],
            "refused_tools": [],
            "blocked_tools": [],
        },
        journal_path=journal_path,
    )

    read_result = read_journal_entries(
        journal_path=journal_path,
    )
    report = format_journal_report(read_result)

    assert "LIGHTHOUSE ACTION JOURNAL" in report
    assert "Request: check memory" in report
    assert "Intent: memory_diagnostics" in report
    assert "Executed tools: inspect_memory_usage" in report