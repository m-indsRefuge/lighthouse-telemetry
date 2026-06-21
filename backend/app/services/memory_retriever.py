"""
Memory retriever for Lighthouse.

This module retrieves relevant Lighthouse memory for an Operator request.

It does not mutate memory.
It does not execute tools.
It does not make final safety decisions.
It returns controlled context that the Lighthouse Engine can later pass to the
reasoning/model layer.

Structured case memories are validated and converted into recall-safe cards
before they can influence engine memory context.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Any

from app.services.memory_cases import (
    extract_case_recall_card,
    validate_case_memory,
)
from app.services.memory_store import (
    MEMORY_STORE_STATUS_OK,
    read_baselines,
    read_case_memories,
    read_knowledge_index,
    read_operator_preferences,
)


MEMORY_RETRIEVER_STATUS_OK = "ok"
MEMORY_RETRIEVER_STATUS_PARTIAL = "partial"
MEMORY_RETRIEVER_STATUS_ERROR = "error"

DEFAULT_CASE_LIMIT = 5
DEFAULT_KNOWLEDGE_LIMIT = 5

MIN_KEYWORD_LENGTH = 3

STOPWORDS = {
    "about",
    "after",
    "again",
    "and",
    "because",
    "before",
    "being",
    "could",
    "does",
    "from",
    "have",
    "into",
    "laptop",
    "please",
    "show",
    "some",
    "tell",
    "that",
    "the",
    "their",
    "there",
    "this",
    "what",
    "when",
    "where",
    "which",
    "while",
    "why",
    "with",
    "would",
    "your",
}


@dataclass(frozen=True)
class MemoryRetrievalQuery:
    """
    Query used to retrieve relevant Lighthouse memory.
    """

    user_request: str
    include_baselines: bool = True
    include_operator_preferences: bool = True
    include_cases: bool = True
    include_knowledge: bool = True
    max_cases: int = DEFAULT_CASE_LIMIT
    max_knowledge_entries: int = DEFAULT_KNOWLEDGE_LIMIT
    keywords: tuple[str, ...] = ()

    def resolved_keywords(self) -> tuple[str, ...]:
        """
        Return explicit keywords or extract them from the user request.
        """
        if self.keywords:
            return normalize_keywords(self.keywords)

        return extract_keywords(self.user_request)

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable query shape.
        """
        return {
            "user_request": self.user_request,
            "include_baselines": self.include_baselines,
            "include_operator_preferences": self.include_operator_preferences,
            "include_cases": self.include_cases,
            "include_knowledge": self.include_knowledge,
            "max_cases": self.max_cases,
            "max_knowledge_entries": self.max_knowledge_entries,
            "keywords": list(self.keywords),
        }


@dataclass(frozen=True)
class ScoredMemoryEntry:
    """
    A memory entry with a relevance score.
    """

    score: int
    entry: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable scored entry shape.
        """
        return {
            "score": self.score,
            "entry": self.entry,
        }


@dataclass(frozen=True)
class MemoryRetrievalResult:
    """
    Result returned by memory retrieval.
    """

    status: str
    message: str
    query: MemoryRetrievalQuery
    keywords: tuple[str, ...]
    baselines: dict[str, Any]
    operator_preferences: dict[str, Any]
    cases: tuple[ScoredMemoryEntry, ...]
    knowledge_entries: tuple[ScoredMemoryEntry, ...]
    source_results: dict[str, dict[str, Any]]
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable retrieval result shape.
        """
        return {
            "status": self.status,
            "message": self.message,
            "query": self.query.to_dict(),
            "keywords": list(self.keywords),
            "baselines": self.baselines,
            "operator_preferences": self.operator_preferences,
            "cases": [case.to_dict() for case in self.cases],
            "knowledge_entries": [
                entry.to_dict()
                for entry in self.knowledge_entries
            ],
            "source_results": self.source_results,
            "errors": list(self.errors),
        }


