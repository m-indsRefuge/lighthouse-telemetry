"""
Tests for the deterministic Operator conversation bridge.

The bridge should translate natural Operator language into safe Lighthouse routes
without calling a model, executing tools, mutating the OS, or writing memory.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.operator_conversation import (
    CONVERSATION_STATUS_NEEDS_CLARIFICATION,
    CONVERSATION_STATUS_OK,
    INTENT_DESTRUCTIVE_ACTION_REQUEST,
    INTENT_DIRECT_COMMAND,
    INTENT_GENERAL_HEALTH_CHECK,
    INTENT_OS_ACTION_REQUEST,
    INTENT_PERFORMANCE_DIAGNOSTIC,
    INTENT_PROCESS_MEMORY_DIAGNOSTIC,
    INTENT_REPAIR_REQUEST,
    build_operator_response,
    format_operator_response,
    interpret_operator_input,
)


def test_empty_input_requires_clarification() -> None:
    """
    Empty input should not be mapped to a command.
    """
    result = interpret_operator_input("   ")

    assert result.status == CONVERSATION_STATUS_NEEDS_CLARIFICATION
    assert result.requires_clarification is True
    assert result.recommended_command is None
    assert result.requires_engine_run is False
    assert result.clarifying_question is not None


def test_slowness_input_routes_to_runplan() -> None:
    """
    General slowness wording should route to a safe engine diagnostic.
    """
    result = interpret_operator_input("my laptop feels weird and slow")

    assert result.status == CONVERSATION_STATUS_OK
    assert result.intent == INTENT_PERFORMANCE_DIAGNOSTIC
    assert result.interpreted_request == "why is my laptop slow"
    assert result.recommended_command == "runplan why is my laptop slow"
    assert result.requires_engine_run is True
    assert "read-only" in result.safety_note


def test_chrome_memory_input_routes_to_process_memory_diagnostic() -> None:
    """
    Chrome memory wording should route to process/memory inspection.
    """
    result = interpret_operator_input("why is chrome eating memory")

    assert result.status == CONVERSATION_STATUS_OK
    assert result.intent == INTENT_PROCESS_MEMORY_DIAGNOSTIC
    assert result.interpreted_request == "why is Chrome using memory"
    assert result.recommended_command == "runplan why is Chrome using memory"
    assert result.requires_engine_run is True
    assert "No process will be closed" in result.safety_note


def test_os_action_input_routes_to_confirmation_gated_runplan() -> None:
    """
    OS-changing wording should route to runplan with confirmation warning.
    """
    result = interpret_operator_input("close chrome")

    assert result.status == CONVERSATION_STATUS_OK
    assert result.intent == INTENT_OS_ACTION_REQUEST
    assert result.recommended_command == "runplan close Chrome because it may be using resources"
    assert result.requires_engine_run is True
    assert result.warnings == ("OS-changing wording detected.",)
    assert "without explicit Operator confirmation" in result.safety_note


def test_destructive_input_routes_to_safe_engine_preview() -> None:
    """
    Destructive wording should not become a direct action.
    """
    result = interpret_operator_input("delete files to make space")

    assert result.status == CONVERSATION_STATUS_OK
    assert result.intent == INTENT_DESTRUCTIVE_ACTION_REQUEST
    assert result.recommended_command == "runplan delete files to make space"
    assert result.requires_engine_run is True
    assert result.warnings == ("Destructive or data-changing wording detected.",)
    assert "No files should be deleted" in result.safety_note


def test_broad_repair_request_routes_to_inspect_first() -> None:
    """
    Broad repair wording should become read-only inspection first.
    """
    result = interpret_operator_input("can you fix my pc")

    assert result.status == CONVERSATION_STATUS_OK
    assert result.intent == INTENT_REPAIR_REQUEST
    assert result.recommended_command == "runplan inspect my computer before suggesting fixes"
    assert result.requires_engine_run is True
    assert "inspect first" in result.safety_note.lower()


def test_general_health_input_routes_to_runplan_health_check() -> None:
    """
    General health wording should route through the engine.
    """
    result = interpret_operator_input("is anything wrong")

    assert result.status == CONVERSATION_STATUS_OK
    assert result.intent == INTENT_GENERAL_HEALTH_CHECK
    assert result.recommended_command == "runplan is anything wrong with my computer"
    assert result.requires_engine_run is True
    assert "read-only" in result.safety_note


def test_existing_direct_command_routes_without_engine_run() -> None:
    """
    Existing simple CLI commands should still be available as direct routes.
    """
    result = interpret_operator_input("show my saved snapshots")

    assert result.status == CONVERSATION_STATUS_OK
    assert result.intent == INTENT_DIRECT_COMMAND
    assert result.recommended_command == "history"
    assert result.requires_engine_run is False
    assert "existing Lighthouse CLI command" in result.safety_note


def test_unknown_input_requires_clarification() -> None:
    """
    Ambiguous input should ask a clarification question instead of guessing.
    """
    result = interpret_operator_input("banana window purple")

    assert result.status == CONVERSATION_STATUS_NEEDS_CLARIFICATION
    assert result.intent == "unknown"
    assert result.requires_clarification is True
    assert result.recommended_command is None
    assert result.clarifying_question is not None


def test_operator_result_to_dict_has_stable_shape() -> None:
    """
    Conversation results should serialize with a stable contract.
    """
    result = interpret_operator_input("close chrome")
    payload = result.to_dict()

    assert payload["status"] == CONVERSATION_STATUS_OK
    assert payload["original_input"] == "close chrome"
    assert payload["normalized_input"] == "close chrome"
    assert payload["intent"] == INTENT_OS_ACTION_REQUEST
    assert payload["interpreted_request"] == "close Chrome because it may be using resources"
    assert payload["recommended_command"] == "runplan close Chrome because it may be using resources"
    assert payload["requires_engine_run"] is True
    assert payload["requires_clarification"] is False
    assert payload["clarifying_question"] is None
    assert isinstance(payload["safety_note"], str)
    assert isinstance(payload["confidence"], float)
    assert payload["warnings"] == ["OS-changing wording detected."]
    assert payload["errors"] == []


def test_build_operator_response_includes_route_and_safety_note() -> None:
    """
    Formatted bridge output should show route and safety boundary.
    """
    result = interpret_operator_input("why is chrome eating memory")
    text = build_operator_response(result)

    assert "LIGHTHOUSE OPERATOR BRIDGE" in text
    assert "Status: ok" in text
    assert "Recommended command: runplan why is Chrome using memory" in text
    assert "Safety note:" in text


def test_format_operator_response_aliases_response_builder() -> None:
    """
    format_operator_response should provide the CLI display string.
    """
    result = interpret_operator_input("my laptop feels slow")

    assert format_operator_response(result) == build_operator_response(result)
