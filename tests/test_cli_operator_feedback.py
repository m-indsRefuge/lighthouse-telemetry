"""
Tests for Operator feedback CLI wiring.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import cli


def test_talk_prints_trace_id(monkeypatch, capsys) -> None:
    def fake_record_operator_interaction(**kwargs):
        return {
            "status": "ok",
            "data": {
                "trace_id": "optrace-test-talk",
                "saved": True,
            },
            "errors": [],
            "warnings": [],
        }

    monkeypatch.setattr(
        cli,
        "record_operator_interaction",
        fake_record_operator_interaction,
    )

    cli.print_operator_conversation_report("why is chrome eating memory")

    output = capsys.readouterr().out

    assert "Trace ID: optrace-test-talk" in output
    assert "No command was executed by talk." in output


def test_talkrun_safe_route_prints_trace_id(monkeypatch, capsys) -> None:
    def fake_record_operator_interaction(**kwargs):
        return {
            "status": "ok",
            "data": {
                "trace_id": "optrace-test-talkrun",
                "saved": True,
            },
            "errors": [],
            "warnings": [],
        }

    calls = []

    monkeypatch.setattr(
        cli,
        "record_operator_interaction",
        fake_record_operator_interaction,
    )
    monkeypatch.setattr(
        cli,
        "print_runplan_report",
        lambda request: calls.append(request),
    )

    cli.print_operator_conversation_run_report("why is chrome eating memory")

    output = capsys.readouterr().out

    assert "Trace ID: optrace-test-talkrun" in output
    assert "Status: ok" in output
    assert calls == ["why is Chrome using memory"]


def test_talkrun_refused_route_prints_trace_id(monkeypatch, capsys) -> None:
    def fake_record_operator_interaction(**kwargs):
        return {
            "status": "ok",
            "data": {
                "trace_id": "optrace-test-refused",
                "saved": True,
            },
            "errors": [],
            "warnings": [],
        }

    calls = []

    monkeypatch.setattr(
        cli,
        "record_operator_interaction",
        fake_record_operator_interaction,
    )
    monkeypatch.setattr(
        cli,
        "print_runplan_report",
        lambda request: calls.append(request),
    )

    cli.print_operator_conversation_run_report("close chrome")

    output = capsys.readouterr().out

    assert "Trace ID: optrace-test-refused" in output
    assert "Status: refused" in output
    assert calls == []


def test_run_canonical_command_handles_feedback_labels(capsys) -> None:
    result = cli.run_canonical_command("feedback labels")

    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE OPERATOR FEEDBACK LABELS" in output
    assert "useful" in output
    assert "wrong_route" in output


def test_run_canonical_command_handles_feedback_save(monkeypatch, capsys) -> None:
    def fake_record_operator_feedback(**kwargs):
        return {
            "status": "ok",
            "message": "Operator feedback recorded.",
            "data": {
                "saved": True,
                "trace_id": kwargs["trace_id"],
                "label": kwargs["label"],
                "feedback_id": "opfb-test",
            },
            "errors": [],
            "warnings": [],
        }

    monkeypatch.setattr(
        cli,
        "record_operator_feedback",
        fake_record_operator_feedback,
    )

    result = cli.run_canonical_command(
        "feedback optrace-test useful routed correctly"
    )

    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE OPERATOR FEEDBACK" in output
    assert "Status: ok" in output
    assert "Trace ID: optrace-test" in output
    assert "Label: useful" in output
    assert "Saved: yes" in output


def test_run_canonical_command_handles_feedback_usage(capsys) -> None:
    result = cli.run_canonical_command("feedback")

    output = capsys.readouterr().out

    assert result == "handled"
    assert "Usage: feedback <trace_id> <label> [note]" in output
