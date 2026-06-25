"""
Tests for V1 Conversational Engine Turn V0.
"""

from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.conversational_engine_turn import (
    CONVERSATIONAL_TURN_SCHEMA_VERSION,
    build_conversational_engine_turn,
    read_conversational_engine_turns,
)


def valid_route_model(prompt: str) -> dict[str, str]:
    return {
        "response": json.dumps(
            {
                "schema_version": "llm_contract_v0",
                "proposed_intent": "performance_diagnostic",
                "interpreted_request": "why is my laptop slow",
                "confidence": 0.91,
                "reasoning_summary": "The user is asking about slow performance.",
                "safety_notes": ["Read-only diagnostic route only."],
            }
        )
    }


def invalid_authority_model(prompt: str) -> dict[str, str]:
    return {
        "response": json.dumps(
            {
                "schema_version": "llm_contract_v0",
                "proposed_intent": "performance_diagnostic",
                "interpreted_request": "why is my laptop slow",
                "confidence": 0.91,
                "reasoning_summary": "The user is asking about slow performance.",
                "safety_notes": ["Read-only diagnostic route only."],
                "command": "runplan why is my laptop slow",
            }
        )
    }


def test_empty_conversational_turn_requires_clarification(tmp_path: Path) -> None:
    result = build_conversational_engine_turn("   ", memory_dir=tmp_path)

    assert result.status == "needs_clarification"
    assert result.executed is False
    assert result.turn_journal_result is None


def test_conversational_turn_records_valid_model_route(tmp_path: Path) -> None:
    result = build_conversational_engine_turn(
        "why is my laptop slow",
        model_callable=valid_route_model,
        memory_dir=tmp_path,
    )

    assert result.status == "ok"
    assert result.executed is False
    assert result.deterministic_result is not None
    assert result.llm_route_result is not None
    assert result.llm_route_result.validation is not None
    assert result.llm_route_result.validation.valid is True
    assert result.selected_route_source == "llm_contract"
    assert result.autorun_gate is not None
    assert result.autorun_gate.allowed is True
    assert result.turn_journal_result is not None
    assert result.turn_journal_result["status"] == "ok"

    records = read_conversational_engine_turns(memory_dir=tmp_path)
    assert len(records) == 1

    record = records[0]
    assert record["schema_version"] == CONVERSATIONAL_TURN_SCHEMA_VERSION
    assert record["mode"] == "conversation_turn_preview"
    assert record["selected_route_source"] == "llm_contract"
    assert record["safety"]["preview_only"] is True
    assert record["safety"]["executed"] is False
    assert record["safety"]["model_authority"] is False
    assert record["safety"]["os_mutation"] is False


def test_invalid_model_route_falls_back_to_deterministic_route(tmp_path: Path) -> None:
    result = build_conversational_engine_turn(
        "why is my laptop slow",
        model_callable=invalid_authority_model,
        memory_dir=tmp_path,
    )

    assert result.status == "ok"
    assert result.executed is False
    assert result.llm_route_result is not None
    assert result.llm_route_result.status == "invalid"
    assert result.llm_route_result.validation is not None
    assert result.llm_route_result.validation.valid is False
    assert result.selected_route_source == "deterministic"
    assert result.selected_route_handoff["intent"] == "performance_diagnostic"

    records = read_conversational_engine_turns(memory_dir=tmp_path)
    assert records[0]["llm_route_result"]["status"] == "invalid"
    assert records[0]["selected_route_source"] == "deterministic"


def test_conversational_turn_to_dict_shape_is_stable(tmp_path: Path) -> None:
    result = build_conversational_engine_turn(
        "why is my laptop slow",
        model_callable=valid_route_model,
        memory_dir=tmp_path,
    )

    assert list(result.to_dict().keys()) == [
        "status",
        "message",
        "user_request",
        "mode",
        "deterministic_result",
        "llm_route_result",
        "selected_route_source",
        "selected_route_handoff",
        "autorun_gate",
        "turn_journal_result",
        "executed",
    ]


def test_conversational_turn_does_not_execute_when_gate_allows(tmp_path: Path) -> None:
    result = build_conversational_engine_turn(
        "why is my laptop slow",
        model_callable=valid_route_model,
        memory_dir=tmp_path,
    )

    assert result.autorun_gate is not None
    assert result.autorun_gate.allowed is True
    assert result.executed is False

    record = read_conversational_engine_turns(memory_dir=tmp_path)[0]
    assert record["safety"]["tool_execution"] is False
    assert record["safety"]["talkrun_integration"] is False

def test_format_conversational_engine_turns_report_empty(tmp_path: Path) -> None:
    from app.services.conversational_engine_turn import (
        format_conversational_engine_turns_report,
    )

    report = format_conversational_engine_turns_report(memory_dir=tmp_path)

    assert "LIGHTHOUSE CONVERSATIONAL ENGINE TURNS" in report
    assert "Shown: 0" in report
    assert "No conversational engine turns recorded yet." in report


def test_format_conversational_engine_turns_report_shows_recent_turn(tmp_path: Path) -> None:
    from app.services.conversational_engine_turn import (
        format_conversational_engine_turns_report,
    )

    build_conversational_engine_turn(
        "why is my laptop slow",
        model_callable=valid_route_model,
        memory_dir=tmp_path,
    )

    report = format_conversational_engine_turns_report(memory_dir=tmp_path)

    assert "LIGHTHOUSE CONVERSATIONAL ENGINE TURNS" in report
    assert "Shown: 1" in report
    assert "turn_id: turn-" in report
    assert "original_input: why is my laptop slow" in report
    assert "deterministic_intent: performance_diagnostic" in report
    assert "selected_route_source: llm_contract" in report
    assert "recommended_command: runplan why is my laptop slow" in report
    assert "executed: no" in report
    assert "preview_only: yes" in report
