"""
Action journal for Lighthouse.

The action journal records Lighthouse planning and execution decisions.

For now, it records read-only plan executions and refusals. Later, before
Lighthouse gains OS-changing tools, this journal will also record permission
requests, confirmations, action execution, and action results.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ACTION_JOURNAL_DIRECTORY = Path("data") / "journal"
ACTION_JOURNAL_FILENAME = "lighthouse_actions.jsonl"
ACTION_JOURNAL_PATH = ACTION_JOURNAL_DIRECTORY / ACTION_JOURNAL_FILENAME

EVENT_TYPE_TOOL_PLAN_EXECUTION = "tool_plan_execution"

JOURNAL_STATUS_OK = "ok"
JOURNAL_STATUS_ERROR = "error"

JOURNAL_SCHEMA_VERSION = 1
DEFAULT_JOURNAL_READ_LIMIT = 20


@dataclass(frozen=True)
class JournalWriteResult:
    """
    Result returned after writing an action journal entry.
    """

    status: str
    message: str
    path: str
    entry: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable result shape.
        """
        return {
            "status": self.status,
            "message": self.message,
            "path": self.path,
            "entry": self.entry,
        }


@dataclass(frozen=True)
class JournalReadResult:
    """
    Result returned after reading action journal entries.
    """

    status: str
    message: str
    path: str
    entries: list[dict[str, Any]]
    entry_count: int
    malformed_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable result shape.
        """
        return {
            "status": self.status,
            "message": self.message,
            "path": self.path,
            "entries": self.entries,
            "entry_count": self.entry_count,
            "malformed_count": self.malformed_count,
        }


def utc_timestamp() -> str:
    """
    Return a UTC timestamp suitable for journal records.
    """
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_action_journal_path() -> Path:
    """
    Return the default Lighthouse action journal path.
    """
    return ACTION_JOURNAL_PATH


def ensure_journal_directory(journal_path: Path | None = None) -> Path:
    """
    Ensure the action journal directory exists.

    Returns the resolved path that should be used for the journal file.
    """
    path = journal_path or get_action_journal_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    return path


def _get_value(source: Any, key: str, default: Any = None) -> Any:
    """
    Read a value from either an object attribute or a dictionary key.
    """
    if isinstance(source, dict):
        return source.get(key, default)

    return getattr(source, key, default)


def _extract_tool_name(tool_record: Any) -> str | None:
    """
    Extract a tool name from a tool result, planned tool, dictionary, or string.
    """
    if isinstance(tool_record, str):
        return tool_record

    if isinstance(tool_record, dict):
        value = tool_record.get("tool_name") or tool_record.get("name")

        if value is None:
            return None

        return str(value)

    value = getattr(tool_record, "tool_name", None) or getattr(tool_record, "name", None)

    if value is None:
        return None

    return str(value)


def _extract_tool_names(tool_records: Any) -> list[str]:
    """
    Extract tool names from an iterable of tool-like records.
    """
    if not tool_records:
        return []

    names: list[str] = []

    for tool_record in tool_records:
        tool_name = _extract_tool_name(tool_record)

        if tool_name:
            names.append(tool_name)

    return names


def build_plan_execution_journal_entry(
    execution_result: Any,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """
    Build a compact journal entry from a ToolPlanExecutionResult-like object.

    This intentionally stores summary metadata only. It does not store full
    telemetry payloads, process lists, or raw event data.
    """
    executed_tools = _extract_tool_names(
        _get_value(execution_result, "executed_tools", ())
    )
    refused_tools = _extract_tool_names(
        _get_value(execution_result, "refused_tools", ())
    )
    blocked_tools = list(_get_value(execution_result, "blocked_tools", ()) or [])
    safe_alternatives = list(
        _get_value(execution_result, "safe_alternatives", ()) or []
    )

    plan_status = str(_get_value(execution_result, "plan_status", "unknown"))
    execution_status = str(_get_value(execution_result, "status", "unknown"))

    return {
        "schema_version": JOURNAL_SCHEMA_VERSION,
        "timestamp": timestamp or utc_timestamp(),
        "event_type": EVENT_TYPE_TOOL_PLAN_EXECUTION,
        "user_request": str(_get_value(execution_result, "user_request", "")),
        "intent": str(_get_value(execution_result, "intent", "unknown")),
        "plan_status": plan_status,
        "execution_status": execution_status,
        "message": str(_get_value(execution_result, "message", "")),
        "executed_tools": executed_tools,
        "refused_tools": refused_tools,
        "blocked_tools": blocked_tools,
        "safe_alternatives": safe_alternatives,
        "requires_confirmation": plan_status == "needs_confirmation",
        "execution_allowed": execution_status in {"completed", "partial"},
    }


def append_journal_entry(
    entry: dict[str, Any],
    journal_path: Path | None = None,
) -> JournalWriteResult:
    """
    Append a single JSONL entry to the Lighthouse action journal.
    """
    path = ensure_journal_directory(journal_path)
    entry_to_write = dict(entry)

    if "timestamp" not in entry_to_write:
        entry_to_write["timestamp"] = utc_timestamp()

    try:
        with path.open("a", encoding="utf-8") as journal_file:
            journal_file.write(
                json.dumps(
                    entry_to_write,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
            )
            journal_file.write("\n")

        return JournalWriteResult(
            status=JOURNAL_STATUS_OK,
            message="Journal entry recorded.",
            path=str(path),
            entry=entry_to_write,
        )
    except OSError as error:
        return JournalWriteResult(
            status=JOURNAL_STATUS_ERROR,
            message=f"Unable to write journal entry: {error}",
            path=str(path),
            entry=None,
        )


def record_plan_execution(
    execution_result: Any,
    journal_path: Path | None = None,
) -> JournalWriteResult:
    """
    Record a Lighthouse tool plan execution result in the action journal.
    """
    entry = build_plan_execution_journal_entry(execution_result)

    return append_journal_entry(
        entry=entry,
        journal_path=journal_path,
    )


def read_journal_entries(
    limit: int = DEFAULT_JOURNAL_READ_LIMIT,
    journal_path: Path | None = None,
) -> JournalReadResult:
    """
    Read recent Lighthouse action journal entries.

    Returns newest entries first.
    """
    path = journal_path or get_action_journal_path()

    if limit <= 0:
        return JournalReadResult(
            status=JOURNAL_STATUS_OK,
            message="No entries requested.",
            path=str(path),
            entries=[],
            entry_count=0,
        )

    if not path.exists():
        return JournalReadResult(
            status=JOURNAL_STATUS_OK,
            message="No action journal found yet.",
            path=str(path),
            entries=[],
            entry_count=0,
        )

    entries: list[dict[str, Any]] = []
    malformed_count = 0

    try:
        with path.open("r", encoding="utf-8") as journal_file:
            for line in journal_file:
                stripped_line = line.strip()

                if not stripped_line:
                    continue

                try:
                    entry = json.loads(stripped_line)
                except json.JSONDecodeError:
                    malformed_count += 1
                    continue

                if isinstance(entry, dict):
                    entries.append(entry)
                else:
                    malformed_count += 1
    except OSError as error:
        return JournalReadResult(
            status=JOURNAL_STATUS_ERROR,
            message=f"Unable to read action journal: {error}",
            path=str(path),
            entries=[],
            entry_count=0,
        )

    recent_entries = list(reversed(entries[-limit:]))

    return JournalReadResult(
        status=JOURNAL_STATUS_OK,
        message="Action journal entries loaded.",
        path=str(path),
        entries=recent_entries,
        entry_count=len(recent_entries),
        malformed_count=malformed_count,
    )


def format_journal_entry(entry: dict[str, Any]) -> str:
    """
    Format one journal entry for CLI display.
    """
    executed_tools = entry.get("executed_tools", [])
    refused_tools = entry.get("refused_tools", [])
    blocked_tools = entry.get("blocked_tools", [])

    lines = [
        f"Time: {entry.get('timestamp', 'Unknown')}",
        f"Type: {entry.get('event_type', 'unknown')}",
        f"Request: {entry.get('user_request', '')}",
        f"Intent: {entry.get('intent', 'unknown')}",
        f"Plan status: {entry.get('plan_status', 'unknown')}",
        f"Execution status: {entry.get('execution_status', 'unknown')}",
        f"Message: {entry.get('message', '')}",
        f"Executed tools: {', '.join(executed_tools) if executed_tools else 'none'}",
        f"Refused tools: {', '.join(refused_tools) if refused_tools else 'none'}",
        f"Blocked tools: {', '.join(blocked_tools) if blocked_tools else 'none'}",
    ]

    return "\n".join(lines)


def format_journal_report(read_result: JournalReadResult) -> str:
    """
    Format a journal read result for display.
    """
    lines = [
        "",
        "LIGHTHOUSE ACTION JOURNAL",
        "=" * 52,
        f"Status: {read_result.status}",
        f"Message: {read_result.message}",
        f"Path: {read_result.path}",
        f"Entries shown: {read_result.entry_count}",
        f"Malformed entries skipped: {read_result.malformed_count}",
    ]

    if not read_result.entries:
        lines.append("=" * 52)
        return "\n".join(lines)

    lines.append("")
    lines.append("Recent entries:")
    lines.append("-" * 52)

    for entry in read_result.entries:
        lines.append(format_journal_entry(entry))
        lines.append("-" * 52)

    lines.append("=" * 52)

    return "\n".join(lines)