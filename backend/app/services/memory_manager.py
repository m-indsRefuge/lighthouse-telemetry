"""
Controlled memory manager for Lighthouse.

This module provides the V1 operational interface for memory.

It sits above memory_store.py and memory_cases.py.

It does not call the model.
It does not execute tools.
It does not mutate the OS.
It only builds, validates, saves, lists, and searches structured memory records.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.memory_cases import (
    CASE_CONFIDENCE_MEDIUM,
    CASE_SOURCE_OPERATOR_ENTERED,
    CASE_STATUS_RESOLVED,
    MEMORY_INFLUENCE_NONE,
    MEMORY_RESULT_NOT_USED,
    RETENTION_PINNED,
    RETENTION_STANDARD,
    JsonDict,
    build_case_id,
    build_memory_usage_trace,
    extract_case_recall_card,
    normalize_tags,
    sort_cases_by_relevance,
    utc_now_iso,
    validate_case_memory,
)
from app.services.memory_store import (
    append_case_memory,
    read_baselines,
    read_case_memories,
    read_knowledge_index,
    read_operator_preferences,
)


MEMORY_MANAGER_STATUS_OK = "ok"
MEMORY_MANAGER_STATUS_ERROR = "error"
MEMORY_MANAGER_STATUS_INVALID = "invalid"
MEMORY_MANAGER_STATUS_DUPLICATE = "duplicate"
MEMORY_MANAGER_STATUS_EMPTY = "empty"


@dataclass(frozen=True)
class MemoryManagerResult:
    """
    Stable result shape for memory manager operations.
    """

    status: str
    message: str
    data: JsonDict
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> JsonDict:
        """
        Convert the result into a stable dictionary.
        """
        return {
            "status": self.status,
            "message": self.message,
            "data": self.data,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def build_case_memory(
    *,
    problem: str,
    symptoms: list[str] | tuple[str, ...],
    suspected_cause: str,
    lesson: str,
    tags: list[str] | tuple[str, ...],
    telemetry_evidence: JsonDict,
    event_evidence: JsonDict,
    action_taken: str,
    outcome: str,
    diagnostic_steps: list[str] | tuple[str, ...],
    decision_notes: list[str] | tuple[str, ...],
    operator_feedback: str = "",
    status: str = CASE_STATUS_RESOLVED,
    confidence: str = CASE_CONFIDENCE_MEDIUM,
    source: str = CASE_SOURCE_OPERATOR_ENTERED,
    created_at: str | None = None,
    updated_at: str | None = None,
    case_id: str | None = None,
    memory_usage_trace: JsonDict | None = None,
    pinned: bool = False,
    retention_policy: str | None = None,
) -> JsonDict:
    """
    Build a structured case memory from guided fields.

    This function only builds the object. It does not write to disk.
    """
    created = created_at or utc_now_iso()
    updated = updated_at or created
    normalized_tags = normalize_tags(tags)

    generated_case_id = case_id or build_case_id(
        problem=problem,
        tags=normalized_tags,
        created_at=created,
    )

    if memory_usage_trace is None:
        memory_usage_trace = build_memory_usage_trace(
            memory_context_used=False,
            memory_influence=MEMORY_INFLUENCE_NONE,
            memory_result=MEMORY_RESULT_NOT_USED,
            memory_relevance_score=0.0,
        )

    if retention_policy is None:
        retention_policy = RETENTION_PINNED if pinned else RETENTION_STANDARD

    return {
        "case_id": generated_case_id,
        "created_at": created,
        "updated_at": updated,
        "status": status,
        "confidence": confidence,
        "source": source,
        "case_card": {
            "problem": problem.strip(),
            "symptoms": [str(symptom).strip() for symptom in symptoms],
            "suspected_cause": suspected_cause.strip(),
            "lesson": lesson.strip(),
            "tags": normalized_tags,
        },
        "evidence": {
            "telemetry_evidence": dict(telemetry_evidence),
            "event_evidence": dict(event_evidence),
            "action_taken": action_taken.strip(),
            "outcome": outcome.strip(),
        },
        "process_trace": {
            "diagnostic_steps": [str(step).strip() for step in diagnostic_steps],
            "decision_notes": [str(note).strip() for note in decision_notes],
            "operator_feedback": operator_feedback.strip(),
        },
        "memory_usage_trace": dict(memory_usage_trace),
        "lifecycle": {
            "use_count": 0,
            "last_used_at": None,
            "pinned": pinned,
            "retention_policy": retention_policy,
        },
    }


def save_case_memory(
    case_memory: JsonDict,
    *,
    memory_dir: Path | str | None = None,
) -> MemoryManagerResult:
    """
    Validate and save a structured case memory.

    Invalid or duplicate case memories are not written.
    """
    validation = validate_case_memory(case_memory)

    if not validation.valid:
        return MemoryManagerResult(
            status=MEMORY_MANAGER_STATUS_INVALID,
            message="Case memory failed validation and was not saved.",
            data={
                "case_id": case_memory.get("case_id", ""),
                "saved": False,
            },
            errors=validation.errors,
            warnings=validation.warnings,
        )

    case_id = str(case_memory.get("case_id", ""))

    try:
        existing_cases_result = read_case_memories(limit=None, memory_dir=memory_dir)
        existing_cases = unwrap_case_memory_records(existing_cases_result)
    except Exception as exc:
        return MemoryManagerResult(
            status=MEMORY_MANAGER_STATUS_ERROR,
            message="Unable to read existing case memories before saving.",
            data={
                "case_id": case_id,
                "saved": False,
            },
            errors=(str(exc),),
            warnings=validation.warnings,
        )

    for existing_case in existing_cases:
        if existing_case.get("case_id") == case_id:
            return MemoryManagerResult(
                status=MEMORY_MANAGER_STATUS_DUPLICATE,
                message="Case memory with this case_id already exists.",
                data={
                    "case_id": case_id,
                    "saved": False,
                },
                warnings=validation.warnings,
            )

    try:
        append_result = append_case_memory(case_memory, memory_dir=memory_dir)

        if is_store_error(append_result):
            return MemoryManagerResult(
                status=MEMORY_MANAGER_STATUS_ERROR,
                message="Unable to save case memory.",
                data={
                    "case_id": case_id,
                    "saved": False,
                },
                errors=(get_store_message(append_result),),
                warnings=validation.warnings,
            )
    except Exception as exc:
        return MemoryManagerResult(
            status=MEMORY_MANAGER_STATUS_ERROR,
            message="Unable to save case memory.",
            data={
                "case_id": case_id,
                "saved": False,
            },
            errors=(str(exc),),
            warnings=validation.warnings,
        )

    return MemoryManagerResult(
        status=MEMORY_MANAGER_STATUS_OK,
        message="Case memory saved.",
        data={
            "case_id": case_id,
            "saved": True,
        },
        warnings=validation.warnings,
    )


def list_case_memories(
    *,
    memory_dir: Path | str | None = None,
    limit: int = 20,
    include_archived: bool = True,
    recall_cards_only: bool = False,
) -> MemoryManagerResult:
    """
    List stored case memories.

    By default, this returns full records. Use recall_cards_only=True to return
    compact recall-safe records.
    """
    try:
        cases_result = read_case_memories(memory_dir=memory_dir)
        cases = unwrap_case_memory_records(cases_result)
    except Exception as exc:
        return MemoryManagerResult(
            status=MEMORY_MANAGER_STATUS_ERROR,
            message="Unable to list case memories.",
            data={
                "case_count": 0,
                "cases": [],
            },
            errors=(str(exc),),
        )

    filtered_cases: list[JsonDict] = []

    for case_memory in cases:
        if not include_archived and case_memory.get("status") == "archived":
            continue

        filtered_cases.append(case_memory)

    if limit > 0:
        filtered_cases = filtered_cases[:limit]

    if recall_cards_only:
        output_cases = [
            extract_case_recall_card(case_memory)
            for case_memory in filtered_cases
        ]
    else:
        output_cases = filtered_cases

    status = MEMORY_MANAGER_STATUS_OK if output_cases else MEMORY_MANAGER_STATUS_EMPTY

    return MemoryManagerResult(
        status=status,
        message="Case memories listed." if output_cases else "No case memories found.",
        data={
            "case_count": len(output_cases),
            "cases": output_cases,
        },
    )


def search_case_memories(
    *,
    user_request: str,
    telemetry: JsonDict | None = None,
    memory_dir: Path | str | None = None,
    limit: int = 3,
    min_score: float = 0.01,
) -> MemoryManagerResult:
    """
    Search case memories using deterministic relevance scoring.

    This does not update use_count yet. V1 keeps search read-only.
    """
    cleaned_request = user_request.strip()

    if not cleaned_request:
        return MemoryManagerResult(
            status=MEMORY_MANAGER_STATUS_INVALID,
            message="A user request is required to search case memories.",
            data={
                "query": user_request,
                "match_count": 0,
                "matches": [],
            },
            errors=("user_request must not be empty.",),
        )

    try:
        cases_result = read_case_memories(memory_dir=memory_dir)
        cases = unwrap_case_memory_records(cases_result)
    except Exception as exc:
        return MemoryManagerResult(
            status=MEMORY_MANAGER_STATUS_ERROR,
            message="Unable to read case memories for search.",
            data={
                "query": cleaned_request,
                "match_count": 0,
                "matches": [],
            },
            errors=(str(exc),),
        )

    valid_cases: list[JsonDict] = []

    for case_memory in cases:
        if validate_case_memory(case_memory).valid:
            valid_cases.append(case_memory)

    scored_cases = sort_cases_by_relevance(
        case_memories=valid_cases,
        user_request=cleaned_request,
        telemetry=telemetry,
        limit=0,
    )

    matches: list[JsonDict] = []

    for case_memory, relevance in scored_cases:
        if relevance.score < min_score:
            continue

        matches.append(
            {
                "case": extract_case_recall_card(case_memory),
                "relevance": relevance.to_dict(),
            }
        )

        if limit > 0 and len(matches) >= limit:
            break

    status = MEMORY_MANAGER_STATUS_OK if matches else MEMORY_MANAGER_STATUS_EMPTY

    return MemoryManagerResult(
        status=status,
        message=(
            "Relevant case memories found."
            if matches
            else "No relevant case memories found."
        ),
        data={
            "query": cleaned_request,
            "match_count": len(matches),
            "matches": matches,
        },
    )


def get_memory_status(
    *,
    memory_dir: Path | str | None = None,
) -> MemoryManagerResult:
    """
    Return a compact status/count summary for Lighthouse memory.
    """
    errors: list[str] = []

    baselines: JsonDict = {}
    preferences: JsonDict = {}
    knowledge_index: JsonDict = {}
    cases: list[JsonDict] = []

    try:
        baselines_result = read_baselines(memory_dir=memory_dir)
        baselines = unwrap_json_memory(baselines_result)
    except Exception as exc:
        errors.append(f"Unable to read baselines: {exc}")

    try:
        preferences_result = read_operator_preferences(memory_dir=memory_dir)
        preferences = unwrap_json_memory(preferences_result)
    except Exception as exc:
        errors.append(f"Unable to read operator preferences: {exc}")

    try:
        knowledge_index_result = read_knowledge_index(memory_dir=memory_dir)
        knowledge_index = unwrap_json_memory(knowledge_index_result)
    except Exception as exc:
        errors.append(f"Unable to read knowledge index: {exc}")

    try:
        cases_result = read_case_memories(memory_dir=memory_dir)
        cases = unwrap_case_memory_records(cases_result)
    except Exception as exc:
        errors.append(f"Unable to read case memories: {exc}")

    valid_case_count = 0
    invalid_case_count = 0

    for case_memory in cases:
        if validate_case_memory(case_memory).valid:
            valid_case_count += 1
        else:
            invalid_case_count += 1

    knowledge_entries = knowledge_index.get("entries", [])

    if not isinstance(knowledge_entries, list):
        knowledge_entries = []

    status = MEMORY_MANAGER_STATUS_ERROR if errors else MEMORY_MANAGER_STATUS_OK

    return MemoryManagerResult(
        status=status,
        message=(
            "Memory status generated."
            if not errors
            else "Memory status generated with errors."
        ),
        data={
            "baseline_count": count_nested_leaf_values(baselines),
            "operator_preference_count": count_nested_leaf_values(preferences),
            "case_count": len(cases),
            "valid_case_count": valid_case_count,
            "invalid_case_count": invalid_case_count,
            "knowledge_entry_count": len(knowledge_entries),
        },
        errors=tuple(errors),
    )


def unwrap_store_data(result: Any, default: Any) -> Any:
    """
    Extract data from a memory-store result.

    memory_store.py returns a MemoryStoreResult object. This helper keeps the
    memory manager isolated from the exact internal shape of that object.
    """
    if hasattr(result, "data"):
        data = getattr(result, "data")

        if data is not None:
            return data

        return default

    if isinstance(result, dict):
        return result

    return result if result is not None else default


def unwrap_case_memory_records(result: Any) -> list[JsonDict]:
    """
    Extract case-memory records from a memory-store result.
    """
    data = unwrap_store_data(result, [])

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        for key in (
            "cases",
            "case_memories",
            "memories",
            "records",
            "entries",
            "items",
            "lines",
            "data",
        ):
            value = data.get(key)

            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

    return []


def unwrap_json_memory(result: Any) -> JsonDict:
    """
    Extract a JSON object from a memory-store result.

    This intentionally avoids unwrapping domain keys such as "memory",
    because baseline data may legitimately contain a top-level "memory" key.
    """
    data = unwrap_store_data(result, {})

    if not isinstance(data, dict):
        return {}

    for key in ("content", "payload", "value", "json"):
        value = data.get(key)

        if isinstance(value, dict):
            return value

    return data


def is_store_error(result: Any) -> bool:
    """
    Return True if a memory-store result appears to represent an error.
    """
    status = getattr(result, "status", None)

    if isinstance(status, str):
        return status.lower() in {"error", "invalid", "failed"}

    if isinstance(result, dict):
        status_value = result.get("status")

        if isinstance(status_value, str):
            return status_value.lower() in {"error", "invalid", "failed"}

    return False


def get_store_message(result: Any) -> str:
    """
    Extract a message from a memory-store result.
    """
    message = getattr(result, "message", None)

    if isinstance(message, str) and message.strip():
        return message

    if isinstance(result, dict):
        message_value = result.get("message")

        if isinstance(message_value, str) and message_value.strip():
            return message_value

    return "Memory store operation failed."


def count_nested_leaf_values(value: Any) -> int:
    """
    Count simple leaf values in nested JSON-like data.
    """
    if isinstance(value, dict):
        return sum(count_nested_leaf_values(nested) for nested in value.values())

    if isinstance(value, list):
        return sum(count_nested_leaf_values(nested) for nested in value)

    if value is None:
        return 0

    return 1