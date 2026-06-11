"""
Windows Event Log collector for Lighthouse.

Reads recent Windows System event logs and extracts events that may help explain
crashes, unexpected shutdowns, driver failures, or hardware issues.

Read-only only. This module does not modify event logs or system settings.
"""

from datetime import datetime
from typing import Any

try:
    import win32evtlog
except Exception:  # pragma: no cover - platform may not have pywin32 available
    win32evtlog = None


CRITICAL_EVENT_IDS = {
    41: "Kernel-Power: unexpected shutdown, forced power loss, or system freeze",
    1001: "BugCheck: Windows recorded a blue screen or crash dump",
    6008: "Unexpected shutdown recorded by Event Log",
}

WARNING_EVENT_IDS = {
    7: "Disk: bad block or storage read/write issue",
    51: "Disk: paging or storage operation warning",
    55: "NTFS: file system structure issue",
    129: "Storage driver reset or timeout",
    153: "Storage I/O operation retry",
}

CONTEXT_EVENT_IDS = {
    42: "Kernel-Power: system entering sleep",
    107: "Kernel-Power: system resumed from sleep",
    130: "Kernel-Power: firmware or power management event",
    131: "Kernel-Power: firmware or power management event",
    566: "Kernel-Power: power management context event",
    6005: "Event Log service started",
    6006: "Event Log service stopped cleanly",
    1074: "Planned shutdown or restart",
}

CRASH_RELATED_SOURCES = {
    "BugCheck",
    "Disk",
    "Display",
    "EventLog",
    "Microsoft-Windows-Kernel-Power",
    "Ntfs",
    "volmgr",
    "WHEA-Logger",
}


def event_time_to_string(event_time: Any) -> str:
    """
    Convert a pywin32 event time object to a readable string.
    """
    try:
        return str(event_time)
    except Exception:
        return "Unknown"


def event_type_to_string(event_type: int) -> str:
    """
    Convert a Windows event type integer to a readable label.
    """
    if win32evtlog is None:
        return "unknown"

    event_type_map = {
        win32evtlog.EVENTLOG_ERROR_TYPE: "error",
        win32evtlog.EVENTLOG_WARNING_TYPE: "warning",
        win32evtlog.EVENTLOG_INFORMATION_TYPE: "information",
        win32evtlog.EVENTLOG_AUDIT_SUCCESS: "audit_success",
        win32evtlog.EVENTLOG_AUDIT_FAILURE: "audit_failure",
    }

    return event_type_map.get(event_type, f"unknown:{event_type}")


def classify_event(event_id: int, source: str) -> str:
    """
    Return a plain-English interpretation of a known system event.
    """
    if event_id in CRITICAL_EVENT_IDS:
        return CRITICAL_EVENT_IDS[event_id]

    if event_id in WARNING_EVENT_IDS:
        return WARNING_EVENT_IDS[event_id]

    if event_id in CONTEXT_EVENT_IDS:
        return CONTEXT_EVENT_IDS[event_id]

    if source == "WHEA-Logger":
        return "WHEA-Logger: possible hardware, CPU, memory, or firmware issue"

    if source in {"Disk", "Ntfs", "volmgr"}:
        return f"{source}: possible disk, file system, or storage driver issue"

    if source == "Display":
        return "Display: possible graphics driver or display subsystem issue"

    if source in CRASH_RELATED_SOURCES:
        return f"{source}: system event context"

    return "System event context"


def classify_severity(event_id: int, source: str, event_type: int) -> str:
    """
    Classify event severity for Lighthouse reporting.

    critical: strong crash or unexpected shutdown indicator
    warning: possible driver, disk, hardware, or system issue
    context: useful background, but not enough to claim a crash
    """
    if event_id in CRITICAL_EVENT_IDS:
        return "critical"

    if event_id in WARNING_EVENT_IDS:
        return "warning"

    if source == "WHEA-Logger":
        return "warning"

    if source in {"Disk", "Ntfs", "volmgr"}:
        return "warning"

    if source == "Display" and win32evtlog is not None:
        if event_type in {
            win32evtlog.EVENTLOG_ERROR_TYPE,
            win32evtlog.EVENTLOG_WARNING_TYPE,
        }:
            return "warning"

    return "context"


