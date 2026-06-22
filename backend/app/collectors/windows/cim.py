"""
Read-only Windows CIM collector for Lighthouse.

This collector uses an allowlisted set of safe CIM classes and normalizes the
results into WindowsEvidenceItem dictionaries.

It does not accept arbitrary user-supplied CIM classes.
It does not execute repair commands.
It does not mutate the operating system.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any, Callable

from app.services.windows_evidence import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_UNKNOWN,
    PRIVACY_LOW,
    PRIVACY_MEDIUM,
    STATUS_ERROR,
    STATUS_OK,
    TRUST_TIER_1_READ_ONLY,
    build_windows_evidence_item,
    summarize_windows_evidence,
)


PowerShellRunner = Callable[[str], str]

CIM_SOURCE = "cim"
DEFAULT_CIM_TIMEOUT_SECONDS = 45

APPROVED_CIM_CLASS_PROPERTIES: dict[str, list[str]] = {
    "Win32_OperatingSystem": [
        "Caption",
        "Version",
        "BuildNumber",
        "LastBootUpTime",
        "OSArchitecture",
    ],
    "Win32_ComputerSystem": [
        "Manufacturer",
        "Model",
        "SystemType",
        "TotalPhysicalMemory",
    ],
    "Win32_BIOS": [
        "Manufacturer",
        "SMBIOSBIOSVersion",
        "ReleaseDate",
    ],
    "Win32_Processor": [
        "Name",
        "NumberOfCores",
        "NumberOfLogicalProcessors",
        "MaxClockSpeed",
    ],
    "Win32_LogicalDisk": [
        "DeviceID",
        "DriveType",
        "Size",
        "FreeSpace",
        "FileSystem",
    ],
    "Win32_PhysicalMemory": [
        "Manufacturer",
        "Capacity",
        "Speed",
    ],
}

PROPERTY_SIGNAL_MAP: dict[tuple[str, str], tuple[str, str]] = {
    ("Win32_OperatingSystem", "Caption"): (
        "os_caption",
        "Windows operating system caption collected from CIM.",
    ),
    ("Win32_OperatingSystem", "Version"): (
        "os_version",
        "Windows operating system version collected from CIM.",
    ),
    ("Win32_OperatingSystem", "BuildNumber"): (
        "os_build_number",
        "Windows build number collected from CIM.",
    ),
    ("Win32_OperatingSystem", "LastBootUpTime"): (
        "last_boot_time",
        "Windows last boot time collected from CIM.",
    ),
    ("Win32_OperatingSystem", "OSArchitecture"): (
        "os_architecture",
        "Windows operating system architecture collected from CIM.",
    ),
    ("Win32_ComputerSystem", "Manufacturer"): (
        "computer_manufacturer",
        "Computer manufacturer collected from CIM.",
    ),
    ("Win32_ComputerSystem", "Model"): (
        "computer_model",
        "Computer model collected from CIM.",
    ),
    ("Win32_ComputerSystem", "SystemType"): (
        "computer_system_type",
        "Computer system type collected from CIM.",
    ),
    ("Win32_ComputerSystem", "TotalPhysicalMemory"): (
        "computer_total_physical_memory_bytes",
        "Total physical memory reported by the computer system CIM class.",
    ),
    ("Win32_BIOS", "Manufacturer"): (
        "bios_manufacturer",
        "BIOS manufacturer collected from CIM.",
    ),
    ("Win32_BIOS", "SMBIOSBIOSVersion"): (
        "bios_version",
        "BIOS version collected from CIM.",
    ),
    ("Win32_BIOS", "ReleaseDate"): (
        "bios_release_date",
        "BIOS release date collected from CIM.",
    ),
    ("Win32_Processor", "Name"): (
        "processor_name",
        "Processor name collected from CIM.",
    ),
    ("Win32_Processor", "NumberOfCores"): (
        "processor_core_count",
        "Processor physical core count collected from CIM.",
    ),
    ("Win32_Processor", "NumberOfLogicalProcessors"): (
        "processor_logical_count",
        "Processor logical processor count collected from CIM.",
    ),
    ("Win32_Processor", "MaxClockSpeed"): (
        "processor_max_clock_speed_mhz",
        "Processor maximum clock speed collected from CIM.",
    ),
    ("Win32_LogicalDisk", "DeviceID"): (
        "logical_disk_device_id",
        "Logical disk device id collected from CIM.",
    ),
    ("Win32_LogicalDisk", "DriveType"): (
        "logical_disk_drive_type",
        "Logical disk drive type collected from CIM.",
    ),
    ("Win32_LogicalDisk", "Size"): (
        "logical_disk_size_bytes",
        "Logical disk size collected from CIM.",
    ),
    ("Win32_LogicalDisk", "FreeSpace"): (
        "logical_disk_free_space_bytes",
        "Logical disk free space collected from CIM.",
    ),
    ("Win32_LogicalDisk", "FileSystem"): (
        "logical_disk_file_system",
        "Logical disk file system collected from CIM.",
    ),
    ("Win32_PhysicalMemory", "Manufacturer"): (
        "physical_memory_manufacturer",
        "Physical memory module manufacturer collected from CIM.",
    ),
    ("Win32_PhysicalMemory", "Capacity"): (
        "physical_memory_capacity_bytes",
        "Physical memory module capacity collected from CIM.",
    ),
    ("Win32_PhysicalMemory", "Speed"): (
        "physical_memory_speed_mhz",
        "Physical memory module speed collected from CIM.",
    ),
}


def build_cim_script(class_name: str, properties: list[str]) -> str:
    """
    Build a safe, allowlisted PowerShell CIM query script.
    """
    property_list = ",".join(properties)

    return (
        "$ErrorActionPreference = 'Stop'; "
        f"Get-CimInstance -ClassName {class_name} | "
        f"Select-Object {property_list} | "
        "ConvertTo-Json -Depth 4"
    )


def run_powershell_script(
    script: str,
    timeout_seconds: int = DEFAULT_CIM_TIMEOUT_SECONDS,
) -> str:
    """
    Run a read-only PowerShell script and return stdout.
    """
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "PowerShell CIM query failed.")

    return completed.stdout.strip()


def parse_cim_json(output: str) -> list[dict[str, Any]]:
    """
    Parse CIM JSON output into a list of dictionaries.
    """
    if not output.strip():
        return []

    parsed = json.loads(output)

    if isinstance(parsed, dict):
        return [parsed]

    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]

    return []


def signal_for_property(class_name: str, property_name: str) -> tuple[str, str]:
    """
    Return the normalized signal name and plain meaning for a CIM property.
    """
    return PROPERTY_SIGNAL_MAP.get(
        (class_name, property_name),
        (
            f"{class_name.lower()}_{property_name.lower()}",
            f"{property_name} collected from {class_name} through CIM.",
        ),
    )


def evidence_items_from_cim_record(
    *,
    class_name: str,
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Convert one CIM record into normalized Windows evidence items.
    """
    items: list[dict[str, Any]] = []
    properties = APPROVED_CIM_CLASS_PROPERTIES.get(class_name, [])

    for property_name in properties:
        if property_name not in record:
            continue

        signal, plain_meaning = signal_for_property(class_name, property_name)
        value = record.get(property_name)
        privacy = PRIVACY_MEDIUM if class_name in {"Win32_ComputerSystem"} else PRIVACY_LOW
        confidence = CONFIDENCE_MEDIUM if value in {None, ""} else CONFIDENCE_HIGH

        items.append(
            build_windows_evidence_item(
                source=CIM_SOURCE,
                collector=class_name,
                signal=signal,
                value=value,
                status=STATUS_OK,
                confidence=confidence,
                trust_tier=TRUST_TIER_1_READ_ONLY,
                requires_admin=False,
                privacy=privacy,
                permission_required=False,
                plain_meaning=plain_meaning,
                raw={
                    "class_name": class_name,
                    "property": property_name,
                },
            )
        )

    return items


