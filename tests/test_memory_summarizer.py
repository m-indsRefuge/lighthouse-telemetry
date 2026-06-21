"""
Tests for Lighthouse memory summarizer.

The memory summarizer turns retrieved memory into compact context that can later
be passed to the engine/model reasoning layer.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.memory_cases import (
    CASE_CONFIDENCE_HIGH,
    CASE_SOURCE_OPERATOR_CONFIRMED,
    MEMORY_INFLUENCE_SUPPORTING_EVIDENCE,
    MEMORY_RESULT_HELPFUL,
    build_memory_usage_trace,
    extract_case_recall_card,
)
from app.services.memory_manager import build_case_memory
from app.services.memory_summarizer import (
    MEMORY_SUMMARY_STATUS_EMPTY,
    MEMORY_SUMMARY_STATUS_OK,
    compact_text,
    flatten_dict,
    format_key_value_section,
    get_entry_identifier,
    get_entry_summary,
    get_entry_tags,
    summarize_memory_context,
    summarize_memory_for_request,
)
from app.services.memory_retriever import (
    retrieve_memory_for_request,
)
from app.services.memory_store import (
    append_case_memory,
    write_baselines,
    write_knowledge_index,
    write_operator_preferences,
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
            },
            "cpu": {
                "normal_idle_percent_max": 10,
            },
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


def test_compact_text_handles_none_bool_and_long_values() -> None:
    """
    Compact text should normalize common values safely.
    """
    assert compact_text(None) == "none"
    assert compact_text(True) == "yes"
    assert compact_text(False) == "no"
    assert compact_text("hello\nworld") == "hello world"

    long_text = "x" * 200
    compacted = compact_text(long_text, max_length=20)

    assert len(compacted) == 20
    assert compacted.endswith("...")


def test_flatten_dict_returns_dotted_keys() -> None:
    """
    Nested dictionaries should flatten into dotted key/value pairs.
    """
    flattened = flatten_dict(
        {
            "memory": {
                "normal": {
                    "min": 30,
                    "max": 40,
                }
            },
            "cpu": 10,
        }
    )

    assert ("memory.normal.min", 30) in flattened
    assert ("memory.normal.max", 40) in flattened
    assert ("cpu", 10) in flattened


def test_format_key_value_section_handles_empty_data() -> None:
    """
    Empty sections should be explicit.
    """
    lines = format_key_value_section(
        title="System baselines",
        data={},
        max_items=5,
    )

    assert lines == [
        "System baselines:",
        "- none",
    ]


def test_get_entry_identifier_prefers_known_ids() -> None:
    """
    Entry identifiers should prefer case_id, memory_id, then id.
    """
    assert get_entry_identifier({"case_id": "case_1", "id": "entry_1"}) == "case_1"
    assert get_entry_identifier({"memory_id": "mem_1", "id": "entry_1"}) == "mem_1"
    assert get_entry_identifier({"id": "entry_1"}) == "entry_1"
    assert get_entry_identifier({}) == "unknown"


def test_get_entry_summary_prefers_summary_then_title() -> None:
    """
    Generic entry summary should prefer summary over title.
    """
    assert get_entry_summary(
        {
            "summary": "Summary text",
            "title": "Title text",
        }
    ) == "Summary text"

    assert get_entry_summary(
        {
            "title": "Title text",
        }
    ) == "Title text"

    assert get_entry_summary({}) == "No summary available."


def test_get_entry_summary_understands_structured_case_recall_card() -> None:
    """
    Structured case recall cards should summarize from case_card fields.
    """
    recall_card = extract_case_recall_card(build_chrome_case())

    summary = get_entry_summary(recall_card)

    assert "Problem: Laptop felt slow" in summary
    assert "Lesson: Chrome high memory usage" in summary
    assert "Outcome: Laptop became more responsive" in summary


def test_get_entry_tags_understands_structured_case_recall_card() -> None:
    """
    Structured case recall cards should expose tags from case_card.
    """
    recall_card = extract_case_recall_card(build_chrome_case())

    assert get_entry_tags(recall_card) == "chrome, memory, slowdown"


def test_summarize_memory_context_builds_context_text(tmp_path) -> None:
    """
    Retrieved memory should become a compact context block.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    retrieval_result = retrieve_memory_for_request(
        "why is chrome using memory",
        memory_dir=memory_dir,
    )

    summary = summarize_memory_context(retrieval_result)

    assert summary.status == MEMORY_SUMMARY_STATUS_OK
    assert summary.user_request == "why is chrome using memory"
    assert "chrome" in summary.keywords
    assert "memory" in summary.keywords
    assert summary.baseline_count > 0
    assert summary.preference_count > 0
    assert summary.case_count == 1
    assert summary.knowledge_count == 1

    assert "LIGHTHOUSE MEMORY CONTEXT" in summary.context_text
    assert "System baselines:" in summary.context_text
    assert "Operator preferences:" in summary.context_text
    assert "Relevant case memories:" in summary.context_text
    assert "case_chrome_memory" in summary.context_text
    assert "Laptop felt slow" in summary.context_text
    assert "Chrome high memory usage has previously caused slowdown" in summary.context_text
    assert "Relevant knowledge entries:" in summary.context_text
    assert "windows_memory_pressure" in summary.context_text