def is_relevant_event(event_id: int, source: str, event_type: int) -> bool:
    """
    Decide whether an event belongs in the Lighthouse report.
    """
    if event_id in CRITICAL_EVENT_IDS:
        return True

    if event_id in WARNING_EVENT_IDS:
        return True

    if event_id in CONTEXT_EVENT_IDS:
        return True

    if source in CRASH_RELATED_SOURCES:
        return True

    if win32evtlog is not None and event_type in {
        win32evtlog.EVENTLOG_ERROR_TYPE,
        win32evtlog.EVENTLOG_WARNING_TYPE,
    }:
        return True

    return False


def summarize_events(events: list[dict[str, Any]]) -> dict[str, int]:
    """
    Count events by severity.
    """
    summary = {
        "critical": 0,
        "warning": 0,
        "context": 0,
    }

    for event in events:
        severity = event.get("severity", "context")

        if severity not in summary:
            severity = "context"

        summary[severity] += 1

    return summary


def get_possible_causes(events: list[dict[str, Any]]) -> list[str]:
    """
    Infer possible causes from crash-related event patterns.

    These are possibilities, not confirmed root causes.
    """
    causes: set[str] = set()

    for event in events:
        event_id = event.get("event_id")
        source = event.get("source", "")
        severity = event.get("severity", "context")

        if severity == "context":
            continue

        if event_id == 41:
            causes.add("Unexpected power loss, forced shutdown, system freeze, or thermal shutdown")

        if event_id == 1001:
            causes.add("Windows bugcheck or blue screen crash")

        if event_id == 6008:
            causes.add("Windows detected that the previous shutdown was unexpected")

        if source in {"Disk", "Ntfs", "volmgr"}:
            causes.add("Possible disk, file system, or storage driver issue")

        if source == "Display":
            causes.add("Possible graphics driver or display subsystem issue")

        if source == "WHEA-Logger":
            causes.add("Possible hardware, CPU, memory, or firmware-level issue")

    if not causes:
        causes.add("No critical crash pattern found in the recent System event log sample")

    return sorted(causes)


def get_recent_system_events(limit: int = 100) -> dict[str, Any]:
    """
    Read recent Windows System events and return crash-relevant entries.

    Args:
        limit: Maximum number of recent events to scan.

    Returns:
        Dictionary containing relevant event log entries and possible causes.
    """
    if win32evtlog is None:
        return {
            "status": "error",
            "message": (
                "pywin32 (win32evtlog) is not available on this system. "
                "This collector only works on Windows with pywin32 installed."
            ),
        }

    try:
        server = None
        log_type = "System"

        handle = win32evtlog.OpenEventLog(server, log_type)

        flags = (
            win32evtlog.EVENTLOG_BACKWARDS_READ
            | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        )

        events_checked = 0
        relevant_events: list[dict[str, Any]] = []

        while events_checked < limit:
            events = win32evtlog.ReadEventLog(handle, flags, 0)

            if not events:
                break

            for event in events:
                if events_checked >= limit:
                    break

                events_checked += 1

                source = event.SourceName
                event_id = event.EventID & 0xFFFF
                event_type = event.EventType

                if not is_relevant_event(event_id, source, event_type):
                    continue

                severity = classify_severity(event_id, source, event_type)

                relevant_events.append(
                    {
                        "time": event_time_to_string(event.TimeGenerated),
                        "source": source,
                        "event_id": event_id,
                        "event_type": event_type,
                        "event_type_label": event_type_to_string(event_type),
                        "severity": severity,
                        "classification": classify_event(event_id, source),
                    }
                )

        win32evtlog.CloseEventLog(handle)

        severity_summary = summarize_events(relevant_events)

        return {
            "status": "ok",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "log": log_type,
            "events_checked": events_checked,
            "relevant_event_count": len(relevant_events),
            "severity_summary": severity_summary,
            "possible_causes": get_possible_causes(relevant_events),
            "events": relevant_events[:20],
        }

    except Exception as error:
        return {
            "status": "error",
            "message": f"Failed to read Windows System event logs: {error}",
        }