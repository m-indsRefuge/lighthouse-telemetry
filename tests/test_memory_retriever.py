"""
Tests for Lighthouse memory retriever.

The memory retriever returns relevant memory context for an Operator request.
It does not write memory or execute tools.
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
)
from app.services.memory_manager import build_case_memory
from app.services.memory_retriever import (
    MEMORY_RETRIEVER_STATUS_OK,
    MemoryRetrievalQuery,
    extract_keywords,
    filter_and_rank_entries,
    normalize_keywords,
    prepare_case_entries_for_retrieval,
    retrieve_memory_context,
    retrieve_memory_for_request,
    score_text_for_keywords,
    value_to_searchable_text,
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


def build_disk_case() -> dict:
    """
    Build a valid structured disk-pressure case.
    """
    return build_case_memory(
        case_id="case_disk_space",
        problem="Disk nearly full",
        symptoms=["low disk space", "storage warning"],
        suspected_cause="Disk pressure on the system drive",
        lesson="Low free disk space can make maintenance and updates harder.",
        tags=["disk", "storage", "cleanup"],
        telemetry_evidence={
            "cpu_usage_percent": 4,
            "memory_usage_percent": 35,
            "disk_usage_percent": 91,
            "top_process_name": "system.exe",
        },
        event_evidence={
            "critical_events": 0,
            "warning_events": 1,
            "context_events": 0,
        },
        action_taken="Operator reviewed large downloads.",
        outcome="Storage review identified cleanup candidates.",
        diagnostic_steps=[
            "Collected telemetry snapshot",
            "Checked disk usage",
        ],
        decision_notes=[
            "Disk usage was above the warning threshold.",
        ],
        operator_feedback="Disk review helped identify large downloads.",
        confidence=CASE_CONFIDENCE_HIGH,
        source=CASE_SOURCE_OPERATOR_CONFIRMED,
        created_at="2026-06-15T12:30:00+00:00",
        updated_at="2026-06-15T12:40:00+00:00",
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
    append_case_memory(build_disk_case(), memory_dir=memory_dir)

    write_knowledge_index(
        {
            "schema_version": 1,
            "entries": [
                {
                    "id": "windows_memory_pressure",
                    "title": "Windows memory pressure troubleshooting",
                    "summary": "High memory usage can make Windows feel slow.",
                    "tags": ["windows", "memory", "slowdown"],
                },
                {
                    "id": "kernel_power_41",
                    "title": "Kernel-Power Event ID 41",
                    "summary": "Unexpected shutdown or restart event context.",
                    "tags": ["windows", "event", "crash"],
                },
            ],
        },
        memory_dir=memory_dir,
    )


def test_extract_keywords_removes_stopwords_and_short_terms() -> None:
    """
    Keyword extraction should keep useful retrieval terms.
    """
    keywords = extract_keywords("Why is my laptop slow with Chrome memory usage?")

    assert "chrome" in keywords
    assert "memory" in keywords
    assert "slow" in keywords
    assert "laptop" not in keywords
    assert "why" not in keywords


def test_normalize_keywords_deduplicates_and_sorts() -> None:
    """
    Explicit keywords should be normalized, deduplicated, and sorted.
    """
    keywords = normalize_keywords(
        [
            "Chrome",
            "chrome",
            "Memory",
            "the",
            "AI",
        ]
    )

    assert keywords == ("chrome", "memory")


def test_value_to_searchable_text_handles_nested_values() -> None:
    """
    Nested dictionaries and lists should become searchable text.
    """
    text = value_to_searchable_text(
        {
            "summary": "Chrome memory pressure",
            "tags": ["slowdown", "windows"],
            "evidence": {
                "process": "chrome.exe",
            },
        }
    )

    assert "summary" in text
    assert "chrome" in text
    assert "memory" in text
    assert "slowdown" in text
    assert "process" in text


def test_score_text_for_keywords_counts_matches() -> None:
    """
    Text scoring should count keyword matches.
    """
    score = score_text_for_keywords(
        "chrome memory chrome slowdown",
        ("chrome", "memory"),
    )

    assert score == 3


def test_filter_and_rank_entries_returns_relevant_entries_first() -> None:
    """
    Entries with stronger keyword matches should rank first.
    """
    entries = [
        {
            "id": "disk",
            "summary": "Disk storage issue.",
        },
        {
            "id": "chrome",
            "summary": "Chrome memory slowdown with Chrome tabs.",
        },
    ]

    ranked = filter_and_rank_entries(
        entries,
        keywords=("chrome", "memory"),
        limit=2,
    )

    assert len(ranked) == 1
    assert ranked[0].entry["id"] == "chrome"
    assert ranked[0].score == 3


def test_prepare_case_entries_skips_invalid_case_memories() -> None:
    """
    Invalid structured case memories should not be allowed into engine context.
    """
    valid_case = build_chrome_case()
    invalid_case = build_chrome_case()
    invalid_case["case_card"]["tags"] = []

    recall_safe_cases, invalid_count = prepare_case_entries_for_retrieval(
        [valid_case, invalid_case]
    )

    assert len(recall_safe_cases) == 1
    assert invalid_count == 1
    assert recall_safe_cases[0]["case_id"] == "case_chrome_memory"


def test_prepare_case_entries_returns_recall_safe_cards() -> None:
    """
    Valid cases should be converted into recall cards before retrieval scoring.
    """
    recall_safe_cases, invalid_count = prepare_case_entries_for_retrieval(
        [build_chrome_case()]
    )

    assert invalid_count == 0
    assert len(recall_safe_cases) == 1
    assert "process_trace" not in recall_safe_cases[0]
    assert "memory_usage_trace" not in recall_safe_cases[0]
    assert recall_safe_cases[0]["case_card"]["problem"] == "Laptop felt slow"


def test_retrieve_memory_for_request_returns_relevant_context(tmp_path) -> None:
    """
    Retrieval should return baselines, preferences, relevant valid cases, and
    relevant knowledge entries.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    result = retrieve_memory_for_request(
        "why is Chrome using memory and making my laptop slow",
        memory_dir=memory_dir,
    )

    assert result.status == MEMORY_RETRIEVER_STATUS_OK
    assert result.baselines["memory"]["normal_idle_percent_min"] == 30
    assert result.operator_preferences["communication"]["style"] == "plain_english"

    assert len(result.cases) == 1
    assert result.cases[0].entry["case_id"] == "case_chrome_memory"
    assert result.cases[0].score > 0
    assert "process_trace" not in result.cases[0].entry
    assert "memory_usage_trace" not in result.cases[0].entry

    assert len(result.knowledge_entries) == 1
    assert result.knowledge_entries[0].entry["id"] == "windows_memory_pressure"

    assert result.source_results["cases"]["invalid_case_count"] == 0
    assert result.errors == ()


