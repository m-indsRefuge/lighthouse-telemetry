"""
Tests for Windows evidence report formatter.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.windows_evidence import build_windows_evidence_item
from app.services.windows_evidence_report import format_windows_evidence_report


def build_item(signal: str, value: object, source: str = "test") -> dict:
    return build_windows_evidence_item(
        source=source,
        collector=source,
        signal=signal,
        value=value,
        plain_meaning=f"Test evidence for {signal}",
    )


def test_format_windows_evidence_report_includes_core_sections() -> None:
    items = [
        build_item("os_caption", "Microsoft Windows 11 Pro", "cim"),
        build_item("last_boot_time", "2026-06-22T08:13:00", "cim"),
        build_item("computer_model", "Example Model", "cim"),
        build_item("processor_name", "Example CPU", "cim"),
        build_item("logical_disk_device_id", "C:", "cim"),
        build_item("logical_disk_size_bytes", 1024 ** 3, "cim"),
        build_item("logical_disk_free_space_bytes", 512 * 1024 ** 2, "cim"),
    ]

    report = format_windows_evidence_report(
        {
            "status": "ok",
            "message": "CIM evidence collection completed.",
            "source": "cim",
            "evidence_items": items,
            "summary": {
                "data": {
                    "valid": True,
                }
            },
            "errors": [],
            "warnings": [],
        }
    )

    assert "LIGHTHOUSE WINDOWS EVIDENCE" in report
    assert "Status: ok" in report
    assert "Operating system:" in report
    assert "Microsoft Windows 11 Pro" in report
    assert "Computer:" in report
    assert "Example Model" in report
    assert "Processor:" in report
    assert "Example CPU" in report
    assert "Logical disks:" in report
    assert "C:" in report
    assert "C::" not in report


def test_cim_only_report_does_not_show_aggregation_only_sections() -> None:
    report = format_windows_evidence_report(
        {
            "status": "ok",
            "message": "CIM evidence collection completed.",
            "source": "cim",
            "evidence_items": [
                build_item("os_caption", "Microsoft Windows 11 Pro", "cim"),
            ],
            "summary": {
                "data": {
                    "valid": True,
                }
            },
            "errors": [],
            "warnings": [],
        }
    )

    assert "Source: cim" in report
    assert "Collectors:" not in report
    assert "Performance counters:" not in report
    assert "Recent Windows event evidence:" not in report
    assert "Deterministic findings:" not in report


def test_format_windows_evidence_report_includes_collector_summary() -> None:
    report = format_windows_evidence_report(
        {
            "status": "ok",
            "message": "Windows evidence aggregation completed.",
            "evidence_items": [],
            "collector_results": [
                {
                    "collector": "cim",
                    "status": "ok",
                    "evidence_count": 10,
                },
                {
                    "collector": "performance_counters",
                    "status": "ok",
                    "evidence_count": 7,
                },
            ],
            "summary": {"data": {"valid": True}},
            "errors": [],
            "warnings": [],
        },
        findings_result={
            "status": "ok",
            "data": {
                "findings": [],
            },
        },
    )

    assert "Collectors:" in report
    assert "- cim: ok (10 evidence items)" in report
    assert "- performance_counters: ok (7 evidence items)" in report


def test_format_windows_evidence_report_includes_performance_and_event_sections() -> None:
    items = [
        build_item("processor_total_percent_time", 12.5, "performance_counter"),
        build_item("processor_queue_length", 1, "performance_counter"),
        build_item("memory_available_mbytes", 12000, "performance_counter"),
        build_item("memory_pages_per_second", 2, "performance_counter"),
        build_item("physical_disk_avg_queue_length", 0.25, "performance_counter"),
        build_item("physical_disk_avg_seconds_per_read", 0.001, "performance_counter"),
        build_item("physical_disk_avg_seconds_per_write", 0.002, "performance_counter"),
        build_item(
            "unexpected_shutdown_or_power_loss",
            {"event_id": 41},
            "windows_event_log",
        ),
        build_item("application_hang", {"event_id": 1002}, "windows_event_log"),
    ]

    report = format_windows_evidence_report(
        {
            "status": "ok",
            "message": "Windows evidence aggregation completed.",
            "evidence_items": items,
            "collector_results": [
                {
                    "collector": "cim",
                    "status": "ok",
                    "evidence_count": 1,
                },
            ],
            "summary": {"data": {"valid": True}},
            "errors": [],
            "warnings": [],
        },
        findings_result={
            "status": "ok",
            "data": {
                "findings": [],
            },
        },
    )

    assert "Performance counters:" in report
    assert "- CPU total time: 12.50%" in report
    assert "Recent Windows event evidence:" in report
    assert "- Unexpected shutdown evidence: 1" in report
    assert "- Application instability evidence: 1" in report


def test_format_windows_evidence_report_includes_deterministic_findings() -> None:
    findings_result = {
        "status": "ok",
        "message": "Windows diagnostic findings generated.",
        "data": {
            "finding_count": 1,
            "findings": [
                {
                    "finding_id": "storage_pressure_detected",
                    "severity": "warning",
                    "confidence": "high",
                    "plain_meaning": "Storage pressure is present.",
                    "recommended_next_step": "Inspect storage evidence.",
                    "permission_required": False,
                }
            ],
        },
        "errors": [],
        "warnings": [],
    }

    report = format_windows_evidence_report(
        {
            "status": "ok",
            "message": "Windows evidence aggregation completed.",
            "evidence_items": [],
            "collector_results": [
                {
                    "collector": "events",
                    "status": "ok",
                    "evidence_count": 1,
                },
            ],
            "summary": {"data": {"valid": True}},
            "errors": [],
            "warnings": [],
        },
        findings_result=findings_result,
    )

    assert "Deterministic findings:" in report
    assert "- storage_pressure_detected [warning, high]" in report
    assert "Meaning: Storage pressure is present." in report
    assert "Permission required: no" in report
