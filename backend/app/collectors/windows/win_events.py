"""
Read-only hardened Windows Get-WinEvent collector for Lighthouse.

This collector uses an allowlisted set of Windows Event Logs and converts
relevant event records into normalized WindowsEvidenceItem dictionaries.

It does not accept arbitrary user-supplied event logs.
It does not clear or mutate event logs.
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
    CONFIDENCE_MEDIUM,
    CONFIDENCE_UNKNOWN,
    PRIVACY_LOW,
    PRIVACY_MEDIUM,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_WARNING,
    TRUST_TIER_1_READ_ONLY,
    build_windows_evidence_item,
    summarize_windows_evidence,
)


PowerShellRunner = Callable[[str], str]

WIN_EVENT_SOURCE = "windows_event_log"
WIN_EVENT_COLLECTOR = "Get-WinEvent"

DEFAULT_WIN_EVENT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_EVENTS_PER_LOG = 100
MAX_ALLOWED_EVENTS_PER_LOG = 500
MAX_MESSAGE_EXCERPT_LENGTH = 300

WIN_EVENT_JSON_DATE_PATTERN = re.compile(r"^/Date\((-?\d+)(?:[+-]\d+)?\)/$")

ALLOWED_EVENT_LOG_NAMES = frozenset({"System", "Application"})
DEFAULT_EVENT_LOG_NAMES = ("System", "Application")

EVENT_TYPE_TO_STATUS = {
    "Critical": STATUS_ERROR,
    "Error": STATUS_ERROR,
    "Warning": STATUS_WARNING,
    "Information": STATUS_OK,
}

RELEVANT_PROVIDERS = frozenset(
    {
        "application error",
        "application hang",
        "bugcheck",
        "disk",
        "eventlog",
        "microsoft-windows-kernel-power",
        "microsoft-windows-whea-logger",
        "microsoft-windows-windowsupdateclient",
        "ntfs",
        "servicing",
        "storahci",
        "volmgr",
        "windows error reporting",
    }
)

EVENT_CLASSIFICATION_MAP: dict[tuple[str, int], dict[str, str]] = {
    ("microsoft-windows-kernel-power", 41): {
        "signal": "unexpected_shutdown_or_power_loss",
        "plain_meaning": (
            "Windows recorded an unexpected shutdown, forced power loss, "
            "system freeze, or power interruption."
        ),
        "recommended_next_step": (
            "Check nearby BugCheck, WHEA, disk, thermal, and power events."
        ),
    },
    ("bugcheck", 1001): {
        "signal": "windows_bugcheck",
        "plain_meaning": "Windows recorded a blue screen or bugcheck crash dump.",
        "recommended_next_step": (
            "Review bugcheck details and nearby driver, WHEA, disk, and update events."
        ),
    },
    ("eventlog", 6008): {
        "signal": "unexpected_shutdown_eventlog",
        "plain_meaning": (
            "The Windows Event Log service recorded that the previous shutdown "
            "was unexpected."
        ),
        "recommended_next_step": (
            "Check for Kernel-Power, BugCheck, WHEA, and disk events near the same time."
        ),
    },
    ("microsoft-windows-whea-logger", 0): {
        "signal": "hardware_or_firmware_warning",
        "plain_meaning": (
            "Windows Hardware Error Architecture logged a possible hardware, "
            "firmware, CPU, memory, or bus issue."
        ),
        "recommended_next_step": (
            "Check BIOS, thermal, driver, and hardware context before recommending repair actions."
        ),
    },
    ("disk", 7): {
        "signal": "disk_bad_block_warning",
        "plain_meaning": "Windows reported a possible bad block or storage media issue.",
        "recommended_next_step": (
            "Check disk health, disk latency, and recent storage controller events."
        ),
    },
    ("disk", 51): {
        "signal": "disk_io_warning",
        "plain_meaning": "Windows reported a paging or storage I/O warning.",
        "recommended_next_step": (
            "Compare with disk queue and latency counters before recommending action."
        ),
    },
    ("disk", 153): {
        "signal": "disk_io_retry_warning",
        "plain_meaning": "Windows reported a retried storage I/O operation.",
        "recommended_next_step": (
            "Check storage driver, disk health, and latency evidence."
        ),
    },
    ("ntfs", 55): {
        "signal": "filesystem_structure_warning",
        "plain_meaning": "NTFS reported a possible file system structure issue.",
        "recommended_next_step": (
            "Recommend inspect-first diagnostics before any repair command."
        ),
    },
    ("storahci", 129): {
        "signal": "storage_controller_reset_warning",
        "plain_meaning": "The storage controller reported a reset or timeout.",
        "recommended_next_step": (
            "Check disk latency counters, storage driver state, and related disk events."
        ),
    },
    ("volmgr", 46): {
        "signal": "crash_dump_initialization_warning",
        "plain_meaning": "Windows reported a crash dump or volume manager issue.",
        "recommended_next_step": "Review nearby bugcheck, disk, and storage events.",
    },
    ("application error", 1000): {
        "signal": "application_crash",
        "plain_meaning": "Windows recorded an application crash.",
        "recommended_next_step": (
            "Check the application name, faulting module, and nearby Windows Error Reporting events."
        ),
    },
    ("application hang", 1002): {
        "signal": "application_hang",
        "plain_meaning": "Windows recorded an application hang.",
        "recommended_next_step": (
            "Compare with CPU, memory, disk latency, and application-specific evidence."
        ),
    },
    ("windows error reporting", 1001): {
        "signal": "windows_error_reporting_event",
        "plain_meaning": "Windows Error Reporting recorded a crash, hang, or fault report.",
        "recommended_next_step": (
            "Use this as supporting context with the matching application or system event."
        ),
    },
}


def escape_powershell_single_quoted(value: str) -> str:
    """
    Escape a string for use inside a PowerShell single-quoted string.
    """
    return value.replace("'", "''")


def clamp_max_events(max_events: int) -> int:
    """
    Clamp event query size to a safe bounded range.
    """
    try:
        value = int(max_events)
    except (TypeError, ValueError):
        return DEFAULT_MAX_EVENTS_PER_LOG

    if value < 1:
        return 1

    return min(value, MAX_ALLOWED_EVENTS_PER_LOG)


def build_win_event_script(
    log_name: str,
    max_events: int = DEFAULT_MAX_EVENTS_PER_LOG,
) -> str:
    """
    Build a safe, allowlisted PowerShell Get-WinEvent script.
    """
    if log_name not in ALLOWED_EVENT_LOG_NAMES:
        raise ValueError(f"Windows event log is not allowlisted: {log_name}")

    safe_log_name = escape_powershell_single_quoted(log_name)
    safe_max_events = clamp_max_events(max_events)

    return (
        "$ErrorActionPreference = 'Stop'; "
        f"Get-WinEvent -LogName '{safe_log_name}' -MaxEvents {safe_max_events} | "
        "Select-Object LogName,ProviderName,Id,LevelDisplayName,TimeCreated,Message | "
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
        raise RuntimeError(
            completed.stderr.strip() or "PowerShell Get-WinEvent query failed."
        )

    return completed.stdout.strip()


def parse_win_event_json(output: str) -> list[dict[str, Any]]:
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


def normalize_win_event_json_date(value: str) -> str:
    """
    Convert PowerShell JSON /Date(milliseconds)/ values into ISO UTC.
    """
    match = WIN_EVENT_JSON_DATE_PATTERN.match(value.strip())

    if not match:
        return value

    milliseconds = int(match.group(1))
    timestamp = milliseconds / 1000

    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def normalize_event_time(value: Any) -> str:
    """
    Normalize event time values into a stable string.
    """
    if value is None:
        return ""

    if isinstance(value, str):
        return normalize_win_event_json_date(value)

    return str(value).strip()


def normalize_provider_name(provider_name: Any) -> str:
    """
    Normalize provider names for deterministic matching.
    """
    return str(provider_name or "").strip().lower()


def normalize_event_id(event_id: Any) -> int | None:
    """
    Normalize Windows event IDs to integers when possible.
    """
    try:
        return int(event_id)
    except (TypeError, ValueError):
        return None


def truncate_message(message: Any) -> str:
    """
    Truncate event messages to avoid large raw payloads in evidence values.
    """
    text = str(message or "").strip()

    if len(text) <= MAX_MESSAGE_EXCERPT_LENGTH:
        return text

    return text[: MAX_MESSAGE_EXCERPT_LENGTH - 3].rstrip() + "..."


def event_mapping_for(provider_name: Any, event_id: Any) -> dict[str, str] | None:
    """
    Return a specific event mapping when one exists.
    """
    normalized_provider = normalize_provider_name(provider_name)
    normalized_event_id = normalize_event_id(event_id)

    if normalized_event_id is None:
        return None

    exact_mapping = EVENT_CLASSIFICATION_MAP.get(
        (normalized_provider, normalized_event_id)
    )

    if exact_mapping:
        return exact_mapping

    if normalized_provider == "microsoft-windows-whea-logger":
        return EVENT_CLASSIFICATION_MAP[("microsoft-windows-whea-logger", 0)]

    return None


def is_relevant_win_event(record: dict[str, Any]) -> bool:
    """
    Decide whether a Get-WinEvent record belongs in evidence output.
    """
    provider = normalize_provider_name(record.get("ProviderName"))
    event_id = normalize_event_id(record.get("Id"))
    level = str(record.get("LevelDisplayName") or "").strip()

    if event_mapping_for(provider, event_id):
        return True

    if provider in RELEVANT_PROVIDERS:
        return True

    return level in {"Critical", "Error", "Warning"}


def status_for_event(record: dict[str, Any]) -> str:
    """
    Convert event level into Windows evidence status.
    """
    level = str(record.get("LevelDisplayName") or "").strip()

    return EVENT_TYPE_TO_STATUS.get(level, STATUS_WARNING)


def generic_signal_for_event(record: dict[str, Any]) -> str:
    """
    Return a generic deterministic signal for unmapped relevant events.
    """
    provider = normalize_provider_name(record.get("ProviderName"))
    event_id = normalize_event_id(record.get("Id"))
    level = str(record.get("LevelDisplayName") or "unknown").strip().lower()
    provider_slug = provider.replace("-", "_").replace(" ", "_") or "unknown_provider"

    if event_id is None:
        return f"windows_event_{level}_{provider_slug}"

    return f"windows_event_{level}_{provider_slug}_{event_id}"


def plain_meaning_for_event(record: dict[str, Any]) -> str:
    """
    Return a plain-English interpretation of a Windows event record.
    """
    provider = normalize_provider_name(record.get("ProviderName"))
    event_id = normalize_event_id(record.get("Id"))
    mapping = event_mapping_for(provider, event_id)

    if mapping:
        return mapping["plain_meaning"]

    level = str(record.get("LevelDisplayName") or "event").strip() or "event"
    provider_name = str(record.get("ProviderName") or "Unknown provider").strip()

    return f"Windows recorded a {level.lower()} event from {provider_name}."


def recommended_next_step_for_event(record: dict[str, Any]) -> str | None:
    """
    Return an inspect-first next step for a Windows event record.
    """
    provider = normalize_provider_name(record.get("ProviderName"))
    event_id = normalize_event_id(record.get("Id"))
    mapping = event_mapping_for(provider, event_id)

    if mapping:
        return mapping["recommended_next_step"]

    return (
        "Use this event as supporting context with CIM, performance counter, "
        "and nearby event evidence."
    )


def evidence_item_from_win_event(record: dict[str, Any]) -> dict[str, Any] | None:
    """
    Convert one Get-WinEvent record into a normalized Windows evidence item.
    """
    if not is_relevant_win_event(record):
        return None

    provider = str(record.get("ProviderName") or "Unknown provider").strip()
    event_id = normalize_event_id(record.get("Id"))
    event_time = normalize_event_time(record.get("TimeCreated"))
    log_name = str(record.get("LogName") or "Unknown log").strip()
    mapping = event_mapping_for(provider, event_id)
    signal = mapping["signal"] if mapping else generic_signal_for_event(record)
    message_excerpt = truncate_message(record.get("Message"))

    return build_windows_evidence_item(
        source=WIN_EVENT_SOURCE,
        collector=WIN_EVENT_COLLECTOR,
        signal=signal,
        value={
            "log_name": log_name,
            "provider": provider,
            "event_id": event_id,
            "level": record.get("LevelDisplayName"),
            "time_created": event_time,
            "message_excerpt": message_excerpt,
        },
        status=status_for_event(record),
        confidence=CONFIDENCE_HIGH if event_id is not None else CONFIDENCE_MEDIUM,
        trust_tier=TRUST_TIER_1_READ_ONLY,
        requires_admin=False,
        privacy=PRIVACY_MEDIUM if message_excerpt else PRIVACY_LOW,
        permission_required=False,
        plain_meaning=plain_meaning_for_event(record),
        recommended_next_step=recommended_next_step_for_event(record),
        raw={
            "log_name": log_name,
            "provider": provider,
            "event_id": event_id,
            "level": record.get("LevelDisplayName"),
            "raw_time_created": record.get("TimeCreated"),
        },
    )


def evidence_items_from_win_events(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Convert Get-WinEvent records into normalized Windows evidence items.
    """
    evidence_items: list[dict[str, Any]] = []

    for record in records:
        item = evidence_item_from_win_event(record)

        if item is not None:
            evidence_items.append(item)

    return evidence_items


