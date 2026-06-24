"""
Tests for Lighthouse CLI LLM preview feedback wiring.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import cli


def test_print_llm_preview_feedback_labels_report(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "format_preview_feedback_labels_report",
        lambda: "PREVIEW FEEDBACK LABELS",
    )

    cli.print_llm_preview_feedback_labels_report()

    output = capsys.readouterr().out

    assert "PREVIEW FEEDBACK LABELS" in output


def test_print_llm_preview_feedback_report(monkeypatch, capsys) -> None:
    def fake_record(preview_id: str, label: str, note: str = "") -> dict:
        return {
            "status": "ok",
            "message": "LLM preview feedback recorded.",
            "data": {
                "saved": True,
                "preview_id": preview_id,
                "feedback_id": "llmprevfb-test",
                "label": label,
            },
            "errors": [],
            "warnings": [],
        }

    monkeypatch.setattr(cli, "record_llm_preview_feedback", fake_record)

    cli.print_llm_preview_feedback_report(
        preview_id="llmprev-test",
        label="useful",
        note="good route",
    )

    output = capsys.readouterr().out

    assert "LIGHTHOUSE LLM PREVIEW FEEDBACK" in output
    assert "Status: ok" in output
    assert "Preview ID: llmprev-test" in output
    assert "Label: useful" in output


def test_run_canonical_command_handles_llm_preview_feedback_labels(
    monkeypatch,
    capsys,
) -> None:
    calls: list[str] = []

    def fake_report() -> None:
        calls.append("called")
        print("FEEDBACK LABELS CALLED")

    monkeypatch.setattr(cli, "print_llm_preview_feedback_labels_report", fake_report)

    result = cli.run_canonical_command("llm preview feedback labels")

    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == ["called"]
    assert "FEEDBACK LABELS CALLED" in output


def test_run_canonical_command_handles_llm_preview_feedback(
    monkeypatch,
    capsys,
) -> None:
    calls: list[tuple[str, str, str]] = []

    def fake_report(preview_id: str, label: str, note: str = "") -> None:
        calls.append((preview_id, label, note))
        print("FEEDBACK SAVE CALLED")

    monkeypatch.setattr(cli, "print_llm_preview_feedback_report", fake_report)

    result = cli.run_canonical_command(
        "llm preview feedback llmprev-123 wrong_route should stay unknown"
    )

    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == [("llmprev-123", "wrong_route", "should stay unknown")]
    assert "FEEDBACK SAVE CALLED" in output


def test_run_canonical_command_handles_llm_preview_feedback_usage(capsys) -> None:
    result = cli.run_canonical_command("llm preview feedback llmprev-123")

    output = capsys.readouterr().out

    assert result == "handled"
    assert "Usage: llm preview feedback <preview_id> <label> [note]" in output
