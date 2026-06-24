"""
Tests for CLI LLM preview journal capture.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import cli
from app.services.llm_contract import validate_llm_route_proposal
from app.services.llm_preview_journal import read_llm_route_previews
from app.services.llm_route_engine import LLMRouteCallResult


def build_result(status: str = "ok") -> LLMRouteCallResult:
    proposal = {
        "schema_version": "llm_contract_v0",
        "proposed_intent": "performance_diagnostic",
        "interpreted_request": "why is my laptop slow",
        "confidence": 0.88,
        "reasoning_summary": "The user described slowness.",
        "safety_notes": ["Read-only diagnostic route."],
    }
    validation = validate_llm_route_proposal(proposal)

    return LLMRouteCallResult(
        status=status,
        message="preview ok",
        model_used="injected_model",
        prompt="prompt text hidden in normal report",
        raw_model_output=proposal,
        validation=validation,
        used_model=True,
    )


def test_llm_preview_records_journal_entry(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "build_llm_route_call",
        lambda user_request, *, model_callable=None: build_result(),
    )

    cli.print_llm_route_preview_report(
        "my laptop is slow",
        memory_dir=tmp_path,
    )

    output = capsys.readouterr().out
    records = read_llm_route_previews(memory_dir=tmp_path)

    assert "LIGHTHOUSE LLM ROUTE PREVIEW" in output
    assert "Preview journal:" in output
    assert "Preview ID: llmprev-" in output
    assert "Saved: yes" in output
    assert "No command was executed by llm preview." in output
    assert len(records) == 1
    assert records[0]["normalized_input"] == "my laptop is slow"
    assert records[0]["safety"]["executed"] is False


def test_llm_preview_does_not_record_empty_request(tmp_path, capsys) -> None:
    cli.print_llm_route_preview_report("", memory_dir=tmp_path)

    output = capsys.readouterr().out
    records = read_llm_route_previews(memory_dir=tmp_path)

    assert "Status: needs_clarification" in output
    assert "No command was executed by llm preview." in output
    assert records == []


def test_print_llm_route_previews_report_outputs_recent_records(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "build_llm_route_call",
        lambda user_request, *, model_callable=None: build_result(),
    )

    cli.print_llm_route_preview_report(
        "my laptop is slow",
        memory_dir=tmp_path,
    )
    capsys.readouterr()

    cli.print_llm_route_previews_report(memory_dir=tmp_path)

    output = capsys.readouterr().out

    assert "LIGHTHOUSE LLM ROUTE PREVIEWS" in output
    assert "Shown: 1" in output
    assert "proposed_intent: performance_diagnostic" in output
    assert "executed: no" in output


def test_run_canonical_command_handles_llm_previews(monkeypatch, capsys) -> None:
    calls: list[int] = []

    def fake_report(*, limit: int = 10) -> None:
        calls.append(limit)
        print("LLM PREVIEWS REPORT CALLED")

    monkeypatch.setattr(cli, "print_llm_route_previews_report", fake_report)

    result = cli.run_canonical_command("llm previews")

    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == [10]
    assert "LLM PREVIEWS REPORT CALLED" in output
