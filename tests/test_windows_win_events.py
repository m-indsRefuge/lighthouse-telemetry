"""
Tests for hardened Windows Get-WinEvent evidence collector.
"""

from pathlib import Path
import json
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.collectors.windows.win_events import (
    ALLOWED_EVENT_LOG_NAMES,
    build_win_event_script,
    clamp_max_events,
    collect_win_event_log_evidence,
    collect_windows_event_evidence,
    evidence_item_from_win_event,
    normalize_event_time,
    normalize_win_event_json_date,
    parse_win_event_json,
    truncate_message,
)
from app.services.windows_evidence import is_valid_windows_evidence_item


def fake_win_event_runner(script: str) -> str:
    assert "Get-WinEvent" in script

    if "System" in script:
        return json.dumps(
            [
                {
                    "LogName": "System",
                    "ProviderName": "Microsoft-Windows-Kernel-Power",
                    "Id": 41,
                    "LevelDisplayName": "Critical",
                    "TimeCreated": "/Date(1781948273961)/",
                    "Message": "The system has rebooted without cleanly shutting down first.",
                },
                {
                    "LogName": "System",
                    "ProviderName": "Disk",
                    "Id": 153,
                    "LevelDisplayName": "Warning",
                    "TimeCreated": "2026-06-22T10:15:00",
                    "Message": "The IO operation was retried.",
                },
                {
                    "LogName": "System",
                    "ProviderName": "Service Control Manager",
                    "Id": 7036,
                    "LevelDisplayName": "Information",
                    "TimeCreated": "2026-06-22T10:20:00",
                    "Message": "A normal information event that should not be included.",
                },
            ]
        )

    if "Application" in script:
        return json.dumps(
            [
                {
                    "LogName": "Application",
                    "ProviderName": "Application Error",
                    "Id": 1000,
                    "LevelDisplayName": "Error",
                    "TimeCreated": "/Date(1736899200000)/",
                    "Message": "Faulting application name: example.exe",
                },
                {
                    "LogName": "Application",
                    "ProviderName": "Application Hang",
                    "Id": 1002,
                    "LevelDisplayName": "Error",
                    "TimeCreated": "2026-06-22T10:30:00",
                    "Message": "The program stopped interacting with Windows.",
                },
            ]
        )

    raise RuntimeError(f"Unexpected script: {script}")


def test_build_win_event_script_uses_allowlisted_log_and_limit() -> None:
    script = build_win_event_script("System", max_events=25)

    assert "Get-WinEvent -LogName 'System'" in script
    assert "-MaxEvents 25" in script
    assert "Select-Object LogName,ProviderName,Id,LevelDisplayName,TimeCreated,Message" in script
    assert "ConvertTo-Json" in script


def test_build_win_event_script_rejects_unapproved_log() -> None:
    try:
        build_win_event_script("Security")
    except ValueError as error:
        assert "not allowlisted" in str(error)
    else:
        raise AssertionError("Expected Security log to be rejected.")


def test_allowed_event_logs_are_limited_to_system_and_application() -> None:
    assert ALLOWED_EVENT_LOG_NAMES == frozenset({"System", "Application"})


def test_clamp_max_events_bounds_query_size() -> None:
    assert clamp_max_events(-1) == 1
    assert clamp_max_events(0) == 1
    assert clamp_max_events(25) == 25
    assert clamp_max_events(99999) == 500


def test_parse_win_event_json_accepts_single_object() -> None:
    records = parse_win_event_json('{"ProviderName": "Disk", "Id": 153}')

    assert records == [{"ProviderName": "Disk", "Id": 153}]


def test_parse_win_event_json_accepts_list_of_objects() -> None:
    records = parse_win_event_json(
        '[{"ProviderName": "Disk", "Id": 153}, {"ProviderName": "EventLog", "Id": 6008}]'
    )

    assert records == [
        {"ProviderName": "Disk", "Id": 153},
        {"ProviderName": "EventLog", "Id": 6008},
    ]


def test_normalize_win_event_json_date_converts_powershell_json_date() -> None:
    assert (
        normalize_win_event_json_date("/Date(1736899200000)/")
        == "2025-01-15T00:00:00+00:00"
    )


