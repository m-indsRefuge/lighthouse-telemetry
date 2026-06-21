"""
Structured memory case utilities for Lighthouse.

This module defines the deterministic schema, validation, recall-card extraction,
and relevance scoring behavior for Lighthouse case memories.

It does not call the model.
It does not execute tools.
It does not mutate the OS.
It does not write to memory storage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


JsonDict = dict[str, Any]


CASE_STATUS_RESOLVED = "resolved"
CASE_STATUS_UNRESOLVED = "unresolved"
CASE_STATUS_ARCHIVED = "archived"

ALLOWED_CASE_STATUSES = {
    CASE_STATUS_RESOLVED,
    CASE_STATUS_UNRESOLVED,
    CASE_STATUS_ARCHIVED,
}


CASE_CONFIDENCE_LOW = "low"
CASE_CONFIDENCE_MEDIUM = "medium"
CASE_CONFIDENCE_HIGH = "high"

ALLOWED_CASE_CONFIDENCE_VALUES = {
    CASE_CONFIDENCE_LOW,
    CASE_CONFIDENCE_MEDIUM,
    CASE_CONFIDENCE_HIGH,
}


CASE_SOURCE_OPERATOR_ENTERED = "operator_entered"
CASE_SOURCE_OPERATOR_CONFIRMED = "operator_confirmed"
CASE_SOURCE_MODEL_SUGGESTED = "model_suggested"
CASE_SOURCE_SYSTEM_GENERATED = "system_generated"

ALLOWED_CASE_SOURCES = {
    CASE_SOURCE_OPERATOR_ENTERED,
    CASE_SOURCE_OPERATOR_CONFIRMED,
    CASE_SOURCE_MODEL_SUGGESTED,
    CASE_SOURCE_SYSTEM_GENERATED,
}


MEMORY_INFLUENCE_NONE = "none"
MEMORY_INFLUENCE_SUPPORTING_EVIDENCE = "supporting_evidence"
MEMORY_INFLUENCE_CHANGED_PRIORITY = "changed_priority"
MEMORY_INFLUENCE_CHANGED_RECOMMENDATION = "changed_recommendation"
MEMORY_INFLUENCE_PREVENTED_UNNECESSARY_ACTION = "prevented_unnecessary_action"
MEMORY_INFLUENCE_FLAGGED_RISK = "flagged_risk"

ALLOWED_MEMORY_INFLUENCE_VALUES = {
    MEMORY_INFLUENCE_NONE,
    MEMORY_INFLUENCE_SUPPORTING_EVIDENCE,
    MEMORY_INFLUENCE_CHANGED_PRIORITY,
    MEMORY_INFLUENCE_CHANGED_RECOMMENDATION,
    MEMORY_INFLUENCE_PREVENTED_UNNECESSARY_ACTION,
    MEMORY_INFLUENCE_FLAGGED_RISK,
}


MEMORY_RESULT_NOT_USED = "not_used"
MEMORY_RESULT_HELPFUL = "helpful"
MEMORY_RESULT_NEUTRAL = "neutral"
MEMORY_RESULT_MISLEADING = "misleading"
MEMORY_RESULT_UNKNOWN = "unknown"

ALLOWED_MEMORY_RESULT_VALUES = {
    MEMORY_RESULT_NOT_USED,
    MEMORY_RESULT_HELPFUL,
    MEMORY_RESULT_NEUTRAL,
    MEMORY_RESULT_MISLEADING,
    MEMORY_RESULT_UNKNOWN,
}


RELEVANCE_LABEL_NONE = "none"
RELEVANCE_LABEL_LOW = "low"
RELEVANCE_LABEL_MEDIUM = "medium"
RELEVANCE_LABEL_HIGH = "high"
RELEVANCE_LABEL_EXACT = "exact"

ALLOWED_RELEVANCE_LABELS = {
    RELEVANCE_LABEL_NONE,
    RELEVANCE_LABEL_LOW,
    RELEVANCE_LABEL_MEDIUM,
    RELEVANCE_LABEL_HIGH,
    RELEVANCE_LABEL_EXACT,
}


RETENTION_STANDARD = "standard"
RETENTION_PINNED = "pinned"

ALLOWED_RETENTION_POLICIES = {
    RETENTION_STANDARD,
    RETENTION_PINNED,
}


MEMORY_TYPE_CASE = "case"
MEMORY_TYPE_KNOWLEDGE = "knowledge"
MEMORY_TYPE_BASELINE = "baseline"
MEMORY_TYPE_OPERATOR_PREFERENCE = "operator_preference"

ALLOWED_MEMORY_TYPES = {
    MEMORY_TYPE_CASE,
    MEMORY_TYPE_KNOWLEDGE,
    MEMORY_TYPE_BASELINE,
    MEMORY_TYPE_OPERATOR_PREFERENCE,
}


REQUIRED_TOP_LEVEL_FIELDS = {
    "case_id",
    "created_at",
    "updated_at",
    "status",
    "confidence",
    "source",
    "case_card",
    "evidence",
    "process_trace",
    "memory_usage_trace",
    "lifecycle",
}

REQUIRED_CASE_CARD_FIELDS = {
    "problem",
    "symptoms",
    "suspected_cause",
    "lesson",
    "tags",
}

REQUIRED_EVIDENCE_FIELDS = {
    "telemetry_evidence",
    "event_evidence",
    "action_taken",
    "outcome",
}

REQUIRED_PROCESS_TRACE_FIELDS = {
    "diagnostic_steps",
    "decision_notes",
    "operator_feedback",
}

REQUIRED_MEMORY_USAGE_TRACE_FIELDS = {
    "memory_context_used",
    "retrieved_case_ids",
    "retrieved_knowledge_ids",
    "retrieved_baseline_keys",
    "memory_influence",
    "memory_result",
    "memory_relevance_score",
    "memory_relevance_label",
    "retrieved_memory_scores",
    "memory_notes",
}

REQUIRED_LIFECYCLE_FIELDS = {
    "use_count",
    "last_used_at",
    "pinned",
    "retention_policy",
}


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "because",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "please",
    "should",
    "so",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "why",
    "with",
    "would",
    "you",
    "your",
}


UNSAFE_MEMORY_TEXT_PATTERNS = {
    "ignore previous instructions",
    "bypass validation",
    "skip confirmation",
    "skip operator confirmation",
    "without confirmation next time",
    "disable safety",
    "override safety",
    "delete system32",
    "edit registry without confirmation",
    "run raw command",
}


@dataclass(frozen=True)
class MemoryCaseValidationResult:
    """
    Validation result for a structured case memory.
    """

    valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> JsonDict:
        """
        Return a serializable validation result.
        """
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class CaseRelevanceResult:
    """
    Deterministic relevance score for a case memory.
    """

    score: float
    label: str
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> JsonDict:
        """
        Return a serializable relevance result.
        """
        return {
            "score": self.score,
            "label": self.label,
            "reasons": list(self.reasons),
        }


def utc_now_iso() -> str:
    """
    Return the current UTC time in ISO format.
    """
    return datetime.now(UTC).isoformat()


def normalize_score(score: Any) -> float:
    """
    Normalize a numeric score into the inclusive 0.0 to 1.0 range.

    Non-numeric values normalize to 0.0.
    """
    if isinstance(score, bool):
        return 0.0

    try:
        numeric_score = float(score)
    except (TypeError, ValueError):
        return 0.0

    if numeric_score < 0.0:
        return 0.0

    if numeric_score > 1.0:
        return 1.0

    return round(numeric_score, 4)


def relevance_label_for_score(score: Any) -> str:
    """
    Return a relevance label for a bounded score.
    """
    normalized = normalize_score(score)

    if normalized >= 0.9:
        return RELEVANCE_LABEL_EXACT

    if normalized >= 0.7:
        return RELEVANCE_LABEL_HIGH

    if normalized >= 0.4:
        return RELEVANCE_LABEL_MEDIUM

    if normalized > 0.0:
        return RELEVANCE_LABEL_LOW

    return RELEVANCE_LABEL_NONE


def slugify(value: str) -> str:
    """
    Convert text into a stable lowercase slug.
    """
    cleaned = value.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned)
    cleaned = cleaned.strip("_")

    return cleaned or "case"


def build_case_id(
    *,
    problem: str,
    tags: list[str] | tuple[str, ...],
    created_at: str,
) -> str:
    """
    Build a deterministic readable case identifier.
    """
    primary_tag = "general"
    normalized_tags = normalize_tags(tags)

    if normalized_tags:
        primary_tag = normalized_tags[0]

    problem_slug = slugify(problem)[:40]
    timestamp_slug = slugify(created_at.replace("+00:00", "z"))[:24]

    return f"case_{primary_tag}_{problem_slug}_{timestamp_slug}"


def normalize_tags(tags: list[str] | tuple[str, ...] | Any) -> list[str]:
    """
    Normalize tag input into unique lowercase slug-like values.

    Non-list and non-tuple values produce an empty list.
    """
    if not isinstance(tags, (list, tuple)):
        return []

    normalized_tags: list[str] = []

    for tag in tags:
        if not isinstance(tag, str):
            continue

        cleaned = slugify(tag)

        if cleaned and cleaned not in normalized_tags:
            normalized_tags.append(cleaned)

    return normalized_tags


def build_memory_usage_trace(
    *,
    memory_context_used: bool = False,
    retrieved_case_ids: list[str] | tuple[str, ...] | None = None,
    retrieved_knowledge_ids: list[str] | tuple[str, ...] | None = None,
    retrieved_baseline_keys: list[str] | tuple[str, ...] | None = None,
    memory_influence: str = MEMORY_INFLUENCE_NONE,
    memory_result: str = MEMORY_RESULT_UNKNOWN,
    memory_relevance_score: float = 0.0,
    retrieved_memory_scores: list[JsonDict] | tuple[JsonDict, ...] | None = None,
    memory_notes: list[str] | tuple[str, ...] | None = None,
) -> JsonDict:
    """
    Build a structured trace describing how memory influenced a case.
    """
    normalized_score = normalize_score(memory_relevance_score)

    return {
        "memory_context_used": bool(memory_context_used),
        "retrieved_case_ids": normalize_string_list(retrieved_case_ids),
        "retrieved_knowledge_ids": normalize_string_list(retrieved_knowledge_ids),
        "retrieved_baseline_keys": normalize_string_list(retrieved_baseline_keys),
        "memory_influence": memory_influence,
        "memory_result": memory_result,
        "memory_relevance_score": normalized_score,
        "memory_relevance_label": relevance_label_for_score(normalized_score),
        "retrieved_memory_scores": list(retrieved_memory_scores or []),
        "memory_notes": normalize_string_list(memory_notes),
    }


def validate_case_memory(case_memory: Any) -> MemoryCaseValidationResult:
    """
    Validate a structured Lighthouse memory case.

    Invalid records are rejected with explicit errors. Warnings are reserved for
    non-fatal quality concerns only.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(case_memory, dict):
        return MemoryCaseValidationResult(
            valid=False,
            errors=("case_memory must be a dictionary.",),
        )

    validate_required_fields(
        value=case_memory,
        required_fields=REQUIRED_TOP_LEVEL_FIELDS,
        path="case_memory",
        errors=errors,
    )

    validate_non_empty_string(
        case_memory.get("case_id"),
        "case_id",
        errors,
    )

    validate_non_empty_string(
        case_memory.get("created_at"),
        "created_at",
        errors,
    )

    validate_non_empty_string(
        case_memory.get("updated_at"),
        "updated_at",
        errors,
    )

    validate_enum_value(
        case_memory.get("status"),
        ALLOWED_CASE_STATUSES,
        "status",
        errors,
    )

    validate_enum_value(
        case_memory.get("confidence"),
        ALLOWED_CASE_CONFIDENCE_VALUES,
        "confidence",
        errors,
    )

    validate_enum_value(
        case_memory.get("source"),
        ALLOWED_CASE_SOURCES,
        "source",
        errors,
    )

    validate_case_card(case_memory.get("case_card"), errors)
    validate_evidence(case_memory.get("evidence"), errors)
    validate_process_trace(case_memory.get("process_trace"), errors)
    validate_memory_usage_trace(case_memory.get("memory_usage_trace"), errors)
    validate_lifecycle(case_memory.get("lifecycle"), errors)

    unsafe_paths = find_unsafe_text_paths(case_memory)

    for unsafe_path in unsafe_paths:
        errors.append(f"{unsafe_path} contains unsafe memory text.")

    return MemoryCaseValidationResult(
        valid=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def is_valid_case_memory(case_memory: Any) -> bool:
    """
    Return True when a case memory passes validation.
    """
    return validate_case_memory(case_memory).valid


def extract_case_recall_card(case_memory: JsonDict) -> JsonDict:
    """
    Return a compact recall-safe card for a memory case.

    The recall card intentionally excludes process_trace and memory_usage_trace.
    """
    case_card = case_memory.get("case_card", {})
    evidence = case_memory.get("evidence", {})
    telemetry_evidence = evidence.get("telemetry_evidence", {})

    evidence_summary = {
        "memory_usage_percent": telemetry_evidence.get("memory_usage_percent"),
        "cpu_usage_percent": telemetry_evidence.get("cpu_usage_percent"),
        "disk_usage_percent": telemetry_evidence.get("disk_usage_percent"),
        "top_process_name": telemetry_evidence.get("top_process_name"),
        "top_process_memory_mb": telemetry_evidence.get("top_process_memory_mb"),
        "action_taken": evidence.get("action_taken"),
        "outcome": evidence.get("outcome"),
    }

    return {
        "case_id": case_memory.get("case_id"),
        "created_at": case_memory.get("created_at"),
        "updated_at": case_memory.get("updated_at"),
        "status": case_memory.get("status"),
        "confidence": case_memory.get("confidence"),
        "source": case_memory.get("source"),
        "case_card": {
            "problem": case_card.get("problem"),
            "symptoms": list(case_card.get("symptoms", [])),
            "suspected_cause": case_card.get("suspected_cause"),
            "lesson": case_card.get("lesson"),
            "tags": list(case_card.get("tags", [])),
        },
        "evidence_summary": evidence_summary,
        "lifecycle": dict(case_memory.get("lifecycle", {})),
    }


def score_case_relevance(
    case_memory: JsonDict,
    *,
    user_request: str,
    telemetry: JsonDict | None = None,
) -> CaseRelevanceResult:
    """
    Score a case memory against a user request and optional telemetry.

    The score is deterministic and bounded from 0.0 to 1.0.
    """
    if not is_valid_case_memory(case_memory):
        return CaseRelevanceResult(
            score=0.0,
            label=RELEVANCE_LABEL_NONE,
            reasons=("invalid_case_memory",),
        )

    request_tokens = tokenize_text(user_request)
    searchable_text = build_case_searchable_text(case_memory)
    case_tokens = tokenize_text(searchable_text)

    reasons: list[str] = []
    score = 0.0

    if request_tokens and case_tokens:
        overlap = sorted(request_tokens.intersection(case_tokens))
        overlap_ratio = len(overlap) / max(len(request_tokens), 1)

        if overlap_ratio > 0:
            score += min(0.45, overlap_ratio * 0.45)
            reasons.append("request_text_match")

    telemetry_score, telemetry_reasons = score_telemetry_relevance(
        case_memory,
        telemetry or {},
    )
    score += telemetry_score
    reasons.extend(telemetry_reasons)

    if case_memory.get("status") == CASE_STATUS_RESOLVED:
        score += 0.1
        reasons.append("resolved_case")

    if case_memory.get("confidence") == CASE_CONFIDENCE_HIGH:
        score += 0.1
        reasons.append("high_confidence")
    elif case_memory.get("confidence") == CASE_CONFIDENCE_MEDIUM:
        score += 0.05
        reasons.append("medium_confidence")

    normalized_score = normalize_score(score)

    if normalized_score == 0.0:
        reasons.append("no_relevance_signals")

    return CaseRelevanceResult(
        score=normalized_score,
        label=relevance_label_for_score(normalized_score),
        reasons=tuple(dedupe_strings(reasons)),
    )


def sort_cases_by_relevance(
    case_memories: list[JsonDict] | tuple[JsonDict, ...],
    *,
    user_request: str,
    telemetry: JsonDict | None = None,
    limit: int = 0,
) -> list[tuple[JsonDict, CaseRelevanceResult]]:
    """
    Return case memories sorted by deterministic relevance.

    Ordering is by highest score first, then case_id for stable tie-breaking.
    """
    scored_cases: list[tuple[JsonDict, CaseRelevanceResult]] = []

    for case_memory in case_memories:
        relevance = score_case_relevance(
            case_memory,
            user_request=user_request,
            telemetry=telemetry,
        )
        scored_cases.append((case_memory, relevance))

    scored_cases.sort(
        key=lambda item: (
            -item[1].score,
            str(item[0].get("case_id", "")),
        )
    )

    if limit > 0:
        return scored_cases[:limit]

    return scored_cases


def validate_case_card(value: Any, errors: list[str]) -> None:
    """
    Validate the case_card section.
    """
    if not isinstance(value, dict):
        errors.append("case_card must be a dictionary.")
        return

    validate_required_fields(
        value=value,
        required_fields=REQUIRED_CASE_CARD_FIELDS,
        path="case_card",
        errors=errors,
    )

    validate_non_empty_string(value.get("problem"), "case_card.problem", errors)
    validate_non_empty_string(
        value.get("suspected_cause"),
        "case_card.suspected_cause",
        errors,
    )
    validate_non_empty_string(value.get("lesson"), "case_card.lesson", errors)

    symptoms = value.get("symptoms")

    if not is_non_empty_string_list(symptoms):
        errors.append("case_card.symptoms must be a non-empty list of strings.")

    tags = value.get("tags")

    if not is_non_empty_string_list(tags):
        errors.append("case_card.tags must be a non-empty list of strings.")


def validate_evidence(value: Any, errors: list[str]) -> None:
    """
    Validate the evidence section.
    """
    if not isinstance(value, dict):
        errors.append("evidence must be a dictionary.")
        return

    validate_required_fields(
        value=value,
        required_fields=REQUIRED_EVIDENCE_FIELDS,
        path="evidence",
        errors=errors,
    )

    telemetry_evidence = value.get("telemetry_evidence")

    if not isinstance(telemetry_evidence, dict) or not telemetry_evidence:
        errors.append("evidence.telemetry_evidence must be a non-empty dictionary.")

    event_evidence = value.get("event_evidence")

    if not isinstance(event_evidence, dict):
        errors.append("evidence.event_evidence must be a dictionary.")

    validate_non_empty_string(
        value.get("action_taken"),
        "evidence.action_taken",
        errors,
    )
    validate_non_empty_string(value.get("outcome"), "evidence.outcome", errors)


def validate_process_trace(value: Any, errors: list[str]) -> None:
    """
    Validate the process_trace section.
    """
    if not isinstance(value, dict):
        errors.append("process_trace must be a dictionary.")
        return

    validate_required_fields(
        value=value,
        required_fields=REQUIRED_PROCESS_TRACE_FIELDS,
        path="process_trace",
        errors=errors,
    )

    diagnostic_steps = value.get("diagnostic_steps")

    if not is_string_list(diagnostic_steps):
        errors.append("process_trace.diagnostic_steps must be a list of strings.")

    decision_notes = value.get("decision_notes")

    if not is_string_list(decision_notes):
        errors.append("process_trace.decision_notes must be a list of strings.")

    operator_feedback = value.get("operator_feedback")

    if not isinstance(operator_feedback, str):
        errors.append("process_trace.operator_feedback must be a string.")


def validate_memory_usage_trace(value: Any, errors: list[str]) -> None:
    """
    Validate the memory_usage_trace section.
    """
    if not isinstance(value, dict):
        errors.append("memory_usage_trace must be a dictionary.")
        return

    validate_required_fields(
        value=value,
        required_fields=REQUIRED_MEMORY_USAGE_TRACE_FIELDS,
        path="memory_usage_trace",
        errors=errors,
    )

    memory_context_used = value.get("memory_context_used")

    if not isinstance(memory_context_used, bool):
        errors.append("memory_usage_trace.memory_context_used must be a boolean.")

    retrieved_case_ids = value.get("retrieved_case_ids")
    retrieved_knowledge_ids = value.get("retrieved_knowledge_ids")
    retrieved_baseline_keys = value.get("retrieved_baseline_keys")
    retrieved_memory_scores = value.get("retrieved_memory_scores")
    memory_notes = value.get("memory_notes")

    if not is_string_list(retrieved_case_ids):
        errors.append("memory_usage_trace.retrieved_case_ids must be a list of strings.")

    if not is_string_list(retrieved_knowledge_ids):
        errors.append(
            "memory_usage_trace.retrieved_knowledge_ids must be a list of strings."
        )

    if not is_string_list(retrieved_baseline_keys):
        errors.append(
            "memory_usage_trace.retrieved_baseline_keys must be a list of strings."
        )

    if not isinstance(retrieved_memory_scores, list):
        errors.append("memory_usage_trace.retrieved_memory_scores must be a list.")

    if not is_string_list(memory_notes):
        errors.append("memory_usage_trace.memory_notes must be a list of strings.")

    validate_enum_value(
        value.get("memory_influence"),
        ALLOWED_MEMORY_INFLUENCE_VALUES,
        "memory_usage_trace.memory_influence",
        errors,
    )

    validate_enum_value(
        value.get("memory_result"),
        ALLOWED_MEMORY_RESULT_VALUES,
        "memory_usage_trace.memory_result",
        errors,
    )

    relevance_score = value.get("memory_relevance_score")

    if isinstance(relevance_score, bool) or not isinstance(relevance_score, (int, float)):
        errors.append("memory_usage_trace.memory_relevance_score must be numeric.")
    elif relevance_score < 0.0 or relevance_score > 1.0:
        errors.append(
            "memory_usage_trace.memory_relevance_score must be between 0.0 and 1.0."
        )

    validate_enum_value(
        value.get("memory_relevance_label"),
        ALLOWED_RELEVANCE_LABELS,
        "memory_usage_trace.memory_relevance_label",
        errors,
    )

    validate_memory_usage_trace_contradictions(value, errors)


def validate_memory_usage_trace_contradictions(
    value: JsonDict,
    errors: list[str],
) -> None:
    """
    Reject logically contradictory memory usage traces.
    """
    memory_context_used = value.get("memory_context_used")
    memory_influence = value.get("memory_influence")
    memory_result = value.get("memory_result")
    relevance_score = value.get("memory_relevance_score")
    relevance_label = value.get("memory_relevance_label")
    retrieved_case_ids = value.get("retrieved_case_ids")
    retrieved_knowledge_ids = value.get("retrieved_knowledge_ids")
    retrieved_baseline_keys = value.get("retrieved_baseline_keys")
    retrieved_memory_scores = value.get("retrieved_memory_scores")

    if memory_context_used is False:
        if retrieved_case_ids:
            errors.append(
                "memory_usage_trace.memory_context_used is false but "
                "retrieved_case_ids is non-empty."
            )

        if retrieved_knowledge_ids:
            errors.append(
                "memory_usage_trace.memory_context_used is false but "
                "retrieved_knowledge_ids is non-empty."
            )

        if retrieved_baseline_keys:
            errors.append(
                "memory_usage_trace.memory_context_used is false but "
                "retrieved_baseline_keys is non-empty."
            )

        if memory_result == MEMORY_RESULT_HELPFUL:
            errors.append(
                "memory_usage_trace.memory_context_used is false but "
                "memory_result is helpful."
            )

        if memory_influence != MEMORY_INFLUENCE_NONE:
            errors.append(
                "memory_usage_trace.memory_context_used is false but "
                "memory_influence is not none."
            )

    if memory_result == MEMORY_RESULT_NOT_USED and retrieved_memory_scores:
        errors.append(
            "memory_usage_trace.memory_result is not_used but "
            "retrieved_memory_scores is non-empty."
        )

    if relevance_score == 0.0 and relevance_label == RELEVANCE_LABEL_EXACT:
        errors.append(
            "memory_usage_trace.memory_relevance_score is 0.0 but "
            "memory_relevance_label is exact."
        )

    if isinstance(relevance_score, (int, float)) and not isinstance(relevance_score, bool):
        expected_label = relevance_label_for_score(relevance_score)

        if relevance_label != expected_label:
            errors.append(
                "memory_usage_trace.memory_relevance_label does not match "
                "memory_relevance_score."
            )


def validate_lifecycle(value: Any, errors: list[str]) -> None:
    """
    Validate the lifecycle section.
    """
    if not isinstance(value, dict):
        errors.append("lifecycle must be a dictionary.")
        return

    validate_required_fields(
        value=value,
        required_fields=REQUIRED_LIFECYCLE_FIELDS,
        path="lifecycle",
        errors=errors,
    )

    use_count = value.get("use_count")

    if isinstance(use_count, bool) or not isinstance(use_count, int):
        errors.append("lifecycle.use_count must be an integer.")
    elif use_count < 0:
        errors.append("lifecycle.use_count must be greater than or equal to 0.")

    last_used_at = value.get("last_used_at")

    if last_used_at is not None and not isinstance(last_used_at, str):
        errors.append("lifecycle.last_used_at must be null or a string.")

    pinned = value.get("pinned")

    if not isinstance(pinned, bool):
        errors.append("lifecycle.pinned must be a boolean.")

    retention_policy = value.get("retention_policy")

    validate_enum_value(
        retention_policy,
        ALLOWED_RETENTION_POLICIES,
        "lifecycle.retention_policy",
        errors,
    )

    if pinned is True and retention_policy != RETENTION_PINNED:
        errors.append(
            "lifecycle.pinned is true but lifecycle.retention_policy is not pinned."
        )

    if pinned is False and retention_policy == RETENTION_PINNED:
        errors.append(
            "lifecycle.pinned is false but lifecycle.retention_policy is pinned."
        )


def validate_required_fields(
    *,
    value: JsonDict,
    required_fields: set[str],
    path: str,
    errors: list[str],
) -> None:
    """
    Validate that all required fields exist.
    """
    for field_name in sorted(required_fields):
        if field_name not in value:
            errors.append(f"{path}.{field_name} is required.")


def validate_non_empty_string(
    value: Any,
    path: str,
    errors: list[str],
) -> None:
    """
    Validate a non-empty string field.
    """
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path} must be a non-empty string.")


