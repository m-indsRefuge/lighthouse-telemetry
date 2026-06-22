"""
Tests for Windows Performance Counter collector.
"""

from pathlib import Path
import json
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.collectors.windows.perf_counters import (
    APPROVED_COUNTERS,
    build_counter_script,
    collect_windows_performance_counters,
    normalize_counter_path,
    parse_counter_json,
)
from app.services.windows_evidence import is_valid_windows_evidence_item


def fake_counter_runner(script: str) -> str:
    assert "Get-Counter" in script

    return json.dumps(
        [
            {
                "Path": r"\\TEST-PC\processor(_total)\% processor time",
                "CookedValue": 8.5,
                "InstanceName": "_Total",
            },
            {
                "Path": r"\\TEST-PC\system\processor queue length",
                "CookedValue": 1,
                "InstanceName": None,
            },
            {
                "Path": r"\\TEST-PC\memory\available mbytes",
                "CookedValue": 12000,
                "InstanceName": None,
            },
            {
                "Path": r"\\TEST-PC\physicaldisk(_total)\avg. disk queue length",
                "CookedValue": 0.25,
                "InstanceName": "_Total",
            },
        ]
    )


def test_build_counter_script_uses_get_counter_and_allowlisted_paths() -> None:
    counter_paths = (
        r"\processor(_total)\% processor time",
        r"\memory\available mbytes",
    )

    script = build_counter_script(counter_paths)

    assert "Get-Counter" in script
    assert "-SampleInterval 1" in script
    assert "-MaxSamples 1" in script
    assert r"\processor(_total)\% processor time" in script
    assert r"\memory\available mbytes" in script
    assert "ConvertTo-Json" in script


def test_parse_counter_json_accepts_single_object() -> None:
    records = parse_counter_json('{"Path": "x", "CookedValue": 1}')

    assert records == [{"Path": "x", "CookedValue": 1}]


def test_parse_counter_json_accepts_list_of_objects() -> None:
    records = parse_counter_json(
        '[{"Path": "a", "CookedValue": 1}, {"Path": "b", "CookedValue": 2}]'
    )

    assert records == [
        {"Path": "a", "CookedValue": 1},
        {"Path": "b", "CookedValue": 2},
    ]


def test_normalize_counter_path_removes_machine_prefix() -> None:
    assert (
        normalize_counter_path(r"\\TEST-PC\Processor(_Total)\% Processor Time")
        == r"\processor(_total)\% processor time"
    )


def test_collect_windows_performance_counters_rejects_unapproved_counter() -> None:
    result = collect_windows_performance_counters(
        counter_paths=(r"\process(*)\id process",),
        runner=fake_counter_runner,
    )

    assert result["status"] == "invalid"
    assert result["evidence_items"] == []
    assert "Performance counter is not allowlisted" in result["errors"][0]


def test_collect_windows_performance_counters_returns_normalized_items() -> None:
    result = collect_windows_performance_counters(runner=fake_counter_runner)

    assert result["status"] == "ok"
    assert result["source"] == "performance_counter"
    assert result["errors"] == []

    signals = {item["signal"] for item in result["evidence_items"]}

    assert "processor_total_percent_time" in signals
    assert "processor_queue_length" in signals
    assert "memory_available_mbytes" in signals
    assert "physical_disk_avg_queue_length" in signals
    assert all(is_valid_windows_evidence_item(item) for item in result["evidence_items"])

    cpu_items = [
        item
        for item in result["evidence_items"]
        if item["signal"] == "processor_total_percent_time"
    ]

    assert cpu_items[0]["value"] == 8.5
    assert cpu_items[0]["raw"]["normalized_path"] == r"\processor(_total)\% processor time"
    assert result["summary"]["status"] == "ok"


def test_collect_windows_performance_counters_formats_timeout_error() -> None:
    def timeout_runner(script: str) -> str:
        raise subprocess.TimeoutExpired(cmd="Get-Counter", timeout=30)

    result = collect_windows_performance_counters(runner=timeout_runner)

    assert result["status"] == "error"
    assert result["errors"] == ["Performance counter query timed out after 30 seconds."]
    assert result["evidence_items"][0]["signal"] == "performance_counter_collection_error"
    assert result["summary"]["status"] == "ok"


def test_default_counter_paths_are_allowlisted() -> None:
    assert APPROVED_COUNTERS

    for counter_path in APPROVED_COUNTERS:
        assert normalize_counter_path(counter_path) in APPROVED_COUNTERS
