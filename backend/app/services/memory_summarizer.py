"""
Memory summarizer for Lighthouse.

This module turns retrieved Lighthouse memory into a compact context block.

It does not mutate memory.
It does not execute tools.
It does not make final safety decisions.
It prepares controlled context that the Lighthouse Engine can later pass to the
reasoning/model layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.memory_retriever import (
    MEMORY_RETRIEVER_STATUS_OK,
    MemoryRetrievalResult,
    ScoredMemoryEntry,
    retrieve_memory_for_request,
)


MEMORY_SUMMARY_STATUS_OK = "ok"
MEMORY_SUMMARY_STATUS_EMPTY = "empty"
MEMORY_SUMMARY_STATUS_PARTIAL = "partial"

DEFAULT_MAX_BASELINE_ITEMS = 8
DEFAULT_MAX_PREFERENCE_ITEMS = 8
DEFAULT_MAX_CASE_ITEMS = 5
DEFAULT_MAX_KNOWLEDGE_ITEMS = 5
DEFAULT_MAX_VALUE_LENGTH = 180


@dataclass(frozen=True)
class MemorySummaryResult:
    """
    Result returned by memory summarization.
    """

    status: str
    message: str
    user_request: str
    keywords: tuple[str, ...]
    context_text: str
    baseline_count: int
    preference_count: int
    case_count: int
    knowledge_count: int
    source_status: dict[str, dict[str, Any]]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable memory summary shape.
        """
        return {
            "status": self.status,
            "message": self.message,
            "user_request": self.user_request,
            "keywords": list(self.keywords),
            "context_text": self.context_text,
            "baseline_count": self.baseline_count,
            "preference_count": self.preference_count,
            "case_count": self.case_count,
            "knowledge_count": self.knowledge_count,
            "source_status": self.source_status,
            "warnings": list(self.warnings),
        }


def compact_text(value: Any, max_length: int = DEFAULT_MAX_VALUE_LENGTH) -> str:
    """
    Convert a value into compact single-line text.
    """
    if value is None:
        return "none"

    if isinstance(value, bool):
        return "yes" if value else "no"

    text = str(value).replace("\n", " ").strip()

    while "  " in text:
        text = text.replace("  ", " ")

    if len(text) <= max_length:
        return text

    return text[: max_length - 3].rstrip() + "..."


def flatten_dict(
    data: dict[str, Any],
    *,
    prefix: str = "",
    max_depth: int = 2,
) -> list[tuple[str, Any]]:
    """
    Flatten a small nested dictionary into dotted key/value pairs.
    """
    if max_depth < 0:
        return []

    flattened: list[tuple[str, Any]] = []

    for key, value in data.items():
        key_text = str(key)
        full_key = f"{prefix}.{key_text}" if prefix else key_text

        if isinstance(value, dict) and max_depth > 0:
            flattened.extend(
                flatten_dict(
                    value,
                    prefix=full_key,
                    max_depth=max_depth - 1,
                )
            )
        else:
            flattened.append((full_key, value))

    return flattened


def format_key_value_section(
    *,
    title: str,
    data: dict[str, Any],
    max_items: int,
) -> list[str]:
    """
    Format a small dictionary section.
    """
    lines = [
        f"{title}:",
    ]

    if not data:
        lines.append("- none")
        return lines

    flattened = flatten_dict(data)
    limited_items = flattened[:max_items]

    for key, value in limited_items:
        lines.append(f"- {key}: {compact_text(value)}")

    remaining_count = len(flattened) - len(limited_items)

    if remaining_count > 0:
        lines.append(f"- ... {remaining_count} more item(s) omitted")

    return lines


def get_entry_identifier(entry: dict[str, Any]) -> str:
    """
    Return a stable identifier for a memory or knowledge entry.
    """
    for key in ("case_id", "memory_id", "id"):
        value = entry.get(key)

        if value:
            return str(value)

    return "unknown"


def get_structured_case_card(entry: dict[str, Any]) -> dict[str, Any]:
    """
    Return a structured case_card dictionary when present.
    """
    case_card = entry.get("case_card")

    return case_card if isinstance(case_card, dict) else {}


