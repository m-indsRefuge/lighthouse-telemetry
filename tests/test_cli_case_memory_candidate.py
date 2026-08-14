"""CLI routing tests for the Lighthouse C01 case-candidate preview."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))


from app import cli


def test_case_preview_command_routes_the_exact_turn_id(monkeypatch, capsys) -> None:
    """Catches a CLI route that drops or substitutes the requested turn identity."""
    calls: list[str] = []

    def fake_preview(turn_id: str):
        calls.append(turn_id)
        return object()

    monkeypatch.setattr(
        cli,
        "preview_case_memory_candidate",
        fake_preview,
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "format_case_memory_candidate_preview_report",
        lambda result: "LIGHTHOUSE CASE CANDIDATE PREVIEW\nNo case memory was written.",
        raising=False,
    )

    result = cli.run_canonical_command("case preview turn-example")
    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == ["turn-example"]
    assert "LIGHTHOUSE CASE CANDIDATE PREVIEW" in output
    assert "No case memory was written." in output


def test_case_preview_requires_a_turn_id(monkeypatch, capsys) -> None:
    """Catches a missing-id command that accidentally previews the latest turn."""

    def fail_if_called(turn_id: str):
        raise AssertionError("case preview must not use an implicit latest turn")

    monkeypatch.setattr(
        cli,
        "preview_case_memory_candidate",
        fail_if_called,
        raising=False,
    )

    result = cli.run_canonical_command("case preview")
    output = capsys.readouterr().out

    assert result == "handled"
    assert "Usage: case preview <turn_id>" in output


def test_case_preview_surfaces_a_safe_missing_turn_report(monkeypatch, capsys) -> None:
    """Catches a missing source that is hidden or routed into another CLI command."""
    calls: list[str] = []

    def fake_preview(turn_id: str):
        calls.append(turn_id)
        return object()

    monkeypatch.setattr(
        cli,
        "preview_case_memory_candidate",
        fake_preview,
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "format_case_memory_candidate_preview_report",
        lambda result: (
            "LIGHTHOUSE CASE CANDIDATE PREVIEW\n"
            "Status: not_found\n"
            "No case memory was written.\n"
            "No tool was executed.\n"
            "No model was called."
        ),
        raising=False,
    )

    result = cli.run_canonical_command("case preview turn-missing")
    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == ["turn-missing"]
    assert "Status: not_found" in output
    assert "No case memory was written." in output
    assert "No tool was executed." in output
    assert "No model was called." in output
