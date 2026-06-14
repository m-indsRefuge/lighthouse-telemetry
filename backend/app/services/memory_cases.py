"""
Structured case-memory utilities for Lighthouse.

This module defines the core V1 case-memory mechanics.

It does not write files.
It does not call the model.
It does not execute tools.
It only validates, scores, and prepares structured case memories.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import re
from typing import Any


JsonDict = dict[str, Any]


CASE_STATUS_DRAFT = "draft"
CASE_STATUS_OPEN = "open"
CASE_STATUS_RESOLVED = "resolved"
CASE_STATUS_REJECTED = "rejected"
CASE_STATUS_ARCHIVED = "archived"

ALLOWED_CASE_STATUSES = {
    CASE_STATUS_DRAFT,
    CASE_STATUS_OPEN,
    CASE_STATUS_RESOLVED,
    CASE_STATUS_REJECTED,
    CASE_STATUS_ARCHIVED,
}

CASE_CONFIDENCE_LOW = "low"
CASE_CONFIDENCE_MEDIUM = "medium"
CASE_CONFIDENCE_HIGH = "high"

ALLOWED_CASE_CONFIDENCE = {
    CASE_CONFIDENCE_LOW,
    CASE_CONFIDENCE_MEDIUM,
    CASE_CONFIDENCE_HIGH,
}

CASE_SOURCE_OPERATOR_CONFIRMED = "operator_confirmed"
CASE_SOURCE_OPERATOR_ENTERED = "operator_entered"
CASE_SOURCE_SYSTEM_OBSERVED = "system_observed"
CASE_SOURCE_MODEL_PROPOSED = "model_proposed"

ALLOWED_CASE_SOURCES = {
    CASE_SOURCE_OPERATOR_CONFIRMED,
    CASE_SOURCE_OPERATOR_ENTERED,
    CASE_SOURCE_SYSTEM_OBSERVED,
    CASE_SOURCE_MODEL_PROPOSED,
}

MEMORY_INFLUENCE_NONE = "none"
MEMORY_INFLUENCE_SUPPORTING_EVIDENCE = "supporting_evidence"
MEMORY_INFLUENCE_CHANGED_PRIORITY = "changed_priority"
MEMORY_INFLUENCE_CHANGED_RECOMMENDATION = "changed_recommendation"
MEMORY_INFLUENCE_PREVENTED_UNNECESSARY_ACTION = "prevented_unnecessary_action"
MEMORY_INFLUENCE_FLAGGED_RISK = "flagged_risk"

ALLOWED_MEMORY_INFLUENCE = {
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

ALLOWED_MEMORY_RESULTS = {
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

MEMORY_TYPE_CASE = "case"
MEMORY_TYPE_KNOWLEDGE = "knowledge"
MEMORY_TYPE_BASELINE = "baseline"
MEMORY_TYPE_PREFERENCE = "preference"

ALLOWED_RETRIEVED_MEMORY_TYPES = {
    MEMORY_TYPE_CASE,
    MEMORY_TYPE_KNOWLEDGE,
    MEMORY_TYPE_BASELINE,
    MEMORY_TYPE_PREFERENCE,
}

RETENTION_STANDARD = "standard"
RETENTION_PINNED = "pinned"
RETENTION_SHORT = "short"
RETENTION_ARCHIVE = "archive"

ALLOWED_RETENTION_POLICIES = {
    RETENTION_STANDARD,
    RETENTION_PINNED,
    RETENTION_SHORT,
    RETENTION_ARCHIVE,
}

UNSAFE_MEMORY_PHRASES = {
    "without confirmation",
    "bypass confirmation",
    "skip confirmation",
    "ignore confirmation",
    "disable safety",
    "ignore safety",
    "run raw command",
    "raw powershell",
    "delete user files",
    "delete files automatically",
    "edit registry",
    "change drivers",
    "change services",
    "uninstall software",
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "because",
    "for",
    "from",
    "how",
    "is",
    "it",
    "my",
    "of",
    "on",
    "or",
    "please",
    "the",
    "this",
    "to",
    "why",
    "with",
}


@dataclass(frozen=True)
class MemoryCaseValidationResult:
    """
    Validation result for a structured case memory.
    """

    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> JsonDict:
        """
        Convert the validation result into a stable dictionary.
        """
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class CaseRelevanceResult:
    """
    Deterministic relevance result for a case memory.
    """

    case_id: str
    score: float
    label: str
    reasons: tuple[str, ...]

    def to_dict(self) -> JsonDict:
        """
        Convert the relevance result into a stable dictionary.
        """
        return {
            "case_id": self.case_id,
            "score": self.score,
            "label": self.label,
            "reasons": list(self.reasons),
        }


def utc_now_iso() -> str:
    """
    Return the current UTC time as an ISO-8601 string.
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_score(value: Any) -> float:
    """
    Normalize a relevance score into the 0.0 to 1.0 range.
    """
    if isinstance(value, bool):
        return 0.0

    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0

    if score < 0:
        return 0.0

    if score > 1:
        return 1.0

    return round(score, 4)


