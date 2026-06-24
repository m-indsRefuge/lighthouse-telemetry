"""
Tests for LLM route preview journal capture.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.llm_contract import validate_llm_route_proposal
from app.services.llm_preview_journal import (
    format_llm_route_previews_report,
    llm_preview_journal_path,
    read_llm_route_previews,
    record_llm_route_preview,
)
from app.services.llm_route_engine import LLMRouteCallResult


def build_preview_result(status: str = "ok") -> LLMRouteCallResult:
    proposal = {
        "schema_version": "llm_contract_v0",
        "proposed_intent": "performance_diagnostic",
        "interpreted_request": "why is my laptop slow",
        "confidence": 0.86,
        "reasoning_summary": "The user described slowness.",
        "safety_notes": ["Read-only diagnostic route."],
    }
    validation = validate_llm_route_proposal(proposal)

    return LLMRouteCallResult(
        status=status,
        message="LLM route proposal passed contract validation.",
        model_used="injected_model",
        prompt="prompt hidden",
        raw_model_output=proposal,
        validation=validation,
        used_model=True,
        warnings=validation.warnings,
    )


def test_record_llm_route_preview_writes_jsonl(tmp_path) -> None:
    result = record_llm_route_preview(
        user_request="my laptop is slow",
        preview_result=build_preview_result(),
        memory_dir=tmp_path,
    )

    assert result["status"] == "ok"
    assert result["data"]["saved"] is True
    assert result["data"]["preview_id"].startswith("llmprev-")
    assert llm_preview_journal_path(tmp_path).exists()

    records = read_llm_route_previews(memory_dir=tmp_path)

    assert len(records) == 1
    assert records[0]["mode"] == "llm_preview"
    assert records[0]["normalized_input"] == "my laptop is slow"
    assert records[0]["status"] == "ok"
    assert records[0]["contract_valid"] is True
    assert records[0]["proposed_intent"] == "performance_diagnostic"
    assert records[0]["interpreted_request"] == "why is my laptop slow"
    assert records[0]["safety"]["preview_only"] is True
    assert records[0]["safety"]["executed"] is False
    assert records[0]["safety"]["model_authority"] is False


def test_read_llm_route_previews_returns_newest_first(tmp_path) -> None:
    record_llm_route_preview(
        user_request="first request",
        preview_result=build_preview_result(),
        memory_dir=tmp_path,
    )
    record_llm_route_preview(
        user_request="second request",
        preview_result=build_preview_result(),
        memory_dir=tmp_path,
    )

    records = read_llm_route_previews(memory_dir=tmp_path)

    assert [record["normalized_input"] for record in records] == [
        "second request",
        "first request",
    ]


def test_format_llm_route_previews_report_handles_empty_journal(tmp_path) -> None:
    report = format_llm_route_previews_report(memory_dir=tmp_path)

    assert "LIGHTHOUSE LLM ROUTE PREVIEWS" in report
    assert "Shown: 0" in report
    assert "No LLM route previews recorded yet." in report


def test_format_llm_route_previews_report_includes_safety_summary(tmp_path) -> None:
    record_llm_route_preview(
        user_request="my laptop is slow",
        preview_result=build_preview_result(),
        memory_dir=tmp_path,
    )

    report = format_llm_route_previews_report(memory_dir=tmp_path)

    assert "LIGHTHOUSE LLM ROUTE PREVIEWS" in report
    assert "contract_valid: True" in report
    assert "proposed_intent: performance_diagnostic" in report
    assert "interpreted_request: why is my laptop slow" in report
    assert "executed: no" in report
    assert "preview_only: yes" in report
