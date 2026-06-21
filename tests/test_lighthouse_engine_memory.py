"""
Tests for Lighthouse Engine memory-context integration.

The engine should attach read-only memory context without changing the existing
safety boundary.
"""

from types import SimpleNamespace
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services import lighthouse_engine
from app.services.engine_memory_context import (
    ENGINE_MEMORY_STATUS_DISABLED,
    ENGINE_MEMORY_STATUS_OK,
)
from app.services.memory_cases import (
    CASE_CONFIDENCE_HIGH,
    CASE_SOURCE_OPERATOR_CONFIRMED,
)
from app.services.memory_manager import build_case_memory
from app.services.memory_store import (
    append_case_memory,
    write_baselines,
    write_knowledge_index,
    write_operator_preferences,
)


def build_chrome_case() -> dict:
    """
    Build a valid structured Chrome memory-pressure case.

    This uses the current V1 memory contract. The engine memory context path
    should only receive validated structured cases converted into recall-safe
    cards.
    """
    return build_case_memory(
        case_id="case_chrome_memory",
        problem="Laptop felt slow",
        symptoms=["slow response", "high memory pressure"],
        suspected_cause="Chrome memory pressure",
        lesson=(
            "Chrome high memory usage has previously matched this slowdown "
            "pattern."
        ),
        tags=["chrome", "memory", "slowdown"],
        telemetry_evidence={
            "cpu_usage_percent": 6,
            "memory_usage_percent": 82,
            "disk_usage_percent": 11,
            "top_process_name": "chrome.exe",
            "top_process_memory_mb": 3200,
        },
        event_evidence={
            "critical_events": 0,
            "warning_events": 0,
            "context_events": 2,
        },
        action_taken="Operator reviewed Chrome memory usage",
        outcome="Laptop responsiveness improved",
        diagnostic_steps=[
            "Collected telemetry snapshot",
            "Checked memory pressure",
            "Listed top memory processes",
        ],
        decision_notes=[
            "CPU was low, so CPU pressure was unlikely.",
            "Memory was elevated and Chrome was the highest memory process.",
        ],
        operator_feedback="The review matched the user-visible slowdown.",
        confidence=CASE_CONFIDENCE_HIGH,
        source=CASE_SOURCE_OPERATOR_CONFIRMED,
        created_at="2026-06-14T12:30:00+00:00",
        updated_at="2026-06-14T12:40:00+00:00",
    )


def seed_memory(memory_dir: Path) -> None:
    """
    Seed test memory data.
    """
    write_baselines(
        {
            "memory": {
                "normal_idle_percent_min": 30,
                "normal_idle_percent_max": 40,
            }
        },
        memory_dir=memory_dir,
    )

    write_operator_preferences(
        {
            "communication": {
                "style": "plain_english",
            }
        },
        memory_dir=memory_dir,
    )

    append_case_memory(
        build_chrome_case(),
        memory_dir=memory_dir,
    )

    write_knowledge_index(
        {
            "schema_version": 1,
            "entries": [
                {
                    "id": "windows_memory_pressure",
                    "title": "Windows memory pressure troubleshooting",
                    "summary": "High memory usage can make Windows feel slow.",
                    "tags": ["windows", "memory", "slowdown"],
                }
            ],
        },
        memory_dir=memory_dir,
    )


def build_fake_execution_result(user_request: str) -> SimpleNamespace:
    """
    Build a minimal execution result compatible with Lighthouse Engine tests.
    """
    return SimpleNamespace(
        user_request=user_request,
        status="ok",
        plan_status="ok",
        intent="slow_laptop_diagnostics",
        message="Fake read-only execution completed.",
        executed_tools=(),
        refused_tools=(),
        blocked_tools=(),
        safe_alternatives=(),
    )