def relevance_label_for_score(score: float) -> str:
    """
    Convert a numeric relevance score into a simple label.
    """
    normalized = normalize_score(score)

    if normalized >= 0.85:
        return RELEVANCE_LABEL_EXACT

    if normalized >= 0.65:
        return RELEVANCE_LABEL_HIGH

    if normalized >= 0.35:
        return RELEVANCE_LABEL_MEDIUM

    if normalized > 0:
        return RELEVANCE_LABEL_LOW

    return RELEVANCE_LABEL_NONE


def build_case_id(
    problem: str,
    tags: list[str] | tuple[str, ...],
    created_at: str | None = None,
) -> str:
    """
    Build a stable-looking case ID from problem, tags, and timestamp seed.
    """
    timestamp = created_at or utc_now_iso()
    clean_tags = normalize_tags(tags)
    label_source = clean_tags[0] if clean_tags else problem
    label = slugify(label_source) or "case"

    seed = f"{problem}|{','.join(clean_tags)}|{timestamp}"
    digest = sha256(seed.encode("utf-8")).hexdigest()[:8]

    return f"case_{label}_{digest}"


def slugify(value: str) -> str:
    """
    Convert text into a compact ID-safe slug.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")

    if not cleaned:
        return ""

    return cleaned[:32]


def normalize_tags(tags: list[str] | tuple[str, ...]) -> list[str]:
    """
    Normalize tags into lowercase unique strings.
    """
    normalized: list[str] = []

    for tag in tags:
        if not isinstance(tag, str):
            continue

        cleaned = tag.strip().lower()

        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)

    return normalized


def build_memory_usage_trace(
    *,
    memory_context_used: bool = False,
    retrieved_case_ids: list[str] | tuple[str, ...] = (),
    retrieved_knowledge_ids: list[str] | tuple[str, ...] = (),
    retrieved_baseline_keys: list[str] | tuple[str, ...] = (),
    memory_influence: str = MEMORY_INFLUENCE_NONE,
    memory_result: str = MEMORY_RESULT_NOT_USED,
    memory_notes: list[str] | tuple[str, ...] = (),
    memory_relevance_score: float = 0.0,
    retrieved_memory_scores: list[JsonDict] | tuple[JsonDict, ...] = (),
) -> JsonDict:
    """
    Build a structured trace of how memory was used in a case.

    This trace is for audit, scenario evaluation, and future recall tuning.
    It should not normally be used as active recall content.
    """
    score = normalize_score(memory_relevance_score)

    return {
        "memory_context_used": memory_context_used,
        "retrieved_case_ids": list(retrieved_case_ids),
        "retrieved_knowledge_ids": list(retrieved_knowledge_ids),
        "retrieved_baseline_keys": list(retrieved_baseline_keys),
        "memory_influence": memory_influence,
        "memory_result": memory_result,
        "memory_relevance_score": score,
        "memory_relevance_label": relevance_label_for_score(score),
        "retrieved_memory_scores": [dict(item) for item in retrieved_memory_scores],
        "memory_notes": list(memory_notes),
    }


def validate_case_memory(case_memory: JsonDict) -> MemoryCaseValidationResult:
    """
    Validate a structured Lighthouse case memory.

    The validator enforces the V1 case-memory shape without calling a model.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(case_memory, dict):
        return MemoryCaseValidationResult(
            valid=False,
            errors=("Case memory must be a dictionary.",),
            warnings=(),
        )

    if contains_unsafe_memory_text(case_memory):
        errors.append("Case memory contains unsafe or policy-bypassing text.")

    _require_non_empty_string(case_memory, "case_id", errors)
    _require_non_empty_string(case_memory, "created_at", errors)
    _require_non_empty_string(case_memory, "updated_at", errors)

    _require_allowed_value(case_memory, "status", ALLOWED_CASE_STATUSES, errors)
    _require_allowed_value(case_memory, "confidence", ALLOWED_CASE_CONFIDENCE, errors)
    _require_allowed_value(case_memory, "source", ALLOWED_CASE_SOURCES, errors)

    case_card = case_memory.get("case_card")
    evidence = case_memory.get("evidence")
    process_trace = case_memory.get("process_trace")
    memory_usage_trace = case_memory.get("memory_usage_trace")
    lifecycle = case_memory.get("lifecycle")

    if not isinstance(case_card, dict):
        errors.append("case_card must be a dictionary.")
    else:
        _validate_case_card(case_card, errors, warnings)

    if not isinstance(evidence, dict):
        errors.append("evidence must be a dictionary.")
    else:
        _validate_evidence(evidence, errors, warnings)

    if not isinstance(process_trace, dict):
        errors.append("process_trace must be a dictionary.")
    else:
        _validate_process_trace(process_trace, errors, warnings)

    if not isinstance(memory_usage_trace, dict):
        errors.append("memory_usage_trace must be a dictionary.")
    else:
        _validate_memory_usage_trace(memory_usage_trace, errors, warnings)

    if not isinstance(lifecycle, dict):
        errors.append("lifecycle must be a dictionary.")
    else:
        _validate_lifecycle(lifecycle, errors, warnings)

    return MemoryCaseValidationResult(
        valid=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def is_valid_case_memory(case_memory: JsonDict) -> bool:
    """
    Return True when a case memory passes validation.
    """
    return validate_case_memory(case_memory).valid


def extract_case_recall_card(case_memory: JsonDict) -> JsonDict:
    """
    Extract the compact recall-safe view of a case memory.

    This intentionally excludes process_trace and memory_usage_trace.
    """
    case_card = case_memory.get("case_card", {})
    evidence = case_memory.get("evidence", {})
    telemetry_evidence = evidence.get("telemetry_evidence", {})
    event_evidence = evidence.get("event_evidence", {})
    lifecycle = case_memory.get("lifecycle", {})

    return {
        "case_id": case_memory.get("case_id", ""),
        "status": case_memory.get("status", ""),
        "confidence": case_memory.get("confidence", ""),
        "source": case_memory.get("source", ""),
        "case_card": {
            "problem": case_card.get("problem", ""),
            "symptoms": list(case_card.get("symptoms", [])),
            "suspected_cause": case_card.get("suspected_cause", ""),
            "lesson": case_card.get("lesson", ""),
            "tags": list(case_card.get("tags", [])),
        },
        "evidence_summary": {
            "cpu_usage_percent": telemetry_evidence.get("cpu_usage_percent"),
            "memory_usage_percent": telemetry_evidence.get("memory_usage_percent"),
            "disk_usage_percent": telemetry_evidence.get("disk_usage_percent"),
            "top_process_name": telemetry_evidence.get("top_process_name"),
            "critical_events": event_evidence.get("critical_events"),
            "warning_events": event_evidence.get("warning_events"),
            "action_taken": evidence.get("action_taken", ""),
            "outcome": evidence.get("outcome", ""),
        },
        "lifecycle": {
            "use_count": lifecycle.get("use_count", 0),
            "last_used_at": lifecycle.get("last_used_at"),
            "pinned": lifecycle.get("pinned", False),
            "retention_policy": lifecycle.get("retention_policy", RETENTION_STANDARD),
        },
    }


def score_case_relevance(
    case_memory: JsonDict,
    user_request: str,
    telemetry: JsonDict | None = None,
) -> CaseRelevanceResult:
    """
    Score a case memory against the current request and optional telemetry.

    This is intentionally deterministic and simple for V1.
    """
    score = 0.0
    reasons: list[str] = []

    case_id = str(case_memory.get("case_id", "unknown_case"))
    case_card = case_memory.get("case_card", {})
    evidence = case_memory.get("evidence", {})
    telemetry_evidence = evidence.get("telemetry_evidence", {})

    request_tokens = tokenize(user_request)
    case_tokens = tokenize_case(case_memory)

    overlap = request_tokens.intersection(case_tokens)

    if overlap:
        overlap_score = min(0.35, len(overlap) * 0.07)
        score += overlap_score
        reasons.append("keyword_or_tag_match")

    query_process = detect_process_name_from_text(user_request)
    case_process = normalize_process_name(telemetry_evidence.get("top_process_name"))

    current_process = ""

    if telemetry:
        current_process = normalize_process_name(extract_top_process_name(telemetry))

    if query_process and case_process and query_process == case_process:
        score += 0.25
        reasons.append("request_process_match")

    if current_process and case_process and current_process == case_process:
        score += 0.25
        reasons.append("telemetry_process_match")

    current_memory = None
    current_cpu = None
    current_disk = None

    if telemetry:
        current_memory = extract_telemetry_percent(telemetry, "memory_usage_percent")
        current_cpu = extract_telemetry_percent(telemetry, "cpu_usage_percent")
        current_disk = extract_telemetry_percent(telemetry, "disk_usage_percent")

    case_memory_percent = extract_telemetry_percent(
        telemetry_evidence,
        "memory_usage_percent",
    )
    case_cpu_percent = extract_telemetry_percent(
        telemetry_evidence,
        "cpu_usage_percent",
    )
    case_disk_percent = extract_telemetry_percent(
        telemetry_evidence,
        "disk_usage_percent",
    )

    if both_high(current_memory, case_memory_percent, warning_at=70):
        score += 0.18
        reasons.append("memory_pressure_match")

    if both_high(current_cpu, case_cpu_percent, warning_at=75):
        score += 0.12
        reasons.append("cpu_pressure_match")

    if both_high(current_disk, case_disk_percent, warning_at=80):
        score += 0.10
        reasons.append("disk_pressure_match")

    if case_memory.get("status") == CASE_STATUS_RESOLVED:
        score += 0.07
        reasons.append("resolved_case")

    confidence = case_memory.get("confidence")

    if confidence == CASE_CONFIDENCE_HIGH:
        score += 0.08
        reasons.append("high_confidence")
    elif confidence == CASE_CONFIDENCE_MEDIUM:
        score += 0.04
        reasons.append("medium_confidence")

    lifecycle = case_memory.get("lifecycle", {})

    if lifecycle.get("pinned") is True:
        score += 0.05
        reasons.append("pinned_case")

    use_count = lifecycle.get("use_count", 0)

    if isinstance(use_count, int) and use_count > 0:
        score += min(0.05, use_count * 0.01)
        reasons.append("previously_reused")

    normalized_score = normalize_score(score)

    return CaseRelevanceResult(
        case_id=case_id,
        score=normalized_score,
        label=relevance_label_for_score(normalized_score),
        reasons=tuple(reasons),
    )


def sort_cases_by_relevance(
    case_memories: list[JsonDict] | tuple[JsonDict, ...],
    user_request: str,
    telemetry: JsonDict | None = None,
    limit: int = 3,
) -> list[tuple[JsonDict, CaseRelevanceResult]]:
    """
    Return the most relevant cases and their relevance scores.
    """
    scored_cases = [
        (
            case_memory,
            score_case_relevance(
                case_memory=case_memory,
                user_request=user_request,
                telemetry=telemetry,
            ),
        )
        for case_memory in case_memories
    ]

    scored_cases.sort(key=lambda item: item[1].score, reverse=True)

    if limit <= 0:
        return scored_cases

    return scored_cases[:limit]


def tokenize(value: str) -> set[str]:
    """
    Tokenize text for simple deterministic matching.
    """
    if not isinstance(value, str):
        return set()

    raw_tokens = re.findall(r"[a-zA-Z0-9_\\.]+", value.lower())
    tokens: set[str] = set()

    for token in raw_tokens:
        cleaned = token.strip("._")

        if not cleaned or cleaned in STOPWORDS:
            continue

        tokens.add(cleaned)

        if cleaned.endswith(".exe"):
            tokens.add(cleaned.removesuffix(".exe"))

    return tokens


def tokenize_case(case_memory: JsonDict) -> set[str]:
    """
    Tokenize the recall-relevant fields of a case memory.
    """
    case_card = case_memory.get("case_card", {})
    evidence = case_memory.get("evidence", {})
    telemetry_evidence = evidence.get("telemetry_evidence", {})

    parts: list[str] = [
        str(case_card.get("problem", "")),
        str(case_card.get("suspected_cause", "")),
        str(case_card.get("lesson", "")),
        str(telemetry_evidence.get("top_process_name", "")),
        str(evidence.get("action_taken", "")),
        str(evidence.get("outcome", "")),
    ]

    symptoms = case_card.get("symptoms", [])
    tags = case_card.get("tags", [])

    if isinstance(symptoms, list):
        parts.extend(str(symptom) for symptom in symptoms)

    if isinstance(tags, list):
        parts.extend(str(tag) for tag in tags)

    return tokenize(" ".join(parts))


def detect_process_name_from_text(value: str) -> str:
    """
    Detect a common process name from request text.
    """
    tokens = tokenize(value)

    process_aliases = {
        "chrome": "chrome.exe",
        "google": "chrome.exe",
        "edge": "msedge.exe",
        "msedge": "msedge.exe",
        "firefox": "firefox.exe",
        "brave": "brave.exe",
        "code": "code.exe",
        "vscode": "code.exe",
        "teams": "teams.exe",
        "discord": "discord.exe",
        "spotify": "spotify.exe",
        "notepad": "notepad.exe",
    }

    for token in tokens:
        if token in process_aliases:
            return process_aliases[token]

        if token.endswith(".exe"):
            return token

    return ""


def normalize_process_name(value: Any) -> str:
    """
    Normalize a process name.
    """
    if not isinstance(value, str):
        return ""

    cleaned = value.strip().lower()

    if not cleaned:
        return ""

    if "." not in cleaned:
        return f"{cleaned}.exe"

    return cleaned


def extract_top_process_name(telemetry: JsonDict) -> str:
    """
    Extract a top process name from either evidence-style or telemetry-style data.
    """
    direct = telemetry.get("top_process_name")

    if isinstance(direct, str) and direct.strip():
        return direct

    processes = telemetry.get("processes", {})

    if isinstance(processes, dict):
        process_list = processes.get("processes", [])

        if isinstance(process_list, list) and process_list:
            first = process_list[0]

            if isinstance(first, dict):
                name = first.get("name")

                if isinstance(name, str):
                    return name

    return ""


def extract_telemetry_percent(telemetry: JsonDict, field_name: str) -> float | None:
    """
    Extract a telemetry percentage from evidence-style or telemetry-style data.
    """
    direct = telemetry.get(field_name)

    if isinstance(direct, (int, float)) and not isinstance(direct, bool):
        return float(direct)

    nested_map = {
        "cpu_usage_percent": ("cpu", "usage_percent"),
        "memory_usage_percent": ("memory", "usage_percent"),
        "disk_usage_percent": ("disk", "usage_percent"),
    }

    nested = nested_map.get(field_name)

    if not nested:
        return None

    group_name, key_name = nested
    group = telemetry.get(group_name, {})

    if not isinstance(group, dict):
        return None

    value = group.get(key_name)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)

    return None