def get_structured_case_evidence_summary(entry: dict[str, Any]) -> dict[str, Any]:
    """
    Return a structured evidence_summary dictionary when present.
    """
    evidence_summary = entry.get("evidence_summary")

    return evidence_summary if isinstance(evidence_summary, dict) else {}


def get_entry_summary(entry: dict[str, Any]) -> str:
    """
    Return a compact human-readable entry summary.

    Structured case recall cards are summarized from case_card and
    evidence_summary fields. Generic memory/knowledge entries still use the
    legacy summary/title/content keys.
    """
    case_card = get_structured_case_card(entry)

    if case_card:
        evidence_summary = get_structured_case_evidence_summary(entry)
        parts: list[str] = []

        problem = case_card.get("problem")
        lesson = case_card.get("lesson")
        outcome = evidence_summary.get("outcome")

        if problem:
            parts.append(f"Problem: {compact_text(problem)}")

        if lesson:
            parts.append(f"Lesson: {compact_text(lesson)}")

        if outcome:
            parts.append(f"Outcome: {compact_text(outcome)}")

        if parts:
            return " | ".join(parts)

    for key in ("summary", "title", "content_text", "content", "resolution"):
        value = entry.get(key)

        if value:
            return compact_text(value)

    return "No summary available."


def get_entry_tags(entry: dict[str, Any]) -> str:
    """
    Return compact tag text for an entry.
    """
    tags = entry.get("tags", [])

    case_card = get_structured_case_card(entry)

    if case_card:
        tags = case_card.get("tags", tags)

    if isinstance(tags, tuple):
        tags = list(tags)

    if not isinstance(tags, list) or not tags:
        return "none"

    return ", ".join(compact_text(tag, max_length=40) for tag in tags)


def get_entry_outcome(entry: dict[str, Any]) -> str:
    """
    Return a compact outcome or resolution when present.
    """
    evidence_summary = get_structured_case_evidence_summary(entry)
    outcome = evidence_summary.get("outcome")

    if outcome:
        return compact_text(outcome)

    resolution = entry.get("resolution")

    if resolution:
        return compact_text(resolution)

    return ""


def format_scored_entries_section(
    *,
    title: str,
    scored_entries: tuple[ScoredMemoryEntry, ...],
    max_items: int,
) -> list[str]:
    """
    Format scored case or knowledge entries.
    """
    lines = [
        f"{title}:",
    ]

    if not scored_entries:
        lines.append("- none")
        return lines

    limited_entries = scored_entries[:max_items]

    for index, scored_entry in enumerate(limited_entries, start=1):
        entry = scored_entry.entry
        identifier = get_entry_identifier(entry)
        summary = get_entry_summary(entry)
        tags = get_entry_tags(entry)

        lines.append(f"{index}. {identifier}")
        lines.append(f"   Score: {scored_entry.score}")
        lines.append(f"   Summary: {summary}")
        lines.append(f"   Tags: {tags}")

        outcome = get_entry_outcome(entry)

        if outcome:
            lines.append(f"   Outcome: {outcome}")

    remaining_count = len(scored_entries) - len(limited_entries)

    if remaining_count > 0:
        lines.append(f"- ... {remaining_count} more item(s) omitted")

    return lines


def build_source_warnings(
    retrieval_result: MemoryRetrievalResult,
) -> tuple[str, ...]:
    """
    Build warning strings from memory retrieval errors and source-status metadata.
    """
    warnings: list[str] = []

    for error in retrieval_result.errors:
        warnings.append(error)

    cases_status = retrieval_result.source_results.get("cases", {})
    invalid_case_count = cases_status.get("invalid_case_count", 0)

    if isinstance(invalid_case_count, int) and invalid_case_count > 0:
        warnings.append(
            f"Skipped {invalid_case_count} invalid case memory record(s)."
        )

    return tuple(warnings)


def count_flattened_items(data: dict[str, Any]) -> int:
    """
    Count flattened key/value pairs in a dictionary.
    """
    if not data:
        return 0

    return len(flatten_dict(data))


