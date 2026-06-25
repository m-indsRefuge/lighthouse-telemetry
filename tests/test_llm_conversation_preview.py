"""
Tests for the LLM conversational preview bridge.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.llm_conversation_preview import (
    build_llm_conversation_preview,
    extract_preview_id,
    format_llm_conversation_preview_report,
)


VALID_PROCESS_MEMORY_PROPOSAL = """
{
  "schema_version": "llm_contract_v0",
  "proposed_intent": "process_memory_diagnostic",
  "interpreted_request": "why is Chrome using memory",
  "confidence": 0.82,
  "reasoning_summary": "The request asks about Chrome memory usage.",
  "safety_notes": ["Read-only diagnostic route only."]
}
"""


def test_empty_llm_talk_needs_clarification() -> None:
    calls: list[str] = []

    def model_callable(prompt: str) -> str:
        calls.append(prompt)
        return VALID_PROCESS_MEMORY_PROPOSAL

    result = build_llm_conversation_preview(
        "",
        model_callable=model_callable,
    )

    assert result.status == "needs_clarification"
    assert result.executed is False
    assert result.deterministic_result is None
    assert result.llm_route_result is None
    assert calls == []


def test_llm_talk_builds_deterministic_and_model_preview(tmp_path: Path) -> None:
    result = build_llm_conversation_preview(
        "why is chrome eating memory",
        model_callable=lambda prompt: VALID_PROCESS_MEMORY_PROPOSAL,
        memory_dir=tmp_path,
    )

    assert result.status == "ok"
    assert result.executed is False
    assert result.deterministic_result is not None
    assert result.deterministic_result.intent == "process_memory_diagnostic"
    assert result.llm_route_result is not None
    assert result.llm_route_result.status == "ok"
    assert result.llm_route_result.validation is not None
    assert result.llm_route_result.validation.valid is True
    assert result.autorun_gate is not None
    assert result.preview_journal_result is not None
    assert result.preview_journal_result["status"] == "ok"
    assert extract_preview_id(result.preview_journal_result)


def test_llm_talk_records_invalid_model_preview(tmp_path: Path) -> None:
    result = build_llm_conversation_preview(
        "why is chrome eating memory",
        model_callable=lambda prompt: "{}",
        memory_dir=tmp_path,
    )

    assert result.status == "ok"
    assert result.executed is False
    assert result.llm_route_result is not None
    assert result.llm_route_result.status == "invalid"
    assert result.preview_journal_result is not None
    assert result.preview_journal_result["status"] == "ok"


def test_llm_talk_report_contains_operator_audit_sections(tmp_path: Path) -> None:
    result = build_llm_conversation_preview(
        "why is chrome eating memory",
        model_callable=lambda prompt: VALID_PROCESS_MEMORY_PROPOSAL,
        memory_dir=tmp_path,
    )

    report = format_llm_conversation_preview_report(result)

    assert "LIGHTHOUSE LLM TALK PREVIEW" in report
    assert "DETERMINISTIC INTERPRETATION" in report
    assert "MODEL PROPOSAL" in report
    assert "ROUTE HANDOFF" in report
    assert "EXECUTION" in report
    assert "No command was executed by llm talk." in report
    assert "Model output cannot bypass the route registry or autorun gate." in report
    assert "Preview ID: llmprev-" in report
    assert "To continue manually: runplan why is Chrome using memory" in report


def test_llm_talk_empty_report_contains_usage() -> None:
    result = build_llm_conversation_preview("")

    report = format_llm_conversation_preview_report(result)

    assert "Status: needs_clarification" in report
    assert "llm talk my laptop feels slow" in report
