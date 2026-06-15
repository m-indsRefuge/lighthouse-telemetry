"""
Tests for Lighthouse memory manager.

The memory manager provides controlled V1 memory operations above the lower-level
memory store and structured case-memory validation layer.
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
    validate_case_memory,
)
from app.services.memory_manager import (
    MEMORY_MANAGER_STATUS_DUPLICATE,
    MEMORY_MANAGER_STATUS_EMPTY,
    MEMORY_MANAGER_STATUS_INVALID,
    MEMORY_MANAGER_STATUS_OK,
    build_case_memory,
    get_memory_status,
    list_case_memories,
    save_case_memory,
    search_case_memories,
)
from app.services.memory_store import (
    write_baselines,
    write_knowledge_index,
    write_operator_preferences,
)


def build_valid_case() -> dict:
    """
    Build a valid case memory using the manager's guided builder.
    """
    memory_usage_trace = build_memory_usage_trace(
        memory_context_used=True,
        retrieved_case_ids=["case_chrome_memory_000"],
        retrieved_knowledge_ids=["windows_memory_pressure"],
        retrieved_baseline_keys=["memory.normal_idle_percent_max"],
        memory_influence=MEMORY_INFLUENCE_SUPPORTING_EVIDENCE,
        memory_result=MEMORY_RESULT_HELPFUL,
        memory_relevance_score=0.82,
        memory_notes=["Previous Chrome memory case matched the current issue."],
    )

    return build_case_memory(
        case_id="case_chrome_memory_001",
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
        memory_usage_trace=memory_usage_trace,
    )


def test_build_case_memory_creates_valid_case() -> None:
    case_memory = build_valid_case()

    validation = validate_case_memory(case_memory)

    assert validation.valid is True
    assert case_memory["case_id"] == "case_chrome_memory_001"
    assert case_memory["case_card"]["tags"] == ["chrome", "memory", "slowdown"]
    assert case_memory["memory_usage_trace"]["memory_context_used"] is True


def test_save_case_memory_writes_valid_case(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    case_memory = build_valid_case()

    result = save_case_memory(case_memory, memory_dir=memory_dir)

    assert result.status == MEMORY_MANAGER_STATUS_OK
    assert result.data["saved"] is True
    assert result.data["case_id"] == "case_chrome_memory_001"


def test_save_case_memory_rejects_invalid_case(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    case_memory = build_valid_case()
    case_memory["case_card"]["lesson"] = ""

    result = save_case_memory(case_memory, memory_dir=memory_dir)

    assert result.status == MEMORY_MANAGER_STATUS_INVALID
    assert result.data["saved"] is False
    assert result.errors


def test_save_case_memory_rejects_duplicate_case_id(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    case_memory = build_valid_case()

    first = save_case_memory(case_memory, memory_dir=memory_dir)
    second = save_case_memory(case_memory, memory_dir=memory_dir)

    assert first.status == MEMORY_MANAGER_STATUS_OK
    assert second.status == MEMORY_MANAGER_STATUS_DUPLICATE
    assert second.data["saved"] is False


def test_list_case_memories_returns_saved_case(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    case_memory = build_valid_case()

    save_case_memory(case_memory, memory_dir=memory_dir)

    result = list_case_memories(memory_dir=memory_dir)

    assert result.status == MEMORY_MANAGER_STATUS_OK
    assert result.data["case_count"] == 1
    assert result.data["cases"][0]["case_id"] == "case_chrome_memory_001"


def test_list_case_memories_can_return_recall_cards_only(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    case_memory = build_valid_case()

    save_case_memory(case_memory, memory_dir=memory_dir)

    result = list_case_memories(
        memory_dir=memory_dir,
        recall_cards_only=True,
    )

    listed_case = result.data["cases"][0]

    assert result.status == MEMORY_MANAGER_STATUS_OK
    assert listed_case["case_id"] == "case_chrome_memory_001"
    assert "process_trace" not in listed_case
    assert "memory_usage_trace" not in listed_case


def test_list_case_memories_empty_memory(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"

    result = list_case_memories(memory_dir=memory_dir)

    assert result.status == MEMORY_MANAGER_STATUS_EMPTY
    assert result.data["case_count"] == 0
    assert result.data["cases"] == []


def test_search_case_memories_returns_relevant_match(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    case_memory = build_valid_case()

    save_case_memory(case_memory, memory_dir=memory_dir)

    telemetry = {
        "memory": {"usage_percent": 84},
        "cpu": {"usage_percent": 5},
        "disk": {"usage_percent": 12},
        "processes": {
            "processes": [
                {
                    "name": "chrome.exe",
                    "memory_mb": 3400,
                }
            ]
        },
    }

    result = search_case_memories(
        user_request="why is Chrome using memory",
        telemetry=telemetry,
        memory_dir=memory_dir,
    )

    assert result.status == MEMORY_MANAGER_STATUS_OK
    assert result.data["match_count"] == 1
    assert result.data["matches"][0]["case"]["case_id"] == "case_chrome_memory_001"
    assert result.data["matches"][0]["relevance"]["score"] >= 0.65


def test_search_case_memories_empty_query_is_invalid(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"

    result = search_case_memories(
        user_request="",
        memory_dir=memory_dir,
    )

    assert result.status == MEMORY_MANAGER_STATUS_INVALID
    assert result.errors


def test_get_memory_status_counts_memory_records(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"

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

    save_case_memory(build_valid_case(), memory_dir=memory_dir)

    result = get_memory_status(memory_dir=memory_dir)

    assert result.status == MEMORY_MANAGER_STATUS_OK
    assert result.data["baseline_count"] == 3
    assert result.data["operator_preference_count"] == 2
    assert result.data["case_count"] == 1
    assert result.data["valid_case_count"] == 1
    assert result.data["invalid_case_count"] == 0
    assert result.data["knowledge_entry_count"] == 1