def format_cim_collection_error(class_name: str, error: BaseException) -> str:
    """
    Format CIM collection errors for Operator-facing reports.
    """
    if isinstance(error, subprocess.TimeoutExpired):
        timeout = error.timeout if error.timeout is not None else "unknown"
        return f"CIM query timed out for {class_name} after {timeout} seconds."

    if isinstance(error, json.JSONDecodeError):
        return f"CIM query returned invalid JSON for {class_name}: {error}"

    message = str(error).strip()

    if message:
        return message

    return f"CIM query failed for {class_name}."


def collect_cim_class_evidence(
    *,
    class_name: str,
    runner: PowerShellRunner | None = None,
) -> dict[str, Any]:
    """
    Collect evidence for one allowlisted CIM class.
    """
    if class_name not in APPROVED_CIM_CLASS_PROPERTIES:
        return {
            "status": "invalid",
            "class_name": class_name,
            "evidence_items": [],
            "errors": [f"CIM class is not allowlisted: {class_name}"],
            "warnings": [],
        }

    selected_runner = runner or run_powershell_script
    properties = APPROVED_CIM_CLASS_PROPERTIES[class_name]
    script = build_cim_script(class_name, properties)

    try:
        output = selected_runner(script)
        records = parse_cim_json(output)
        evidence_items: list[dict[str, Any]] = []

        for record in records:
            evidence_items.extend(
                evidence_items_from_cim_record(
                    class_name=class_name,
                    record=record,
                )
            )

        return {
            "status": "ok",
            "class_name": class_name,
            "record_count": len(records),
            "evidence_items": evidence_items,
            "errors": [],
            "warnings": [],
        }
    except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        error_message = format_cim_collection_error(class_name, error)
        error_item = build_windows_evidence_item(
            source=CIM_SOURCE,
            collector=class_name,
            signal="cim_collection_error",
            value=None,
            status=STATUS_ERROR,
            confidence=CONFIDENCE_UNKNOWN,
            trust_tier=TRUST_TIER_1_READ_ONLY,
            requires_admin=False,
            privacy=PRIVACY_LOW,
            permission_required=False,
            plain_meaning=f"Lighthouse could not collect {class_name} CIM evidence.",
            errors=[error_message],
            raw={"class_name": class_name},
        )

        return {
            "status": "error",
            "class_name": class_name,
            "record_count": 0,
            "evidence_items": [error_item],
            "errors": [error_message],
            "warnings": [],
        }


def collect_windows_cim_evidence(
    *,
    runner: PowerShellRunner | None = None,
) -> dict[str, Any]:
    """
    Collect safe Tier 1 Windows-native evidence through approved CIM classes.
    """
    class_results: list[dict[str, Any]] = []
    evidence_items: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    for class_name in APPROVED_CIM_CLASS_PROPERTIES:
        class_result = collect_cim_class_evidence(
            class_name=class_name,
            runner=runner,
        )
        class_results.append(class_result)
        evidence_items.extend(class_result.get("evidence_items", []))
        errors.extend(class_result.get("errors", []))
        warnings.extend(class_result.get("warnings", []))

    if errors and evidence_items:
        status = "partial"
        message = "CIM evidence collection completed with errors."
    elif errors:
        status = "error"
        message = "CIM evidence collection failed."
    else:
        status = "ok"
        message = "CIM evidence collection completed."

    return {
        "status": status,
        "message": message,
        "source": CIM_SOURCE,
        "class_results": class_results,
        "evidence_items": evidence_items,
        "summary": summarize_windows_evidence(evidence_items),
        "errors": errors,
        "warnings": warnings,
    }
