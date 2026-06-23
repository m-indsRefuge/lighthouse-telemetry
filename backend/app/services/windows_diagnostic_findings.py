"""
Deterministic Windows diagnostic findings for Lighthouse.

This module converts normalized WindowsEvidenceItem records into compact,
deterministic diagnostic findings.

It does not call the model.
It does not execute tools.
It does not mutate the operating system.
It does not recommend repair commands directly.
"""

from __future__ import annotations

from typing import Any

from app.services.windows_evidence import is_valid_windows_evidence_item


CPU_PERCENT_HIGH = 85.0
PROCESSOR_QUEUE_HIGH = 2.0
MEMORY_AVAILABLE_MBYTES_LOW = 1024.0
MEMORY_PAGES_PER_SECOND_HIGH = 50.0
DISK_QUEUE_HIGH = 2.0
DISK_LATENCY_SECONDS_HIGH = 0.05

READ_ONLY_NEXT_TOOLS = [
    "collect.windows.cim",
    "collect.windows.performance_counters",
    "collect.windows.events",
]


def numeric_value(value: Any) -> float | None:
    """
    Convert a value to float when possible.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evidence_signal(item: dict[str, Any]) -> str:
    """
    Return the signal field from a Windows evidence item.
    """
    return str(item.get("signal") or "").strip()


def evidence_by_signal(
    evidence_items: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Group valid evidence items by signal.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}

    for item in evidence_items:
        if not is_valid_windows_evidence_item(item):
            continue

        signal = evidence_signal(item)

        if not signal:
            continue

        grouped.setdefault(signal, []).append(item)

    return grouped


def first_numeric_signal_value(
    grouped: dict[str, list[dict[str, Any]]],
    signal: str,
) -> float | None:
    """
    Return the first numeric value for a signal.
    """
    for item in grouped.get(signal, []):
        value = numeric_value(item.get("value"))

        if value is not None:
            return value

    return None


def has_signal(
    grouped: dict[str, list[dict[str, Any]]],
    *signals: str,
) -> bool:
    """
    Return true when any signal exists.
    """
    return any(signal in grouped and grouped[signal] for signal in signals)


def supporting_count(
    grouped: dict[str, list[dict[str, Any]]],
    signals: list[str],
) -> int:
    """
    Count evidence records supporting a set of signals.
    """
    return sum(len(grouped.get(signal, [])) for signal in signals)


def build_finding(
    *,
    finding_id: str,
    category: str,
    severity: str,
    confidence: str,
    plain_meaning: str,
    supporting_signals: list[str],
    grouped: dict[str, list[dict[str, Any]]],
    recommended_next_step: str,
    allowed_next_tools: list[str] | None = None,
    permission_required: bool = False,
) -> dict[str, Any]:
    """
    Build a stable deterministic diagnostic finding.
    """
    return {
        "finding_id": finding_id,
        "category": category,
        "severity": severity,
        "confidence": confidence,
        "plain_meaning": plain_meaning,
        "supporting_signals": supporting_signals,
        "supporting_evidence_count": supporting_count(grouped, supporting_signals),
        "recommended_next_step": recommended_next_step,
        "allowed_next_tools": allowed_next_tools or READ_ONLY_NEXT_TOOLS,
        "permission_required": permission_required,
        "safety_note": (
            "This finding supports read-only diagnosis only. "
            "Repair or OS-changing actions require a separate permission gate."
        ),
    }


def detect_cpu_pressure(
    grouped: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    """
    Detect likely CPU pressure from processor counters.
    """
    cpu_percent = first_numeric_signal_value(grouped, "processor_total_percent_time")
    queue_length = first_numeric_signal_value(grouped, "processor_queue_length")

    supporting_signals: list[str] = []

    if cpu_percent is not None and cpu_percent >= CPU_PERCENT_HIGH:
        supporting_signals.append("processor_total_percent_time")

    if queue_length is not None and queue_length >= PROCESSOR_QUEUE_HIGH:
        supporting_signals.append("processor_queue_length")

    if not supporting_signals:
        return None

    confidence = "high" if len(supporting_signals) > 1 else "medium"

    return build_finding(
        finding_id="cpu_pressure_detected",
        category="performance",
        severity="warning",
        confidence=confidence,
        plain_meaning="Processor pressure appears elevated.",
        supporting_signals=supporting_signals,
        grouped=grouped,
        recommended_next_step=(
            "Compare CPU pressure with running processes before recommending action."
        ),
    )


def detect_memory_pressure(
    grouped: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    """
    Detect likely memory pressure from memory counters.
    """
    available_mbytes = first_numeric_signal_value(grouped, "memory_available_mbytes")
    pages_per_second = first_numeric_signal_value(grouped, "memory_pages_per_second")

    supporting_signals: list[str] = []

    if available_mbytes is not None and available_mbytes <= MEMORY_AVAILABLE_MBYTES_LOW:
        supporting_signals.append("memory_available_mbytes")

    if pages_per_second is not None and pages_per_second >= MEMORY_PAGES_PER_SECOND_HIGH:
        supporting_signals.append("memory_pages_per_second")

    if not supporting_signals:
        return None

    confidence = "high" if len(supporting_signals) > 1 else "medium"

    return build_finding(
        finding_id="memory_pressure_detected",
        category="performance",
        severity="warning",
        confidence=confidence,
        plain_meaning="Memory pressure appears elevated.",
        supporting_signals=supporting_signals,
        grouped=grouped,
        recommended_next_step=(
            "Inspect memory-heavy processes and paging behavior before recommending action."
        ),
    )


def detect_storage_pressure(
    grouped: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    """
    Detect storage pressure from disk counters and event evidence.
    """
    disk_queue = first_numeric_signal_value(
        grouped,
        "physical_disk_avg_queue_length",
    )
    read_latency = first_numeric_signal_value(
        grouped,
        "physical_disk_avg_seconds_per_read",
    )
    write_latency = first_numeric_signal_value(
        grouped,
        "physical_disk_avg_seconds_per_write",
    )

    counter_signals: list[str] = []
    event_signals: list[str] = []

    if disk_queue is not None and disk_queue >= DISK_QUEUE_HIGH:
        counter_signals.append("physical_disk_avg_queue_length")

    if read_latency is not None and read_latency >= DISK_LATENCY_SECONDS_HIGH:
        counter_signals.append("physical_disk_avg_seconds_per_read")

    if write_latency is not None and write_latency >= DISK_LATENCY_SECONDS_HIGH:
        counter_signals.append("physical_disk_avg_seconds_per_write")

    for signal in [
        "disk_bad_block_warning",
        "disk_io_warning",
        "disk_io_retry_warning",
        "filesystem_structure_warning",
        "storage_controller_reset_warning",
    ]:
        if has_signal(grouped, signal):
            event_signals.append(signal)

    supporting_signals = counter_signals + event_signals

    if not supporting_signals:
        return None

    confidence = "high" if counter_signals and event_signals else "medium"

    return build_finding(
        finding_id="storage_pressure_detected",
        category="storage",
        severity="warning",
        confidence=confidence,
        plain_meaning="Storage pressure or storage warning evidence is present.",
        supporting_signals=supporting_signals,
        grouped=grouped,
        recommended_next_step=(
            "Correlate disk latency, queue length, and storage events before recommending repair."
        ),
    )


def detect_shutdown_or_crash_evidence(
    grouped: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """
    Detect unexpected shutdown and bugcheck evidence.
    """
    findings: list[dict[str, Any]] = []

    if has_signal(
        grouped,
        "unexpected_shutdown_or_power_loss",
        "unexpected_shutdown_eventlog",
    ):
        signals = [
            signal
            for signal in [
                "unexpected_shutdown_or_power_loss",
                "unexpected_shutdown_eventlog",
            ]
            if has_signal(grouped, signal)
        ]

        findings.append(
            build_finding(
                finding_id="unexpected_shutdown_evidence",
                category="stability",
                severity="warning",
                confidence="high",
                plain_meaning="Windows recorded unexpected shutdown evidence.",
                supporting_signals=signals,
                grouped=grouped,
                recommended_next_step=(
                    "Check nearby BugCheck, WHEA, disk, thermal, and power evidence."
                ),
            )
        )

    if has_signal(grouped, "windows_bugcheck"):
        findings.append(
            build_finding(
                finding_id="windows_bugcheck_evidence",
                category="stability",
                severity="warning",
                confidence="high",
                plain_meaning="Windows recorded blue screen or bugcheck evidence.",
                supporting_signals=["windows_bugcheck"],
                grouped=grouped,
                recommended_next_step=(
                    "Inspect bugcheck context and nearby driver, disk, and WHEA evidence."
                ),
            )
        )

    return findings


def detect_hardware_warning_evidence(
    grouped: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    """
    Detect hardware or firmware warning evidence.
    """
    if not has_signal(grouped, "hardware_or_firmware_warning"):
        return None

    return build_finding(
        finding_id="possible_hardware_or_firmware_instability",
        category="hardware",
        severity="warning",
        confidence="medium",
        plain_meaning=(
            "Windows recorded hardware or firmware warning evidence."
        ),
        supporting_signals=["hardware_or_firmware_warning"],
        grouped=grouped,
        recommended_next_step=(
            "Review BIOS, thermal, driver, and hardware context before recommending action."
        ),
    )


def detect_application_instability(
    grouped: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    """
    Detect application crash or hang evidence.
    """
    signals = [
        signal
        for signal in [
            "application_crash",
            "application_hang",
            "windows_error_reporting_event",
        ]
        if has_signal(grouped, signal)
    ]

    if not signals:
        return None

    return build_finding(
        finding_id="application_instability_detected",
        category="application",
        severity="warning",
        confidence="medium",
        plain_meaning="Windows recorded application crash or hang evidence.",
        supporting_signals=signals,
        grouped=grouped,
        recommended_next_step=(
            "Correlate with CPU, memory, disk pressure, and the affected application."
        ),
    )


def build_no_major_findings(
    grouped: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """
    Build a stable finding when no warning rules are triggered.
    """
    return build_finding(
        finding_id="no_major_windows_findings_detected",
        category="summary",
        severity="info",
        confidence="medium",
        plain_meaning=(
            "No major Windows pressure, crash, storage, hardware, or application "
            "instability findings were detected from the available evidence."
        ),
        supporting_signals=[],
        grouped=grouped,
        recommended_next_step=(
            "Continue with read-only diagnostics if the Operator is still seeing symptoms."
        ),
        allowed_next_tools=READ_ONLY_NEXT_TOOLS,
        permission_required=False,
    )


def build_windows_diagnostic_findings(
    evidence_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Convert normalized Windows evidence into deterministic diagnostic findings.
    """
    grouped = evidence_by_signal(evidence_items)
    findings: list[dict[str, Any]] = []

    for detector in [
        detect_cpu_pressure,
        detect_memory_pressure,
        detect_storage_pressure,
        detect_hardware_warning_evidence,
        detect_application_instability,
    ]:
        finding = detector(grouped)

        if finding is not None:
            findings.append(finding)

    findings.extend(detect_shutdown_or_crash_evidence(grouped))

    if not findings:
        findings.append(build_no_major_findings(grouped))

    return {
        "status": "ok",
        "message": "Windows diagnostic findings generated.",
        "data": {
            "finding_count": len(findings),
            "findings": findings,
        },
        "errors": [],
        "warnings": [],
    }
