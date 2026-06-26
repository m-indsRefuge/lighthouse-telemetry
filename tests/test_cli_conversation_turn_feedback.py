"""
CLI tests for conversational turn feedback capture.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import cli


def test_turn_feedback_labels_command_prints_labels(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "format_turn_feedback_labels_report",
        lambda: "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK LABELS",
    )

    result = cli.run_canonical_command("turn feedback labels")
    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK LABELS" in output


def test_turn_feedback_command_records_feedback(monkeypatch, capsys) -> None:
    calls = {}

    def fake_record(*, turn_id: str, label: str, note: str = ""):
        calls["turn_id"] = turn_id
        calls["label"] = label
        calls["note"] = note
        return {
            "status": "ok",
            "message": "Conversational turn feedback recorded.",
            "data": {
                "saved": True,
                "turn_id": turn_id,
                "feedback_id": "turnfb-example",
                "label": label,
            },
            "errors": [],
            "warnings": [],
        }

    monkeypatch.setattr(cli, "record_turn_feedback", fake_record)
    monkeypatch.setattr(
        cli,
        "format_turn_feedback_result",
        lambda result: "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK",
    )

    result = cli.run_canonical_command(
        "turn feedback turn-example useful routed correctly"
    )
    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == {
        "turn_id": "turn-example",
        "label": "useful",
        "note": "routed correctly",
    }
    assert "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK" in output


def test_conversation_turn_feedback_alias_records_feedback(monkeypatch, capsys) -> None:
    calls = {}

    def fake_record(*, turn_id: str, label: str, note: str = ""):
        calls["turn_id"] = turn_id
        calls["label"] = label
        calls["note"] = note
        return {
            "status": "ok",
            "message": "Conversational turn feedback recorded.",
            "data": {"saved": True, "turn_id": turn_id, "label": label},
            "errors": [],
            "warnings": [],
        }

    monkeypatch.setattr(cli, "record_turn_feedback", fake_record)
    monkeypatch.setattr(
        cli,
        "format_turn_feedback_result",
        lambda result: "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK",
    )

    result = cli.run_canonical_command(
        "conversation turn feedback turn-example useful checked"
    )
    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == {
        "turn_id": "turn-example",
        "label": "useful",
        "note": "checked",
    }
    assert "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK" in output


def test_turn_feedback_usage_does_not_route_to_turn_preview(capsys) -> None:
    result = cli.run_canonical_command("turn feedback")
    output = capsys.readouterr().out

    assert result == "handled"
    assert "Usage: turn feedback <turn_id> <label> [note]" in output
    assert "LIGHTHOUSE CONVERSATIONAL ENGINE TURN" not in output