def test_engine_attaches_memory_context(tmp_path, monkeypatch) -> None:
    """
    Engine results should include read-only memory context when enabled.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    monkeypatch.setattr(
        lighthouse_engine,
        "execute_tools_for_request",
        lambda request: build_fake_execution_result(request),
    )
    monkeypatch.setattr(
        lighthouse_engine,
        "record_plan_execution",
        lambda execution_result: SimpleNamespace(
            status="ok",
            message="Journaled.",
            path="fake_journal.jsonl",
        ),
    )

    result = lighthouse_engine.run_lighthouse_engine(
        "chrome memory",
        memory_dir=memory_dir,
    )

    assert result.status == "ok"
    assert result.memory_context is not None
    assert result.memory_context.status == ENGINE_MEMORY_STATUS_OK
    assert "LIGHTHOUSE MEMORY CONTEXT" in result.memory_context.context_text
    assert "case_chrome_memory" in result.memory_context.context_text
    assert "windows_memory_pressure" in result.memory_context.context_text
    assert result.errors == ()


def test_engine_memory_context_is_recall_safe(tmp_path, monkeypatch) -> None:
    """
    Engine memory context should not expose audit/process internals from cases.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    monkeypatch.setattr(
        lighthouse_engine,
        "execute_tools_for_request",
        lambda request: build_fake_execution_result(request),
    )
    monkeypatch.setattr(
        lighthouse_engine,
        "record_plan_execution",
        lambda execution_result: SimpleNamespace(
            status="ok",
            message="Journaled.",
            path="fake_journal.jsonl",
        ),
    )

    result = lighthouse_engine.run_lighthouse_engine(
        "chrome memory",
        memory_dir=memory_dir,
    )

    assert result.memory_context is not None
    assert "process_trace" not in result.memory_context.context_text
    assert "memory_usage_trace" not in result.memory_context.context_text
    assert "diagnostic_steps" not in result.memory_context.context_text
    assert "decision_notes" not in result.memory_context.context_text


def test_engine_can_disable_memory_context(tmp_path, monkeypatch) -> None:
    """
    Engine memory context should be explicitly disableable.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    monkeypatch.setattr(
        lighthouse_engine,
        "execute_tools_for_request",
        lambda request: build_fake_execution_result(request),
    )
    monkeypatch.setattr(
        lighthouse_engine,
        "record_plan_execution",
        lambda execution_result: SimpleNamespace(
            status="ok",
            message="Journaled.",
            path="fake_journal.jsonl",
        ),
    )

    result = lighthouse_engine.run_lighthouse_engine(
        "chrome memory",
        include_memory_context=False,
        memory_dir=memory_dir,
    )

    assert result.status == "ok"
    assert result.memory_context is not None
    assert result.memory_context.status == ENGINE_MEMORY_STATUS_DISABLED
    assert result.memory_context.enabled is False
    assert result.memory_context.context_text == ""


def test_engine_result_to_dict_includes_memory_context(tmp_path, monkeypatch) -> None:
    """
    Engine result serialization should include memory_context.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    monkeypatch.setattr(
        lighthouse_engine,
        "execute_tools_for_request",
        lambda request: build_fake_execution_result(request),
    )
    monkeypatch.setattr(
        lighthouse_engine,
        "record_plan_execution",
        lambda execution_result: SimpleNamespace(
            status="ok",
            message="Journaled.",
            path="fake_journal.jsonl",
        ),
    )

    result = lighthouse_engine.run_lighthouse_engine(
        "chrome memory",
        memory_dir=memory_dir,
    )
    payload = result.to_dict()

    assert payload["status"] == "ok"
    assert payload["memory_context"] is not None
    assert payload["memory_context"]["status"] == ENGINE_MEMORY_STATUS_OK
    assert "LIGHTHOUSE MEMORY CONTEXT" in payload["memory_context"]["context_text"]


def test_engine_empty_request_does_not_build_memory_context() -> None:
    """
    Empty requests should still stop before memory retrieval.
    """
    result = lighthouse_engine.run_lighthouse_engine("   ")

    assert result.status == "needs_clarification"
    assert result.memory_context is None
    assert result.execution_result is None
    assert result.confirmation_previews == ()