def normalize_text(value: Any) -> str:
    """
    Normalize text for conservative keyword matching.
    """
    text = str(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_keyword(keyword: str) -> str:
    """
    Normalize one keyword.
    """
    return normalize_text(keyword)


def normalize_keywords(keywords: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """
    Normalize, deduplicate, and sort keywords.
    """
    normalized = {
        normalize_keyword(keyword)
        for keyword in keywords
        if isinstance(keyword, str)
        and len(normalize_keyword(keyword)) >= MIN_KEYWORD_LENGTH
        and normalize_keyword(keyword) not in STOPWORDS
    }

    return tuple(sorted(normalized))


def extract_keywords(user_request: str) -> tuple[str, ...]:
    """
    Extract simple retrieval keywords from an Operator request.
    """
    normalized_request = normalize_text(user_request)
    raw_terms = tuple(normalized_request.split())

    return normalize_keywords(raw_terms)


def is_structured_case_recall_card(value: Any) -> bool:
    """
    Return True when value appears to be a structured case recall card.
    """
    return (
        isinstance(value, dict)
        and isinstance(value.get("case_card"), dict)
        and isinstance(value.get("evidence_summary"), dict)
    )


def structured_case_recall_card_to_searchable_text(entry: dict[str, Any]) -> str:
    """
    Build searchable text from recall-safe structured case fields.

    This intentionally avoids generic telemetry key names such as
    memory_usage_percent and disk_usage_percent because those keys appear on
    most recall cards and would create weak false-positive matches.
    """
    case_card = entry.get("case_card", {})
    evidence_summary = entry.get("evidence_summary", {})

    parts: list[Any] = []

    if isinstance(case_card, dict):
        parts.extend(
            [
                case_card.get("problem", ""),
                case_card.get("symptoms", []),
                case_card.get("suspected_cause", ""),
                case_card.get("lesson", ""),
                case_card.get("tags", []),
            ]
        )

    if isinstance(evidence_summary, dict):
        parts.extend(
            [
                evidence_summary.get("top_process_name", ""),
                evidence_summary.get("action_taken", ""),
                evidence_summary.get("outcome", ""),
            ]
        )

    return " ".join(value_to_searchable_text(part) for part in parts if part)


def value_to_searchable_text(value: Any) -> str:
    """
    Convert nested memory values into searchable text.

    Identifier fields are included by key name but their values are not scored.
    This avoids an entry id like "chrome" artificially increasing relevance
    beyond the actual memory content.

    Structured case recall cards use a narrower searchable projection so common
    telemetry key names do not create false-positive relevance matches.
    """
    if value is None:
        return ""

    if isinstance(value, str):
        return normalize_text(value)

    if isinstance(value, (int, float, bool)):
        return normalize_text(value)

    if is_structured_case_recall_card(value):
        return structured_case_recall_card_to_searchable_text(value)

    if isinstance(value, dict):
        parts: list[str] = []

        for key, nested_value in value.items():
            normalized_key = normalize_text(key)
            parts.append(normalized_key)

            if normalized_key in {"id", "case_id", "memory_id"}:
                continue

            parts.append(value_to_searchable_text(nested_value))

        return " ".join(part for part in parts if part)

    if isinstance(value, (list, tuple, set)):
        return " ".join(
            part
            for part in (value_to_searchable_text(item) for item in value)
            if part
        )

    return normalize_text(value)


def score_text_for_keywords(text: str, keywords: tuple[str, ...]) -> int:
    """
    Score text against keywords using simple whole-term matching.
    """
    if not keywords:
        return 0

    normalized_text = normalize_text(text)

    if not normalized_text:
        return 0

    score = 0

    for keyword in keywords:
        pattern = rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])"
        matches = re.findall(pattern, normalized_text)
        score += len(matches)

    return score


