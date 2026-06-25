"""
Tests for Lighthouse CLI LLM conversational preview bridge.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import cli


def test_print_llm_talk_report_uses_bridge(monkeypatch, capsys) -> None:
    calls: list[str] = []

    def fake_build(user_request: str, **kwargs):
        calls.append(user_request)
        return {"status": "ok", "user_request": user_request}

    def fake_format(result) -> str:
        return f"REPORT: {result['user_request']}"

    monkeypatch.setattr(cli, "build_llm_conversation_preview", fake_build)
    monkeypatch.setattr(cli, "format_llm_conversation_preview_report", fake_format)

    cli.print_llm_conversation_preview_report("why is chrome eating memory")

    output = capsys.readouterr().out

    assert calls == ["why is chrome eating memory"]
    assert "REPORT: why is chrome eating memory" in output


def test_run_canonical_command_handles_llm_talk(monkeypatch, capsys) -> None:
    calls: list[str] = []

    def fake_report(user_request: str) -> None:
        calls.append(user_request)
        print("LLM TALK CALLED")

    monkeypatch.setattr(cli, "print_llm_conversation_preview_report", fake_report)

    result = cli.run_canonical_command("llm talk why is chrome eating memory")

    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == ["why is chrome eating memory"]
    assert "LLM TALK CALLED" in output


def test_run_canonical_command_handles_empty_llm_talk(monkeypatch, capsys) -> None:
    calls: list[str] = []

    def fake_report(user_request: str) -> None:
        calls.append(user_request)
        print("EMPTY LLM TALK CALLED")

    monkeypatch.setattr(cli, "print_llm_conversation_preview_report", fake_report)

    result = cli.run_canonical_command("llm talk")

    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == [""]
    assert "EMPTY LLM TALK CALLED" in output


def test_llm_talk_route_precedes_generic_llm_command(monkeypatch, capsys) -> None:
    calls: list[str] = []

    def fake_report(user_request: str) -> None:
        calls.append(user_request)
        print("LLM TALK ROUTE")

    monkeypatch.setattr(cli, "print_llm_conversation_preview_report", fake_report)

    result = cli.run_canonical_command("llm talk my laptop feels slow")

    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == ["my laptop feels slow"]
    assert "LLM TALK ROUTE" in output
