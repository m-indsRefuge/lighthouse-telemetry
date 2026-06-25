"""
CLI hygiene and safety regression tests for Lighthouse V1 consolidation.
"""

from pathlib import Path
import ast
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import cli


CLI_PATH = BACKEND_PATH / "app" / "cli.py"


def test_cli_has_single_windows_evidence_report_definition() -> None:
    """
    The CLI should not shadow print_windows_evidence_report with duplicate definitions.
    """
    tree = ast.parse(CLI_PATH.read_text(encoding="utf-8"))

    definitions = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    ]

    assert definitions.count("print_windows_evidence_report") == 1


def test_llm_talk_route_remains_preview_only(monkeypatch, capsys) -> None:
    """
    llm talk should call the preview bridge and must not execute runplan.
    """
    calls: list[tuple[str, str]] = []

    def fake_llm_talk(user_request: str) -> None:
        calls.append(("llm_talk", user_request))
        print("LLM TALK PREVIEW ONLY")

    def forbidden_runplan(user_request: str) -> None:
        calls.append(("runplan", user_request))
        raise AssertionError("llm talk must not execute runplan")

    monkeypatch.setattr(cli, "print_llm_conversation_preview_report", fake_llm_talk)
    monkeypatch.setattr(cli, "print_runplan_report", forbidden_runplan)

    result = cli.run_canonical_command("llm talk why is chrome eating memory")

    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == [("llm_talk", "why is chrome eating memory")]
    assert "LLM TALK PREVIEW ONLY" in output


def test_llm_preview_route_remains_preview_only(monkeypatch, capsys) -> None:
    """
    llm preview should call the preview report and must not execute runplan.
    """
    calls: list[tuple[str, str]] = []

    def fake_llm_preview(user_request: str) -> None:
        calls.append(("llm_preview", user_request))
        print("LLM PREVIEW ONLY")

    def forbidden_runplan(user_request: str) -> None:
        calls.append(("runplan", user_request))
        raise AssertionError("llm preview must not execute runplan")

    monkeypatch.setattr(cli, "print_llm_route_preview_report", fake_llm_preview)
    monkeypatch.setattr(cli, "print_runplan_report", forbidden_runplan)

    result = cli.run_canonical_command("llm preview why is chrome eating memory")

    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == [("llm_preview", "why is chrome eating memory")]
    assert "LLM PREVIEW ONLY" in output


def test_talkrun_still_uses_autorun_gate(monkeypatch, capsys) -> None:
    """
    talkrun should continue to use its dedicated safe autorun gate path.
    """
    calls: list[str] = []

    class FakeGate:
        allowed = False
        status = "refused"
        reason = "test refusal"
        errors: tuple[str, ...] = ()
        engine_request = None

        def to_dict(self) -> dict:
            return {
                "status": self.status,
                "allowed": self.allowed,
                "reason": self.reason,
                "engine_request": self.engine_request,
                "errors": [],
                "warnings": [],
            }

    class FakeConversationResult:
        status = "ok"
        intent = "os_action_request"
        recommended_command = "runplan restart computer"
        route_handoff = {
            "route_ready": True,
            "route_known": True,
            "intent": "os_action_request",
            "recommended_command": "runplan restart computer",
        }

        def to_dict(self) -> dict:
            return {
                "status": self.status,
                "intent": self.intent,
                "original_input": "restart computer",
                "normalized_input": "restart computer",
                "interpreted_request": "restart computer",
                "recommended_command": self.recommended_command,
                "decision_trace": {},
                "route_handoff": self.route_handoff,
            }

    def fake_interpret(user_input: str) -> FakeConversationResult:
        calls.append(f"interpret:{user_input}")
        return FakeConversationResult()

    def fake_format(result: FakeConversationResult) -> str:
        return "FORMATTED TALKRUN"

    def fake_gate(handoff: dict) -> FakeGate:
        calls.append("gate")
        return FakeGate()

    def fake_record(**kwargs) -> dict:
        calls.append("record")
        return {
            "status": "ok",
            "message": "recorded",
            "data": {"trace_id": "optrace-test"},
            "errors": [],
            "warnings": [],
        }

    def forbidden_runplan(user_request: str) -> None:
        calls.append(f"runplan:{user_request}")
        raise AssertionError("refused talkrun must not execute runplan")

    monkeypatch.setattr(cli, "interpret_operator_input", fake_interpret)
    monkeypatch.setattr(cli, "format_operator_response", fake_format)
    monkeypatch.setattr(cli, "validate_route_handoff_for_autorun", fake_gate)
    monkeypatch.setattr(cli, "record_operator_interaction", fake_record)
    monkeypatch.setattr(cli, "print_runplan_report", forbidden_runplan)

    cli.print_operator_conversation_run_report("restart computer")

    output = capsys.readouterr().out

    assert calls == ["interpret:restart computer", "gate", "record"]
    assert "Status: refused" in output
    assert "No command was executed by talkrun." in output


def test_dataset_commands_still_route_to_expected_reports(monkeypatch, capsys) -> None:
    """
    Dataset commands should still dispatch to their dedicated report functions.
    """
    calls: list[str] = []

    def fake_operator_dataset() -> None:
        calls.append("operator")
        print("OPERATOR DATASET")

    def fake_llm_dataset() -> None:
        calls.append("llm")
        print("LLM DATASET")

    monkeypatch.setattr(cli, "print_operator_dataset_export_report", fake_operator_dataset)
    monkeypatch.setattr(cli, "print_llm_preview_dataset_export_report", fake_llm_dataset)

    result_operator = cli.run_canonical_command("dataset operator")
    result_llm = cli.run_canonical_command("dataset llm preview")

    output = capsys.readouterr().out

    assert result_operator == "handled"
    assert result_llm == "handled"
    assert calls == ["operator", "llm"]
    assert "OPERATOR DATASET" in output
    assert "LLM DATASET" in output
