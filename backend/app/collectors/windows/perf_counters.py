"""
Read-only Windows Performance Counter collector for Lighthouse.

This collector uses an allowlisted set of safe counter paths and normalizes the
results into WindowsEvidenceItem dictionaries.

It does not accept arbitrary user-supplied counter paths.
It does not execute repair commands.
It does not mutate the operating system.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any, Callable

from app.services.windows_evidence import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_UNKNOWN,
    PRIVACY_LOW,
    STATUS_ERROR,
    STATUS_OK,
    TRUST_TIER_1_READ_ONLY,
    build_windows_evidence_item,
    summarize_windows_evidence,
)


PowerShellRunner = Callable[[str], str]

PERFORMANCE_COUNTER_SOURCE = "performance_counter"
PERFORMANCE_COUNTER_COLLECTOR = "Get-Counter"
DEFAULT_PERFORMANCE_COUNTER_TIMEOUT_SECONDS = 30

APPROVED_COUNTERS: dict[str, tuple[str, str]] = {
    r"\processor(_total)\% processor time": (
        "processor_total_percent_time",
        "Total processor utilization collected from Windows Performance Counters.",
    ),
    r"\system\processor queue length": (
        "processor_queue_length",
        "Processor queue length collected from Windows Performance Counters.",
    ),
    r"\memory\available mbytes": (
        "memory_available_mbytes",
        "Available physical memory in megabytes collected from Windows Performance Counters.",
    ),
    r"\memory\committed bytes": (
        "memory_committed_bytes",
        "Committed memory bytes collected from Windows Performance Counters.",
    ),
    r"\memory\pages/sec": (
        "memory_pages_per_second",
        "Memory pages per second collected from Windows Performance Counters.",
    ),
    r"\physicaldisk(_total)\avg. disk queue length": (
        "physical_disk_avg_queue_length",
        "Average physical disk queue length collected from Windows Performance Counters.",
    ),
    r"\physicaldisk(_total)\avg. disk sec/read": (
        "physical_disk_avg_seconds_per_read",
        "Average disk read latency collected from Windows Performance Counters.",
    ),
    r"\physicaldisk(_total)\avg. disk sec/write": (
        "physical_disk_avg_seconds_per_write",
        "Average disk write latency collected from Windows Performance Counters.",
    ),
    r"\physicaldisk(_total)\disk reads/sec": (
        "physical_disk_reads_per_second",
        "Disk reads per second collected from Windows Performance Counters.",
    ),
    r"\physicaldisk(_total)\disk writes/sec": (
        "physical_disk_writes_per_second",
        "Disk writes per second collected from Windows Performance Counters.",
    ),
    r"\system\system up time": (
        "system_up_time_seconds",
        "System uptime in seconds collected from Windows Performance Counters.",
    ),
}

DEFAULT_COUNTER_PATHS = tuple(APPROVED_COUNTERS.keys())


def escape_powershell_single_quoted(value: str) -> str:
    """
    Escape a string for use inside a PowerShell single-quoted string.
    """
    return value.replace("'", "''")


def build_counter_script(counter_paths: list[str] | tuple[str, ...]) -> str:
    """
    Build a safe, allowlisted PowerShell Get-Counter script.
    """
    escaped_paths = [
        f"'{escape_powershell_single_quoted(counter_path)}'"
        for counter_path in counter_paths
    ]
    powershell_array = "@(" + ", ".join(escaped_paths) + ")"

    return (
        "$ErrorActionPreference = 'Stop'; "
        f"Get-Counter -Counter {powershell_array} -SampleInterval 1 -MaxSamples 1 | "
        "Select-Object -ExpandProperty CounterSamples | "
        "Select-Object Path,CookedValue,InstanceName | "
        "ConvertTo-Json -Depth 4"
    )


def run_powershell_script(
    script: str,
    timeout_seconds: int = DEFAULT_PERFORMANCE_COUNTER_TIMEOUT_SECONDS,
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
        raise RuntimeError(
            completed.stderr.strip() or "PowerShell Get-Counter query failed."
        )

    return completed.stdout.strip()


def parse_counter_json(output: str) -> list[dict[str, Any]]:
    """
    Parse Get-Counter JSON output into a list of dictionaries.
    """
    if not output.strip():
        return []

    parsed = json.loads(output)

    if isinstance(parsed, dict):
        return [parsed]

    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]

    return []


def normalize_counter_path(counter_path: str) -> str:
    """
    Normalize a counter path so local machine prefixes do not affect matching.
    """
    normalized = str(counter_path).strip().replace("/", "\\")

    if normalized.startswith("\\\\"):
        without_prefix = normalized[2:]

        if "\\" in without_prefix:
            normalized = "\\" + without_prefix.split("\\", 1)[1]

    return normalized.lower()


def validate_counter_paths(counter_paths: list[str] | tuple[str, ...]) -> list[str]:
    """
    Return errors for any counter path that is not in the allowlist.
    """
    errors: list[str] = []

    for counter_path in counter_paths:
        normalized_path = normalize_counter_path(counter_path)

        if normalized_path not in APPROVED_COUNTERS:
            errors.append(f"Performance counter is not allowlisted: {counter_path}")

    return errors


def coerce_counter_value(value: Any) -> float | Any:
    """
    Convert numeric counter values to float when possible.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def signal_for_counter_path(counter_path: str) -> tuple[str, str]:
    """
    Return the normalized signal name and plain meaning for a counter path.
    """
    normalized_path = normalize_counter_path(counter_path)

    return APPROVED_COUNTERS.get(
        normalized_path,
        (
            normalized_path.strip("\\").replace("\\", "_").replace(" ", "_"),
            f"{counter_path} collected from Windows Performance Counters.",
        ),
    )


