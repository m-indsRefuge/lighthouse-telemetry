"""
Tests for deterministic Windows diagnostic findings.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.windows_diagnostic_findings import (
    build_windows_diagnostic_findings,
)
from app.services.windows_evidence import build_windows_evidence_item


def item(signal: str, value: object) -> dict:
    return build_windows_evidence_item(
        source="test",
        collector="test",
        signal=signal,
        value=value,
        plain_meaning=f"Test evidence for {signal}",
    )


def finding_ids(result: dict) -> set[str]:
    return {
        finding["finding_id"]
        for finding in result["data"]["findings"]
    }


def test_build_windows_diagnostic_findings_detects_cpu_pressure() -> None:
    result = build_windows_diagnostic_findings(
        [
            item("processor_total_percent_time", 95),
        ]
    )

    assert result["status"] == "ok"
    assert "cpu_pressure_detected" in finding_ids(result)


def test_build_windows_diagnostic_findings_detects_memory_pressure() -> None:
    result = build_windows_diagnostic_findings(
        [
            item("memory_available_mbytes", 512),
            item("memory_pages_per_second", 100),
        ]
    )

    ids = finding_ids(result)

    assert "memory_pressure_detected" in ids

    finding = result["data"]["findings"][0]
    assert finding["permission_required"] is False
    assert "collect.windows.performance_counters" in finding["allowed_next_tools"]


def test_build_windows_diagnostic_findings_detects_storage_pressure_from_counter() -> None:
    result = build_windows_diagnostic_findings(
        [
            item("physical_disk_avg_queue_length", 4),
        ]
    )

    assert "storage_pressure_detected" in finding_ids(result)


def test_build_windows_diagnostic_findings_boosts_storage_confidence_with_event() -> None:
    result = build_windows_diagnostic_findings(
        [
            item("physical_disk_avg_queue_length", 4),
            item("disk_io_retry_warning", {"event_id": 153}),
        ]
    )

    findings = result["data"]["findings"]
    storage = [
        finding
        for finding in findings
        if finding["finding_id"] == "storage_pressure_detected"
    ][0]

    assert storage["confidence"] == "high"
    assert "physical_disk_avg_queue_length" in storage["supporting_signals"]
    assert "disk_io_retry_warning" in storage["supporting_signals"]


def test_build_windows_diagnostic_findings_detects_unexpected_shutdown() -> None:
    result = build_windows_diagnostic_findings(
        [
            item("unexpected_shutdown_or_power_loss", {"event_id": 41}),
        ]
    )

    assert "unexpected_shutdown_evidence" in finding_ids(result)


def test_build_windows_diagnostic_findings_detects_bugcheck() -> None:
    result = build_windows_diagnostic_findings(
        [
            item("windows_bugcheck", {"event_id": 1001}),
        ]
    )

    assert "windows_bugcheck_evidence" in finding_ids(result)


def test_build_windows_diagnostic_findings_detects_hardware_warning() -> None:
    result = build_windows_diagnostic_findings(
        [
            item("hardware_or_firmware_warning", {"provider": "WHEA-Logger"}),
        ]
    )

    assert "possible_hardware_or_firmware_instability" in finding_ids(result)


def test_build_windows_diagnostic_findings_detects_application_instability() -> None:
    result = build_windows_diagnostic_findings(
        [
            item("application_hang", {"event_id": 1002}),
            item("application_crash", {"event_id": 1000}),
        ]
    )

    assert "application_instability_detected" in finding_ids(result)


def test_build_windows_diagnostic_findings_returns_no_major_findings_when_clean() -> None:
    result = build_windows_diagnostic_findings(
        [
            item("processor_total_percent_time", 5),
            item("memory_available_mbytes", 16000),
            item("physical_disk_avg_queue_length", 0.1),
        ]
    )

    assert finding_ids(result) == {"no_major_windows_findings_detected"}
    assert result["data"]["finding_count"] == 1


def test_build_windows_diagnostic_findings_ignores_invalid_items() -> None:
    result = build_windows_diagnostic_findings(
        [
            {"signal": "processor_total_percent_time", "value": 99},
        ]
    )

    assert finding_ids(result) == {"no_major_windows_findings_detected"}
