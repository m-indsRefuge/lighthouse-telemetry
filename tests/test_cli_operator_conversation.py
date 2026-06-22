"""
Tests for Lighthouse CLI Operator conversation bridge wiring.

The talk command should interpret natural Operator input and recommend safe
Lighthouse routes without executing the recommended command.

The talkrun command may auto-run only safe read-only diagnostic runplan routes.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import cli


def test_talk_report_for_slowness_routes_to_runplan(capsys) -> None:
    """
    talk should map slowness wording to a safe runplan route.
    """
    cli.print_operator_conversation_report("my laptop feels weird and slow")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE TALK" in output
    assert "LIGHTHOUSE OPERATOR BRIDGE" in output
    assert "Intent: performance_diagnostic" in output
    assert "Recommended command: runplan why is my laptop slow" in output
    assert "No command was executed by talk." in output
    assert "To continue, type: runplan why is my laptop slow" in output


def test_talk_report_for_chrome_memory_routes_to_process_memory_runplan(capsys) -> None:
    """
    talk should map Chrome memory wording to process/memory inspection.
    """
    cli.print_operator_conversation_report("why is chrome eating memory")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE TALK" in output
    assert "Intent: process_memory_diagnostic" in output
    assert "Recommended command: runplan why is Chrome using memory" in output
    assert "No process will be closed" in output
    assert "No command was executed by talk." in output


def test_talk_report_for_close_chrome_warns_and_recommends_runplan(capsys) -> None:
    """
    talk should not execute OS-changing requests directly.
    """
    cli.print_operator_conversation_report("close chrome")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE TALK" in output
    assert "Intent: os_action_request" in output
    assert "Recommended command: runplan close Chrome because it may be using resources" in output
    assert "OS-changing wording detected." in output
    assert "without explicit Operator confirmation" in output
    assert "No command was executed by talk." in output


def test_talk_report_for_delete_files_warns_and_recommends_runplan(capsys) -> None:
    """
    talk should route destructive wording to safe inspection only.
    """
    cli.print_operator_conversation_report("delete files to make space")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE TALK" in output
    assert "Intent: destructive_action_request" in output
    assert "Recommended command: runplan delete files to make space" in output
    assert "Destructive or data-changing wording detected." in output
    assert "No files should be deleted" in output
    assert "No command was executed by talk." in output


def test_talk_report_for_unknown_input_asks_clarification(capsys) -> None:
    """
    talk should ask clarification instead of guessing on unknown input.
    """
    cli.print_operator_conversation_report("banana window purple")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE TALK" in output
    assert "Status: needs_clarification" in output
    assert "Intent: unknown" in output
    assert "Clarifying question:" in output
    assert "Recommended command:" not in output
    assert "No command was executed by talk." in output


def test_run_canonical_command_handles_talk(capsys) -> None:
    """
    CLI canonical command routing should support talk <text>.
    """
    result = cli.run_canonical_command("talk close chrome")

    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE TALK" in output
    assert "Intent: os_action_request" in output
    assert "No command was executed by talk." in output


def test_talkrun_for_slowness_autoruns_safe_runplan(monkeypatch, capsys) -> None:
    """
    talkrun should auto-run safe read-only performance diagnostics.
    """
    calls = []

    def fake_runplan(request: str) -> None:
        calls.append(request)
        print(f"RUNPLAN CALLED: {request}")

    monkeypatch.setattr(cli, "print_runplan_report", fake_runplan)

    cli.print_operator_conversation_run_report("my laptop feels weird and slow")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE TALKRUN" in output
    assert "Intent: performance_diagnostic" in output
    assert "Autorun decision:" in output
    assert "Status: ok" in output
    assert "Auto-running read-only route through Operator Autorun Gate." in output
    assert "RUNPLAN CALLED: why is my laptop slow" in output
    assert calls == ["why is my laptop slow"]


def test_talkrun_for_chrome_memory_autoruns_safe_runplan(monkeypatch, capsys) -> None:
    """
    talkrun should auto-run safe read-only process/memory diagnostics.
    """
    calls = []

    def fake_runplan(request: str) -> None:
        calls.append(request)
        print(f"RUNPLAN CALLED: {request}")

    monkeypatch.setattr(cli, "print_runplan_report", fake_runplan)

    cli.print_operator_conversation_run_report("why is chrome eating memory")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE TALKRUN" in output
    assert "Intent: process_memory_diagnostic" in output
    assert "RUNPLAN CALLED: why is Chrome using memory" in output
    assert calls == ["why is Chrome using memory"]


def test_talkrun_refuses_close_chrome(monkeypatch, capsys) -> None:
    """
    talkrun must not auto-run OS-changing requests.
    """
    calls = []

    monkeypatch.setattr(cli, "print_runplan_report", lambda request: calls.append(request))

    cli.print_operator_conversation_run_report("close chrome")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE TALKRUN" in output
    assert "Intent: os_action_request" in output
    assert "Status: refused" in output
    assert "Only read-only diagnostic routes may be auto-run" in output
    assert "No command was executed by talkrun." in output
    assert calls == []


def test_talkrun_refuses_delete_files(monkeypatch, capsys) -> None:
    """
    talkrun must not auto-run destructive requests.
    """
    calls = []

    monkeypatch.setattr(cli, "print_runplan_report", lambda request: calls.append(request))

    cli.print_operator_conversation_run_report("delete files to make space")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE TALKRUN" in output
    assert "Intent: destructive_action_request" in output
    assert "Status: refused" in output
    assert "No command was executed by talkrun." in output
    assert calls == []


def test_talkrun_refuses_unknown_input(monkeypatch, capsys) -> None:
    """
    talkrun must not auto-run unclear requests.
    """
    calls = []

    monkeypatch.setattr(cli, "print_runplan_report", lambda request: calls.append(request))

    cli.print_operator_conversation_run_report("banana window purple")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE TALKRUN" in output
    assert "Status: needs_clarification" in output
    assert "Autorun decision:" in output
    assert "Status: refused" in output
    assert "No command was executed by talkrun." in output
    assert calls == []


def test_run_canonical_command_handles_talkrun(monkeypatch, capsys) -> None:
    """
    CLI canonical command routing should support talkrun <text>.
    """
    calls = []

    def fake_runplan(request: str) -> None:
        calls.append(request)
        print(f"RUNPLAN CALLED: {request}")

    monkeypatch.setattr(cli, "print_runplan_report", fake_runplan)

    result = cli.run_canonical_command("talkrun why is chrome eating memory")

    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE TALKRUN" in output
    assert "Intent: process_memory_diagnostic" in output
    assert "RUNPLAN CALLED: why is Chrome using memory" in output
    assert calls == ["why is Chrome using memory"]


