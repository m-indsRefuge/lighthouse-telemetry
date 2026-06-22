"""
Tests for Windows CIM collector.
"""

from pathlib import Path
import json
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.collectors.windows.cim import (
    APPROVED_CIM_CLASS_PROPERTIES,
    build_cim_script,
    collect_cim_class_evidence,
    collect_windows_cim_evidence,
    normalize_cim_json_date,
    normalize_cim_value,
    parse_cim_json,
)
from app.services.windows_evidence import is_valid_windows_evidence_item


def fake_cim_runner(script: str) -> str:
    if "Win32_OperatingSystem" in script:
        return json.dumps(
            {
                "Caption": "Microsoft Windows 11 Pro",
                "Version": "10.0.22631",
                "BuildNumber": "22631",
                "LastBootUpTime": "/Date(1781948273961)/",
                "OSArchitecture": "64-bit",
            }
        )

    if "Win32_ComputerSystem" in script:
        return json.dumps(
            {
                "Manufacturer": "Example Manufacturer",
                "Model": "Example Model",
                "SystemType": "x64-based PC",
                "TotalPhysicalMemory": 34359738368,
            }
        )

    if "Win32_BIOS" in script:
        return json.dumps(
            {
                "Manufacturer": "Example BIOS",
                "SMBIOSBIOSVersion": "1.0.0",
                "ReleaseDate": "/Date(1736899200000)/",
            }
        )

    if "Win32_Processor" in script:
        return json.dumps(
            {
                "Name": "Example CPU",
                "NumberOfCores": 20,
                "NumberOfLogicalProcessors": 28,
                "MaxClockSpeed": 2100,
            }
        )

    if "Win32_LogicalDisk" in script:
        return json.dumps(
            [
                {
                    "DeviceID": "C:",
                    "DriveType": 3,
                    "Size": 1024,
                    "FreeSpace": 512,
                    "FileSystem": "NTFS",
                }
            ]
        )

    if "Win32_PhysicalMemory" in script:
        return json.dumps(
            [
                {
                    "Manufacturer": "Example RAM",
                    "Capacity": 17179869184,
                    "Speed": 5600,
                },
                {
                    "Manufacturer": "Example RAM",
                    "Capacity": 17179869184,
                    "Speed": 5600,
                },
            ]
        )

    raise RuntimeError(f"Unexpected script: {script}")


def test_build_cim_script_uses_allowlisted_class_and_properties() -> None:
    script = build_cim_script(
        "Win32_OperatingSystem",
        APPROVED_CIM_CLASS_PROPERTIES["Win32_OperatingSystem"],
    )

    assert "Get-CimInstance -ClassName Win32_OperatingSystem" in script
    assert "Caption,Version,BuildNumber,LastBootUpTime,OSArchitecture" in script
    assert "ConvertTo-Json" in script


def test_parse_cim_json_accepts_single_object() -> None:
    records = parse_cim_json('{"Caption": "Windows"}')

    assert records == [{"Caption": "Windows"}]


def test_parse_cim_json_accepts_list_of_objects() -> None:
    records = parse_cim_json('[{"Name": "A"}, {"Name": "B"}]')

    assert records == [{"Name": "A"}, {"Name": "B"}]


def test_normalize_cim_json_date_converts_powershell_json_date() -> None:
    normalized = normalize_cim_json_date("/Date(1736899200000)/")

    assert normalized == "2025-01-15T00:00:00+00:00"


def test_normalize_cim_json_date_preserves_non_matching_string() -> None:
    assert normalize_cim_json_date("2026-06-22T08:13:00") == "2026-06-22T08:13:00"


def test_normalize_cim_value_only_changes_cim_json_dates() -> None:
    assert normalize_cim_value("/Date(1736899200000)/") == "2025-01-15T00:00:00+00:00"
    assert normalize_cim_value("LENOVO") == "LENOVO"
    assert normalize_cim_value(20) == 20


def test_collect_cim_class_evidence_rejects_unapproved_class() -> None:
    result = collect_cim_class_evidence(
        class_name="Win32_Process",
        runner=fake_cim_runner,
    )

    assert result["status"] == "invalid"
    assert result["evidence_items"] == []
    assert "CIM class is not allowlisted" in result["errors"][0]


def test_collect_cim_class_evidence_returns_normalized_items() -> None:
    result = collect_cim_class_evidence(
        class_name="Win32_OperatingSystem",
        runner=fake_cim_runner,
    )

    assert result["status"] == "ok"
    assert result["record_count"] == 1

    signals = {item["signal"] for item in result["evidence_items"]}

    assert "os_caption" in signals
    assert "os_version" in signals
    assert "last_boot_time" in signals
    assert all(is_valid_windows_evidence_item(item) for item in result["evidence_items"])

    last_boot_items = [
        item
        for item in result["evidence_items"]
        if item["signal"] == "last_boot_time"
    ]
    assert last_boot_items[0]["value"] == "2026-06-20T09:37:53.961000+00:00"
    assert last_boot_items[0]["raw"]["raw_value"] == "/Date(1781948273961)/"


def test_collect_windows_cim_evidence_collects_all_approved_classes() -> None:
    result = collect_windows_cim_evidence(runner=fake_cim_runner)

    assert result["status"] == "ok"
    assert result["source"] == "cim"
    assert len(result["class_results"]) == len(APPROVED_CIM_CLASS_PROPERTIES)
    assert result["errors"] == []

    signals = {item["signal"] for item in result["evidence_items"]}

    assert "os_caption" in signals
    assert "computer_model" in signals
    assert "bios_version" in signals
    assert "processor_name" in signals
    assert "logical_disk_free_space_bytes" in signals
    assert "physical_memory_capacity_bytes" in signals
    assert result["summary"]["status"] == "ok"

    bios_release_items = [
        item
        for item in result["evidence_items"]
        if item["signal"] == "bios_release_date"
    ]
    assert bios_release_items[0]["value"] == "2025-01-15T00:00:00+00:00"


def test_collect_windows_cim_evidence_handles_partial_errors() -> None:
    def partly_failing_runner(script: str) -> str:
        if "Win32_BIOS" in script:
            raise RuntimeError("CIM failure")

        return fake_cim_runner(script)

    result = collect_windows_cim_evidence(runner=partly_failing_runner)

    assert result["status"] == "partial"
    assert "CIM failure" in result["errors"]
    assert any(
        item["signal"] == "cim_collection_error"
        and item["collector"] == "Win32_BIOS"
        for item in result["evidence_items"]
    )
    assert result["summary"]["data"]["total_items"] > 0


def test_collect_cim_class_evidence_formats_timeout_error() -> None:
    def timeout_runner(script: str) -> str:
        raise subprocess.TimeoutExpired(cmd="Get-CimInstance", timeout=45)

    result = collect_cim_class_evidence(
        class_name="Win32_OperatingSystem",
        runner=timeout_runner,
    )

    assert result["status"] == "error"
    assert result["errors"] == [
        "CIM query timed out for Win32_OperatingSystem after 45 seconds."
    ]
    assert result["evidence_items"][0]["signal"] == "cim_collection_error"
    assert result["evidence_items"][0]["errors"] == [
        "CIM query timed out for Win32_OperatingSystem after 45 seconds."
    ]