def validate_event_log_names(log_names: list[str] | tuple[str, ...]) -> list[str]:
    """
    Return errors for any event log name that is not in the allowlist.
    """
    errors: list[str] = []

    for log_name in log_names:
        if log_name not in ALLOWED_EVENT_LOG_NAMES:
            errors.append(f"Windows event log is not allowlisted: {log_name}")

    return errors


def format_win_event_collection_error(log_name: str, error: BaseException) -> str:
    """
    Format Get-WinEvent collection errors for Operator-facing reports.
    """
    if isinstance(error, subprocess.TimeoutExpired):
        timeout = error.timeout if error.timeout is not None else "unknown"
        return f"Get-WinEvent query timed out for {log_name} after {timeout} seconds."

    if isinstance(error, json.JSONDecodeError):
        return f"Get-WinEvent query returned invalid JSON for {log_name}: {error}"

    message = str(error).strip()

    if message:
        return message

    return f"Get-WinEvent query failed for {log_name}."


def build_error_evidence_item(log_name: str, error_message: str) -> dict[str, Any]:
    """
    Build an error evidence item for a failed event log collection run.
    """
    return build_windows_evidence_item(
        source=WIN_EVENT_SOURCE,
        collector=WIN_EVENT_COLLECTOR,
        signal="windows_event_collection_error",
        value=None,
        status=STATUS_ERROR,
        confidence=CONFIDENCE_UNKNOWN,
        trust_tier=TRUST_TIER_1_READ_ONLY,
        requires_admin=False,
        privacy=PRIVACY_LOW,
        permission_required=False,
        plain_meaning=f"Lighthouse could not collect Windows event evidence from {log_name}.",
        errors=[error_message],
        raw={"log_name": log_name},
    )


