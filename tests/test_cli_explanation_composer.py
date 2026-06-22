"""
Tests for Lighthouse CLI explanation-composer wiring.

The runplan CLI output should include the deterministic human-facing explanation
without changing the engine safety boundary.
"""

from types import SimpleNamespace
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import cli


def make_tool_result(
    tool_name: str,
    *,
    status: str = "executed",
    message: str = "Fake tool result.",
) -> SimpleNamespace:
    """
    Build a fake tool execution/refusal result compatible with CLI output.
    """
    return SimpleNamespace(
        tool_name=tool_name,
        status=status,
        message=message,
        data={},
        safety_summary={"reason": "Fake safety reason."},
    )


def make_memory_summary() -> SimpleNamespace:
    """
    Build a fake memory summary object.
    """
    return SimpleNamespace(
        baseline_count=1,
        preference_count=1,
        case_count=1,
        knowledge_count=1,
    )


def make_memory_context() -> SimpleNamespace:
    """
    Build a fake engine memory context object.
    """
    return SimpleNamespace(
        status="ok",
        enabled=True,
        message="Memory context summarized successfully.",
        summary=make_memory_summary(),
        warnings=(),
        errors=(),
        context_text="LIGHTHOUSE MEMORY CONTEXT\ncase_chrome_memory",
    )


def make_plan_journal_result() -> SimpleNamespace:
    """
    Build a fake plan journal result.
    """
    return SimpleNamespace(
        status="ok",
        message="Journaled.",
        path="fake_journal.jsonl",
    )


def make_safe_engine_result() -> SimpleNamespace:
    """
    Build a fake safe read-only engine result.
    """
    execution_result = SimpleNamespace(
        user_request="why is my laptop slow",
        status="ok",
        plan_status="ok",
        intent="slow_laptop_diagnostics",
        message="Fake read-only execution completed.",
        executed_tools=(
            make_tool_result("collect_snapshot"),
            make_tool_result("list_top_processes"),
        ),
        refused_tools=(),
        blocked_tools=(),
        safe_alternatives=(),
    )

    return SimpleNamespace(
        user_request="why is my laptop slow",
        status="ok",
        execution_status="ok",
        plan_status="ok",
        intent="slow_laptop_diagnostics",
        message="Fake read-only execution completed.",
        errors=(),
        memory_context=make_memory_context(),
        execution_result=execution_result,
        confirmation_previews=(),
        plan_journal_result=make_plan_journal_result(),
    )


def make_confirmation_required_engine_result() -> SimpleNamespace:
    """
    Build a fake confirmation-required engine result.
    """
    execution_result = SimpleNamespace(
        user_request="close Chrome because it is using memory",
        status="refused",
        plan_status="needs_confirmation",
        intent="close_process_request",
        message="This request requires explicit Operator confirmation.",
        executed_tools=(),
        refused_tools=(
            make_tool_result(
                "close_selected_process",
                status="refused",
                message="Confirmation required.",
            ),
        ),
        blocked_tools=(),
        safe_alternatives=("collect_snapshot", "list_top_processes"),
    )

    return SimpleNamespace(
        user_request="close Chrome because it is using memory",
        status="ok",
        execution_status="refused",
        plan_status="needs_confirmation",
        intent="close_process_request",
        message="This request requires explicit Operator confirmation.",
        errors=(),
        memory_context=make_memory_context(),
        execution_result=execution_result,
        confirmation_previews=(),
        plan_journal_result=make_plan_journal_result(),
    )


def test_runplan_report_prints_deterministic_explanation(monkeypatch, capsys) -> None:
    """
    runplan should print the deterministic Lighthouse explanation.
    """
    monkeypatch.setattr(
        cli,
        "run_lighthouse_engine",
        lambda request: make_safe_engine_result(),
    )

    cli.print_runplan_report("why is my laptop slow")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE RUN PLAN" in output
    assert "LIGHTHOUSE EXPLANATION" in output
    assert "What I checked:" in output
    assert "What I found:" in output
    assert "What this means:" in output
    assert "Safe next step:" in output
    assert "Lighthouse ran safe read-only diagnostic tools." in output
    assert "collect_snapshot" in output
    assert "list_top_processes" in output
    assert "Memory context:" in output
    assert "Journal:" in output


def test_runplan_report_explains_confirmation_required_without_claiming_action(
    monkeypatch,
    capsys,
) -> None:
    """
    runplan should explain confirmation-required requests without claiming action.
    """
    monkeypatch.setattr(
        cli,
        "run_lighthouse_engine",
        lambda request: make_confirmation_required_engine_result(),
    )
    monkeypatch.setattr(
        cli,
        "print_confirmation_previews",
        lambda engine_result: None,
    )

    cli.print_runplan_report("close Chrome because it is using memory")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE EXPLANATION" in output
    assert "needs explicit Operator confirmation" in output
    assert "I did not close anything" in output
    assert "close_selected_process" in output
    assert "collect_snapshot" in output
    assert "list_top_processes" in output
    assert "I closed" not in output
