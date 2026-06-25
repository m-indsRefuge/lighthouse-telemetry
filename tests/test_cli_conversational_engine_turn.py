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