def validate_enum_value(
    value: Any,
    allowed_values: set[str],
    path: str,
    errors: list[str],
) -> None:
    """
    Validate that a value is one of the allowed enum values.
    """
    if not isinstance(value, str) or value not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        errors.append(f"{path} must be one of: {allowed}.")


def normalize_string_list(value: list[str] | tuple[str, ...] | None) -> list[str]:
    """
    Normalize optional string-list input.
    """
    if value is None:
        return []

    if not isinstance(value, (list, tuple)):
        return []

    normalized_values: list[str] = []

    for item in value:
        if isinstance(item, str):
            cleaned = item.strip()

            if cleaned:
                normalized_values.append(cleaned)

    return normalized_values


def is_string_list(value: Any) -> bool:
    """
    Return True when value is a list of strings.
    """
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def is_non_empty_string_list(value: Any) -> bool:
    """
    Return True when value is a non-empty list of non-empty strings.
    """
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def find_unsafe_text_paths(value: Any, *, path: str = "") -> list[str]:
    """
    Return paths to strings containing unsafe memory text.
    """
    unsafe_paths: list[str] = []

    if isinstance(value, dict):
        for key, nested_value in value.items():
            nested_path = f"{path}.{key}" if path else str(key)
            unsafe_paths.extend(find_unsafe_text_paths(nested_value, path=nested_path))

        return unsafe_paths

    if isinstance(value, list):
        for index, nested_value in enumerate(value):
            nested_path = f"{path}[{index}]"
            unsafe_paths.extend(find_unsafe_text_paths(nested_value, path=nested_path))

        return unsafe_paths

    if isinstance(value, str):
        lowered = value.lower()

        for unsafe_pattern in UNSAFE_MEMORY_TEXT_PATTERNS:
            if unsafe_pattern in lowered:
                unsafe_paths.append(path or "value")
                break

    return unsafe_paths


