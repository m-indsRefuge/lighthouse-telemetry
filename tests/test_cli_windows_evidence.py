"""
Tests for Windows evidence CLI wiring.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import cli
from app.services.windows_evidence import build_windows_evidence_item


def fake_aggregated_windows_evidence_result() -> dict:
    return {
        "status": "ok",
        "message": "Windows evidence aggregation completed.",
        "source": "aggregated_windows_evidence",
        "collector_results": [
            {
                "collector": "cim",
                "status": "ok",
                "evidence_count": 2,
                "errors": [],
                "warnings": [],
            },
            {
                "collector": "performance_counters",
                "status": "ok",
                "evidence_count": 1,
                "errors": [],
                "warnings": [],
            },
            {
                "collector": "events",
                "status": "ok",
                "evidence_count": 1,
                "errors": [],
                "warnings": [],
            },
        ],
        "evidence_items": [
            build_windows_evidence_item(
                source="cim",
                collector="Win32_OperatingSystem",
                signal="os_caption",
                value="Microsoft Windows 11 Pro",
            ),
            build_windows_evidence_item(
                source="cim",
                collector="Win32_Processor",
                signal="processor_name",
                value="Example CPU",
            ),
            build_windows_evidence_item(
                source="performance_counter",
                collector="Get-Counter",
                signal="processor_total_percent_time",
                value=11.5,
            ),
            build_windows_evidence_item(
                source="windows_event_log",
                collector="Get-WinEvent",
                signal="application_hang",
                value={"event_id": 1002},
            ),
        ],
        "summary": {
            "data": {
                "valid": True,
            }
        },
        "errors": [],
        "warnings": [],
    }


def fake_cim_result() -> dict:
    return {
        "status": "ok",
        "message": "CIM evidence collection completed.",
        "source": "cim",
        "evidence_items": [
            build_windows_evidence_item(
                source="cim",
                collector="Win32_OperatingSystem",
                signal="os_caption",
                value="Microsoft Windows 11 Pro",
            ),
            build_windows_evidence_item(
                source="cim",
                collector="Win32_Processor",
                signal="processor_name",
                value="Example CPU",
            ),
        ],
        "summary": {
            "data": {
                "valid": True,
            }
        },
        "errors": [],
        "warnings": [],
    }


def fake_findings_result(evidence_items: list[dict]) -> dict:
    assert evidence_items

    return {
        "status": "ok",
        "message": "Windows diagnostic findings generated.",
        "data": {
            "finding_count": 1,
            "findings": [
                {
                    "finding_id": "application_instability_detected",
                    "category": "application",
                    "severity": "warning",
                    "confidence": "medium",
                    "plain_meaning": "Windows recorded application instability evidence.",
                    "supporting_signals": ["application_hang"],
                    "supporting_evidence_count": 1,
                    "recommended_next_step": "Correlate with CPU, memory, disk pressure.",
                    "allowed_next_tools": [
                        "collect.windows.cim",
                        "collect.windows.performance_counters",
                        "collect.windows.events",
                    ],
                    "permission_required": False,
                    "safety_note": "Read-only diagnosis only.",
                }
            ],
        },
        "errors": [],
        "warnings": [],
    }


def test_run_canonical_command_handles_windows(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "collect_windows_evidence",
        fake_aggregated_windows_evidence_result,
    )
    monkeypatch.setattr(
        cli,
        "build_windows_diagnostic_findings",
        fake_findings_result,
    )

    result = cli.run_canonical_command("windows")

    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE WINDOWS EVIDENCE" in output
    assert "Status: ok" in output
    assert "Source: aggregated_windows_evidence" in output
    assert "Collectors:" in output
    assert "- cim: ok (2 evidence items)" in output
    assert "Microsoft Windows 11 Pro" in output
    assert "Example CPU" in output
    assert "Performance counters:" in output
    assert "Recent Windows event evidence:" in output
    assert "Deterministic findings:" in output
    assert "application_instability_detected" in output


def test_run_canonical_command_handles_windows_evidence_alias(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "collect_windows_evidence",
        fake_aggregated_windows_evidence_result,
    )
    monkeypatch.setattr(
        cli,
        "build_windows_diagnostic_findings",
        fake_findings_result,
    )

    result = cli.run_canonical_command("windows evidence")

    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE WINDOWS EVIDENCE" in output
    assert "Deterministic findings:" in output


def test_run_canonical_command_handles_cim_alias_as_cim_only(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "collect_windows_cim_evidence",
        fake_cim_result,
    )

    result = cli.run_canonical_command("cim evidence")

    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE WINDOWS EVIDENCE" in output
    assert "Source: cim" in output
    assert "Microsoft Windows 11 Pro" in output
    assert "Collectors:" not in output
    assert "Deterministic findings:" not in output


def test_help_mentions_windows_and_cim_commands(capsys) -> None:
    cli.print_help()

    output = capsys.readouterr().out

    assert "windows" in output
    assert "Show aggregated Windows-native evidence and findings" in output
    assert "cim" in output
    assert "Show Windows-native CIM evidence only" in output