def build_summary_status(
    *,
    retrieval_result: MemoryRetrievalResult,
    baseline_count: int,
    preference_count: int,
    case_count: int,
    knowledge_count: int,
) -> str:
    """
    Build memory summary status.
    """
    total_count = baseline_count + preference_count + case_count + knowledge_count

    if total_count == 0:
        return MEMORY_SUMMARY_STATUS_EMPTY

    if retrieval_result.status != MEMORY_RETRIEVER_STATUS_OK:
        return MEMORY_SUMMARY_STATUS_PARTIAL

    return MEMORY_SUMMARY_STATUS_OK


def build_summary_message(status: str) -> str:
    """
    Build human-readable memory summary message.
    """
    if status == MEMORY_SUMMARY_STATUS_OK:
        return "Memory context summarized successfully."

    if status == MEMORY_SUMMARY_STATUS_PARTIAL:
        return "Memory context summarized with one or more source warnings."

    return "No relevant memory context was found."


def summarize_memory_context(
    retrieval_result: MemoryRetrievalResult,
    *,
    max_baseline_items: int = DEFAULT_MAX_BASELINE_ITEMS,
    max_preference_items: int = DEFAULT_MAX_PREFERENCE_ITEMS,
    max_case_items: int = DEFAULT_MAX_CASE_ITEMS,
    max_knowledge_items: int = DEFAULT_MAX_KNOWLEDGE_ITEMS,
) -> MemorySummaryResult:
    """
    Summarize retrieved memory into a compact context block.
    """
    baseline_count = count_flattened_items(retrieval_result.baselines)
    preference_count = count_flattened_items(retrieval_result.operator_preferences)
    case_count = len(retrieval_result.cases)
    knowledge_count = len(retrieval_result.knowledge_entries)

    status = build_summary_status(
        retrieval_result=retrieval_result,
        baseline_count=baseline_count,
        preference_count=preference_count,
        case_count=case_count,
        knowledge_count=knowledge_count,
    )

    lines = [
        "LIGHTHOUSE MEMORY CONTEXT",
        "=" * 52,
        f"User request: {retrieval_result.query.user_request}",
        (
            "Keywords: "
            + (
                ", ".join(retrieval_result.keywords)
                if retrieval_result.keywords
                else "none"
            )
        ),
        "",
    ]

    lines.extend(
        format_key_value_section(
            title="System baselines",
            data=retrieval_result.baselines,
            max_items=max_baseline_items,
        )
    )
    lines.append("")

    lines.extend(
        format_key_value_section(
            title="Operator preferences",
            data=retrieval_result.operator_preferences,
            max_items=max_preference_items,
        )
    )
    lines.append("")

    lines.extend(
        format_scored_entries_section(
            title="Relevant case memories",
            scored_entries=retrieval_result.cases,
            max_items=max_case_items,
        )
    )
    lines.append("")

    lines.extend(
        format_scored_entries_section(
            title="Relevant knowledge entries",
            scored_entries=retrieval_result.knowledge_entries,
            max_items=max_knowledge_items,
        )
    )

    warnings = build_source_warnings(retrieval_result)

    if warnings:
        lines.append("")
        lines.append("Memory source warnings:")

        for warning in warnings:
            lines.append(f"- {warning}")

    lines.append("=" * 52)

    return MemorySummaryResult(
        status=status,
        message=build_summary_message(status),
        user_request=retrieval_result.query.user_request,
        keywords=retrieval_result.keywords,
        context_text="\n".join(lines),
        baseline_count=baseline_count,
        preference_count=preference_count,
        case_count=case_count,
        knowledge_count=knowledge_count,
        source_status=retrieval_result.source_results,
        warnings=warnings,
    )


def summarize_memory_for_request(
    user_request: str,
    *,
    memory_dir: Path | str | None = None,
    max_cases: int = DEFAULT_MAX_CASE_ITEMS,
    max_knowledge_entries: int = DEFAULT_MAX_KNOWLEDGE_ITEMS,
) -> MemorySummaryResult:
    """
    Retrieve and summarize memory for an Operator request.
    """
    retrieval_result = retrieve_memory_for_request(
        user_request,
        memory_dir=memory_dir,
        max_cases=max_cases,
        max_knowledge_entries=max_knowledge_entries,
    )

    return summarize_memory_context(retrieval_result)
