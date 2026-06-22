"""
Human-readable Windows evidence report formatter for Lighthouse.

This formats normalized Windows evidence items into an Operator-facing report.
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
    default: str = "Unknown",
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
            f"- {display_device_id}{separator} free {bytes_to_gb(free)} of {bytes_to_gb(size)} "
            f"({file_system})"
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


def format_windows_evidence_report(result: dict[str, Any]) -> str:
    """
    Format Windows-native CIM evidence for the Operator.
    """
    items = result.get("evidence_items", [])
    errors = result.get("errors", [])
    warnings = result.get("warnings", [])
    summary = result.get("summary", {})
    summary_data = summary.get("data", {}) if isinstance(summary, dict) else {}

    if not isinstance(items, list):
        items = []

    lines = [
        "LIGHTHOUSE WINDOWS EVIDENCE",
        "-" * 52,
        f"Status: {result.get('status', 'unknown')}",
        f"Message: {result.get('message', 'No message returned.')}",
        f"Source: {result.get('source', 'unknown')}",
        f"Evidence items: {len(items)}",
        f"Warnings: {len(warnings) if isinstance(warnings, list) else 0}",
        f"Errors: {len(errors) if isinstance(errors, list) else 0}",
    ]

    if summary_data:
        lines.append(f"Schema valid: {summary_data.get('valid', 'unknown')}")

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

    if warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in warnings)

    if errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"- {error}" for error in errors)

    return "\n".join(lines)