def collect_win_event_log_evidence(
    *,
    log_name: str,
    max_events: int = DEFAULT_MAX_EVENTS_PER_LOG,
    runner: PowerShellRunner | None = None,
) -> dict[str, Any]:
    """
    Collect normalized evidence from one allowlisted Windows event log.
    """
    validation_errors = validate_event_log_names((log_name,))

    if validation_errors:
        return {
            "status": "invalid",
            "log_name": log_name,
            "records_checked": 0,
            "evidence_items": [],
            "errors": validation_errors,
            "warnings": [],
        }

    selected_runner = runner or run_powershell_script
    safe_max_events = clamp_max_events(max_events)
    script = build_win_event_script(log_name, safe_max_events)

    try:
        output = selected_runner(script)
        records = parse_win_event_json(output)
        evidence_items = evidence_items_from_win_events(records)

        return {
            "status": "ok",
            "log_name": log_name,
            "records_checked": len(records),
            "evidence_items": evidence_items,
            "errors": [],
            "warnings": [],
        }
    except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        error_message = format_win_event_collection_error(log_name, error)
        error_item = build_error_evidence_item(log_name, error_message)

        return {
            "status": "error",
            "log_name": log_name,
            "records_checked": 0,
            "evidence_items": [error_item],
            "errors": [error_message],
            "warnings": [],
        }


