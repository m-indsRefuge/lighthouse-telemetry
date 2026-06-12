"""
Tests for the Lighthouse confirmation gate.

The confirmation gate defines the safety process for future permission-gated
tools. It does not execute OS-changing tools.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.confirmation_gate import (
    CONFIRMATION_STATUS_ACCEPTED,
    CONFIRMATION_STATUS_BLOCKED,
    CONFIRMATION_STATUS_NEEDS_TARGET,
    CONFIRMATION_STATUS_NOT_REQUIRED,
    CONFIRMATION_STATUS_REFUSED,
    CONFIRMATION_STATUS_REQUIRED,
    CONFIRMATION_STATUS_UNKNOWN_TOOL,
    build_confirmation_phrase,
    build_confirmation_request,
    format_confirmation_request,
    format_confirmation_result,
    validate_confirmation_for_tool,
    validate_confirmation_input,
)


def test_build_confirmation_phrase_uses_exact_tool_name() -> None:
    """
    Confirmation phrases should be deterministic and explicit.
    """
    phrase = build_confirmation_phrase("close_selected_process")

    assert phrase == "CONFIRM CLOSE SELECTED PROCESS"


def test_unknown_tool_cannot_be_confirmed() -> None:
    """
    Unknown tools should not receive confirmation phrases.
    """
    request = build_confirmation_request("invented_tool")

    assert request.status == CONFIRMATION_STATUS_UNKNOWN_TOOL
    assert request.tool_name == "invented_tool"
    assert request.required_phrase is None
    assert request.executable_after_confirmation is False
    assert request.safety_summary["confirmation_allowed"] is False


def test_blocked_tool_cannot_be_confirmed() -> None:
    """
    Blocked tools should never become confirmable.
    """
    request = build_confirmation_request(
        "delete_user_files",
        target="C:\\Users\\Nolan\\Documents",
    )

    assert request.status == CONFIRMATION_STATUS_BLOCKED
    assert request.required_phrase is None
    assert request.executable_after_confirmation is False
    assert request.safety_summary["confirmation_allowed"] is False


def test_read_only_tool_does_not_need_confirmation() -> None:
    """
    Read-only tools should not require confirmation.
    """
    request = build_confirmation_request("collect_snapshot")

    assert request.status == CONFIRMATION_STATUS_NOT_REQUIRED
    assert request.required_phrase is None
    assert request.requires_confirmation is False
    assert request.executable_after_confirmation is False


def test_confirmation_tool_requires_target_when_registered_that_way() -> None:
    """
    Target-required action tools should not be confirmable without a target.
    """
    request = build_confirmation_request("close_selected_process")

    assert request.status == CONFIRMATION_STATUS_NEEDS_TARGET
    assert request.required_phrase is None
    assert request.requires_target is True
    assert request.executable_after_confirmation is False


def test_confirmation_request_is_created_for_targeted_action_tool() -> None:
    """
    A confirmation-required tool with a target should produce a phrase.
    """
    request = build_confirmation_request(
        "close_selected_process",
        target="chrome.exe",
    )

    assert request.status == CONFIRMATION_STATUS_REQUIRED
    assert request.tool_name == "close_selected_process"
    assert request.target == "chrome.exe"
    assert request.required_phrase == "CONFIRM CLOSE SELECTED PROCESS"
    assert request.requires_confirmation is True
    assert request.requires_target is True
    assert request.executable_after_confirmation is True
    assert request.safety_summary["confirmation_allowed"] is True


def test_validate_confirmation_accepts_exact_phrase() -> None:
    """
    Exact Operator confirmation should be accepted.
    """
    request = build_confirmation_request(
        "close_selected_process",
        target="chrome.exe",
    )

    result = validate_confirmation_input(
        request=request,
        operator_input="CONFIRM CLOSE SELECTED PROCESS",
    )

    assert result.status == CONFIRMATION_STATUS_ACCEPTED
    assert result.accepted is True
    assert result.tool_name == "close_selected_process"
    assert result.target == "chrome.exe"


def test_validate_confirmation_accepts_phrase_with_outer_whitespace() -> None:
    """
    Leading/trailing whitespace should not block an otherwise exact phrase.
    """
    request = build_confirmation_request(
        "close_selected_process",
        target="chrome.exe",
    )

    result = validate_confirmation_input(
        request=request,
        operator_input="  CONFIRM CLOSE SELECTED PROCESS  ",
    )

    assert result.status == CONFIRMATION_STATUS_ACCEPTED
    assert result.accepted is True


def test_validate_confirmation_rejects_wrong_case() -> None:
    """
    Confirmation phrases are intentionally case-sensitive.
    """
    request = build_confirmation_request(
        "close_selected_process",
        target="chrome.exe",
    )

    result = validate_confirmation_input(
        request=request,
        operator_input="confirm close selected process",
    )

    assert result.status == CONFIRMATION_STATUS_REFUSED
    assert result.accepted is False
    assert "did not match exactly" in result.message


def test_validate_confirmation_rejects_wrong_phrase() -> None:
    """
    Similar but incorrect phrases should be refused.
    """
    request = build_confirmation_request(
        "close_selected_process",
        target="chrome.exe",
    )

    result = validate_confirmation_input(
        request=request,
        operator_input="CONFIRM CLOSE CHROME",
    )

    assert result.status == CONFIRMATION_STATUS_REFUSED
    assert result.accepted is False


def test_validate_confirmation_refuses_non_confirmable_request() -> None:
    """
    A blocked request cannot be accepted even if the operator types something.
    """
    request = build_confirmation_request("delete_user_files", target="Downloads")

    result = validate_confirmation_input(
        request=request,
        operator_input="CONFIRM DELETE USER FILES",
    )

    assert result.status == CONFIRMATION_STATUS_REFUSED
    assert result.accepted is False
    assert "not confirmable" in result.message


def test_validate_confirmation_for_tool_convenience_function() -> None:
    """
    The convenience function should build and validate in one call.
    """
    result = validate_confirmation_for_tool(
        tool_name="close_selected_process",
        target="chrome.exe",
        operator_input="CONFIRM CLOSE SELECTED PROCESS",
    )

    assert result.status == CONFIRMATION_STATUS_ACCEPTED
    assert result.accepted is True


def test_confirmation_request_to_dict_shape() -> None:
    """
    Confirmation requests should expose a stable dictionary shape.
    """
    request = build_confirmation_request(
        "close_selected_process",
        target="chrome.exe",
    )

    payload = request.to_dict()

    assert payload["status"] == CONFIRMATION_STATUS_REQUIRED
    assert payload["tool_name"] == "close_selected_process"
    assert payload["required_phrase"] == "CONFIRM CLOSE SELECTED PROCESS"
    assert payload["target"] == "chrome.exe"
    assert payload["executable_after_confirmation"] is True
    assert "safety_summary" in payload


def test_confirmation_result_to_dict_shape() -> None:
    """
    Confirmation results should expose a stable dictionary shape.
    """
    result = validate_confirmation_for_tool(
        tool_name="close_selected_process",
        target="chrome.exe",
        operator_input="CONFIRM CLOSE SELECTED PROCESS",
    )

    payload = result.to_dict()

    assert payload["status"] == CONFIRMATION_STATUS_ACCEPTED
    assert payload["accepted"] is True
    assert payload["tool_name"] == "close_selected_process"
    assert payload["target"] == "chrome.exe"
    assert "request" in payload


def test_format_confirmation_request_contains_required_fields() -> None:
    """
    Formatted confirmation requests should be readable.
    """
    request = build_confirmation_request(
        "close_selected_process",
        target="chrome.exe",
    )

    report = format_confirmation_request(request)

    assert "LIGHTHOUSE CONFIRMATION GATE" in report
    assert "Tool: close_selected_process" in report
    assert "Target: chrome.exe" in report
    assert "CONFIRM CLOSE SELECTED PROCESS" in report


def test_format_confirmation_result_contains_required_fields() -> None:
    """
    Formatted confirmation results should be readable.
    """
    result = validate_confirmation_for_tool(
        tool_name="close_selected_process",
        target="chrome.exe",
        operator_input="CONFIRM CLOSE SELECTED PROCESS",
    )

    report = format_confirmation_result(result)

    assert "LIGHTHOUSE CONFIRMATION RESULT" in report
    assert "Accepted: yes" in report
    assert "Tool: close_selected_process" in report
    assert "Target: chrome.exe" in report