def both_high(
    current_value: float | None,
    case_value: float | None,
    *,
    warning_at: float,
) -> bool:
    """
    Return True when both current and case telemetry show pressure.
    """
    if current_value is None or case_value is None:
        return False

    return current_value >= warning_at and case_value >= warning_at


def contains_unsafe_memory_text(value: Any) -> bool:
    """
    Return True if any nested string contains unsafe memory text.
    """
    for text in iter_nested_strings(value):
        lowered = text.lower()

        for phrase in UNSAFE_MEMORY_PHRASES:
            if phrase in lowered:
                return True

    return False


def iter_nested_strings(value: Any) -> tuple[str, ...]:
    """
    Collect nested strings from a JSON-like value.
    """
    strings: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, str):
            strings.append(item)
            return

        if isinstance(item, dict):
            for nested in item.values():
                walk(nested)
            return

        if isinstance(item, list | tuple):
            for nested in item:
                walk(nested)

    walk(value)

    return tuple(strings)


def _validate_case_card(
    case_card: JsonDict,
    errors: list[str],
    warnings: list[str],
) -> None:
    _require_non_empty_string(case_card, "problem", errors)
    _require_string_list(case_card, "symptoms", errors, require_non_empty=True)
    _require_non_empty_string(case_card, "suspected_cause", errors)
    _require_non_empty_string(case_card, "lesson", errors)
    _require_string_list(case_card, "tags", errors, require_non_empty=True)

    tags = case_card.get("tags", [])

    if isinstance(tags, list):
        normalized = normalize_tags(tags)

        if len(normalized) != len(tags):
            warnings.append("case_card.tags contains duplicate or non-normalized values.")


