"""
Windows Event Log collector for Lighthouse.

Reads recent Windows System event logs and extracts events that may
help explain crashes, unexpected shutdowns, driver failures, or hardware issues.

Read-only only. This module does not modify event logs or system settings.
"""

from datetime import datetime
from typing import Any

try:
    import win32evtlog
except Exception:  # pragma: no cover - platform may not have pywin32 available
    win32evtlog = None


CRASH_RELATED_EVENT_IDS = {
    41: "Kernel-Power: unexpected shutdown or power loss",
    1001: "BugCheck: Windows recorded a blue screen or crash dump",
    6008: "Unexpected shutdown recorded by Event Log",
    1074: "Planned shutdown or restart",
    6005: "Event Log service started",
    6006: "Event Log service stopped cleanly",
}

CRASH_RELATED_SOURCES = {
    "Microsoft-Windows-Kernel-Power",
    "BugCheck",
    "EventLog",
    "Disk",
    "Ntfs",
    "Display",
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


def classify_event(event_id: int, source: str) -> str:
    """
    Return a plain-English interpretation of a known crash-related event.
    """

    clean_event_id = event_id & 0xFFFF

    if clean_event_id in CRASH_RELATED_EVENT_IDS:
        return CRASH_RELATED_EVENT_IDS[clean_event_id]

    if source in CRASH_RELATED_SOURCES:
        return f"{source}: potentially relevant system event"

    return "Potentially relevant system event"


def get_possible_causes(events: list[dict[str, Any]]) -> list[str]:
    """
    Infer possible causes from crash-related event patterns.

    These are possibilities, not confirmed root causes.
    """

    causes: set[str] = set()

    for event in events:
        event_id = event.get("event_id")
        source = event.get("source", "")

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
        causes.add("No clear crash cause found in the recent System event log sample")

    return sorted(causes)


def get_recent_system_events(limit: int = 100) -> dict[str, Any]:
    """
    Read recent Windows System events and return crash-relevant entries.

    Args:
        limit: Maximum number of recent events to scan.

    Returns:
        Dictionary containing relevant event log entries and possible causes.
    """

    # pywin32 (win32evtlog) is only available on Windows with pywin32 installed.
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

                is_relevant = (
                    event_id in CRASH_RELATED_EVENT_IDS
                    or source in CRASH_RELATED_SOURCES
                    or event_type in {
                        win32evtlog.EVENTLOG_ERROR_TYPE,
                        win32evtlog.EVENTLOG_WARNING_TYPE,
                    }
                )

                if not is_relevant:
                    continue

                relevant_events.append(
                    {
                        "time": event_time_to_string(event.TimeGenerated),
                        "source": source,
                        "event_id": event_id,
                        "event_type": event_type,
                        "classification": classify_event(event_id, source),
                    }
                )

        win32evtlog.CloseEventLog(handle)

        return {
            "status": "ok",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "log": log_type,
            "events_checked": events_checked,
            "relevant_event_count": len(relevant_events),
            "possible_causes": get_possible_causes(relevant_events),
            "events": relevant_events[:20],
        }

    except Exception as error:
        return {
            "status": "error",
            "message": f"Failed to read Windows System event logs: {error}",
        }