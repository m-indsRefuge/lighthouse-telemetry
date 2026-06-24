"""
Tests for Lighthouse LLM route preview CLI boundary.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import cli
from app.services.llm_contract import validate_llm_route_proposal
from app.services.llm_route_engine import LLMRouteCallResult


def build_result(status: str, proposal: dict | None) -> LLMRouteCallResult:
    validation = validate_llm_route_proposal(proposal) if proposal is not None else None

    return LLMRouteCallResult(
        status=status,
        message=f"preview {status}",
        model_used="injected_model",
        prompt="prompt text hidden in normal report",
        raw_model_output=proposal,
        validation=validation,
        used_model=True,
        errors=validation.errors if validation is not None and not validation.valid else (),
        warnings=validation.warnings if validation is not None else (),
    )


def test_llm_route_preview_requires_request(capsys) -> None:
    cli.print_llm_route_preview_report("")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE LLM ROUTE PREVIEW" in output
    assert "Status: needs_clarification" in output
    assert "Please provide a request after llm preview." in output
    assert "No command was executed by llm preview." in output


def test_llm_route_preview_shows_valid_contract_result(monkeypatch, capsys) -> None:
    result = build_result(
        "ok",
        {
            "schema_version": "llm_contract_v0",
            "proposed_intent": "performance_diagnostic",
            "interpreted_request": "why is my laptop slow",
            "confidence": 0.88,
            "reasoning_summary": "The user described slowness.",
            "safety_notes": ["Read-only diagnostic route."],
        },
    )

    calls: list[str] = []

    def fake_call(user_request: str, *, model_callable=None) -> LLMRouteCallResult:
        calls.append(user_request)
        return result

    monkeypatch.setattr(cli, "build_llm_route_call", fake_call)

    cli.print_llm_route_preview_report("my laptop is slow")

    output = capsys.readouterr().out

    assert calls == ["my laptop is slow"]
    assert "LIGHTHOUSE LLM ROUTE PREVIEW" in output
    assert "Status: ok" in output
    assert "Contract valid: yes" in output
    assert "Proposed intent: performance_diagnostic" in output
    assert "Interpreted request: why is my laptop slow" in output
    assert "Recommended command: runplan why is my laptop slow" in output
    assert "Autorun allowed: yes" in output
    assert "No command was executed by llm preview." in output


def test_llm_route_preview_shows_invalid_contract_result(monkeypatch, capsys) -> None:
    result = build_result(
        "invalid",
        {
            "schema_version": "llm_contract_v0",
            "proposed_intent": "performance_diagnostic",
            "interpreted_request": "why is my laptop slow",
            "confidence": 0.88,
            "tool_name": "unsafe_tool",
            "approved": True,
        },
    )

    monkeypatch.setattr(
        cli,
        "build_llm_route_call",
        lambda user_request, *, model_callable=None: result,
    )

    cli.print_llm_route_preview_report("my laptop is slow")

    output = capsys.readouterr().out

    assert "Status: invalid" in output
    assert "Contract valid: no" in output
    assert "Contract errors:" in output
    assert "forbidden authority field" in output
    assert "No command was executed by llm preview." in output


def test_llm_route_preview_shows_disabled_model_result(monkeypatch, capsys) -> None:
    result = LLMRouteCallResult(
        status="disabled",
        message="LLM route proposal was not attempted.",
        model_used="qwen2.5:3b",
        prompt="prompt text",
        raw_model_output=None,
        validation=None,
        used_model=False,
    )

    monkeypatch.setattr(
        cli,
        "build_llm_route_call",
        lambda user_request, *, model_callable=None: result,
    )

    cli.print_llm_route_preview_report("my laptop is slow")

    output = capsys.readouterr().out

    assert "Status: disabled" in output
    assert "Used model: no" in output
    assert "Contract validation: not_available" in output
    assert "No command was executed by llm preview." in output


def test_run_canonical_command_handles_llm_preview(monkeypatch, capsys) -> None:
    calls: list[str] = []

    def fake_preview(user_request: str) -> None:
        calls.append(user_request)
        print(f"LLM PREVIEW CALLED: {user_request}")

    monkeypatch.setattr(cli, "print_llm_route_preview_report", fake_preview)

    result = cli.run_canonical_command("llm preview my laptop is slow")

    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == ["my laptop is slow"]
    assert "LLM PREVIEW CALLED: my laptop is slow" in output


def test_run_canonical_command_handles_empty_llm_preview(monkeypatch, capsys) -> None:
    calls: list[str] = []

    def fake_preview(user_request: str) -> None:
        calls.append(user_request)
        print("EMPTY LLM PREVIEW CALLED")

    monkeypatch.setattr(cli, "print_llm_route_preview_report", fake_preview)

    result = cli.run_canonical_command("llm preview")

    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == [""]
    assert "EMPTY LLM PREVIEW CALLED" in output
