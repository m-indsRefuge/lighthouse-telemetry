"""
Tests for Windows evidence aggregation.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.windows_evidence import (
    build_windows_evidence_item,
    is_valid_windows_evidence_item,
)
from app.services.windows_evidence_aggregator import collect_windows_evidence


def build_test_item(signal: str, value: object = 1) -> dict:
    return build_windows_evidence_item(
        source="test",
        collector="test",
        signal=signal,
        value=value,
        plain_meaning=f"Test signal: {signal}",
    )


def test_collect_windows_evidence_aggregates_successful_collectors() -> None:
    def cim_collector() -> dict:
        return {
            "status": "ok",
            "message": "CIM ok",
            "source": "cim",
            "evidence_items": [build_test_item("os_caption", "Windows")],
            "errors": [],
            "warnings": [],
        }

    def perf_collector() -> dict:
        return {
            "status": "ok",
            "message": "Performance ok",
            "source": "performance_counter",
            "evidence_items": [build_test_item("processor_total_percent_time", 15)],
            "errors": [],
            "warnings": [],
        }

    result = collect_windows_evidence(
        collectors={
            "cim": cim_collector,
            "performance_counters": perf_collector,
        }
    )

    assert result["status"] == "ok"
    assert result["collector_count"] == 2
    assert result["ok_collector_count"] == 2
    assert result["failed_collector_count"] == 0
    assert len(result["evidence_items"]) == 2
    assert all(is_valid_windows_evidence_item(item) for item in result["evidence_items"])


def test_collect_windows_evidence_returns_partial_when_one_collector_fails() -> None:
    def good_collector() -> dict:
        return {
            "status": "ok",
            "message": "ok",
            "source": "test",
            "evidence_items": [build_test_item("memory_available_mbytes", 16000)],
            "errors": [],
            "warnings": [],
        }

    def failing_collector() -> dict:
        raise RuntimeError("collector exploded")

    result = collect_windows_evidence(
        collectors={
            "good": good_collector,
            "bad": failing_collector,
        }
    )

    assert result["status"] == "partial"
    assert result["collector_count"] == 2
    assert result["ok_collector_count"] == 1
    assert result["failed_collector_count"] == 1
    assert "collector exploded" in result["errors"]
    assert any(
        item["signal"] == "bad_collection_exception"
        for item in result["evidence_items"]
    )


def test_collect_windows_evidence_excludes_invalid_evidence_items() -> None:
    def invalid_collector() -> dict:
        return {
            "status": "ok",
            "message": "bad evidence",
            "source": "test",
            "evidence_items": [
                {"signal": "missing required fields"},
                build_test_item("valid_signal", 1),
            ],
            "errors": [],
            "warnings": [],
        }

    result = collect_windows_evidence(
        collectors={
            "invalid": invalid_collector,
        }
    )

    assert result["status"] == "ok"
    assert len(result["evidence_items"]) == 1
    assert result["evidence_items"][0]["signal"] == "valid_signal"
    assert result["warnings"] == [
        "invalid evidence item 0 failed WindowsEvidenceItem validation."
    ]


def test_collect_windows_evidence_handles_non_dict_collector_result() -> None:
    def bad_shape_collector() -> list:
        return []

    result = collect_windows_evidence(
        collectors={
            "bad_shape": bad_shape_collector,
        }
    )

    assert result["status"] == "error"
    assert result["evidence_items"] == []
    assert result["errors"] == [
        "bad_shape collector returned non-dictionary result."
    ]
