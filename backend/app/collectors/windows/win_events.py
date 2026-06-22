"""
Hardened read-only Windows Get-WinEvent evidence collector for Lighthouse.

This collector uses allowlisted event query scopes and normalizes matching
Windows Event Log entries into WindowsEvidenceItem dictionaries.

It does not accept arbitrary user-supplied event log queries.
It does not clear, write, or mutate event logs.
It does not execute repair commands.
It does not mutate the operating system.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import subprocess
from typing import Any, Callable

from app.services.windows_evidence import (
    CONFIDENCE_HIGH,
    CONFIDENCE_UNKNOWN,
    PRIVACY_MEDIUM,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_WARNING,
    TRUST_TIER_1_READ_ONLY,
    build_windows_evidence_item,
    summarize_windows_evidence,
)


PowerShellRunner = Callable[[str], str]

WINDOWS_EVENT_SOURCE = "windows_event_log"
WINDOWS_EVENT_COLLECTOR = "Get-WinEvent"
DEFAULT_WIN_EVENT_TIMEOUT_SECONDS = 30
WINDOWS_EVENT_JSON_DATE_PATTERN = re.compile(r"^/Date\((-?\d+)(?:[+-]\d+)?\)/$")
MAX_MESSAGE_EXCERPT_LENGTH = 300

APPROVED_EVENT_QUERIES: dict[str, dict[str, Any]] = {
    "system_stability": {
        "log_name": "System",
        "event_ids": [7, 41, 51, 55, 129, 153, 1001, 6008],
        "max_events": 50,
        "plain_meaning": "Recent Windows System stability, shutdown, storage, and crash events.",
    },
    "application_stability": {
        "log_name": "Application",
        "event_ids": [1000, 1001, 1002],
        "max_events": 50,
        "plain_meaning": "Recent application crash, hang, and Windows Error Reporting events.",
    },
    "windows_update": {
        "log_name": "System",
        "event_ids": [19, 20, 25, 31, 34, 43, 44],
        "provider_names": ["Microsoft-Windows-WindowsUpdateClient"],
        "max_events": 50,
        "plain_meaning": "Recent Windows Update success, failure, and update lifecycle events.",
    },
}

DEFAULT_EVENT_QUERY_IDS = tuple(APPROVED_EVENT_QUERIES.keys())

CRITICAL_EVENT_IDS = frozenset({41, 1001, 6008})
STORAGE_EVENT_IDS = frozenset({7, 51, 55, 129, 153})
WINDOWS_UPDATE_FAILURE_EVENT_IDS = frozenset({20, 25, 34})


def escape_powershell_single_quoted(value: str) -> str:
    """
    Escape a string for use inside a PowerShell single-quoted string.
    """
    return value.replace("'", "''")


def powershell_array(values: list[Any] | tuple[Any, ...]) -> str:
    """
    Build a PowerShell array expression for strings or integers.
    """
    parts: list[str] = []

    for value in values:
        if isinstance(value, int):
            parts.append(str(value))
        else:
            parts.append(f"'{escape_powershell_single_quoted(str(value))}'")

    return "@(" + ", ".join(parts) + ")"


def build_event_query_script(query: dict[str, Any]) -> str:
    """
    Build a safe, allowlisted PowerShell Get-WinEvent query script.
    """
    log_name = escape_powershell_single_quoted(str(query["log_name"]))
    event_ids = powershell_array(tuple(query.get("event_ids", [])))
    provider_names = query.get("provider_names") or []
    max_events = int(query.get("max_events", 50))

    filter_parts = [
        f"LogName = '{log_name}'",
        f"Id = {event_ids}",
    ]

    if provider_names:
        filter_parts.append(f"ProviderName = {powershell_array(tuple(provider_names))}")

    filter_hashtable = "@{" + "; ".join(filter_parts) + "}"

    return (
        "$ErrorActionPreference = 'Stop'; "
        f"Get-WinEvent -FilterHashtable {filter_hashtable} -MaxEvents {max_events} | "
        "Select-Object TimeCreated,ProviderName,Id,LevelDisplayName,Message,LogName | "
        "ConvertTo-Json -Depth 4"
    )


def run_powershell_script(
    script: str,
    timeout_seconds: int = DEFAULT_WIN_EVENT_TIMEOUT_SECONDS,
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
        raise RuntimeError(completed.stderr.strip() or "PowerShell Get-WinEvent query failed.")

    return completed.stdout.strip()


def parse_event_json(output: str) -> list[dict[str, Any]]:
    """
    Parse Get-WinEvent JSON output into a list of dictionaries.
    """
    if not output.strip():
        return []

    parsed = json.loads(output)

    if isinstance(parsed, dict):
        return [parsed]

    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]

    return []


def normalize_event_time(value: Any) -> str:
    """
    Normalize Event Log time values into readable ISO-like strings where possible.
    """
    if value is None:
        return ""

    if isinstance(value, str):
        stripped = value.strip()
        match = WINDOWS_EVENT_JSON_DATE_PATTERN.match(stripped)

        if match:
            milliseconds = int(match.group(1))
            timestamp = milliseconds / 1000
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()

        return stripped

    return str(value).strip()


def truncate_message(message: Any) -> str:
    """
    Return a compact message excerpt for evidence raw data.
    """
    if message is None:
        return ""

    text = str(message).strip().replace("\r", " ").replace("\n", " ")

    if len(text) <= MAX_MESSAGE_EXCERPT_LENGTH:
        return text

    return text[:MAX_MESSAGE_EXCERPT_LENGTH].rstrip() + "..."


def normalize_provider_name(provider_name: Any) -> str:
    """
    Normalize Windows event provider name.
    """
    if provider_name is None:
        return ""

    return str(provider_name).strip()


def normalize_event_id(event_id: Any) -> int | None:
    """
    Normalize Windows event ID values.
    """
    try:
        return int(event_id)
    except (TypeError, ValueError):
        return None


def event_signal_for_record(record: dict[str, Any]) -> str:
    """
    Return a normalized signal for a Windows event record.
    """
    provider_name = normalize_provider_name(record.get("ProviderName"))
    event_id = normalize_event_id(record.get("Id"))
    log_name = str(record.get("LogName") or "").strip()

    if event_id == 41:
        return "unexpected_shutdown_or_power_loss"

    if event_id == 6008:
        return "unexpected_shutdown_recorded"

    if provider_name == "BugCheck" or (event_id == 1001 and log_name == "System"):
        return "windows_bugcheck"

    if provider_name == "WHEA-Logger":
        return "whea_hardware_warning"

    if provider_name in {"Disk", "Ntfs", "volmgr", "storahci"} or event_id in STORAGE_EVENT_IDS:
        return "storage_or_file_system_warning"

    if provider_name == "Application Error" or event_id == 1000:
        return "application_crash"

    if provider_name == "Application Hang" or event_id == 1002:
        return "application_hang"

    if provider_name == "Windows Error Reporting":
        return "windows_error_reporting"

    if provider_name == "Microsoft-Windows-WindowsUpdateClient":
        if event_id in WINDOWS_UPDATE_FAILURE_EVENT_IDS:
            return "windows_update_warning"

        return "windows_update_event"

    return "windows_event_log_entry"


def event_status_for_record(record: dict[str, Any]) -> str:
    """
    Return WindowsEvidenceItem status for a Windows event record.
    """
    provider_name = normalize_provider_name(record.get("ProviderName"))
    event_id = normalize_event_id(record.get("Id"))
    level = str(record.get("LevelDisplayName") or "").strip().lower()

    if event_id in CRITICAL_EVENT_IDS:
        return STATUS_ERROR

    if event_id in STORAGE_EVENT_IDS:
        return STATUS_WARNING

    if provider_name in {"WHEA-Logger", "Disk", "Ntfs", "volmgr", "storahci"}:
        return STATUS_WARNING

    if provider_name == "Microsoft-Windows-WindowsUpdateClient":
        if event_id in WINDOWS_UPDATE_FAILURE_EVENT_IDS:
            return STATUS_WARNING

    if level in {"critical", "error"}:
        return STATUS_ERROR

    if level == "warning":
        return STATUS_WARNING

    return STATUS_OK


def plain_meaning_for_record(record: dict[str, Any]) -> str:
    """
    Return Operator-facing plain meaning for a Windows event record.
    """
    signal = event_signal_for_record(record)

    meanings = {
        "unexpected_shutdown_or_power_loss": "Windows recorded a Kernel-Power event that can indicate power loss, forced shutdown, system freeze, or thermal shutdown.",
        "unexpected_shutdown_recorded": "Windows recorded that the previous shutdown was unexpected.",
        "windows_bugcheck": "Windows recorded a bugcheck or crash-report event.",
        "whea_hardware_warning": "Windows hardware error architecture reported possible hardware, CPU, memory, firmware, or device instability.",
        "storage_or_file_system_warning": "Windows recorded a storage, disk, driver, or file-system event that may affect stability or performance.",
        "application_crash": "Windows recorded an application crash.",
        "application_hang": "Windows recorded an application hang.",
        "windows_error_reporting": "Windows Error Reporting recorded an application or system fault report.",
        "windows_update_warning": "Windows Update recorded a warning or failure event.",
        "windows_update_event": "Windows Update recorded an update lifecycle event.",
    }

    return meanings.get(signal, "Windows Event Log entry collected as diagnostic context.")


def recommended_next_step_for_record(record: dict[str, Any]) -> str | None:
    """
    Return a conservative next-step recommendation for a Windows event record.
    """
    signal = event_signal_for_record(record)

    if signal in {"unexpected_shutdown_or_power_loss", "unexpected_shutdown_recorded"}:
        return "Check nearby BugCheck, WHEA, disk, thermal, and power events before recommending repair."

    if signal == "windows_bugcheck":
        return "Correlate with WHEA, driver, disk, and recent update events before recommending next diagnostics."

    if signal == "whea_hardware_warning":
        return "Correlate with temperature, BIOS, CPU, memory, and device-driver evidence."

    if signal == "storage_or_file_system_warning":
        return "Correlate with disk latency counters and storage health evidence."

    if signal in {"application_crash", "application_hang", "windows_error_reporting"}:
        return "Correlate with process, memory pressure, and recent application update context."

    if signal in {"windows_update_warning", "windows_update_event"}:
        return "Correlate with servicing, restart, and system integrity evidence."

    return None


def evidence_item_from_event_record(
    *,
    query_id: str,
    record: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Convert one Get-WinEvent record into a normalized Windows evidence item.
    """
    provider_name = normalize_provider_name(record.get("ProviderName"))
    event_id = normalize_event_id(record.get("Id"))

    if not provider_name or event_id is None:
        return None

    time_created = normalize_event_time(record.get("TimeCreated"))
    status = event_status_for_record(record)

    return build_windows_evidence_item(
        source=WINDOWS_EVENT_SOURCE,
        collector=WINDOWS_EVENT_COLLECTOR,
        signal=event_signal_for_record(record),
        value={
            "time_created": time_created,
            "provider_name": provider_name,
            "event_id": event_id,
            "level": str(record.get("LevelDisplayName") or "").strip(),
            "log_name": str(record.get("LogName") or "").strip(),
        },
        status=status,
        confidence=CONFIDENCE_HIGH,
        trust_tier=TRUST_TIER_1_READ_ONLY,
        requires_admin=False,
        privacy=PRIVACY_MEDIUM,
        permission_required=False,
        plain_meaning=plain_meaning_for_record(record),
        recommended_next_step=recommended_next_step_for_record(record),
        raw={
            "query_id": query_id,
            "provider_name": provider_name,
            "event_id": event_id,
            "message_excerpt": truncate_message(record.get("Message")),
        },
    )