def evidence_item_from_counter_sample(sample: dict[str, Any]) -> dict[str, Any] | None:
    """
    Convert one Get-Counter sample into a normalized Windows evidence item.
    """
    counter_path = sample.get("Path") or sample.get("CounterPath")

    if not counter_path:
        return None

    signal, plain_meaning = signal_for_counter_path(str(counter_path))
    value = coerce_counter_value(sample.get("CookedValue"))
    confidence = CONFIDENCE_LOW if value in {None, ""} else CONFIDENCE_HIGH

    return build_windows_evidence_item(
        source=PERFORMANCE_COUNTER_SOURCE,
        collector=PERFORMANCE_COUNTER_COLLECTOR,
        signal=signal,
        value=value,
        status=STATUS_OK,
        confidence=confidence,
        trust_tier=TRUST_TIER_1_READ_ONLY,
        requires_admin=False,
        privacy=PRIVACY_LOW,
        permission_required=False,
        plain_meaning=plain_meaning,
        raw={
            "path": counter_path,
            "normalized_path": normalize_counter_path(str(counter_path)),
            "instance_name": sample.get("InstanceName"),
        },
    )


def evidence_items_from_counter_samples(
    samples: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convert Get-Counter samples into normalized Windows evidence items.
    """
    evidence_items: list[dict[str, Any]] = []

    for sample in samples:
        item = evidence_item_from_counter_sample(sample)

        if item is not None:
            evidence_items.append(item)

    return evidence_items


def format_counter_collection_error(error: BaseException) -> str:
    """
    Format Performance Counter collection errors for Operator-facing reports.
    """
    if isinstance(error, subprocess.TimeoutExpired):
        timeout = error.timeout if error.timeout is not None else "unknown"
        return f"Performance counter query timed out after {timeout} seconds."

    if isinstance(error, json.JSONDecodeError):
        return f"Performance counter query returned invalid JSON: {error}"

    message = str(error).strip()

    if message:
        return message

    return "Performance counter query failed."


def build_error_evidence_item(error_message: str) -> dict[str, Any]:
    """
    Build an error evidence item for a failed counter collection run.
    """
    return build_windows_evidence_item(
        source=PERFORMANCE_COUNTER_SOURCE,
        collector=PERFORMANCE_COUNTER_COLLECTOR,
        signal="performance_counter_collection_error",
        value=None,
        status=STATUS_ERROR,
        confidence=CONFIDENCE_UNKNOWN,
        trust_tier=TRUST_TIER_1_READ_ONLY,
        requires_admin=False,
        privacy=PRIVACY_LOW,
        permission_required=False,
        plain_meaning="Lighthouse could not collect Windows Performance Counter evidence.",
        errors=[error_message],
    )


def collect_windows_performance_counters(
    *,
    counter_paths: list[str] | tuple[str, ...] | None = None,
    runner: PowerShellRunner | None = None,
) -> dict[str, Any]:
    """
    Collect safe Tier 1 Windows performance pressure evidence.
    """
    selected_counter_paths = tuple(counter_paths or DEFAULT_COUNTER_PATHS)
    validation_errors = validate_counter_paths(selected_counter_paths)

    if validation_errors:
        return {
            "status": "invalid",
            "message": "Performance counter collection rejected invalid counter paths.",
            "source": PERFORMANCE_COUNTER_SOURCE,
            "counter_paths": list(selected_counter_paths),
            "evidence_items": [],
            "summary": summarize_windows_evidence([]),
            "errors": validation_errors,
            "warnings": [],
        }

    selected_runner = runner or run_powershell_script
    script = build_counter_script(selected_counter_paths)

    try:
        output = selected_runner(script)
        samples = parse_counter_json(output)
        evidence_items = evidence_items_from_counter_samples(samples)

        return {
            "status": "ok",
            "message": "Performance counter evidence collection completed.",
            "source": PERFORMANCE_COUNTER_SOURCE,
            "counter_paths": list(selected_counter_paths),
            "sample_count": len(samples),
            "evidence_items": evidence_items,
            "summary": summarize_windows_evidence(evidence_items),
            "errors": [],
            "warnings": [],
        }
    except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        error_message = format_counter_collection_error(error)
        error_item = build_error_evidence_item(error_message)

        return {
            "status": "error",
            "message": "Performance counter evidence collection failed.",
            "source": PERFORMANCE_COUNTER_SOURCE,
            "counter_paths": list(selected_counter_paths),
            "sample_count": 0,
            "evidence_items": [error_item],
            "summary": summarize_windows_evidence([error_item]),
            "errors": [error_message],
            "warnings": [],
        }