def _validate_evidence(
    evidence: JsonDict,
    errors: list[str],
    warnings: list[str],
) -> None:
    telemetry_evidence = evidence.get("telemetry_evidence")
    event_evidence = evidence.get("event_evidence")

    if not isinstance(telemetry_evidence, dict):
        errors.append("evidence.telemetry_evidence must be a dictionary.")
    else:
        if not telemetry_evidence:
            errors.append("evidence.telemetry_evidence must not be empty.")

        if telemetry_evidence.get("memory_usage_percent") is None:
            warnings.append("telemetry_evidence.memory_usage_percent is missing.")

    if not isinstance(event_evidence, dict):
        errors.append("evidence.event_evidence must be a dictionary.")

    _require_non_empty_string(evidence, "action_taken", errors)
    _require_non_empty_string(evidence, "outcome", errors)


def _validate_process_trace(
    process_trace: JsonDict,
    errors: list[str],
    warnings: list[str],
) -> None:
    _require_string_list(process_trace, "diagnostic_steps", errors, require_non_empty=True)
    _require_string_list(process_trace, "decision_notes", errors, require_non_empty=True)

    operator_feedback = process_trace.get("operator_feedback")

    if operator_feedback is not None and not isinstance(operator_feedback, str):
        errors.append("process_trace.operator_feedback must be a string when present.")

    if operator_feedback is None:
        warnings.append("process_trace.operator_feedback is missing.")


