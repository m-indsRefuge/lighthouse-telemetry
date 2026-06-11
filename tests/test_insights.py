"""
Tests for the Lighthouse insight engine.
"""

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.insights import build_system_insight, format_insight_report


def build_fake_telemetry(
    cpu_usage: float = 10.0,
    memory_usage: float = 40.0,
    disk_usage: float = 20.0,
) -> dict[str, Any]:
    """
    Build fake telemetry for testing the insight engine.
    """
    return {
        "cpu": {
            "status": "ok",
            "usage_percent": cpu_usage,
            "physical_cores": 8,
            "logical_cores": 16,
        },
        "memory": {
            "status": "ok",
            "usage_percent": memory_usage,
            "total_gb": 16,
            "used_gb": 6.4,
            "available_gb": 9.6,
        },
        "disk": {
            "status": "ok",
            "usage_percent": disk_usage,
            "total_gb": 512,
            "used_gb": 102,
            "free_gb": 410,
        },
        "processes": {
            "status": "ok",
            "processes": [
                {
                    "pid": 1234,
                    "name": "TestProcess.exe",
                    "memory_mb": 512.25,
                    "cpu_percent": 1.2,
                }
            ],
        },
    }


def build_fake_event_report(
    critical: int = 0,
    warning: int = 0,
    context: int = 5,
) -> dict[str, Any]:
    """
    Build fake event-log evidence for testing the insight engine.
    """
    return {
        "status": "ok",
        "severity_summary": {
            "critical": critical,
            "warning": warning,
            "context": context,
        },
        "possible_causes": [],
        "events": [],
    }


def test_good_system_insight_returns_good_status() -> None:
    telemetry = build_fake_telemetry()
    event_report = build_fake_event_report()

    insight = build_system_insight(telemetry, event_report)

    assert insight["status"] == "ok"
    assert insight["overall_status"] == "GOOD"
    assert "did not find an obvious system fault" in insight["summary"]
    assert insight["metrics"]["cpu_status"] == "OK"
    assert insight["metrics"]["memory_status"] == "OK"
    assert insight["metrics"]["disk_status"] == "OK"


def test_high_cpu_returns_warning_status() -> None:
    telemetry = build_fake_telemetry(cpu_usage=82.0)
    event_report = build_fake_event_report()

    insight = build_system_insight(telemetry, event_report)

    assert insight["status"] == "ok"
    assert insight["overall_status"] == "WARNING"
    assert insight["metrics"]["cpu_status"] == "WARNING"
    assert any("CPU usage is elevated" in finding for finding in insight["findings"])


def test_critical_memory_returns_warning_status_for_live_pressure() -> None:
    telemetry = build_fake_telemetry(memory_usage=94.0)
    event_report = build_fake_event_report()

    insight = build_system_insight(telemetry, event_report)

    assert insight["status"] == "ok"
    assert insight["overall_status"] == "WARNING"
    assert insight["metrics"]["memory_status"] == "CRITICAL"
    assert any("Memory usage is critically high" in finding for finding in insight["findings"])


def test_critical_event_returns_critical_status() -> None:
    telemetry = build_fake_telemetry()
    event_report = build_fake_event_report(critical=1)

    insight = build_system_insight(telemetry, event_report)

    assert insight["status"] == "ok"
    assert insight["overall_status"] == "CRITICAL"
    assert insight["metrics"]["critical_events"] == 1
    assert "critical event-log evidence" in insight["summary"]


def test_warning_event_returns_warning_status() -> None:
    telemetry = build_fake_telemetry()
    event_report = build_fake_event_report(warning=2)

    insight = build_system_insight(telemetry, event_report)

    assert insight["status"] == "ok"
    assert insight["overall_status"] == "WARNING"
    assert insight["metrics"]["warning_events"] == 2
    assert "warning-level system evidence" in insight["summary"]


def test_format_insight_report_contains_main_sections() -> None:
    telemetry = build_fake_telemetry()
    event_report = build_fake_event_report()

    insight = build_system_insight(telemetry, event_report)
    report = format_insight_report(insight)

    assert "LIGHTHOUSE INSIGHT" in report
    assert "Overall status: GOOD" in report
    assert "Assessment:" in report
    assert "Findings:" in report
    assert "Conclusion:" in report
    assert "Suggested next step:" in report