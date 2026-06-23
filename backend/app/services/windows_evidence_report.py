"""
Human-readable Windows evidence report formatter for Lighthouse.

This formats Windows evidence into an Operator-facing report.

It supports two safe report shapes:

1. CIM-only evidence
2. Aggregated Windows evidence with deterministic findings

It does not collect telemetry by itself.
It does not call the model.
It does not execute tools.
It does not mutate the operating system.
"""

from __future__ import annotations

from typing import Any


def signal_values(items: list[dict[str, Any]], signal: str) -> list[Any]:
    """
    Return all values for a normalized evidence signal.
    """
    return [
        item.get("value")
        for item in items
        if item.get("signal") == signal
    ]


def first_signal_value(
    items: list[dict[str, Any]],
    signal: str,
    default: Any = "Unknown",
) -> Any:
    """
    Return the first value for a signal, or a default.
    """
    values = signal_values(items, signal)

    if not values:
        return default

    value = values[0]

    if value in {None, ""}:
        return default

    return value


def bytes_to_gb(value: Any) -> str:
    """
    Convert a byte value into a readable GB string.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Unknown"

    return f"{number / (1024 ** 3):.2f} GB"


def format_number(value: Any, suffix: str = "", decimals: int = 2) -> str:
    """
    Format a number for Operator-facing output.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Unknown"

    return f"{number:.{decimals}f}{suffix}"


def format_seconds(value: Any) -> str:
    """
    Format seconds as milliseconds when useful.
    """
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return "Unknown"

    return f"{seconds * 1000:.2f} ms"


def format_disk_lines(items: list[dict[str, Any]]) -> list[str]:
    """
    Build readable disk lines from logical disk CIM evidence.
    """
    device_ids = signal_values(items, "logical_disk_device_id")
    sizes = signal_values(items, "logical_disk_size_bytes")
    free_values = signal_values(items, "logical_disk_free_space_bytes")
    file_systems = signal_values(items, "logical_disk_file_system")

    lines: list[str] = []

    for index, device_id in enumerate(device_ids):
        size = sizes[index] if index < len(sizes) else None
        free = free_values[index] if index < len(free_values) else None
        file_system = file_systems[index] if index < len(file_systems) else "Unknown"
        display_device_id = str(device_id).strip() if device_id else "Unknown"
        separator = "" if display_device_id.endswith(":") else ":"

        lines.append(
            f"- {display_device_id}{separator} free {bytes_to_gb(free)} "
            f"of {bytes_to_gb(size)} ({file_system})"
        )

    if not lines:
        lines.append("- No logical disk evidence available.")

    return lines


def format_memory_module_lines(items: list[dict[str, Any]]) -> list[str]:
    """
    Build readable physical memory module lines from CIM evidence.
    """
    capacities = signal_values(items, "physical_memory_capacity_bytes")
    speeds = signal_values(items, "physical_memory_speed_mhz")
    manufacturers = signal_values(items, "physical_memory_manufacturer")

    lines: list[str] = []

    for index, capacity in enumerate(capacities):
        speed = speeds[index] if index < len(speeds) else "Unknown"
        manufacturer = (
            manufacturers[index]
            if index < len(manufacturers)
            else "Unknown"
        )

        lines.append(
            f"- {manufacturer}: {bytes_to_gb(capacity)} at {speed} MHz"
        )

    if not lines:
        lines.append("- No physical memory module evidence available.")

    return lines


def format_collector_lines(result: dict[str, Any]) -> list[str]:
    """
    Build collector summary lines from an aggregated Windows evidence result.
    """
    collector_results = result.get("collector_results", [])

    if not isinstance(collector_results, list) or not collector_results:
        return ["- No collector summary available."]

    lines: list[str] = []

    for collector in collector_results:
        if not isinstance(collector, dict):
            continue

        name = collector.get("collector", "unknown")
        status = collector.get("status", "unknown")
        count = collector.get("evidence_count", 0)

        lines.append(f"- {name}: {status} ({count} evidence items)")

    if not lines:
        lines.append("- No collector summary available.")

    return lines


def format_performance_counter_lines(items: list[dict[str, Any]]) -> list[str]:
    """
    Build performance counter summary lines.
    """
    return [
        (
            "- CPU total time: "
            f"{format_number(first_signal_value(items, 'processor_total_percent_time', None), '%')}"
        ),
        (
            "- Processor queue length: "
            f"{format_number(first_signal_value(items, 'processor_queue_length', None))}"
        ),
        (
            "- Memory available: "
            f"{format_number(first_signal_value(items, 'memory_available_mbytes', None), ' MB')}"
        ),
        (
            "- Memory pages/sec: "
            f"{format_number(first_signal_value(items, 'memory_pages_per_second', None))}"
        ),
        (
            "- Disk queue length: "
            f"{format_number(first_signal_value(items, 'physical_disk_avg_queue_length', None))}"
        ),
        (
            "- Disk read latency: "
            f"{format_seconds(first_signal_value(items, 'physical_disk_avg_seconds_per_read', None))}"
        ),
        (
            "- Disk write latency: "
            f"{format_seconds(first_signal_value(items, 'physical_disk_avg_seconds_per_write', None))}"
        ),
    ]


def count_signals(items: list[dict[str, Any]], signals: list[str]) -> int:
    """
    Count evidence records matching a set of signals.
    """
    return sum(len(signal_values(items, signal)) for signal in signals)


