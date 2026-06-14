"""
Tests for Lighthouse Engine v1.

The engine is the first unified orchestration layer. It coordinates planning,
safe read-only execution, target resolution, confirmation preview generation,
and journaling.

It does not execute OS-changing tools.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.confirmation_gate import (
    CONFIRMATION_STATUS_NEEDS_TARGET,
    CONFIRMATION_STATUS_REQUIRED,
)
from app.services.lighthouse_engine import (
    ENGINE_EXECUTION_STATUS_NOT_RUN,
    ENGINE_STATUS_NEEDS_CLARIFICATION,
    ENGINE_STATUS_OK,
    build_confirmation_previews,
    run_lighthouse_engine,
)


def make_journal_result(message: str = "Journal entry recorded."):
    """
    Build a small fake journal result for engine tests.
    """
    return SimpleNamespace(
        status="ok",
        message=message,
        path="data/journal/lighthouse_actions.jsonl",
    )


def test_engine_returns_needs_clarification_for_empty_request() -> None:
    """
    Empty Operator requests should not run execution or journaling.
    """
    result = run_lighthouse_engine("   ")

    assert result.status == ENGINE_STATUS_NEEDS_CLARIFICATION
    assert result.execution_status == ENGINE_EXECUTION_STATUS_NOT_RUN
    assert result.plan_status == "needs_clarification"
    assert result.intent == "unknown"
    assert result.execution_result is None
    assert result.confirmation_previews == ()
    assert result.plan_journal_result is None
    assert result.errors == ()


def test_engine_runs_safe_read_only_plan_without_confirmation_preview(monkeypatch) -> None:
    """
    Safe read-only plans should be executed and journaled without confirmation
    preview records.
    """
    fake_execution_result = SimpleNamespace(
        user_request="please optimize RAM usage",
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
        assert user_request == "please optimize RAM usage"
        return fake_execution_result

    def fake_record_plan_execution(execution_result):
        assert execution_result is fake_execution_result
        return make_journal_result("Plan journal entry recorded.")

    def fake_record_target_confirmation_preview(**kwargs):
        raise AssertionError("Confirmation preview journal should not be called.")

    monkeypatch.setattr(
        "app.services.lighthouse_engine.execute_tools_for_request",
        fake_execute_tools_for_request,
    )
    monkeypatch.setattr(
        "app.services.lighthouse_engine.record_plan_execution",
        fake_record_plan_execution,
    )
    monkeypatch.setattr(
        "app.services.lighthouse_engine.record_target_confirmation_preview",
        fake_record_target_confirmation_preview,
    )

    result = run_lighthouse_engine("please optimize RAM usage")

    assert result.status == ENGINE_STATUS_OK
    assert result.execution_status == "ok"
    assert result.plan_status == "ok"
    assert result.intent == "slow_laptop_diagnostics"
    assert result.execution_result is fake_execution_result
    assert result.confirmation_previews == ()
    assert result.plan_journal_result.status == "ok"
    assert result.errors == ()


def test_engine_builds_target_aware_confirmation_preview(monkeypatch) -> None:
    """
    Confirmation-required plans should produce a target-aware confirmation
    preview and record that preview in the confirmation journal.
    """
    refused_tool = SimpleNamespace(tool_name="close_selected_process")
    fake_execution_result = SimpleNamespace(
        user_request="close Chrome because it is using memory",
        status="refused",
        plan_status="needs_confirmation",
        intent="close_process_request",
        message=(
            "This request requires explicit Operator confirmation. "
            "The read-only executor cannot run confirmation-gated actions."
        ),
        executed_tools=(),
        refused_tools=(refused_tool,),
        blocked_tools=(),
        safe_alternatives=("collect_snapshot", "list_top_processes"),
    )

    preview_journal_calls = []

    def fake_execute_tools_for_request(user_request: str):
        assert user_request == "close Chrome because it is using memory"
        return fake_execution_result

    def fake_record_plan_execution(execution_result):
        assert execution_result is fake_execution_result
        return make_journal_result("Plan journal entry recorded.")

    def fake_record_target_confirmation_preview(**kwargs):
        preview_journal_calls.append(kwargs)
        return make_journal_result("Confirmation preview journal entry recorded.")

    monkeypatch.setattr(
        "app.services.lighthouse_engine.execute_tools_for_request",
        fake_execute_tools_for_request,
    )
    monkeypatch.setattr(
        "app.services.lighthouse_engine.record_plan_execution",
        fake_record_plan_execution,
    )
    monkeypatch.setattr(
        "app.services.lighthouse_engine.record_target_confirmation_preview",
        fake_record_target_confirmation_preview,
    )

    result = run_lighthouse_engine("close Chrome because it is using memory")

    assert result.status == ENGINE_STATUS_OK
    assert result.execution_status == "refused"
    assert result.plan_status == "needs_confirmation"
    assert result.intent == "close_process_request"
    assert result.plan_journal_result.status == "ok"
    assert result.errors == ()

    assert len(result.confirmation_previews) == 1

    preview = result.confirmation_previews[0]

    assert preview.tool_name == "close_selected_process"
    assert preview.target_resolution.status == "candidate_found"
    assert preview.target_resolution.target == "chrome.exe"
    assert preview.target_resolution.display_name == "Google Chrome"

    assert preview.confirmation_request.status == CONFIRMATION_STATUS_REQUIRED
    assert preview.confirmation_request.target == "chrome.exe"
    assert preview.confirmation_request.required_phrase == (
        "CONFIRM CLOSE SELECTED PROCESS"
    )
    assert preview.confirmation_request.executable_after_confirmation is True

    assert preview.journal_result.status == "ok"

    assert len(preview_journal_calls) == 1
    assert preview_journal_calls[0]["user_request"] == (
        "close Chrome because it is using memory"
    )
    assert preview_journal_calls[0]["tool_name"] == "close_selected_process"


def test_engine_builds_needs_target_preview_for_ambiguous_browser(monkeypatch) -> None:
    """
    Ambiguous target requests should produce a confirmation preview, but no
    confirmable target should be passed to the confirmation gate.
    """
    refused_tool = SimpleNamespace(tool_name="close_selected_process")
    fake_execution_result = SimpleNamespace(
        user_request="close the browser",
        status="refused",
        plan_status="needs_confirmation",
        intent="close_process_request",
        message="This request requires explicit Operator confirmation.",
        executed_tools=(),
        refused_tools=(refused_tool,),
        blocked_tools=(),
        safe_alternatives=("collect_snapshot", "list_top_processes"),
    )

    def fake_record_plan_execution(execution_result):
        assert execution_result is fake_execution_result
        return make_journal_result("Plan journal entry recorded.")

    def fake_record_target_confirmation_preview(**kwargs):
        return make_journal_result("Confirmation preview journal entry recorded.")

    monkeypatch.setattr(
        "app.services.lighthouse_engine.execute_tools_for_request",
        lambda user_request: fake_execution_result,
    )
    monkeypatch.setattr(
        "app.services.lighthouse_engine.record_plan_execution",
        fake_record_plan_execution,
    )
    monkeypatch.setattr(
        "app.services.lighthouse_engine.record_target_confirmation_preview",
        fake_record_target_confirmation_preview,
    )

    result = run_lighthouse_engine("close the browser")

    assert result.status == ENGINE_STATUS_OK
    assert result.execution_status == "refused"
    assert result.plan_status == "needs_confirmation"

    assert len(result.confirmation_previews) == 1

    preview = result.confirmation_previews[0]

    assert preview.target_resolution.status == "ambiguous_target"
    assert preview.target_resolution.target is None
    assert len(preview.target_resolution.candidates) >= 2

    assert preview.confirmation_request.status == CONFIRMATION_STATUS_NEEDS_TARGET
    assert preview.confirmation_request.target is None
    assert preview.confirmation_request.required_phrase is None
    assert preview.confirmation_request.executable_after_confirmation is False


def test_build_confirmation_previews_returns_empty_for_non_confirmation_plan() -> None:
    """
    Non-confirmation plans should not produce confirmation previews.
    """
    fake_execution_result = SimpleNamespace(
        user_request="please optimize RAM usage",
        status="ok",
        plan_status="ok",
        intent="slow_laptop_diagnostics",
        message="Safe read-only tools executed.",
        executed_tools=(),
        refused_tools=(),
        blocked_tools=(),
        safe_alternatives=(),
    )

    previews = build_confirmation_previews(fake_execution_result)

    assert previews == ()


def test_engine_result_to_dict_contains_unified_shape(monkeypatch) -> None:
    """
    The engine should expose a serializable unified result shape.
    """
    refused_tool = SimpleNamespace(tool_name="close_selected_process")
    fake_execution_result = SimpleNamespace(
        user_request="close Chrome because it is using memory",
        status="refused",
        plan_status="needs_confirmation",
        intent="close_process_request",
        message="This request requires explicit Operator confirmation.",
        executed_tools=(),
        refused_tools=(refused_tool,),
        blocked_tools=(),
        safe_alternatives=("collect_snapshot", "list_top_processes"),
    )

    monkeypatch.setattr(
        "app.services.lighthouse_engine.execute_tools_for_request",
        lambda user_request: fake_execution_result,
    )
    monkeypatch.setattr(
        "app.services.lighthouse_engine.record_plan_execution",
        lambda execution_result: make_journal_result("Plan journal entry recorded."),
    )
    monkeypatch.setattr(
        "app.services.lighthouse_engine.record_target_confirmation_preview",
        lambda **kwargs: make_journal_result(
            "Confirmation preview journal entry recorded."
        ),
    )

    result = run_lighthouse_engine("close Chrome because it is using memory")
    payload = result.to_dict()

    assert payload["status"] == ENGINE_STATUS_OK
    assert payload["execution_status"] == "refused"
    assert payload["plan_status"] == "needs_confirmation"
    assert payload["intent"] == "close_process_request"
    assert payload["plan_journal_result"]["status"] == "ok"
    assert payload["errors"] == []

    assert len(payload["confirmation_previews"]) == 1

    preview = payload["confirmation_previews"][0]

    assert preview["tool_name"] == "close_selected_process"
    assert preview["target_resolution"]["target"] == "chrome.exe"
    assert preview["confirmation_request"]["status"] == CONFIRMATION_STATUS_REQUIRED
    assert preview["confirmation_request"]["target"] == "chrome.exe"
    assert preview["journal_result"]["status"] == "ok"