def tokenize_text(value: str) -> set[str]:
    """
    Tokenize text for deterministic relevance scoring.
    """
    if not isinstance(value, str):
        return set()

    tokens = {
        token
        for token in re.split(r"[^a-zA-Z0-9_]+", value.lower())
        if token and token not in STOPWORDS
    }

    return tokens


def build_case_searchable_text(case_memory: JsonDict) -> str:
    """
    Build searchable text from recall-safe case fields.
    """
    case_card = case_memory.get("case_card", {})
    evidence = case_memory.get("evidence", {})
    telemetry_evidence = evidence.get("telemetry_evidence", {})

    parts = [
        case_memory.get("case_id", ""),
        case_memory.get("status", ""),
        case_memory.get("confidence", ""),
        case_card.get("problem", ""),
        case_card.get("suspected_cause", ""),
        case_card.get("lesson", ""),
        " ".join(case_card.get("symptoms", [])),
        " ".join(case_card.get("tags", [])),
        evidence.get("action_taken", ""),
        evidence.get("outcome", ""),
        str(telemetry_evidence.get("top_process_name", "")),
    ]

    return " ".join(str(part) for part in parts if part)


def score_telemetry_relevance(
    case_memory: JsonDict,
    telemetry: JsonDict,
) -> tuple[float, list[str]]:
    """
    Score telemetry similarity between current telemetry and a memory case.
    """
    if not telemetry:
        return 0.0, []

    evidence = case_memory.get("evidence", {})
    telemetry_evidence = evidence.get("telemetry_evidence", {})

    score = 0.0
    reasons: list[str] = []

    current_top_process = extract_top_process_name(telemetry)
    case_top_process = telemetry_evidence.get("top_process_name")

    if current_top_process and case_top_process:
        if str(current_top_process).lower() == str(case_top_process).lower():
            score += 0.2
            reasons.append("telemetry_process_match")

    current_memory_percent = extract_memory_usage_percent(telemetry)
    case_memory_percent = telemetry_evidence.get("memory_usage_percent")

    if is_high_memory(current_memory_percent) and is_high_memory(case_memory_percent):
        score += 0.15
        reasons.append("memory_pressure_match")

    current_cpu_percent = extract_cpu_usage_percent(telemetry)
    case_cpu_percent = telemetry_evidence.get("cpu_usage_percent")

    if is_low_cpu(current_cpu_percent) and is_low_cpu(case_cpu_percent):
        score += 0.05
        reasons.append("low_cpu_pattern_match")

    return score, reasons