def format_event_evidence_lines(items: list[dict[str, Any]]) -> list[str]:
    """
    Build Windows event evidence summary lines.
    """
    unexpected_shutdown_count = count_signals(
        items,
        [
            "unexpected_shutdown_or_power_loss",
            "unexpected_shutdown_eventlog",
        ],
    )
    bugcheck_count = count_signals(items, ["windows_bugcheck"])
    hardware_warning_count = count_signals(items, ["hardware_or_firmware_warning"])
    storage_warning_count = count_signals(
        items,
        [
            "disk_bad_block_warning",
            "disk_io_warning",
            "disk_io_retry_warning",
            "filesystem_structure_warning",
            "storage_controller_reset_warning",
        ],
    )
    application_instability_count = count_signals(
        items,
        [
            "application_crash",
            "application_hang",
            "windows_error_reporting_event",
        ],
    )

    return [
        f"- Unexpected shutdown evidence: {unexpected_shutdown_count}",
        f"- BugCheck evidence: {bugcheck_count}",
        f"- Hardware/firmware warning evidence: {hardware_warning_count}",
        f"- Storage warning evidence: {storage_warning_count}",
        f"- Application instability evidence: {application_instability_count}",
    ]


def format_findings_lines(findings_result: dict[str, Any] | None) -> list[str]:
    """
    Build deterministic diagnostic finding lines.
    """
    if not isinstance(findings_result, dict):
        return ["- Findings were not generated."]

    data = findings_result.get("data", {})

    if not isinstance(data, dict):
        return ["- Findings were not generated."]

    findings = data.get("findings", [])

    if not isinstance(findings, list) or not findings:
        return ["- No findings returned."]

    lines: list[str] = []

    for finding in findings:
        if not isinstance(finding, dict):
            continue

        finding_id = finding.get("finding_id", "unknown_finding")
        severity = finding.get("severity", "unknown")
        confidence = finding.get("confidence", "unknown")
        plain_meaning = finding.get("plain_meaning", "No explanation returned.")
        next_step = finding.get("recommended_next_step", "No next step returned.")
        permission_required = finding.get("permission_required", False)

        lines.append(f"- {finding_id} [{severity}, {confidence}]")
        lines.append(f"  Meaning: {plain_meaning}")
        lines.append(f"  Next step: {next_step}")
        lines.append(f"  Permission required: {'yes' if permission_required else 'no'}")

    if not lines:
        lines.append("- No findings returned.")

    return lines


def format_windows_evidence_report(
    result: dict[str, Any],
    findings_result: dict[str, Any] | None = None,
) -> str:
    """
    Format Windows-native evidence for the Operator.
    """
    items = result.get("evidence_items", [])
    errors = result.get("errors", [])
    warnings = result.get("warnings", [])
    summary = result.get("summary", {})
    summary_data = summary.get("data", {}) if isinstance(summary, dict) else {}

    if not isinstance(items, list):
        items = []

    if not isinstance(errors, list):
        errors = []

    if not isinstance(warnings, list):
        warnings = []

    is_aggregated_report = bool(result.get("collector_results")) or findings_result is not None

    lines = [
        "LIGHTHOUSE WINDOWS EVIDENCE",
        "-" * 52,
        f"Status: {result.get('status', 'unknown')}",
        f"Message: {result.get('message', 'No message returned.')}",
        f"Source: {result.get('source', 'aggregated_windows_evidence')}",
        f"Evidence items: {len(items)}",
        f"Warnings: {len(warnings)}",
        f"Errors: {len(errors)}",
    ]

    if summary_data:
        lines.append(f"Schema valid: {summary_data.get('valid', 'unknown')}")

    if is_aggregated_report:
        lines.extend(
            [
                "",
                "Collectors:",
            ]
        )
        lines.extend(format_collector_lines(result))

    lines.extend(
        [
            "",
            "Operating system:",
            f"- Caption: {first_signal_value(items, 'os_caption')}",
            f"- Version: {first_signal_value(items, 'os_version')}",
            f"- Build: {first_signal_value(items, 'os_build_number')}",
            f"- Architecture: {first_signal_value(items, 'os_architecture')}",
            f"- Last boot: {first_signal_value(items, 'last_boot_time')}",
            "",
            "Computer:",
            f"- Manufacturer: {first_signal_value(items, 'computer_manufacturer')}",
            f"- Model: {first_signal_value(items, 'computer_model')}",
            f"- System type: {first_signal_value(items, 'computer_system_type')}",
            (
                "- Total physical memory: "
                f"{bytes_to_gb(first_signal_value(items, 'computer_total_physical_memory_bytes', None))}"
            ),
            "",
            "Processor:",
            f"- Name: {first_signal_value(items, 'processor_name')}",
            f"- Cores: {first_signal_value(items, 'processor_core_count')}",
            f"- Logical processors: {first_signal_value(items, 'processor_logical_count')}",
            (
                "- Max clock speed: "
                f"{first_signal_value(items, 'processor_max_clock_speed_mhz')} MHz"
            ),
            "",
            "BIOS:",
            f"- Manufacturer: {first_signal_value(items, 'bios_manufacturer')}",
            f"- Version: {first_signal_value(items, 'bios_version')}",
            f"- Release date: {first_signal_value(items, 'bios_release_date')}",
            "",
            "Logical disks:",
        ]
    )

    lines.extend(format_disk_lines(items))

    lines.extend(
        [
            "",
            "Physical memory modules:",
        ]
    )
    lines.extend(format_memory_module_lines(items))

    if is_aggregated_report:
        lines.extend(
            [
                "",
                "Performance counters:",
            ]
        )
        lines.extend(format_performance_counter_lines(items))

        lines.extend(
            [
                "",
                "Recent Windows event evidence:",
            ]
        )
        lines.extend(format_event_evidence_lines(items))

        lines.extend(
            [
                "",
                "Deterministic findings:",
            ]
        )
        lines.extend(format_findings_lines(findings_result))

    if warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in warnings)

    if errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"- {error}" for error in errors)

    return "\n".join(lines)