def _validate_memory_usage_trace(
    memory_usage_trace: JsonDict,
    errors: list[str],
    warnings: list[str],
) -> None:
    if not isinstance(memory_usage_trace.get("memory_context_used"), bool):
        errors.append("memory_usage_trace.memory_context_used must be a boolean.")

    _require_string_list(memory_usage_trace, "retrieved_case_ids", errors)
    _require_string_list(memory_usage_trace, "retrieved_knowledge_ids", errors)
    _require_string_list(memory_usage_trace, "retrieved_baseline_keys", errors)

    _require_allowed_value(
        memory_usage_trace,
        "memory_influence",
        ALLOWED_MEMORY_INFLUENCE,
        errors,
    )
    _require_allowed_value(
        memory_usage_trace,
        "memory_result",
        ALLOWED_MEMORY_RESULTS,
        errors,
    )

    relevance_score = memory_usage_trace.get("memory_relevance_score")

    if not is_score(relevance_score):
        errors.append("memory_usage_trace.memory_relevance_score must be between 0.0 and 1.0.")

    _require_allowed_value(
        memory_usage_trace,
        "memory_relevance_label",
        ALLOWED_RELEVANCE_LABELS,
        errors,
    )

    expected_label = relevance_label_for_score(normalize_score(relevance_score))

    if memory_usage_trace.get("memory_relevance_label") != expected_label:
        warnings.append("memory_usage_trace.memory_relevance_label does not match score.")

    retrieved_memory_scores = memory_usage_trace.get("retrieved_memory_scores")

    if not isinstance(retrieved_memory_scores, list):
        errors.append("memory_usage_trace.retrieved_memory_scores must be a list.")
    else:
        for index, item in enumerate(retrieved_memory_scores):
            _validate_retrieved_memory_score(item, index, errors)

    _require_string_list(memory_usage_trace, "memory_notes", errors)

    if (
        memory_usage_trace.get("memory_context_used") is True
        and normalize_score(relevance_score) == 0
    ):
        warnings.append("memory context was used but relevance score is 0.")


