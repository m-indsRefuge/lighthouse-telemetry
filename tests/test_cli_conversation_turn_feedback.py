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


def test_turn_feedbacks_command_prints_recent_feedback(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "format_turn_feedback_report",
        lambda limit=10: "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK\nShown: 1",
    )

    result = cli.run_canonical_command("turn feedbacks")
    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK" in output
    assert "Shown: 1" in output


def test_turn_feedback_journal_alias_prints_recent_feedback(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "format_turn_feedback_report",
        lambda limit=10: "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK JOURNAL",
    )

    result = cli.run_canonical_command("turn feedback journal")
    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK JOURNAL" in output


def test_conversation_turn_feedbacks_alias_prints_recent_feedback(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "format_turn_feedback_report",
        lambda limit=10: "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK",
    )

    result = cli.run_canonical_command("conversation turn feedbacks")
    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK" in output

def test_turn_feedback_latest_command_records_feedback_for_latest_turn(
    monkeypatch,
    capsys,
) -> None:
    calls = {}

    monkeypatch.setattr(
        cli,
        "read_conversational_engine_turns",
        lambda limit=1: [{"turn_id": "turn-latest"}],
    )

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
                "feedback_id": "turnfb-latest",
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
        "turn feedback latest useful routed correctly"
    )
    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == {
        "turn_id": "turn-latest",
        "label": "useful",
        "note": "routed correctly",
    }
    assert "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK" in output


def test_turn_feedback_latest_command_handles_missing_turns(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        cli,
        "read_conversational_engine_turns",
        lambda limit=1: [],
    )

    result = cli.run_canonical_command("turn feedback latest useful checked")
    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK" in output
    assert "Status: invalid" in output
    assert "No conversational engine turns recorded yet." in output
    assert "Saved: no" in output


def test_turn_feedback_literal_placeholder_is_rejected(
    monkeypatch,
    capsys,
) -> None:
    def fail_record(*, turn_id: str, label: str, note: str = ""):
        raise AssertionError("record_turn_feedback should not be called")

    monkeypatch.setattr(cli, "record_turn_feedback", fail_record)

    result = cli.run_canonical_command(
        "turn feedback <turn_id> useful routed correctly"
    )
    output = capsys.readouterr().out

    assert result == "handled"
    assert "Usage: turn feedback <turn_id> <label> [note]" in output
    assert "Do not include angle brackets." in output
    assert "turn feedback latest <label> [note]" in output

def test_turn_feedback_command_surfaces_unknown_turn_response(monkeypatch, capsys) -> None:
    def fake_record(*, turn_id: str, label: str, note: str = ""):
        return {
            "status": "invalid",
            "message": "Conversational turn ID was not found.",
            "data": {
                "saved": False,
                "turn_id": turn_id,
                "label": label,
            },
            "errors": [
                "Unknown conversational turn id. Run 'turns' to copy a real turn id, "
                "or use 'turn feedback latest <label> [note]'."
            ],
            "warnings": [],
        }

    monkeypatch.setattr(cli, "record_turn_feedback", fake_record)

    result = cli.run_canonical_command(
        "turn feedback turn-missing useful routed correctly"
    )
    output = capsys.readouterr().out

    assert result == "handled"
    assert "Status: invalid" in output
    assert "Conversational turn ID was not found." in output
    assert "Saved: no" in output
    assert "turn feedback latest" in output
