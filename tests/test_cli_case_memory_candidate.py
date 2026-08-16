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

# === C02 TASK 5: EXACT CASE APPROVAL CLI ===


def test_case_approve_routes_exact_turn_and_fingerprint(
    monkeypatch,
    capsys,
) -> None:
    calls: list[tuple[str, str]] = []

    fingerprint = "a" * 64

    monkeypatch.setattr(
        cli,
        "promote_case_memory_candidate",
        lambda turn_id, supplied_fingerprint: (
            calls.append((turn_id, supplied_fingerprint)) or object()
        ),
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "format_case_memory_promotion_result",
        lambda result: (
            "LIGHTHOUSE CASE PROMOTION\n"
            "Status: ok\n"
            "Decision: promoted"
        ),
        raising=False,
    )

    result = cli.run_canonical_command(
        f"case approve turn-example {fingerprint}"
    )
    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == [("turn-example", fingerprint)]
    assert "LIGHTHOUSE CASE PROMOTION" in output
    assert "Status: ok" in output
    assert "Decision: promoted" in output


def test_case_approve_accepts_uppercase_fingerprint_but_routes_normalized(
    monkeypatch,
    capsys,
) -> None:
    calls: list[tuple[str, str]] = []

    lowercase = "abcdef0123456789" * 4
    uppercase = lowercase.upper()

    monkeypatch.setattr(
        cli,
        "promote_case_memory_candidate",
        lambda turn_id, supplied_fingerprint: (
            calls.append((turn_id, supplied_fingerprint)) or object()
        ),
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "format_case_memory_promotion_result",
        lambda result: "LIGHTHOUSE CASE PROMOTION\nStatus: ok",
        raising=False,
    )

    result = cli.run_canonical_command(
        f"case approve turn-example {uppercase}"
    )

    capsys.readouterr()

    assert result == "handled"
    assert calls == [("turn-example", lowercase)]


def test_case_approve_requires_exact_turn_and_fingerprint(
    monkeypatch,
    capsys,
) -> None:
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        cli,
        "promote_case_memory_candidate",
        lambda turn_id, fingerprint: calls.append(
            (turn_id, fingerprint)
        ),
        raising=False,
    )

    commands = [
        "case approve",
        "case approve turn-example",
        f"case approve turn-example {'a' * 64} extra",
    ]

    for command in commands:
        result = cli.run_canonical_command(command)
        output = capsys.readouterr().out

        assert result == "handled"
        assert "Usage: case approve <turn_id> <fingerprint>" in output

    assert calls == []


def test_case_approve_rejects_malformed_fingerprint_before_promotion(
    monkeypatch,
    capsys,
) -> None:
    def fail_if_called(turn_id: str, fingerprint: str):
        raise AssertionError(
            "Malformed fingerprint must not reach promotion service."
        )

    monkeypatch.setattr(
        cli,
        "promote_case_memory_candidate",
        fail_if_called,
        raising=False,
    )

    for malformed in [
        "short",
        "g" * 64,
        "a" * 63,
        "a" * 65,
    ]:
        result = cli.run_canonical_command(
            f"case approve turn-example {malformed}"
        )
        output = capsys.readouterr().out

        assert result == "handled"
        assert "Usage: case approve <turn_id> <fingerprint>" in output


def test_case_approve_rejects_latest_shortcut(
    monkeypatch,
    capsys,
) -> None:
    def fail_if_called(turn_id: str, fingerprint: str):
        raise AssertionError(
            "case approve must never resolve an implicit latest turn."
        )

    monkeypatch.setattr(
        cli,
        "promote_case_memory_candidate",
        fail_if_called,
        raising=False,
    )

    fingerprint = "a" * 64

    result = cli.run_canonical_command(
        f"case approve latest {fingerprint}"
    )
    output = capsys.readouterr().out

    assert result == "handled"
    assert "Usage: case approve <turn_id> <fingerprint>" in output
    assert "latest" in output.lower()


def test_case_help_lists_exact_approval_command(capsys) -> None:
    result = cli.run_canonical_command("help")
    output = capsys.readouterr().out

    assert result == "handled"
    assert "case approve <turn_id> <fingerprint>" in output