def _validate_retrieved_memory_score(
    item: Any,
    index: int,
    errors: list[str],
) -> None:
    if not isinstance(item, dict):
        errors.append(f"retrieved_memory_scores[{index}] must be a dictionary.")
        return

    _require_non_empty_string(item, "memory_id", errors)

    _require_allowed_value(
        item,
        "memory_type",
        ALLOWED_RETRIEVED_MEMORY_TYPES,
        errors,
        field_label=f"retrieved_memory_scores[{index}].memory_type",
    )

    relevance_score = item.get("relevance_score")

    if not is_score(relevance_score):
        errors.append(
            f"retrieved_memory_scores[{index}].relevance_score must be between 0.0 and 1.0."
        )

    _require_allowed_value(
        item,
        "relevance_label",
        ALLOWED_RELEVANCE_LABELS,
        errors,
        field_label=f"retrieved_memory_scores[{index}].relevance_label",
    )

    _require_string_list(
        item,
        "match_reasons",
        errors,
        field_label=f"retrieved_memory_scores[{index}].match_reasons",
    )


def _validate_lifecycle(
    lifecycle: JsonDict,
    errors: list[str],
    warnings: list[str],
) -> None:
    use_count = lifecycle.get("use_count")

    if not isinstance(use_count, int) or isinstance(use_count, bool) or use_count < 0:
        errors.append("lifecycle.use_count must be a non-negative integer.")

    if not isinstance(lifecycle.get("pinned"), bool):
        errors.append("lifecycle.pinned must be a boolean.")

    _require_allowed_value(
        lifecycle,
        "retention_policy",
        ALLOWED_RETENTION_POLICIES,
        errors,
    )

    if lifecycle.get("pinned") is True and lifecycle.get("retention_policy") != RETENTION_PINNED:
        warnings.append("Pinned case should usually use pinned retention policy.")


def _require_non_empty_string(
    payload: JsonDict,
    field_name: str,
    errors: list[str],
) -> None:
    value = payload.get(field_name)

    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field_name} must be a non-empty string.")


def _require_allowed_value(
    payload: JsonDict,
    field_name: str,
    allowed_values: set[str],
    errors: list[str],
    field_label: str | None = None,
) -> None:
    value = payload.get(field_name)
    label = field_label or field_name

    if value not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        errors.append(f"{label} must be one of: {allowed}.")


def _require_string_list(
    payload: JsonDict,
    field_name: str,
    errors: list[str],
    *,
    require_non_empty: bool = False,
    field_label: str | None = None,
) -> None:
    value = payload.get(field_name)
    label = field_label or field_name

    if not isinstance(value, list):
        errors.append(f"{label} must be a list of strings.")
        return

    if require_non_empty and not value:
        errors.append(f"{label} must not be empty.")
        return

    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}[{index}] must be a non-empty string.")


def is_score(value: Any) -> bool:
    """
    Return True when a value is a valid 0.0 to 1.0 score.
    """
    if isinstance(value, bool):
        return False

    if not isinstance(value, (int, float)):
        return False

    return 0.0 <= float(value) <= 1.0