"""
Tests for the Lighthouse target resolver.

The target resolver identifies candidate targets for tool requests.
It does not execute tools, confirm actions, or change the OS.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.target_resolver import (
    TARGET_CONFIDENCE_HIGH,
    TARGET_CONFIDENCE_LOW,
    TARGET_CONFIDENCE_MEDIUM,
    TARGET_CONFIDENCE_NONE,
    TARGET_STATUS_AMBIGUOUS_TARGET,
    TARGET_STATUS_BLOCKED_TOOL,
    TARGET_STATUS_CANDIDATE_FOUND,
    TARGET_STATUS_NO_TARGET_FOUND,
    TARGET_STATUS_NO_TARGET_NEEDED,
    TARGET_STATUS_UNKNOWN_TOOL,
    build_ambiguous_browser_candidates,
    contains_phrase,
    find_process_candidates,
    format_target_resolution,
    normalize_text_for_matching,
    resolve_target_for_tool,
)


def test_normalize_text_for_matching_simplifies_text() -> None:
    """
    Matching text should be lowercase and punctuation-insensitive.
    """
    normalized = normalize_text_for_matching("Close Chrome.exe, please!")

    assert normalized == "close chrome exe please"


def test_contains_phrase_matches_whole_phrase() -> None:
    """
    Phrase matching should avoid partial word matches.
    """
    text = normalize_text_for_matching("Please close Google Chrome now.")

    assert contains_phrase(text, "google chrome") is True
    assert contains_phrase(text, "chrome") is True
    assert contains_phrase(text, "edge") is False


def test_find_process_candidates_detects_chrome() -> None:
    """
    Chrome should resolve to the chrome.exe candidate.
    """
    candidates = find_process_candidates("close Chrome because it is using memory")

    assert len(candidates) == 1
    assert candidates[0].target == "chrome.exe"
    assert candidates[0].display_name == "Google Chrome"
    assert candidates[0].confidence == TARGET_CONFIDENCE_MEDIUM


def test_find_process_candidates_detects_exact_exe_with_high_confidence() -> None:
    """
    Exact executable references should be higher confidence.
    """
    candidates = find_process_candidates("close chrome.exe because it is frozen")

    assert len(candidates) == 1
    assert candidates[0].target == "chrome.exe"
    assert candidates[0].confidence == TARGET_CONFIDENCE_HIGH


def test_find_process_candidates_detects_edge() -> None:
    """
    Edge should resolve to msedge.exe.
    """
    candidates = find_process_candidates("close Microsoft Edge")

    assert len(candidates) == 1
    assert candidates[0].target == "msedge.exe"
    assert candidates[0].display_name == "Microsoft Edge"


def test_find_process_candidates_detects_visual_studio_code() -> None:
    """
    Visual Studio Code should resolve to Code.exe.
    """
    candidates = find_process_candidates("close Visual Studio Code")

    assert len(candidates) == 1
    assert candidates[0].target == "Code.exe"
    assert candidates[0].display_name == "Visual Studio Code"


def test_resolve_target_for_close_process_returns_candidate() -> None:
    """
    A clear process request should return a candidate target.
    """
    resolution = resolve_target_for_tool(
        tool_name="close_selected_process",
        user_request="close Chrome because it is using memory",
    )

    assert resolution.status == TARGET_STATUS_CANDIDATE_FOUND
    assert resolution.tool_name == "close_selected_process"
    assert resolution.target == "chrome.exe"
    assert resolution.display_name == "Google Chrome"
    assert resolution.confidence == TARGET_CONFIDENCE_MEDIUM
    assert resolution.requires_operator_review is True
    assert resolution.requires_target is True
    assert resolution.safety_summary["target_resolution_allowed"] is True


def test_resolve_target_for_close_process_is_case_insensitive() -> None:
    """
    Target matching should be case-insensitive.
    """
    resolution = resolve_target_for_tool(
        tool_name="close_selected_process",
        user_request="CLOSE CHROME",
    )

    assert resolution.status == TARGET_STATUS_CANDIDATE_FOUND
    assert resolution.target == "chrome.exe"


def test_resolve_target_for_close_process_returns_ambiguous_when_multiple_found() -> None:
    """
    Multiple named process targets should require Operator review.
    """
    resolution = resolve_target_for_tool(
        tool_name="close_selected_process",
        user_request="close Chrome and Edge",
    )

    assert resolution.status == TARGET_STATUS_AMBIGUOUS_TARGET
    assert resolution.target is None
    assert len(resolution.candidates) == 2
    assert {candidate.target for candidate in resolution.candidates} == {
        "chrome.exe",
        "msedge.exe",
    }


def test_resolve_target_for_generic_browser_is_ambiguous() -> None:
    """
    Generic browser requests should not assume a specific browser.
    """
    resolution = resolve_target_for_tool(
        tool_name="close_selected_process",
        user_request="close the browser",
    )

    assert resolution.status == TARGET_STATUS_AMBIGUOUS_TARGET
    assert resolution.target is None
    assert resolution.confidence == TARGET_CONFIDENCE_LOW
    assert len(resolution.candidates) >= 2


def test_resolve_target_for_close_process_returns_no_target_found() -> None:
    """
    Vague references should not invent a target.
    """
    resolution = resolve_target_for_tool(
        tool_name="close_selected_process",
        user_request="close it because it is using memory",
    )

    assert resolution.status == TARGET_STATUS_NO_TARGET_FOUND
    assert resolution.target is None
    assert resolution.confidence == TARGET_CONFIDENCE_NONE
    assert resolution.requires_operator_review is True


def test_resolve_target_for_read_only_tool_returns_no_target_needed() -> None:
    """
    Read-only tools that do not require targets should bypass resolution.
    """
    resolution = resolve_target_for_tool(
        tool_name="collect_snapshot",
        user_request="check my laptop health",
    )

    assert resolution.status == TARGET_STATUS_NO_TARGET_NEEDED
    assert resolution.target is None
    assert resolution.requires_operator_review is False
    assert resolution.requires_target is False


def test_resolve_target_for_blocked_tool_returns_blocked() -> None:
    """
    Blocked tools should not receive executable targets.
    """
    resolution = resolve_target_for_tool(
        tool_name="delete_user_files",
        user_request="delete files from downloads",
    )

    assert resolution.status == TARGET_STATUS_BLOCKED_TOOL
    assert resolution.target is None
    assert resolution.requires_operator_review is True
    assert resolution.safety_summary["target_resolution_allowed"] is False


def test_resolve_target_for_unknown_tool_returns_unknown() -> None:
    """
    Unknown tools should not receive target resolution.
    """
    resolution = resolve_target_for_tool(
        tool_name="invented_tool",
        user_request="do something to chrome",
    )

    assert resolution.status == TARGET_STATUS_UNKNOWN_TOOL
    assert resolution.target is None
    assert resolution.safety_summary["target_resolution_allowed"] is False


def test_build_ambiguous_browser_candidates_returns_browser_options() -> None:
    """
    Generic browser ambiguity should expose candidate browsers.
    """
    candidates = build_ambiguous_browser_candidates()

    assert len(candidates) >= 2
    assert "chrome.exe" in {candidate.target for candidate in candidates}
    assert all(candidate.confidence == TARGET_CONFIDENCE_LOW for candidate in candidates)


def test_target_candidate_to_dict_shape() -> None:
    """
    Target candidates should expose a stable dictionary shape.
    """
    candidates = find_process_candidates("close chrome")

    payload = candidates[0].to_dict()

    assert payload["target"] == "chrome.exe"
    assert payload["display_name"] == "Google Chrome"
    assert payload["confidence"] == TARGET_CONFIDENCE_MEDIUM
    assert payload["source"] == "alias_table"


def test_target_resolution_to_dict_shape() -> None:
    """
    Target resolutions should expose a stable dictionary shape.
    """
    resolution = resolve_target_for_tool(
        tool_name="close_selected_process",
        user_request="close chrome",
    )

    payload = resolution.to_dict()

    assert payload["status"] == TARGET_STATUS_CANDIDATE_FOUND
    assert payload["tool_name"] == "close_selected_process"
    assert payload["target"] == "chrome.exe"
    assert payload["display_name"] == "Google Chrome"
    assert payload["requires_operator_review"] is True
    assert len(payload["candidates"]) == 1


def test_format_target_resolution_contains_candidate_details() -> None:
    """
    Formatted target resolution should be readable in the CLI later.
    """
    resolution = resolve_target_for_tool(
        tool_name="close_selected_process",
        user_request="close chrome",
    )

    report = format_target_resolution(resolution)

    assert "LIGHTHOUSE TARGET RESOLUTION" in report
    assert "Status: candidate_found" in report
    assert "Tool: close_selected_process" in report
    assert "Target: chrome.exe" in report
    assert "Google Chrome" in report