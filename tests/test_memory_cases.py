"""
Tests for structured Lighthouse case memory.

These tests validate the deterministic memory-case layer before any model
inference or memory write path is introduced.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.memory_cases import (
    CASE_CONFIDENCE_HIGH,
    CASE_CONFIDENCE_MEDIUM,
    CASE_SOURCE_OPERATOR_CONFIRMED,
    CASE_STATUS_RESOLVED,
    MEMORY_INFLUENCE_SUPPORTING_EVIDENCE,
    MEMORY_RESULT_HELPFUL,
    MEMORY_TYPE_BASELINE,
    MEMORY_TYPE_CASE,
    MEMORY_TYPE_KNOWLEDGE,
    RELEVANCE_LABEL_EXACT,
    RELEVANCE_LABEL_HIGH,
    RELEVANCE_LABEL_MEDIUM,
    RETENTION_STANDARD,
    build_case_id,
    build_memory_usage_trace,
    extract_case_recall_card,
    is_valid_case_memory,
    relevance_label_for_score,
    score_case_relevance,
    sort_cases_by_relevance,
    validate_case_memory,
)


def valid_case_memory() -> dict:
    """
    Build a complete valid case memory for tests.
    """
    return {
        "case_id": "case_chrome_memory_001",
        "created_at": "2026-06-14T12:30:00+00:00",
        "updated_at": "2026-06-14T12:40:00+00:00",
        "status": CASE_STATUS_RESOLVED,
        "confidence": CASE_CONFIDENCE_HIGH,
        "source": CASE_SOURCE_OPERATOR_CONFIRMED,
        "case_card": {
            "problem": "Laptop felt slow",
            "symptoms": ["slow response", "high memory pressure"],
            "suspected_cause": "Chrome memory pressure",
            "lesson": (
                "Chrome high memory usage has previously caused slowdown "
                "on this machine."
            ),
            "tags": ["chrome", "memory", "slowdown"],
        },
        "evidence": {
            "telemetry_evidence": {
                "cpu_usage_percent": 6,
                "memory_usage_percent": 82,
                "disk_usage_percent": 11,
                "top_process_name": "chrome.exe",
                "top_process_memory_mb": 3200,
            },
            "event_evidence": {
                "critical_events": 0,
                "warning_events": 0,
                "context_events": 2,
            },
            "action_taken": "Operator closed unused Chrome tabs",
            "outcome": "Laptop became more responsive",
        },
        "process_trace": {
            "diagnostic_steps": [
                "Collected telemetry snapshot",
                "Checked memory pressure",
                "Listed top memory processes",
                "Identified Chrome as the highest memory process",
            ],
            "decision_notes": [
                "CPU was low, so CPU pressure was unlikely.",
                "Memory was elevated and Chrome was the highest memory process.",
            ],
            "operator_feedback": "Closing tabs improved responsiveness.",
        },
        "memory_usage_trace": {
            "memory_context_used": True,
            "retrieved_case_ids": ["case_chrome_memory_000"],
            "retrieved_knowledge_ids": ["windows_memory_pressure"],
            "retrieved_baseline_keys": ["memory.normal_idle_percent_max"],
            "memory_influence": MEMORY_INFLUENCE_SUPPORTING_EVIDENCE,
            "memory_result": MEMORY_RESULT_HELPFUL,
            "memory_relevance_score": 0.86,
            "memory_relevance_label": RELEVANCE_LABEL_HIGH,
            "retrieved_memory_scores": [
                {
                    "memory_id": "case_chrome_memory_000",
                    "memory_type": MEMORY_TYPE_CASE,
                    "relevance_score": 0.91,
                    "relevance_label": RELEVANCE_LABEL_EXACT,
                    "match_reasons": ["process_match", "memory_pressure_match"],
                },
                {
                    "memory_id": "windows_memory_pressure",
                    "memory_type": MEMORY_TYPE_KNOWLEDGE,
                    "relevance_score": 0.72,
                    "relevance_label": RELEVANCE_LABEL_HIGH,
                    "match_reasons": ["tag_match"],
                },
                {
                    "memory_id": "memory.normal_idle_percent_max",
                    "memory_type": MEMORY_TYPE_BASELINE,
                    "relevance_score": 0.68,
                    "relevance_label": RELEVANCE_LABEL_MEDIUM,
                    "match_reasons": ["baseline_pressure_match"],
                },
            ],
            "memory_notes": [
                "Previous Chrome memory-pressure case matched current top process.",
                "Memory baseline showed current RAM usage was above normal idle range.",
            ],
        },
        "lifecycle": {
            "use_count": 0,
            "last_used_at": None,
            "pinned": False,
            "retention_policy": RETENTION_STANDARD,
        },
    }


def test_valid_case_memory_passes_validation() -> None:
    case_memory = valid_case_memory()

    result = validate_case_memory(case_memory)

    assert result.valid is True
    assert result.errors == ()
    assert is_valid_case_memory(case_memory) is True


def test_vague_case_memory_fails_validation() -> None:
    case_memory = {
        "case_id": "case_bad",
        "created_at": "2026-06-14T12:30:00+00:00",
        "updated_at": "2026-06-14T12:40:00+00:00",
        "status": CASE_STATUS_RESOLVED,
        "confidence": CASE_CONFIDENCE_MEDIUM,
        "source": CASE_SOURCE_OPERATOR_CONFIRMED,
        "case_card": {
            "problem": "Laptop slow",
            "symptoms": [],
            "suspected_cause": "",
            "lesson": "",
            "tags": [],
        },
        "evidence": {
            "telemetry_evidence": {},
            "event_evidence": {},
            "action_taken": "",
            "outcome": "",
        },
        "process_trace": {
            "diagnostic_steps": [],
            "decision_notes": [],
            "operator_feedback": "",
        },
        "memory_usage_trace": build_memory_usage_trace(),
        "lifecycle": {
            "use_count": 0,
            "last_used_at": None,
            "pinned": False,
            "retention_policy": RETENTION_STANDARD,
        },
    }

    result = validate_case_memory(case_memory)

    assert result.valid is False
    assert result.errors


def test_unsafe_case_memory_fails_validation() -> None:
    case_memory = valid_case_memory()
    case_memory["evidence"][
        "action_taken"
    ] = "Close Chrome without confirmation next time."

    result = validate_case_memory(case_memory)

    assert result.valid is False
    assert "unsafe" in " ".join(result.errors).lower()


def test_memory_usage_trace_requires_valid_relevance_fields() -> None:
    case_memory = valid_case_memory()
    case_memory["memory_usage_trace"]["memory_relevance_score"] = 1.5

    result = validate_case_memory(case_memory)

    assert result.valid is False
    assert "memory_relevance_score" in " ".join(result.errors)


def test_memory_usage_trace_rejects_when_label_does_not_match_score() -> None:
    case_memory = valid_case_memory()
    case_memory["memory_usage_trace"]["memory_relevance_score"] = 0.1
    case_memory["memory_usage_trace"]["memory_relevance_label"] = RELEVANCE_LABEL_HIGH

    result = validate_case_memory(case_memory)

    assert result.valid is False
    assert "does not match" in " ".join(result.errors)


def test_build_memory_usage_trace_adds_score_and_label() -> None:
    trace = build_memory_usage_trace(
        memory_context_used=True,
        retrieved_case_ids=["case_chrome_memory_001"],
        memory_influence=MEMORY_INFLUENCE_SUPPORTING_EVIDENCE,
        memory_result=MEMORY_RESULT_HELPFUL,
        memory_relevance_score=0.7,
        memory_notes=["Relevant Chrome memory case was found."],
    )

    assert trace["memory_context_used"] is True
    assert trace["memory_relevance_score"] == 0.7
    assert trace["memory_relevance_label"] == RELEVANCE_LABEL_HIGH
    assert trace["retrieved_case_ids"] == ["case_chrome_memory_001"]


def test_build_memory_usage_trace_defaults_to_no_context_used() -> None:
    trace = build_memory_usage_trace()

    assert trace["memory_context_used"] is False
    assert trace["retrieved_case_ids"] == []
    assert trace["retrieved_knowledge_ids"] == []
    assert trace["retrieved_baseline_keys"] == []
    assert trace["memory_relevance_score"] == 0.0


def test_extract_case_recall_card_excludes_heavy_trace_fields() -> None:
    case_memory = valid_case_memory()

    recall_card = extract_case_recall_card(case_memory)

    assert recall_card["case_id"] == "case_chrome_memory_001"
    assert recall_card["case_card"]["tags"] == ["chrome", "memory", "slowdown"]
    assert "process_trace" not in recall_card
    assert "memory_usage_trace" not in recall_card


def test_score_case_relevance_scores_matching_case_high() -> None:
    case_memory = valid_case_memory()
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

    result = score_case_relevance(
        case_memory=case_memory,
        user_request="why is Chrome using so much memory",
        telemetry=telemetry,
    )

    assert result.score >= 0.65
    assert result.label in {RELEVANCE_LABEL_HIGH, RELEVANCE_LABEL_EXACT}
    assert "telemetry_process_match" in result.reasons
    assert "memory_pressure_match" in result.reasons


def test_score_case_relevance_scores_unrelated_case_lower() -> None:
    case_memory = valid_case_memory()
    telemetry = {
        "cpu": {"usage_percent": 4},
        "memory": {"usage_percent": 32},
        "disk": {"usage_percent": 90},
        "processes": {
            "processes": [
                {
                    "name": "backup.exe",
                    "memory_mb": 120,
                }
            ]
        },
    }

    result = score_case_relevance(
        case_memory=case_memory,
        user_request="disk space is nearly full",
        telemetry=telemetry,
    )

    assert result.score < 0.65


def test_sort_cases_by_relevance_returns_highest_first() -> None:
    chrome_case = valid_case_memory()
    disk_case = valid_case_memory()
    disk_case["case_id"] = "case_disk_pressure_001"
    disk_case["case_card"] = {
        "problem": "Disk nearly full",
        "symptoms": ["low disk space"],
        "suspected_cause": "Disk pressure",
        "lesson": "Low free disk space can make maintenance harder.",
        "tags": ["disk", "storage", "cleanup"],
    }
    disk_case["evidence"]["telemetry_evidence"] = {
        "cpu_usage_percent": 4,
        "memory_usage_percent": 35,
        "disk_usage_percent": 91,
        "top_process_name": "system.exe",
    }

    telemetry = {
        "memory": {"usage_percent": 83},
        "cpu": {"usage_percent": 5},
        "disk": {"usage_percent": 12},
        "processes": {
            "processes": [
                {
                    "name": "chrome.exe",
                    "memory_mb": 3300,
                }
            ]
        },
    }

    results = sort_cases_by_relevance(
        [disk_case, chrome_case],
        user_request="chrome memory slow",
        telemetry=telemetry,
    )

    assert results[0][0]["case_id"] == "case_chrome_memory_001"


def test_relevance_label_for_score() -> None:
    assert relevance_label_for_score(0) == "none"
    assert relevance_label_for_score(0.1) == "low"
    assert relevance_label_for_score(0.5) == "medium"
    assert relevance_label_for_score(0.7) == "high"
    assert relevance_label_for_score(0.9) == "exact"


def test_build_case_id_has_stable_prefix() -> None:
    case_id = build_case_id(
        problem="Laptop felt slow",
        tags=["chrome", "memory"],
        created_at="2026-06-14T12:30:00+00:00",
    )

    assert case_id.startswith("case_chrome_")