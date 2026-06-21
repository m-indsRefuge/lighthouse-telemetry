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
from app.services.memory_cases import (
    CASE_CONFIDENCE_HIGH,
    CASE_SOURCE_OPERATOR_CONFIRMED,
    MEMORY_INFLUENCE_SUPPORTING_EVIDENCE,
    MEMORY_RESULT_HELPFUL,
    build_memory_usage_trace,
)
from app.services.memory_manager import build_case_memory
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


def build_chrome_case() -> dict:
    """
    Build a valid structured Chrome memory-pressure case.
    """
    return build_case_memory(
        case_id="case_chrome_memory",
        problem="Laptop felt slow",
        symptoms=["slow response", "high memory pressure"],
        suspected_cause="Chrome memory pressure",
        lesson="Chrome high memory usage has previously caused slowdown on this machine.",
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
        action_taken="Operator closed unused Chrome tabs",
        outcome="Laptop became more responsive",
        diagnostic_steps=[
            "Collected telemetry snapshot",
            "Checked memory pressure",
            "Listed top memory processes",
        ],
        decision_notes=[
            "CPU was low, so CPU pressure was unlikely.",
            "Memory was elevated and Chrome was the highest memory process.",
        ],
        operator_feedback="Closing tabs improved responsiveness.",
        confidence=CASE_CONFIDENCE_HIGH,
        source=CASE_SOURCE_OPERATOR_CONFIRMED,
        created_at="2026-06-14T12:30:00+00:00",
        updated_at="2026-06-14T12:40:00+00:00",
        memory_usage_trace=build_memory_usage_trace(
            memory_context_used=True,
            retrieved_case_ids=["case_chrome_memory_000"],
            retrieved_knowledge_ids=["windows_memory_pressure"],
            retrieved_baseline_keys=["memory.normal_idle_percent_max"],
            memory_influence=MEMORY_INFLUENCE_SUPPORTING_EVIDENCE,
            memory_result=MEMORY_RESULT_HELPFUL,
            memory_relevance_score=0.82,
            memory_notes=["Previous Chrome memory case matched the current issue."],
        ),
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

    append_case_memory(build_chrome_case(), memory_dir=memory_dir)

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
    Seeded structured memory should produce useful engine memory context.
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
    assert "Laptop felt slow" in context.context_text
    assert "windows_memory_pressure" in context.context_text
    assert context.errors == ()


def test_engine_memory_context_excludes_process_trace(tmp_path) -> None:
    """
    Engine memory context must not expose process_trace internals.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    context = build_engine_memory_context(
        "chrome memory",
        memory_dir=memory_dir,
    )

    assert "process_trace" not in context.context_text
    assert "diagnostic_steps" not in context.context_text
    assert "Collected telemetry snapshot" not in context.context_text


def test_engine_memory_context_excludes_memory_usage_trace(tmp_path) -> None:
    """
    Engine memory context must not expose memory_usage_trace internals.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    context = build_engine_memory_context(
        "chrome memory",
        memory_dir=memory_dir,
    )

    assert "memory_usage_trace" not in context.context_text
    assert "retrieved_case_ids" not in context.context_text
    assert "Previous Chrome memory case matched" not in context.context_text


def test_build_engine_memory_context_skips_invalid_cases(tmp_path) -> None:
    """
    Invalid case memories should be skipped before reaching engine context.
    """
    memory_dir = tmp_path / "memory"
    valid_case = build_chrome_case()
    invalid_case = build_chrome_case()
    invalid_case["case_id"] = "case_invalid"
    invalid_case["case_card"]["tags"] = []

    append_case_memory(valid_case, memory_dir=memory_dir)
    append_case_memory(invalid_case, memory_dir=memory_dir)

    context = build_engine_memory_context(
        "chrome memory",
        memory_dir=memory_dir,
    )

    assert context.status == ENGINE_MEMORY_STATUS_OK
    assert "case_chrome_memory" in context.context_text
    assert "case_invalid" not in context.context_text
    assert context.summary is not None
    assert context.summary.source_status["cases"]["invalid_case_count"] == 1
    assert context.warnings == ("Skipped 1 invalid case memory record(s).",)


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
