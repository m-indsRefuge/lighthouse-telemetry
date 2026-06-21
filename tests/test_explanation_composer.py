"""
Tests for the deterministic Lighthouse explanation composer.

The composer formats already-produced engine facts into plain-language output.
It must not call the model, execute tools, mutate the OS, or write memory.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.explanation_composer import (
    EXPLANATION_STATUS_ERROR,
    EXPLANATION_STATUS_OK,
    compose_engine_explanation,
)


def make_tool(tool_name: str) -> SimpleNamespace:
    """
    Build a fake tool result object.
    """
    return SimpleNamespace(tool_name=tool_name)


def make_memory_context(
    *,
    enabled: bool = True,
    status: str = "ok",
    context_text: str = "LIGHTHOUSE MEMORY CONTEXT\ncase_chrome_memory",
    warnings: tuple[str, ...] = (),
) -> SimpleNamespace:
    """
    Build a fake engine memory context object.
    """
    return SimpleNamespace(
        enabled=enabled,
        status=status,
        context_text=context_text,
        warnings=warnings,
    )


def make_engine_result(
    *,
    status: str = "ok",
    message: str = "Safe read-only tools executed.",
    user_request: str = "why is my laptop slow",
    execution_status: str = "ok",
    plan_status: str = "ok",
    intent: str = "slow_laptop_diagnostics",
    execution_result: SimpleNamespace | None = None,
    memory_context: SimpleNamespace | None = None,
    errors: tuple[str, ...] = (),
) -> SimpleNamespace:
    """
    Build an engine-result-like object for composer tests.
    """
    if execution_result is None and execution_status != "not_run":
        execution_result = SimpleNamespace(
            user_request=user_request,
            status=execution_status,
            plan_status=plan_status,
            intent=intent,
            message=message,
            executed_tools=(make_tool("collect_snapshot"), make_tool("list_top_processes")),
            refused_tools=(),
            blocked_tools=(),
            safe_alternatives=(),
        )

    return SimpleNamespace(
        status=status,
        message=message,
        user_request=user_request,
        execution_status=execution_status,
        plan_status=plan_status,
        intent=intent,
        execution_result=execution_result,
        confirmation_previews=(),
        plan_journal_result=None,
        memory_context=memory_context,
        errors=errors,
    )


def test_explanation_for_empty_request() -> None:
    """
    Empty or unclear engine results should produce clarification guidance.
    """
    engine_result = make_engine_result(
        status="needs_clarification",
        message="Please provide an Operator request.",
        user_request="   ",
        execution_status="not_run",
        plan_status="needs_clarification",
        intent="unknown",
        execution_result=None,
    )

    explanation = compose_engine_explanation(engine_result)

    assert explanation.status == EXPLANATION_STATUS_OK
    assert "needs clarification" in explanation.text
    assert "did not run tools" in explanation.text
    assert "Ask a more specific question" in explanation.text


def test_explanation_for_safe_read_only_plan() -> None:
    """
    Safe read-only execution should be explained without suggesting mutation.
    """
    engine_result = make_engine_result(
        user_request="why is my laptop slow",
    )

    explanation = compose_engine_explanation(engine_result)

    assert explanation.status == EXPLANATION_STATUS_OK
    assert "Lighthouse ran safe read-only diagnostic tools" in explanation.text
    assert "collect_snapshot" in explanation.text
    assert "list_top_processes" in explanation.text
    assert "Review the current health summary and top processes" in explanation.text


def test_explanation_for_confirmation_required_plan() -> None:
    """
    Confirmation-required plans should explain that no action ran.
    """
    execution_result = SimpleNamespace(
        user_request="close Chrome because it is using memory",
        status="refused",
        plan_status="needs_confirmation",
        intent="close_process_request",
        message="This request requires explicit Operator confirmation.",
        executed_tools=(),
        refused_tools=(make_tool("close_selected_process"),),
        blocked_tools=(),
        safe_alternatives=("collect_snapshot", "list_top_processes"),
    )
    engine_result = make_engine_result(
        user_request="close Chrome because it is using memory",
        execution_status="refused",
        plan_status="needs_confirmation",
        intent="close_process_request",
        execution_result=execution_result,
    )

    explanation = compose_engine_explanation(engine_result)

    assert "needs explicit Operator confirmation" in explanation.text
    assert "I did not close anything" in explanation.text
    assert "Review the target and confirmation preview" in explanation.text


def test_explanation_mentions_memory_when_available() -> None:
    """
    Useful memory context should be mentioned as supporting context only.
    """
    engine_result = make_engine_result(
        user_request="chrome memory",
        memory_context=make_memory_context(),
    )

    explanation = compose_engine_explanation(engine_result)

    assert "Lighthouse found relevant memory context" in explanation.text
    assert "Memory is supporting context only" in explanation.text


def test_explanation_does_not_claim_action_was_taken_when_executor_refused() -> None:
    """
    Refused execution must not be described as a completed OS action.
    """
    execution_result = SimpleNamespace(
        user_request="close Chrome",
        status="refused",
        plan_status="needs_confirmation",
        intent="close_process_request",
        message="This request requires explicit Operator confirmation.",
        executed_tools=(),
        refused_tools=(make_tool("close_selected_process"),),
        blocked_tools=(),
        safe_alternatives=("collect_snapshot",),
    )
    engine_result = make_engine_result(
        user_request="close Chrome",
        execution_status="refused",
        plan_status="needs_confirmation",
        intent="close_process_request",
        execution_result=execution_result,
    )

    explanation = compose_engine_explanation(engine_result)

    assert "I did not close anything" in explanation.text
    assert "I closed" not in explanation.text
    assert "Lighthouse ran safe read-only diagnostic tools" not in explanation.text


def test_explanation_handles_errors_without_crashing() -> None:
    """
    Engine errors should be carried through without crashing the composer.
    """
    engine_result = make_engine_result(
        status="error",
        message="Engine failed.",
        user_request="chrome memory",
        execution_status="not_run",
        plan_status="error",
        intent="unknown",
        execution_result=None,
        errors=("fake engine error",),
    )

    explanation = compose_engine_explanation(engine_result)

    assert explanation.status == EXPLANATION_STATUS_ERROR
    assert explanation.errors == ("fake engine error",)
    assert "reported an error" in explanation.text
    assert "engine errors" in explanation.text


def test_explanation_result_to_dict_has_stable_shape() -> None:
    """
    Explanation results should expose a stable serializable shape.
    """
    engine_result = make_engine_result(
        user_request="chrome memory",
        memory_context=make_memory_context(warnings=("memory warning",)),
    )

    explanation = compose_engine_explanation(engine_result)
    payload = explanation.to_dict()

    assert payload["status"] == EXPLANATION_STATUS_OK
    assert payload["message"] == "Explanation composed successfully."
    assert payload["user_request"] == "chrome memory"
    assert isinstance(payload["text"], str)
    assert isinstance(payload["sections"], dict)
    assert payload["warnings"] == ["memory warning"]
    assert payload["errors"] == []