def test_retrieve_memory_for_disk_request_returns_disk_case(tmp_path) -> None:
    """
    Disk requests should retrieve disk-related case memory.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    result = retrieve_memory_for_request(
        "is my disk storage full",
        memory_dir=memory_dir,
    )

    assert result.status == MEMORY_RETRIEVER_STATUS_OK
    assert len(result.cases) == 1
    assert result.cases[0].entry["case_id"] == "case_disk_space"


def test_retrieve_memory_context_can_disable_sources(tmp_path) -> None:
    """
    Retrieval query flags should disable selected sources.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    query = MemoryRetrievalQuery(
        user_request="chrome memory",
        include_baselines=False,
        include_operator_preferences=False,
        include_cases=True,
        include_knowledge=False,
    )

    result = retrieve_memory_context(
        query,
        memory_dir=memory_dir,
    )

    assert result.status == MEMORY_RETRIEVER_STATUS_OK
    assert result.baselines == {}
    assert result.operator_preferences == {}
    assert len(result.cases) == 1
    assert result.knowledge_entries == ()
    assert "baselines" not in result.source_results
    assert "operator_preferences" not in result.source_results
    assert "knowledge_index" not in result.source_results


def test_retrieve_memory_context_respects_case_limit(tmp_path) -> None:
    """
    Case retrieval should respect max_cases.
    """
    memory_dir = tmp_path / "memory"

    case_one = build_chrome_case()
    case_two = build_chrome_case()
    case_two["case_id"] = "case_chrome_memory_2"
    case_two["case_card"]["lesson"] = "Chrome memory issue two."

    append_case_memory(case_one, memory_dir=memory_dir)
    append_case_memory(case_two, memory_dir=memory_dir)

    query = MemoryRetrievalQuery(
        user_request="chrome memory",
        max_cases=1,
    )

    result = retrieve_memory_context(
        query,
        memory_dir=memory_dir,
    )

    assert len(result.cases) == 1


def test_retrieve_memory_context_reports_invalid_skipped_cases(tmp_path) -> None:
    """
    Retrieval source status should report invalid skipped case memories.
    """
    memory_dir = tmp_path / "memory"
    valid_case = build_chrome_case()
    invalid_case = build_chrome_case()
    invalid_case["case_id"] = "case_invalid"
    invalid_case["case_card"]["tags"] = []

    append_case_memory(valid_case, memory_dir=memory_dir)
    append_case_memory(invalid_case, memory_dir=memory_dir)

    result = retrieve_memory_for_request(
        "chrome memory",
        memory_dir=memory_dir,
    )

    assert len(result.cases) == 1
    assert result.cases[0].entry["case_id"] == "case_chrome_memory"
    assert result.source_results["cases"]["raw_case_count"] == 2
    assert result.source_results["cases"]["valid_case_count"] == 1
    assert result.source_results["cases"]["invalid_case_count"] == 1


def test_retrieval_result_to_dict_has_stable_shape(tmp_path) -> None:
    """
    Retrieval results should expose a serializable stable shape.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    result = retrieve_memory_for_request(
        "chrome memory",
        memory_dir=memory_dir,
    )
    payload = result.to_dict()

    assert payload["status"] == MEMORY_RETRIEVER_STATUS_OK
    assert payload["query"]["user_request"] == "chrome memory"
    assert "chrome" in payload["keywords"]
    assert "memory" in payload["keywords"]
    assert isinstance(payload["baselines"], dict)
    assert isinstance(payload["operator_preferences"], dict)
    assert isinstance(payload["cases"], list)
    assert isinstance(payload["knowledge_entries"], list)
    assert isinstance(payload["source_results"], dict)
    assert payload["errors"] == []
