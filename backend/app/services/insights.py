"""
Insight engine for Lighthouse.

Turns raw telemetry and event-log evidence into a plain-English assessment.

This module does not collect data and does not modify the system.
It only interprets already-collected read-only information.
"""

from typing import Any


def classify_percent(value: Any, warning_at: float, critical_at: float) -> str:
    """
    Convert a percentage value into a simple status label.
    """
    try:
        percent = float(value)
    except (TypeError, ValueError):
        return "UNKNOWN"

    if percent >= critical_at:
        return "CRITICAL"

    if percent >= warning_at:
        return "WARNING"

    return "OK"


def get_top_memory_process(telemetry: dict[str, Any]) -> dict[str, Any] | None:
    """
    Return the highest memory process from telemetry, if available.
    """
    processes = telemetry.get("processes", {})
    process_list = processes.get("processes", [])

    if not process_list:
        return None

    return process_list[0]


def build_system_insight(
    telemetry: dict[str, Any],
    event_report: dict[str, Any],
) -> dict[str, Any]:
    """
    Build a plain-English system insight from telemetry and event evidence.
    """
    cpu = telemetry.get("cpu", {})
    memory = telemetry.get("memory", {})
    disk = telemetry.get("disk", {})

    cpu_status = classify_percent(cpu.get("usage_percent"), 75, 90)
    memory_status = classify_percent(memory.get("usage_percent"), 80, 90)
    disk_status = classify_percent(disk.get("usage_percent"), 80, 90)

    event_status = event_report.get("status", "unknown")
    severity_summary = event_report.get("severity_summary", {})

    critical_events = severity_summary.get("critical", 0)
    warning_events = severity_summary.get("warning", 0)
    context_events = severity_summary.get("context", 0)

    findings: list[str] = []
    recommendations: list[str] = []

    has_live_pressure = any(
        status in {"WARNING", "CRITICAL"}
        for status in {cpu_status, memory_status, disk_status}
    )

    has_event_pressure = critical_events > 0 or warning_events > 0

    if cpu_status == "OK":
        findings.append(f"CPU usage is healthy at {cpu.get('usage_percent', 'Unknown')}%.")
    elif cpu_status == "WARNING":
        findings.append(f"CPU usage is elevated at {cpu.get('usage_percent', 'Unknown')}%.")
        recommendations.append("Check the processes report for high CPU usage.")
    elif cpu_status == "CRITICAL":
        findings.append(f"CPU usage is critically high at {cpu.get('usage_percent', 'Unknown')}%.")
        recommendations.append("Close heavy applications or inspect high CPU processes.")

    if memory_status == "OK":
        findings.append(
            f"Memory usage is healthy at {memory.get('usage_percent', 'Unknown')}%."
        )
    elif memory_status == "WARNING":
        findings.append(
            f"Memory usage is elevated at {memory.get('usage_percent', 'Unknown')}%."
        )
        recommendations.append("Close unused applications or browser tabs.")
    elif memory_status == "CRITICAL":
        findings.append(
            f"Memory usage is critically high at {memory.get('usage_percent', 'Unknown')}%."
        )
        recommendations.append("Close memory-heavy applications and recheck the system.")

    if disk_status == "OK":
        findings.append(f"Disk usage is healthy at {disk.get('usage_percent', 'Unknown')}%.")
    elif disk_status == "WARNING":
        findings.append(f"Disk usage is elevated at {disk.get('usage_percent', 'Unknown')}%.")
        recommendations.append("Consider freeing storage space soon.")
    elif disk_status == "CRITICAL":
        findings.append(f"Disk usage is critically high at {disk.get('usage_percent', 'Unknown')}%.")
        recommendations.append("Free storage space on the system drive.")

    top_process = get_top_memory_process(telemetry)

    if top_process:
        findings.append(
            "The highest memory process is "
            f"{top_process.get('name', 'Unknown')} "
            f"using {top_process.get('memory_mb', 'Unknown')} MB."
        )

    if event_status != "ok":
        findings.append(
            "Windows event-log evidence could not be checked: "
            f"{event_report.get('message', 'Unknown error')}"
        )
    else:
        if critical_events > 0:
            findings.append(f"{critical_events} critical crash-related event(s) were found.")
            recommendations.append("Run the events command and review the critical event details.")
        elif warning_events > 0:
            findings.append(f"{warning_events} warning-level system event(s) were found.")
            recommendations.append("Run the events command and review the warning event details.")
        else:
            findings.append(
                "No critical crash pattern was found in the recent Windows System event log sample."
            )

        if context_events > 0:
            findings.append(
                f"{context_events} context event(s) were found, mostly useful for background."
            )

    if critical_events > 0:
        overall_status = "CRITICAL"
        summary = "Lighthouse found critical event-log evidence that may need investigation."
        conclusion = "A crash-related or unexpected shutdown pattern may be present."
    elif warning_events > 0:
        overall_status = "WARNING"
        summary = "Lighthouse found warning-level system evidence."
        conclusion = "The system is usable, but there may be a driver, disk, hardware, or event-log issue to review."
    elif has_live_pressure:
        overall_status = "WARNING"
        summary = "Lighthouse found live system pressure."
        conclusion = "The computer may feel slow right now because one or more resources are under pressure."
    else:
        overall_status = "GOOD"
        summary = "Lighthouse did not find an obvious system fault."
        conclusion = "CPU, memory, disk, and recent event evidence look healthy right now."

    if not recommendations:
        recommendations.append("No immediate action needed.")

    return {
        "status": "ok",
        "overall_status": overall_status,
        "summary": summary,
        "findings": findings,
        "conclusion": conclusion,
        "recommendations": recommendations,
        "metrics": {
            "cpu_status": cpu_status,
            "memory_status": memory_status,
            "disk_status": disk_status,
            "critical_events": critical_events,
            "warning_events": warning_events,
            "context_events": context_events,
        },
    }


def format_insight_report(insight: dict[str, Any]) -> str:
    """
    Format a Lighthouse insight dictionary for terminal output.
    """
    lines: list[str] = []

    lines.append("")
    lines.append("LIGHTHOUSE INSIGHT")
    lines.append("=" * 52)
    lines.append(f"Overall status: {insight.get('overall_status', 'UNKNOWN')}")
    lines.append("")
    lines.append("Assessment:")
    lines.append(f"- {insight.get('summary', 'No summary available.')}")

    lines.append("")
    lines.append("Findings:")

    for finding in insight.get("findings", []):
        lines.append(f"- {finding}")

    lines.append("")
    lines.append("Conclusion:")
    lines.append(f"- {insight.get('conclusion', 'No conclusion available.')}")

    lines.append("")
    lines.append("Suggested next step:")

    for recommendation in insight.get("recommendations", []):
        lines.append(f"- {recommendation}")

    lines.append("=" * 52)

    return "\n".join(lines)