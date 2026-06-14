"""
Tests for Lighthouse engine memory context.

This layer prepares read-only memory context for the Lighthouse Engine.
It should not mutate memory, execute tools, or call the model.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.engine_memory_context import (
    ENGINE_MEMORY_STATUS_DISABLED,
    ENGINE_MEMORY_STATUS_EMPTY,
    ENGINE_MEMORY_STATUS_ERROR,
    ENGINE_MEMORY_STATUS_OK,
    ENGINE_MEMORY_STATUS_PARTIAL,
    build_disabled_memory_context,
    build_engine_memory_context,
    build_error_memory_context,
    build_memory_context_prompt_block,
    has_useful_memory_context,
    map_memory_summary_status,
)
from app.services.memory_store import (
    append_case_memory,
    write_baselines,
    write_knowledge_index,
    write_operator_preferences,
)
from app.services.memory_summarizer import (
    MEMORY_SUMMARY_STATUS_EMPTY,
    MEMORY_SUMMARY_STATUS_OK,
    MEMORY_SUMMARY_STATUS_PARTIAL,
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
            },
            "safety": {
                "diagnostics_before_action": True,
            },
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


def test_map_memory_summary_status() -> None:
    """
    Memory summary statuses should map to engine memory statuses.
    """
    assert map_memory_summary_status(MEMORY_SUMMARY_STATUS_OK) == (
        ENGINE_MEMORY_STATUS_OK
    )
    assert map_memory_summary_status(MEMORY_SUMMARY_STATUS_EMPTY) == (
        ENGINE_MEMORY_STATUS_EMPTY
    )
    assert map_memory_summary_status(MEMORY_SUMMARY_STATUS_PARTIAL) == (
        ENGINE_MEMORY_STATUS_PARTIAL
    )
    assert map_memory_summary_status("unknown") == ENGINE_MEMORY_STATUS_ERROR


def test_build_disabled_memory_context() -> None:
    """
    Disabled memory context should not retrieve anything.
    """
    context = build_disabled_memory_context("why is my laptop slow")

    assert context.status == ENGINE_MEMORY_STATUS_DISABLED
    assert context.enabled is False
    assert context.user_request == "why is my laptop slow"
    assert context.context_text == ""
    assert context.summary is None
    assert context.warnings == ()
    assert context.errors == ()


def test_build_error_memory_context() -> None:
    """
    Error memory context should expose a stable error shape.
    """
    context = build_error_memory_context(
        user_request="chrome memory",
        error="fake memory failure",
    )

    assert context.status == ENGINE_MEMORY_STATUS_ERROR
    assert context.enabled is True
    assert context.user_request == "chrome memory"
    assert context.context_text == ""
    assert context.summary is None
    assert context.warnings == ()
    assert context.errors == ("fake memory failure",)


def test_build_engine_memory_context_disabled_flag(tmp_path) -> None:
    """
    The enabled flag should allow memory context to be disabled.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    context = build_engine_memory_context(
        "chrome memory",
        enabled=False,
        memory_dir=memory_dir,
    )

    assert context.status == ENGINE_MEMORY_STATUS_DISABLED
    assert context.enabled is False
    assert context.summary is None
    assert context.context_text == ""
    assert context.errors == ()


def test_build_engine_memory_context_with_seeded_memory(tmp_path) -> None:
    """
    Seeded memory should produce useful engine memory context.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    context = build_engine_memory_context(
        "why is Chrome using memory",
        memory_dir=memory_dir,
    )

    assert context.status == ENGINE_MEMORY_STATUS_OK
    assert context.enabled is True
    assert context.summary is not None
    assert context.user_request == "why is Chrome using memory"
    assert "LIGHTHOUSE MEMORY CONTEXT" in context.context_text
    assert "case_chrome_memory" in context.context_text
    assert "windows_memory_pressure" in context.context_text
    assert context.errors == ()


def test_build_engine_memory_context_empty_memory(tmp_path) -> None:
    """
    Empty memory should return a stable empty context.
    """
    memory_dir = tmp_path / "memory"

    context = build_engine_memory_context(
        "unknown topic",
        memory_dir=memory_dir,
    )

    assert context.status == ENGINE_MEMORY_STATUS_EMPTY
    assert context.enabled is True
    assert context.summary is not None
    assert context.errors == ()
    assert "LIGHTHOUSE MEMORY CONTEXT" in context.context_text


def test_has_useful_memory_context_returns_true_for_seeded_memory(tmp_path) -> None:
    """
    Useful memory context should be true for ok context with text.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    context = build_engine_memory_context(
        "chrome memory",
        memory_dir=memory_dir,
    )

    assert has_useful_memory_context(context) is True


def test_has_useful_memory_context_returns_false_when_disabled() -> None:
    """
    Disabled memory context should not be considered useful.
    """
    context = build_engine_memory_context(
        "chrome memory",
        enabled=False,
    )

    assert has_useful_memory_context(context) is False


def test_has_useful_memory_context_returns_false_when_empty(tmp_path) -> None:
    """
    Empty memory context should not be considered useful for model prompting.
    """
    memory_dir = tmp_path / "memory"

    context = build_engine_memory_context(
        "unknown topic",
        memory_dir=memory_dir,
    )

    assert context.status == ENGINE_MEMORY_STATUS_EMPTY
    assert has_useful_memory_context(context) is False


def test_build_memory_context_prompt_block_with_useful_memory(tmp_path) -> None:
    """
    Prompt block should return memory context text when useful.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    context = build_engine_memory_context(
        "chrome memory",
        memory_dir=memory_dir,
    )

    prompt_block = build_memory_context_prompt_block(context)

    assert "LIGHTHOUSE MEMORY CONTEXT" in prompt_block
    assert "case_chrome_memory" in prompt_block


def test_build_memory_context_prompt_block_when_disabled() -> None:
    """
    Prompt block should explain when memory is disabled.
    """
    context = build_engine_memory_context(
        "chrome memory",
        enabled=False,
    )

    prompt_block = build_memory_context_prompt_block(context)

    assert prompt_block == "Lighthouse memory context is disabled."


def test_build_memory_context_prompt_block_when_empty(tmp_path) -> None:
    """
    Prompt block should explain when there is no useful memory.
    """
    memory_dir = tmp_path / "memory"

    context = build_engine_memory_context(
        "unknown topic",
        memory_dir=memory_dir,
    )

    prompt_block = build_memory_context_prompt_block(context)

    assert prompt_block == "No relevant Lighthouse memory context was found."


def test_engine_memory_context_to_dict_has_stable_shape(tmp_path) -> None:
    """
    Engine memory context should expose a stable serializable shape.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    context = build_engine_memory_context(
        "chrome memory",
        memory_dir=memory_dir,
    )
    payload = context.to_dict()

    assert payload["status"] == ENGINE_MEMORY_STATUS_OK
    assert payload["enabled"] is True
    assert payload["user_request"] == "chrome memory"
    assert isinstance(payload["context_text"], str)
    assert isinstance(payload["summary"], dict)
    assert payload["warnings"] == []
    assert payload["errors"] == []