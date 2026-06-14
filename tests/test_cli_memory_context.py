"""
Tests for Lighthouse CLI memory-context display.

The CLI should expose compact memory-context status without dumping the full
engine/model memory block by default.
"""

from types import SimpleNamespace
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import cli


def build_fake_summary() -> SimpleNamespace:
    """
    Build a fake memory summary object for CLI output tests.
    """
    return SimpleNamespace(
        baseline_count=2,
        preference_count=1,
        case_count=1,
        knowledge_count=1,
    )


def build_fake_memory_context() -> SimpleNamespace:
    """
    Build a fake engine memory context object for CLI output tests.
    """
    return SimpleNamespace(
        status="ok",
        enabled=True,
        message="Memory context summarized successfully.",
        summary=build_fake_summary(),
        warnings=(),
        errors=(),
        context_text="LIGHTHOUSE MEMORY CONTEXT\ncase_chrome_memory",
    )


def build_fake_execution_result() -> SimpleNamespace:
    """
    Build a minimal fake execution result for runplan output tests.
    """
    return SimpleNamespace(
        executed_tools=(),
        refused_tools=(),
        blocked_tools=(),
        safe_alternatives=(),
    )


def build_fake_engine_result() -> SimpleNamespace:
    """
    Build a minimal fake engine result for runplan output tests.
    """
    return SimpleNamespace(
        user_request="chrome memory",
        status="ok",
        execution_status="ok",
        plan_status="ok",
        intent="slow_laptop_diagnostics",
        message="Fake engine result.",
        errors=(),
        memory_context=build_fake_memory_context(),
        execution_result=build_fake_execution_result(),
        confirmation_previews=(),
        plan_journal_result=None,
    )


def test_print_memory_context_summary_with_context(capsys) -> None:
    """
    CLI should print compact memory-context counts.
    """
    engine_result = build_fake_engine_result()

    cli.print_memory_context_summary(engine_result)

    output = capsys.readouterr().out

    assert "Memory context:" in output
    assert "Status: ok" in output
    assert "Enabled: yes" in output
    assert "Baselines: 2" in output
    assert "Operator preferences: 1" in output
    assert "Relevant cases: 1" in output
    assert "Knowledge entries: 1" in output
    assert "Full memory context: available to engine" in output


def test_print_memory_context_summary_without_context(capsys) -> None:
    """
    CLI should handle missing engine memory context safely.
    """
    engine_result = SimpleNamespace(memory_context=None)

    cli.print_memory_context_summary(engine_result)

    output = capsys.readouterr().out

    assert "Memory context:" in output
    assert "Status: not_available" in output
    assert "No memory context was returned" in output


def test_runplan_report_prints_memory_context(monkeypatch, capsys) -> None:
    """
    runplan should include the compact memory-context section.
    """
    monkeypatch.setattr(
        cli,
        "run_lighthouse_engine",
        lambda request: build_fake_engine_result(),
    )

    cli.print_runplan_report("chrome memory")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE RUN PLAN" in output
    assert "Memory context:" in output
    assert "Baselines: 2" in output
    assert "Operator preferences: 1" in output
    assert "Relevant cases: 1" in output
    assert "Knowledge entries: 1" in output