def test_normalize_event_time_preserves_non_matching_string() -> None:
    assert normalize_event_time("2026-06-22T10:15:00") == "2026-06-22T10:15:00"


def test_truncate_message_limits_large_event_messages() -> None:
    message = "x" * 400

    assert len(truncate_message(message)) == 300
    assert truncate_message(message).endswith("...")


def test_evidence_item_from_known_kernel_power_event() -> None:
    item = evidence_item_from_win_event(
        {
            "LogName": "System",
            "ProviderName": "Microsoft-Windows-Kernel-Power",
            "Id": 41,
            "LevelDisplayName": "Critical",
            "TimeCreated": "/Date(1781948273961)/",
            "Message": "Unexpected shutdown.",
        }
    )

    assert item is not None
    assert item["signal"] == "unexpected_shutdown_or_power_loss"
    assert item["status"] == "error"
    assert item["value"]["event_id"] == 41
    assert item["value"]["time_created"] == "2026-06-20T09:37:53.961000+00:00"
    assert item["raw"]["raw_time_created"] == "/Date(1781948273961)/"
    assert is_valid_windows_evidence_item(item)


def test_evidence_item_ignores_uninteresting_information_event() -> None:
    item = evidence_item_from_win_event(
        {
            "LogName": "System",
            "ProviderName": "Service Control Manager",
            "Id": 7036,
            "LevelDisplayName": "Information",
            "TimeCreated": "2026-06-22T10:20:00",
            "Message": "Service started.",
        }
    )

    assert item is None


def test_collect_win_event_log_evidence_rejects_unapproved_log() -> None:
    result = collect_win_event_log_evidence(
        log_name="Security",
        runner=fake_win_event_runner,
    )

    assert result["status"] == "invalid"
    assert result["evidence_items"] == []
    assert "not allowlisted" in result["errors"][0]


def test_collect_win_event_log_evidence_returns_normalized_items() -> None:
    result = collect_win_event_log_evidence(
        log_name="System",
        runner=fake_win_event_runner,
    )

    assert result["status"] == "ok"
    assert result["log_name"] == "System"
    assert result["records_checked"] == 3

    signals = {item["signal"] for item in result["evidence_items"]}

    assert "unexpected_shutdown_or_power_loss" in signals
    assert "disk_io_retry_warning" in signals
    assert all(is_valid_windows_evidence_item(item) for item in result["evidence_items"])


def test_collect_windows_event_evidence_collects_default_logs() -> None:
    result = collect_windows_event_evidence(runner=fake_win_event_runner)

    assert result["status"] == "ok"
    assert result["source"] == "windows_event_log"
    assert result["log_names"] == ["System", "Application"]
    assert result["errors"] == []
    assert len(result["log_results"]) == 2

    signals = {item["signal"] for item in result["evidence_items"]}

    assert "unexpected_shutdown_or_power_loss" in signals
    assert "disk_io_retry_warning" in signals
    assert "application_crash" in signals
    assert "application_hang" in signals
    assert result["summary"]["status"] == "ok"


def test_collect_windows_event_evidence_handles_partial_errors() -> None:
    def partly_failing_runner(script: str) -> str:
        if "Application" in script:
            raise RuntimeError("Application log failure")

        return fake_win_event_runner(script)

    result = collect_windows_event_evidence(runner=partly_failing_runner)

    assert result["status"] == "partial"
    assert "Application log failure" in result["errors"]
    assert any(
        item["signal"] == "windows_event_collection_error"
        for item in result["evidence_items"]
    )
    assert result["summary"]["data"]["total_items"] > 0


def test_collect_windows_event_evidence_formats_timeout_error() -> None:
    def timeout_runner(script: str) -> str:
        raise subprocess.TimeoutExpired(cmd="Get-WinEvent", timeout=30)

    result = collect_windows_event_evidence(
        log_names=("System",),
        runner=timeout_runner,
    )

    assert result["status"] == "partial"
    assert result["errors"] == [
        "Get-WinEvent query timed out for System after 30 seconds."
    ]
    assert result["evidence_items"][0]["signal"] == "windows_event_collection_error"