def test_summarize_memory_for_request_retrieves_and_summarizes(tmp_path) -> None:
    """
    Convenience wrapper should retrieve then summarize memory.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    summary = summarize_memory_for_request(
        "chrome memory slowdown",
        memory_dir=memory_dir,
    )

    assert summary.status == MEMORY_SUMMARY_STATUS_OK
    assert summary.case_count == 1
    assert summary.knowledge_count == 1
    assert "Chrome high memory usage has previously caused slowdown" in summary.context_text
    assert "Laptop became more responsive" in summary.context_text


def test_summarize_memory_context_reports_invalid_skipped_cases(tmp_path) -> None:
    """
    Source warnings should report invalid case memories skipped by retrieval.
    """
    memory_dir = tmp_path / "memory"
    valid_case = build_chrome_case()
    invalid_case = build_chrome_case()
    invalid_case["case_id"] = "case_invalid"
    invalid_case["case_card"]["tags"] = []

    append_case_memory(valid_case, memory_dir=memory_dir)
    append_case_memory(invalid_case, memory_dir=memory_dir)

    summary = summarize_memory_for_request(
        "chrome memory",
        memory_dir=memory_dir,
    )

    assert summary.case_count == 1
    assert summary.warnings == ("Skipped 1 invalid case memory record(s).",)
    assert "Skipped 1 invalid case memory record(s)." in summary.context_text


def test_summarize_empty_memory_context_returns_empty_status(tmp_path) -> None:
    """
    Empty memory should produce a stable empty summary.
    """
    memory_dir = tmp_path / "memory"

    retrieval_result = retrieve_memory_for_request(
        "unknown topic",
        memory_dir=memory_dir,
    )

    summary = summarize_memory_context(retrieval_result)

    assert summary.status == MEMORY_SUMMARY_STATUS_EMPTY
    assert summary.baseline_count == 0
    assert summary.preference_count == 0
    assert summary.case_count == 0
    assert summary.knowledge_count == 0
    assert "System baselines:" in summary.context_text
    assert "- none" in summary.context_text


def test_summary_result_to_dict_has_stable_shape(tmp_path) -> None:
    """
    Summary results should expose a serializable stable shape.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    summary = summarize_memory_for_request(
        "chrome memory",
        memory_dir=memory_dir,
    )
    payload = summary.to_dict()

    assert payload["status"] == MEMORY_SUMMARY_STATUS_OK
    assert payload["user_request"] == "chrome memory"
    assert "chrome" in payload["keywords"]
    assert "memory" in payload["keywords"]
    assert isinstance(payload["context_text"], str)
    assert payload["baseline_count"] > 0
    assert payload["preference_count"] > 0
    assert payload["case_count"] == 1
    assert payload["knowledge_count"] == 1
    assert isinstance(payload["source_status"], dict)
    assert payload["warnings"] == []