def score_memory_entry(
    entry: dict[str, Any],
    keywords: tuple[str, ...],
) -> ScoredMemoryEntry:
    """
    Score one memory entry against query keywords.
    """
    searchable_text = value_to_searchable_text(entry)
    score = score_text_for_keywords(searchable_text, keywords)

    return ScoredMemoryEntry(
        score=score,
        entry=entry,
    )


def get_entry_identifier(entry: dict[str, Any]) -> str:
    """
    Return a stable identifier for deterministic tie-breaking.
    """
    for key in ("case_id", "memory_id", "id"):
        value = entry.get(key)

        if value:
            return str(value)

    return ""


def filter_and_rank_entries(
    entries: list[dict[str, Any]],
    *,
    keywords: tuple[str, ...],
    limit: int,
    include_recent_when_no_keywords: bool = True,
) -> tuple[ScoredMemoryEntry, ...]:
    """
    Filter and rank entries by keyword relevance.

    If no keywords are available, return recent entries with score 0.
    """
    if limit <= 0:
        return ()

    scored_entries = [
        score_memory_entry(entry, keywords)
        for entry in entries
        if isinstance(entry, dict)
    ]

    if not keywords:
        if not include_recent_when_no_keywords:
            return ()

        return tuple(scored_entries[:limit])

    relevant_entries = [
        scored_entry
        for scored_entry in scored_entries
        if scored_entry.score > 0
    ]

    relevant_entries.sort(
        key=lambda item: (
            -item.score,
            get_entry_identifier(item.entry),
        )
    )

    return tuple(relevant_entries[:limit])


def compact_source_result(result: Any) -> dict[str, Any]:
    """
    Convert a memory-store result into a compact source result.
    """
    return {
        "status": getattr(result, "status", "unknown"),
        "message": getattr(result, "message", ""),
        "path": str(getattr(result, "path", "")),
        "error": getattr(result, "error", None),
    }


def collect_source_error(source_name: str, source_result: Any) -> str | None:
    """
    Return a compact source error message when a memory-store result failed.
    """
    if getattr(source_result, "status", None) == MEMORY_STORE_STATUS_OK:
        return None

    error = getattr(source_result, "error", None)
    message = getattr(source_result, "message", "Unknown memory source error.")

    if error:
        return f"{source_name}: {message} ({error})"

    return f"{source_name}: {message}"


def get_entries_from_store_result(result: Any) -> list[dict[str, Any]]:
    """
    Extract list entries from a memory-store result.

    memory_store.py returns JSONL reads as {"entries": [...]}; this helper also
    accepts direct list-shaped data for defensive compatibility.
    """
    data = getattr(result, "data", None)

    if isinstance(data, list):
        return [entry for entry in data if isinstance(entry, dict)]

    if isinstance(data, dict):
        entries = data.get("entries", [])

        if isinstance(entries, list):
            return [entry for entry in entries if isinstance(entry, dict)]

    return []


