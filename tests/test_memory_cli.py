"""
Tests for Lighthouse memory CLI reporting helpers.
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
from app.services.memory_cli import (
    format_memory_case_list_report,
    format_memory_case_search_report,
    format_memory_command_report,
    format_memory_status_report,
)
from app.services.memory_manager import build_case_memory, save_case_memory
from app.services.memory_store import (
    write_baselines,
    write_knowledge_index,
    write_operator_preferences,
)


def build_valid_case() -> dict:
    """
    Build a valid case memory for CLI report tests.
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


def seed_memory(memory_dir: Path) -> None:
    """
    Seed memory records for CLI report tests.
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


def test_format_memory_status_report(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    report = format_memory_status_report(memory_dir=memory_dir)

    assert "LIGHTHOUSE MEMORY STATUS" in report
    assert "Status: ok" in report
    assert "- Baselines: 3" in report
    assert "- Operator preferences: 2" in report
    assert "- Case memories: 1" in report
    assert "- Knowledge entries: 1" in report


def test_format_memory_case_list_report(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    report = format_memory_case_list_report(memory_dir=memory_dir)

    assert "LIGHTHOUSE MEMORY CASES" in report
    assert "case_chrome_memory_001" in report
    assert "Chrome memory pressure" in report
    assert "Laptop became more responsive" in report
    assert "chrome, memory, slowdown" in report


def test_format_memory_case_list_report_empty(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"

    report = format_memory_case_list_report(memory_dir=memory_dir)

    assert "LIGHTHOUSE MEMORY CASES" in report
    assert "Status: empty" in report
    assert "No case memories found." in report


def test_format_memory_case_search_report(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

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

    report = format_memory_case_search_report(
        "why is Chrome using memory",
        telemetry=telemetry,
        memory_dir=memory_dir,
    )

    assert "LIGHTHOUSE MEMORY SEARCH" in report
    assert "Status: ok" in report
    assert "Matches: 1" in report
    assert "case_chrome_memory_001" in report
    assert "Relevance score:" in report
    assert "memory_pressure_match" in report


def test_format_memory_command_report_routes_status(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    report = format_memory_command_report(
        "memory status",
        memory_dir=memory_dir,
    )

    assert "LIGHTHOUSE MEMORY STATUS" in report
    assert "- Case memories: 1" in report


def test_format_memory_command_report_routes_case_list(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    report = format_memory_command_report(
        "memory cases",
        memory_dir=memory_dir,
    )

    assert "LIGHTHOUSE MEMORY CASES" in report
    assert "case_chrome_memory_001" in report


def test_format_memory_command_report_routes_search(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    telemetry = {
        "memory": {"usage_percent": 84},
        "processes": {
            "processes": [
                {
                    "name": "chrome.exe",
                    "memory_mb": 3400,
                }
            ]
        },
    }

    report = format_memory_command_report(
        "memory search chrome memory",
        telemetry=telemetry,
        memory_dir=memory_dir,
    )

    assert "LIGHTHOUSE MEMORY SEARCH" in report
    assert "case_chrome_memory_001" in report


def test_format_memory_command_report_unknown_command() -> None:
    report = format_memory_command_report("memory unknown")

    assert "Status: unknown_command" in report
    assert "Available memory commands:" in report