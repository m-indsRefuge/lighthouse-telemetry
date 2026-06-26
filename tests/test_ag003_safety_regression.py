"""
AG-003 safety regression tests for Lighthouse.

These tests capture the follow-up hardening points from the Antigravity
validation report without changing production behavior.
"""

from pathlib import Path
import json
import sys
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import cli
from app.services.lighthouse_engine import ENGINE_STATUS_OK, run_lighthouse_engine
from app.services.llm_contract import (
    LLM_CONTRACT_SCHEMA_VERSION,
    validate_llm_route_proposal,
)


def make_journal_result(message: str = "Journal entry recorded."):
    """
    Build a small fake journal result for engine-boundary tests.
    """
    return SimpleNamespace(
        status="ok",
        message=message,
        path="data/journal/lighthouse_actions.jsonl",
    )


def test_ag003_talkrun_passes_deterministic_engine_request(monkeypatch, capsys) -> None:
    """
    talkrun should pass the deterministic engine_request into runplan, not the
    display command string.
    """
    calls: list[str] = []

    def fake_runplan(request: str) -> None:
        calls.append(request)
        print(f"RUNPLAN CALLED: {request}")

    monkeypatch.setattr(cli, "print_runplan_report", fake_runplan)

    cli.print_operator_conversation_run_report("my laptop feels weird and slow")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE TALKRUN" in output
    assert "Intent: performance_diagnostic" in output
    assert "Auto-running read-only route through Operator Autorun Gate." in output
    assert "RUNPLAN CALLED: why is my laptop slow" in output
    assert calls == ["why is my laptop slow"]
    assert calls != ["runplan why is my laptop slow"]


@pytest.mark.parametrize(
    ("request", "expected_intent"),
    [
        ("close chrome", "os_action_request"),
        ("delete files to make space", "destructive_action_request"),
    ],
)
def test_ag003_talkrun_refuses_high_risk_intents(
    request: str,
    expected_intent: str,
    monkeypatch,
    capsys,
) -> None:
    """
    talkrun must refuse the two highest-risk natural-language categories before
    they can reach runplan.
    """
    calls: list[str] = []

    monkeypatch.setattr(cli, "print_runplan_report", lambda request: calls.append(request))

    cli.print_operator_conversation_run_report(request)

    output = capsys.readouterr().out

    assert "LIGHTHOUSE TALKRUN" in output
    assert f"Intent: {expected_intent}" in output
    assert "Autorun decision:" in output
    assert "Status: refused" in output
    assert "No command was executed by talkrun." in output
    assert calls == []


def test_ag003_talkrun_whitespace_input_does_not_execute(monkeypatch, capsys) -> None:
    """
    Empty or whitespace-only talkrun input must stop at clarification and never
    call runplan.
    """
    calls: list[str] = []

    monkeypatch.setattr(cli, "print_runplan_report", lambda request: calls.append(request))

    cli.print_operator_conversation_run_report("   ")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE TALKRUN" in output
    assert "Status: needs_clarification" in output
    assert "Autorun decision:" in output
    assert "Status: refused" in output
    assert "No command was executed by talkrun." in output
    assert calls == []


def test_ag003_invalid_direct_command_contract_has_inert_handoff() -> None:
    """
    Invalid LLM contract results must not expose an autorunnable handoff.
    """
    payload = {
        "schema_version": LLM_CONTRACT_SCHEMA_VERSION,
        "proposed_intent": "direct_command",
        "interpreted_request": "windows",
        "confidence": 0.91,
    }

    result = validate_llm_route_proposal(payload)

    assert result.valid is False
    assert "LLM contract may not propose direct CLI commands." in result.errors
    assert result.route_handoff.get("autorun_allowed") is not True
    assert result.route_handoff.get("command_family") != "runplan"
    assert result.route_handoff.get("engine_request") is None


def test_ag003_engine_llm_route_contract_is_evidence_not_execution_authority(monkeypatch) -> None:
    """
    The optional engine LLM route contract may attach route evidence, but it must
    not decide what the engine executes.
    """
    execution_calls: list[str] = []
    fake_execution_result = SimpleNamespace(
        user_request="my laptop feels slow",
        status="ok",
        plan_status="ok",
        intent="slow_laptop_diagnostics",
        message="Safe read-only tools executed.",
        executed_tools=(),
        refused_tools=(),
        blocked_tools=(),
        safe_alternatives=(),
    )

    def fake_execute_tools_for_request(user_request: str):
        execution_calls.append(user_request)
        return fake_execution_result

    def fake_model(prompt: str) -> str:
        assert "my laptop feels slow" in prompt
        return json.dumps(
            {
                "schema_version": LLM_CONTRACT_SCHEMA_VERSION,
                "proposed_intent": "destructive_action_request",
                "interpreted_request": "delete files to make space",
                "confidence": 0.88,
                "reasoning_summary": "The model proposed a destructive route.",
                "safety_notes": ["This must remain manual-review only."],
            }
        )

    monkeypatch.setattr(
        "app.services.lighthouse_engine.execute_tools_for_request",
        fake_execute_tools_for_request,
    )
    monkeypatch.setattr(
        "app.services.lighthouse_engine.record_plan_execution",
        lambda execution_result: make_journal_result("Plan journal entry recorded."),
    )
    monkeypatch.setattr(
        "app.services.lighthouse_engine.record_target_confirmation_preview",
        lambda **kwargs: pytest.fail("No confirmation preview should be recorded."),
    )

    result = run_lighthouse_engine(
        "my laptop feels slow",
        include_memory_context=False,
        include_llm_route_contract=True,
        llm_route_model=fake_model,
    )

    assert result.status == ENGINE_STATUS_OK
    assert result.execution_result is fake_execution_result
    assert execution_calls == ["my laptop feels slow"]

    assert result.llm_route_contract is not None
    assert result.llm_route_contract.validation is not None
    assert result.llm_route_contract.validation.valid is True
    assert result.llm_route_contract.validation.route_handoff["intent"] == (
        "destructive_action_request"
    )
    assert result.llm_route_contract.validation.route_handoff["autorun_allowed"] is False
    assert result.llm_route_contract.validation.route_handoff[
        "manual_review_required"
    ] is True
    assert result.llm_route_contract.validation.route_handoff["engine_request"] == (
        "delete files to make space"
    )