def extract_top_process_name(telemetry: JsonDict) -> str:
    """
    Extract the top process name from telemetry.
    """
    processes = telemetry.get("processes", {})
    process_list = processes.get("processes", [])

    if not isinstance(processes, dict):
        return ""

    if not isinstance(process_list, list) or not process_list:
        return ""

    top_process = process_list[0]

    if not isinstance(top_process, dict):
        return ""

    name = top_process.get("name", "")

    return str(name)


def extract_memory_usage_percent(telemetry: JsonDict) -> float | None:
    """
    Extract memory usage percent from telemetry.
    """
    memory = telemetry.get("memory", {})

    if not isinstance(memory, dict):
        return None

    value = memory.get("usage_percent")

    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def extract_cpu_usage_percent(telemetry: JsonDict) -> float | None:
    """
    Extract CPU usage percent from telemetry.
    """
    cpu = telemetry.get("cpu", {})

    if not isinstance(cpu, dict):
        return None

    value = cpu.get("usage_percent")

    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def is_high_memory(value: Any) -> bool:
    """
    Return True when memory usage is high enough to indicate pressure.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 75


def is_low_cpu(value: Any) -> bool:
    """
    Return True when CPU usage is low.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value <= 20


def dedupe_strings(values: list[str] | tuple[str, ...]) -> list[str]:
    """
    Return values without duplicates while preserving order.
    """
    deduped: list[str] = []

    for value in values:
        if value not in deduped:
            deduped.append(value)

    return deduped