def evidence_items_from_event_records(
    *,
    query_id: str,
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convert Get-WinEvent records into normalized Windows evidence items.
    """
    evidence_items: list[dict[str, Any]] = []

    for record in records:
        item = evidence_item_from_event_record(query_id=query_id, record=record)

        if item is not None:
            evidence_items.append(item)

    return evidence_items


def format_event_collection_error(query_id: str, error: BaseException) -> str:
    """
    Format Event Log collection errors for Operator-facing reports.
    """
    if isinstance(error, subprocess.TimeoutExpired):
        timeout = error.timeout if error.timeout is not None else "unknown"
        return f"Get-WinEvent query timed out for {query_id} after {timeout} seconds."

    if isinstance(error, json.JSONDecodeError):
        return f"Get-WinEvent query returned invalid JSON for {query_id}: {error}"

    message = str(error).strip()

    if message:
        return message

    return f"Get-WinEvent query failed for {query_id}."


def build_error_evidence_item(query_id: str, error_message: str) -> dict[str, Any]:
    """
    Build an error evidence item for a failed Event Log collection run.
    """
    return build_windows_evidence_item(
        source=WINDOWS_EVENT_SOURCE,
        collector=WINDOWS_EVENT_COLLECTOR,
        signal="windows_event_log_collection_error",
        value={"query_id": query_id},
        status=STATUS_ERROR,
        confidence=CONFIDENCE_UNKNOWN,
        trust_tier=TRUST_TIER_1_READ_ONLY,
        requires_admin=False,
        privacy=PRIVACY_MEDIUM,
        permission_required=False,
        plain_meaning="Lighthouse could not collect Windows Event Log evidence.",
        errors=[error_message],
        raw={"query_id": query_id},
    )


def collect_windows_event_query(
    *,
    query_id: str,
    runner: PowerShellRunner | None = None,
) -> dict[str, Any]:
    """
    Collect evidence for one allowlisted Get-WinEvent query scope.
    """
    if query_id not in APPROVED_EVENT_QUERIES:
        return {
            "status": "invalid",
            "message": "Windows Event Log query rejected.",
            "query_id": query_id,
            "evidence_items": [],
            "errors": [f"Windows Event Log query is not allowlisted: {query_id}"],
            "warnings": [],
        }

    selected_runner = runner or run_powershell_script
    query = APPROVED_EVENT_QUERIES[query_id]
    script = build_event_query_script(query)

    try:
        output = selected_runner(script)
        records = parse_event_json(output)
        evidence_items = evidence_items_from_event_records(
            query_id=query_id,
            records=records,
        )

        return {
            "status": "ok",
            "message": "Windows Event Log evidence collection completed.",
            "query_id": query_id,
            "record_count": len(records),
            "evidence_items": evidence_items,
            "errors": [],
            "warnings": [],
        }
    except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        error_message = format_event_collection_error(query_id, error)
        error_item = build_error_evidence_item(query_id, error_message)

        return {
            "status": "error",
            "message": "Windows Event Log evidence collection failed.",
            "query_id": query_id,
            "record_count": 0,
            "evidence_items": [error_item],
            "errors": [error_message],
            "warnings": [],
        }


def collect_windows_event_evidence(
    *,
    query_ids: list[str] | tuple[str, ...] | None = None,
    runner: PowerShellRunner | None = None,
) -> dict[str, Any]:
    """
    Collect safe Tier 1 Windows Event Log evidence through approved queries.
    """
    selected_query_ids = tuple(query_ids or DEFAULT_EVENT_QUERY_IDS)
    query_results: list[dict[str, Any]] = []
    evidence_items: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    for query_id in selected_query_ids:
        query_result = collect_windows_event_query(
            query_id=query_id,
            runner=runner,
        )
        query_results.append(query_result)
        evidence_items.extend(query_result.get("evidence_items", []))
        errors.extend(query_result.get("errors", []))
        warnings.extend(query_result.get("warnings", []))

    if any(result.get("status") == "invalid" for result in query_results):
        status = "invalid"
        message = "Windows Event Log evidence collection rejected invalid query IDs."
    elif errors and evidence_items:
        status = "partial"
        message = "Windows Event Log evidence collection completed with errors."
    elif errors:
        status = "error"
        message = "Windows Event Log evidence collection failed."
    else:
        status = "ok"
        message = "Windows Event Log evidence collection completed."

    return {
        "status": status,
        "message": message,
        "source": WINDOWS_EVENT_SOURCE,
        "query_ids": list(selected_query_ids),
        "query_results": query_results,
        "evidence_items": evidence_items,
        "summary": summarize_windows_evidence(evidence_items),
        "errors": errors,
        "warnings": warnings,
    }