def prepare_case_entries_for_retrieval(
    raw_cases: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """
    Validate stored case memories and return recall-safe case entries.

    Invalid cases are skipped. Valid cases are converted into recall cards so
    process_trace and memory_usage_trace cannot leak into engine memory context.
    """
    recall_safe_cases: list[dict[str, Any]] = []
    invalid_case_count = 0

    for raw_case in raw_cases:
        validation = validate_case_memory(raw_case)

        if not validation.valid:
            invalid_case_count += 1
            continue

        recall_safe_cases.append(extract_case_recall_card(raw_case))

    return recall_safe_cases, invalid_case_count


def build_retrieval_status(errors: list[str]) -> str:
    """
    Build retrieval status from collected errors.
    """
    if not errors:
        return MEMORY_RETRIEVER_STATUS_OK

    return MEMORY_RETRIEVER_STATUS_PARTIAL


def build_retrieval_message(status: str) -> str:
    """
    Build a human-readable retrieval message.
    """
    if status == MEMORY_RETRIEVER_STATUS_OK:
        return "Memory retrieved successfully."

    if status == MEMORY_RETRIEVER_STATUS_PARTIAL:
        return "Memory retrieved with one or more source errors."

    return "Memory retrieval failed."


def retrieve_memory_context(
    query: MemoryRetrievalQuery,
    *,
    memory_dir: Path | str | None = None,
) -> MemoryRetrievalResult:
    """
    Retrieve relevant memory context for an Operator request.
    """
    keywords = query.resolved_keywords()
    source_results: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    baselines: dict[str, Any] = {}
    operator_preferences: dict[str, Any] = {}
    cases: tuple[ScoredMemoryEntry, ...] = ()
    knowledge_entries: tuple[ScoredMemoryEntry, ...] = ()

    if query.include_baselines:
        baseline_result = read_baselines(memory_dir=memory_dir)
        source_results["baselines"] = compact_source_result(baseline_result)

        error = collect_source_error("baselines", baseline_result)

        if error:
            errors.append(error)
        elif isinstance(baseline_result.data, dict):
            baselines = baseline_result.data

    if query.include_operator_preferences:
        preferences_result = read_operator_preferences(memory_dir=memory_dir)
        source_results["operator_preferences"] = compact_source_result(
            preferences_result
        )

        error = collect_source_error("operator_preferences", preferences_result)

        if error:
            errors.append(error)
        elif isinstance(preferences_result.data, dict):
            operator_preferences = preferences_result.data

    if query.include_cases:
        cases_result = read_case_memories(
            limit=None,
            newest_first=True,
            memory_dir=memory_dir,
        )
        source_results["cases"] = compact_source_result(cases_result)

        error = collect_source_error("cases", cases_result)

        if error:
            errors.append(error)
        else:
            raw_cases = get_entries_from_store_result(cases_result)
            recall_safe_cases, invalid_case_count = prepare_case_entries_for_retrieval(
                raw_cases
            )

            source_results["cases"] = {
                **source_results["cases"],
                "raw_case_count": len(raw_cases),
                "valid_case_count": len(recall_safe_cases),
                "invalid_case_count": invalid_case_count,
            }

            cases = filter_and_rank_entries(
                recall_safe_cases,
                keywords=keywords,
                limit=query.max_cases,
            )

    if query.include_knowledge:
        knowledge_result = read_knowledge_index(memory_dir=memory_dir)
        source_results["knowledge_index"] = compact_source_result(knowledge_result)

        error = collect_source_error("knowledge_index", knowledge_result)

        if error:
            errors.append(error)
        elif isinstance(knowledge_result.data, dict):
            raw_entries = knowledge_result.data.get("entries", [])

            if isinstance(raw_entries, list):
                knowledge_entries = filter_and_rank_entries(
                    raw_entries,
                    keywords=keywords,
                    limit=query.max_knowledge_entries,
                    include_recent_when_no_keywords=False,
                )

    status = build_retrieval_status(errors)

    return MemoryRetrievalResult(
        status=status,
        message=build_retrieval_message(status),
        query=query,
        keywords=keywords,
        baselines=baselines,
        operator_preferences=operator_preferences,
        cases=cases,
        knowledge_entries=knowledge_entries,
        source_results=source_results,
        errors=tuple(errors),
    )


def retrieve_memory_for_request(
    user_request: str,
    *,
    memory_dir: Path | str | None = None,
    max_cases: int = DEFAULT_CASE_LIMIT,
    max_knowledge_entries: int = DEFAULT_KNOWLEDGE_LIMIT,
) -> MemoryRetrievalResult:
    """
    Convenience wrapper for retrieving memory from an Operator request.
    """
    query = MemoryRetrievalQuery(
        user_request=user_request,
        max_cases=max_cases,
        max_knowledge_entries=max_knowledge_entries,
    )

    return retrieve_memory_context(
        query,
        memory_dir=memory_dir,
    )
