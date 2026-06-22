"""
Tests for deterministic Operator conversation decision traces.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.operator_conversation import (
    INTENT_DESTRUCTIVE_ACTION_REQUEST,
    INTENT_OS_ACTION_REQUEST,
    INTENT_PERFORMANCE_DIAGNOSTIC,
    INTENT_PROCESS_MEMORY_DIAGNOSTIC,
    INTENT_UNKNOWN,
    build_operator_response,
    interpret_operator_input,
)


def test_slowness_trace_records_read_only_diagnostic_decision() -> None:
    result = interpret_operator_input("my laptop feels weird and slow")
    trace = result.decision_trace or {}

    assert trace["normalized_input"] == "my laptop feels weird and slow"
    assert trace["selected_intent"] == INTENT_PERFORMANCE_DIAGNOSTIC
    assert trace["safety_class"] == "read_only_diagnostic"
    assert trace["autorun_eligible"] is True
    assert "slowness_words" in trace["matched_signal_groups"]
    assert "slow" in trace["matched_signal_groups"]["slowness_words"]


def test_chrome_memory_trace_records_process_and_memory_signals() -> None:
    result = interpret_operator_input("why is chrome eating memory")
    trace = result.decision_trace or {}

    assert trace["selected_intent"] == INTENT_PROCESS_MEMORY_DIAGNOSTIC
    assert trace["safety_class"] == "read_only_diagnostic"
    assert trace["autorun_eligible"] is True
    assert "chrome" in trace["matched_signal_groups"]["process_words"]
    assert "memory" in trace["matched_signal_groups"]["memory_words"]


def test_close_chrome_trace_records_os_changing_decision() -> None:
    result = interpret_operator_input("close chrome")
    trace = result.decision_trace or {}

    assert trace["selected_intent"] == INTENT_OS_ACTION_REQUEST
    assert trace["safety_class"] == "os_changing"
    assert trace["autorun_eligible"] is False
    assert "close" in trace["matched_signal_groups"]["action_words"]
    assert "chrome" in trace["matched_signal_groups"]["process_words"]


def test_delete_files_trace_records_destructive_decision() -> None:
    result = interpret_operator_input("delete files to make space")
    trace = result.decision_trace or {}

    assert trace["selected_intent"] == INTENT_DESTRUCTIVE_ACTION_REQUEST
    assert trace["safety_class"] == "destructive_or_data_changing"
    assert trace["autorun_eligible"] is False
    assert "delete" in trace["matched_signal_groups"]["destructive_words"]


def test_unknown_trace_records_clarification_state() -> None:
    result = interpret_operator_input("banana window purple")
    trace = result.decision_trace or {}

    assert trace["selected_intent"] == INTENT_UNKNOWN
    assert trace["safety_class"] == "needs_clarification"
    assert trace["autorun_eligible"] is False
    assert trace["requires_clarification"] is True


def test_operator_response_prints_decision_trace() -> None:
    result = interpret_operator_input("close chrome")

    output = build_operator_response(result)

    assert "Decision trace:" in output
    assert "- selected_intent: os_action_request" in output
    assert "- safety_class: os_changing" in output
    assert "- autorun_eligible: no" in output
    assert "- matched_signal_groups:" in output

def test_decision_trace_includes_route_contract_metadata() -> None:
    result = interpret_operator_input("close chrome")
    trace = result.decision_trace or {}

    assert trace["route_known"] is True
    assert trace["command_family"] == "runplan_preview_only"
    assert trace["manual_review_required"] is True

    route_contract = trace["route_contract"]

    assert route_contract["intent"] == INTENT_OS_ACTION_REQUEST
    assert route_contract["safety_class"] == "os_changing"
    assert route_contract["autorun_allowed"] is False

def test_conversation_result_includes_authoritative_route_handoff() -> None:
    result = interpret_operator_input("why is chrome eating memory")
    payload = result.to_dict()
    handoff = payload["route_handoff"]

    assert handoff["route_ready"] is True
    assert handoff["command_family"] == "runplan"
    assert handoff["engine_request"] == "why is Chrome using memory"
    assert handoff["autorun_allowed"] is True
    assert handoff["manual_review_required"] is False


def test_unsafe_conversation_result_handoff_requires_manual_review() -> None:
    result = interpret_operator_input("close chrome")
    payload = result.to_dict()
    handoff = payload["route_handoff"]

    assert handoff["route_ready"] is True
    assert handoff["command_family"] == "runplan_preview_only"
    assert handoff["engine_request"] == "close Chrome because it may be using resources"
    assert handoff["autorun_allowed"] is False
    assert handoff["manual_review_required"] is True


def test_unknown_conversation_result_handoff_is_not_ready() -> None:
    result = interpret_operator_input("banana window purple")
    payload = result.to_dict()
    handoff = payload["route_handoff"]

    assert handoff["route_ready"] is False
    assert handoff["command_family"] == "none"
    assert handoff["engine_request"] is None
    assert handoff["autorun_allowed"] is False