def collect_windows_event_evidence(
    *,
    log_names: list[str] | tuple[str, ...] | None = None,
    max_events_per_log: int = DEFAULT_MAX_EVENTS_PER_LOG,
    runner: PowerShellRunner | None = None,
) -> dict[str, Any]:
    """
    Collect safe Tier 1 Windows event evidence from allowlisted event logs.
    """
    selected_log_names = tuple(log_names or DEFAULT_EVENT_LOG_NAMES)
    validation_errors = validate_event_log_names(selected_log_names)

    if validation_errors:
        return {
            "status": "invalid",
            "message": "Windows event evidence collection rejected invalid log names.",
            "source": WIN_EVENT_SOURCE,
            "log_names": list(selected_log_names),
            "log_results": [],
            "evidence_items": [],
            "summary": summarize_windows_evidence([]),
            "errors": validation_errors,
            "warnings": [],
        }

    log_results: list[dict[str, Any]] = []
    evidence_items: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    for log_name in selected_log_names:
        log_result = collect_win_event_log_evidence(
            log_name=log_name,
            max_events=max_events_per_log,
            runner=runner,
        )
        log_results.append(log_result)
        evidence_items.extend(log_result.get("evidence_items", []))
        errors.extend(log_result.get("errors", []))
        warnings.extend(log_result.get("warnings", []))

    if errors and evidence_items:
        status = "partial"
        message = "Windows event evidence collection completed with errors."
    elif errors:
        status = "error"
        message = "Windows event evidence collection failed."
    else:
        status = "ok"
        message = "Windows event evidence collection completed."

    return {
        "status": status,
        "message": message,
        "source": WIN_EVENT_SOURCE,
        "log_names": list(selected_log_names),
        "log_results": log_results,
        "evidence_items": evidence_items,
        "summary": summarize_windows_evidence(evidence_items),
        "errors": errors,
        "warnings": warnings,
    }
