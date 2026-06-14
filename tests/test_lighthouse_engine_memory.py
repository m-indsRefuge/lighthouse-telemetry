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
from app.services.memory_store import (
    append_case_memory,
    write_baselines,
    write_knowledge_index,
    write_operator_preferences,
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
        {
            "case_id": "case_chrome_memory",
            "summary": "Chrome caused high memory pressure and laptop slowdown.",
            "resolution": "Operator closed unused Chrome tabs.",
            "tags": ["chrome", "memory", "slowdown"],
        },
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