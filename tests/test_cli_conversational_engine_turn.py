"""
CLI tests for V1 Conversational Engine Turn V0 routing.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import cli


class FakeTurnResult:
    pass


def test_turn_command_routes_to_conversational_engine_turn(monkeypatch, capsys) -> None:
    calls = {}

    def fake_build(user_request, *, model_callable=None, memory_dir=None):
        calls["user_request"] = user_request
        return FakeTurnResult()

    def fake_format(result):
        return "\n".join(
            [
                "LIGHTHOUSE CONVERSATIONAL ENGINE TURN",
                "Mode: preview_only",
                "Execution: disabled",
                "No command was executed by this conversational turn.",
            ]
        )

    monkeypatch.setattr(cli, "build_conversational_engine_turn", fake_build)
    monkeypatch.setattr(cli, "format_conversational_engine_turn_report", fake_format)

    result = cli.run_canonical_command("turn why is my laptop slow")
    output = capsys.readouterr().out

    assert result == "handled"
    assert calls["user_request"] == "why is my laptop slow"
    assert "LIGHTHOUSE CONVERSATIONAL ENGINE TURN" in output
    assert "No command was executed" in output


def test_engine_turn_alias_routes_to_conversational_engine_turn(monkeypatch, capsys) -> None:
    calls = {}

    def fake_build(user_request, *, model_callable=None, memory_dir=None):
        calls["user_request"] = user_request
        return FakeTurnResult()

    monkeypatch.setattr(cli, "build_conversational_engine_turn", fake_build)
    monkeypatch.setattr(
        cli,
        "format_conversational_engine_turn_report",
        lambda result: "LIGHTHOUSE CONVERSATIONAL ENGINE TURN",
    )

    result = cli.run_canonical_command("engine turn why is chrome eating memory")
    output = capsys.readouterr().out

    assert result == "handled"
    assert calls["user_request"] == "why is chrome eating memory"
    assert "LIGHTHOUSE CONVERSATIONAL ENGINE TURN" in output

def test_turns_command_prints_conversational_turn_history(monkeypatch, capsys) -> None:
    called = {}

    def fake_report(*, limit=10, memory_dir=None):
        called["limit"] = limit
        return "\n".join(
            [
                "LIGHTHOUSE CONVERSATIONAL ENGINE TURNS",
                "Shown: 1",
                "turn_id: turn-example",
            ]
        )

    monkeypatch.setattr(cli, "format_conversational_engine_turns_report", fake_report)

    result = cli.run_canonical_command("turns")
    output = capsys.readouterr().out

    assert result == "handled"
    assert called["limit"] == 10
    assert "LIGHTHOUSE CONVERSATIONAL ENGINE TURNS" in output
    assert "turn_id: turn-example" in output


def test_conversation_turns_alias_prints_conversational_turn_history(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        cli,
        "format_conversational_engine_turns_report",
        lambda *, limit=10, memory_dir=None: "LIGHTHOUSE CONVERSATIONAL ENGINE TURNS",
    )

    result = cli.run_canonical_command("conversation turns")
    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE CONVERSATIONAL ENGINE TURNS" in output
