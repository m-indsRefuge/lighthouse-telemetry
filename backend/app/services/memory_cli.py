"""
CLI reporting helpers for Lighthouse memory.

This module formats memory manager results into readable Operator-facing text.

It does not call the model.
It does not execute tools.
It does not mutate the OS.
It does not write memory directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.memory_cases import JsonDict
from app.services.memory_manager import (
    MEMORY_MANAGER_STATUS_EMPTY,
    MemoryManagerResult,
    get_memory_status,
    list_case_memories,
    search_case_memories,
)


REPORT_WIDTH = 52


def format_memory_status_report(
    *,
    memory_dir: Path | str | None = None,
) -> str:
    """
    Format a compact Lighthouse memory status report.
    """
    result = get_memory_status(memory_dir=memory_dir)
    data = result.data

    lines = [
        "",
        "LIGHTHOUSE MEMORY STATUS",
        "=" * REPORT_WIDTH,
        f"Status: {result.status}",
        f"Message: {result.message}",
        "",
        "Memory counts:",
        f"- Baselines: {data.get('baseline_count', 0)}",
        f"- Operator preferences: {data.get('operator_preference_count', 0)}",
        f"- Case memories: {data.get('case_count', 0)}",
        f"- Valid cases: {data.get('valid_case_count', 0)}",
        f"- Invalid cases: {data.get('invalid_case_count', 0)}",
        f"- Knowledge entries: {data.get('knowledge_entry_count', 0)}",
    ]

    append_result_messages(lines, result)
    lines.append("=" * REPORT_WIDTH)

    return "\n".join(lines)


def format_memory_case_list_report(
    *,
    memory_dir: Path | str | None = None,
    limit: int = 10,
) -> str:
    """
    Format a compact list of stored case memories.
    """
    result = list_case_memories(
        memory_dir=memory_dir,
        limit=limit,
        recall_cards_only=True,
    )

    lines = [
        "",
        "LIGHTHOUSE MEMORY CASES",
        "=" * REPORT_WIDTH,
        f"Status: {result.status}",
        f"Message: {result.message}",
        f"Cases shown: {result.data.get('case_count', 0)}",
    ]

    append_result_messages(lines, result)

    cases = result.data.get("cases", [])

    if not cases:
        lines.append("")
        lines.append("No case memories found.")
        lines.append("=" * REPORT_WIDTH)
        return "\n".join(lines)

    lines.append("")
    lines.append("Cases:")
    lines.append("-" * REPORT_WIDTH)

    for index, case_memory in enumerate(cases, start=1):
        lines.extend(format_case_recall_card(index, case_memory))

    lines.append("=" * REPORT_WIDTH)

    return "\n".join(lines)


def format_memory_case_search_report(
    user_request: str,
    *,
    telemetry: JsonDict | None = None,
    memory_dir: Path | str | None = None,
    limit: int = 3,
) -> str:
    """
    Format deterministic case-memory search results.
    """
    result = search_case_memories(
        user_request=user_request,
        telemetry=telemetry,
        memory_dir=memory_dir,
        limit=limit,
    )

    lines = [
        "",
        "LIGHTHOUSE MEMORY SEARCH",
        "=" * REPORT_WIDTH,
        f"Status: {result.status}",
        f"Message: {result.message}",
        f"Query: {result.data.get('query', user_request)}",
        f"Matches: {result.data.get('match_count', 0)}",
    ]

    append_result_messages(lines, result)

    matches = result.data.get("matches", [])

    if not matches:
        lines.append("")
        lines.append("No relevant case memories found.")
        lines.append("=" * REPORT_WIDTH)
        return "\n".join(lines)

    lines.append("")
    lines.append("Relevant cases:")
    lines.append("-" * REPORT_WIDTH)

    for index, match in enumerate(matches, start=1):
        case_memory = match.get("case", {})
        relevance = match.get("relevance", {})
        lines.extend(format_case_search_match(index, case_memory, relevance))

    lines.append("=" * REPORT_WIDTH)

    return "\n".join(lines)


def append_result_messages(lines: list[str], result: MemoryManagerResult) -> None:
    """
    Append warnings and errors to an output report.
    """
    if result.warnings:
        lines.append("")
        lines.append("Warnings:")

        for warning in result.warnings:
            lines.append(f"- {warning}")

    if result.errors:
        lines.append("")
        lines.append("Errors:")

        for error in result.errors:
            lines.append(f"- {error}")


def format_case_recall_card(index: int, case_memory: JsonDict) -> list[str]:
    """
    Format one compact case recall card.
    """
    case_card = case_memory.get("case_card", {})
    evidence_summary = case_memory.get("evidence_summary", {})
    lifecycle = case_memory.get("lifecycle", {})

    lines = [
        f"{index}. {case_memory.get('case_id', 'unknown_case')}",
        f"   Status: {case_memory.get('status', 'unknown')}",
        f"   Confidence: {case_memory.get('confidence', 'unknown')}",
        f"   Problem: {case_card.get('problem', 'Unknown')}",
        f"   Suspected cause: {case_card.get('suspected_cause', 'Unknown')}",
        f"   Lesson: {case_card.get('lesson', 'No lesson recorded.')}",
        f"   Tags: {format_string_list(case_card.get('tags', []))}",
        f"   Memory usage: {format_optional_percent(evidence_summary.get('memory_usage_percent'))}",
        f"   Top process: {evidence_summary.get('top_process_name', 'Unknown')}",
        f"   Outcome: {evidence_summary.get('outcome', 'Unknown')}",
        f"   Use count: {lifecycle.get('use_count', 0)}",
        "-" * REPORT_WIDTH,
    ]

    return lines


def format_case_search_match(
    index: int,
    case_memory: JsonDict,
    relevance: JsonDict,
) -> list[str]:
    """
    Format one case-memory search match.
    """
    lines = format_case_recall_card(index, case_memory)

    relevance_lines = [
        f"   Relevance score: {relevance.get('score', 0)}",
        f"   Relevance label: {relevance.get('label', 'none')}",
        f"   Match reasons: {format_string_list(relevance.get('reasons', []))}",
        "-" * REPORT_WIDTH,
    ]

    if lines and lines[-1] == "-" * REPORT_WIDTH:
        lines = lines[:-1]

    lines.extend(relevance_lines)

    return lines


def format_optional_percent(value: Any) -> str:
    """
    Format a percentage value when available.
    """
    if value is None:
        return "Unknown"

    return f"{value}%"


def format_string_list(value: Any) -> str:
    """
    Format a list of strings.
    """
    if not isinstance(value, list) or not value:
        return "none"

    return ", ".join(str(item) for item in value)


def format_memory_command_report(
    command: str,
    *,
    telemetry: JsonDict | None = None,
    memory_dir: Path | str | None = None,
) -> str:
    """
    Format a memory command report.

    This router is intentionally small so the main CLI can delegate memory
    commands without knowing memory manager internals.
    """
    cleaned_command = command.strip()
    normalized_command = cleaned_command.lower()

    if normalized_command in {"memory", "memory status", "status"}:
        return format_memory_status_report(memory_dir=memory_dir)

    if normalized_command in {
        "memory cases",
        "memory case list",
        "memory list",
        "cases",
        "case list",
    }:
        return format_memory_case_list_report(memory_dir=memory_dir)

    search_prefixes = (
        "memory search ",
        "memory case search ",
        "case search ",
        "search ",
    )

    for prefix in search_prefixes:
        if normalized_command.startswith(prefix):
            query = cleaned_command[len(prefix):].strip()
            return format_memory_case_search_report(
                query,
                telemetry=telemetry,
                memory_dir=memory_dir,
            )

    return "\n".join(
        [
            "",
            "LIGHTHOUSE MEMORY",
            "=" * REPORT_WIDTH,
            "Status: unknown_command",
            "Message: Unknown memory command.",
            "",
            "Available memory commands:",
            "- memory status",
            "- memory cases",
            "- memory search <text>",
            "=" * REPORT_WIDTH,
        ]
    )