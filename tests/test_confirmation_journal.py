"""
Tests for Lighthouse confirmation journaling.

Confirmation journaling records target-resolution and confirmation-gate
decisions. It does not execute OS-changing tools.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.confirmation_gate import (
    CONFIRMATION_STATUS_ACCEPTED,
    build_confirmation_request,
    validate_confirmation_input,
)
from app.services.confirmation_journal import (
    EVENT_TYPE_CONFIRMATION_RESULT,
    EVENT_TYPE_TARGET_CONFIRMATION_PREVIEW,
    build_confirmation_result_entry,
    build_target_confirmation_preview_entry,
    record_confirmation_result,
    record_target_confirmation_preview,
)
from app.services.target_resolver import (
    TARGET_STATUS_CANDIDATE_FOUND,
    resolve_target_for_tool,
)


def test_build_target_confirmation_preview_entry_shape() -> None:
    """
    Target confirmation preview entries should have a stable compact shape.
    """
    target_resolution = resolve_target_for_tool(
        tool_name="close_selected_process",
        user_request="close Chrome because it is using memory",
    )
    confirmation_request = build_confirmation_request(
        tool_name="close_selected_process",
        target=target_resolution.target,
    )

    entry = build_target_confirmation_preview_entry(
        user_request="close Chrome because it is using memory",
        tool_name="close_selected_process",
        target_resolution=target_resolution,
        confirmation_request=confirmation_request,
        timestamp="2026-01-01T00:00:00Z",
    )

    assert entry["schema_version"] == 1
    assert entry["event_type"] == EVENT_TYPE_TARGET_CONFIRMATION_PREVIEW
    assert entry["timestamp"] == "2026-01-01T00:00:00Z"
    assert entry["user_request"] == "close Chrome because it is using memory"
    assert entry["tool_name"] == "close_selected_process"

    assert entry["target_resolution"]["status"] == TARGET_STATUS_CANDIDATE_FOUND
    assert entry["target_resolution"]["target"] == "chrome.exe"
    assert entry["target_resolution"]["display_name"] == "Google Chrome"
    assert entry["target_resolution"]["candidate_count"] == 1

    assert entry["confirmation_request"]["status"] == "confirmation_required"
    assert entry["confirmation_request"]["target"] == "chrome.exe"
    assert entry["confirmation_request"]["required_phrase"] == (
        "CONFIRM CLOSE SELECTED PROCESS"
    )

    assert entry["safety"]["action_executed"] is False
    assert entry["safety"]["confirmation_input_accepted"] is False
    assert entry["safety"]["preview_only"] is True


def test_build_target_confirmation_preview_entry_handles_missing_target() -> None:
    """
    Ambiguous or missing targets should still be journalable.
    """
    target_resolution = resolve_target_for_tool(
        tool_name="close_selected_process",
        user_request="close the browser",
    )
    confirmation_request = build_confirmation_request(
        tool_name="close_selected_process",
        target=None,
    )

    entry = build_target_confirmation_preview_entry(
        user_request="close the browser",
        tool_name="close_selected_process",
        target_resolution=target_resolution,
        confirmation_request=confirmation_request,
        timestamp="2026-01-01T00:00:00Z",
    )

    assert entry["event_type"] == EVENT_TYPE_TARGET_CONFIRMATION_PREVIEW
    assert entry["target_resolution"]["target"] is None
    assert entry["target_resolution"]["candidate_count"] >= 2
    assert entry["confirmation_request"]["status"] == "needs_target"
    assert entry["confirmation_request"]["required_phrase"] is None
    assert entry["safety"]["action_executed"] is False


def test_build_confirmation_result_entry_for_accepted_confirmation() -> None:
    """
    Accepted confirmation results should be journalable without executing.
    """
    request = build_confirmation_request(
        tool_name="close_selected_process",
        target="chrome.exe",
    )
    result = validate_confirmation_input(
        request=request,
        operator_input="CONFIRM CLOSE SELECTED PROCESS",
    )

    entry = build_confirmation_result_entry(
        user_request="close Chrome because it is using memory",
        confirmation_result=result,
        timestamp="2026-01-01T00:00:00Z",
    )

    assert entry["schema_version"] == 1
    assert entry["event_type"] == EVENT_TYPE_CONFIRMATION_RESULT
    assert entry["timestamp"] == "2026-01-01T00:00:00Z"
    assert entry["tool_name"] == "close_selected_process"
    assert entry["target"] == "chrome.exe"

    assert entry["confirmation_result"]["status"] == CONFIRMATION_STATUS_ACCEPTED
    assert entry["confirmation_result"]["accepted"] is True
    assert entry["confirmation_result"]["required_phrase"] == (
        "CONFIRM CLOSE SELECTED PROCESS"
    )

    assert entry["safety"]["action_executed"] is False
    assert entry["safety"]["confirmation_input_accepted"] is True
    assert entry["safety"]["preview_only"] is False


def test_record_target_confirmation_preview_writes_to_journal(tmp_path, monkeypatch) -> None:
    """
    Recording a preview should append through the shared action journal.
    """
    journal_path = tmp_path / "lighthouse_actions.jsonl"

    def fake_append_journal_entry(entry):
        from types import SimpleNamespace

        journal_path.write_text(str(entry), encoding="utf-8")
        return SimpleNamespace(
            status="ok",
            message="Journal entry recorded.",
            path=journal_path,
        )

    monkeypatch.setattr(
        "app.services.confirmation_journal.append_journal_entry",
        fake_append_journal_entry,
    )

    target_resolution = resolve_target_for_tool(
        tool_name="close_selected_process",
        user_request="close Chrome because it is using memory",
    )
    confirmation_request = build_confirmation_request(
        tool_name="close_selected_process",
        target=target_resolution.target,
    )

    result = record_target_confirmation_preview(
        user_request="close Chrome because it is using memory",
        tool_name="close_selected_process",
        target_resolution=target_resolution,
        confirmation_request=confirmation_request,
    )

    assert result.status == "ok"
    assert result.path == str(journal_path)
    assert result.entry["event_type"] == EVENT_TYPE_TARGET_CONFIRMATION_PREVIEW
    assert journal_path.exists()


def test_record_confirmation_result_writes_to_journal(tmp_path, monkeypatch) -> None:
    """
    Recording a confirmation result should append through the shared journal.
    """
    journal_path = tmp_path / "lighthouse_actions.jsonl"

    def fake_append_journal_entry(entry):
        from types import SimpleNamespace

        journal_path.write_text(str(entry), encoding="utf-8")
        return SimpleNamespace(
            status="ok",
            message="Journal entry recorded.",
            path=journal_path,
        )

    monkeypatch.setattr(
        "app.services.confirmation_journal.append_journal_entry",
        fake_append_journal_entry,
    )

    request = build_confirmation_request(
        tool_name="close_selected_process",
        target="chrome.exe",
    )
    confirmation_result = validate_confirmation_input(
        request=request,
        operator_input="CONFIRM CLOSE SELECTED PROCESS",
    )

    result = record_confirmation_result(
        user_request="close Chrome because it is using memory",
        confirmation_result=confirmation_result,
    )

    assert result.status == "ok"
    assert result.path == str(journal_path)
    assert result.entry["event_type"] == EVENT_TYPE_CONFIRMATION_RESULT
    assert journal_path.exists()