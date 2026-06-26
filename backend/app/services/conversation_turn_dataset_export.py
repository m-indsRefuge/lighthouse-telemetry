"""
Dataset export for Lighthouse conversational engine turn records.

This module converts preview-only conversational engine turns into a clean JSONL
dataset for evaluation and later translation-layer/training work.

It does not call the model.
It does not execute tools.
It does not mutate the operating system.
It does not give model output authority.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.conversational_engine_turn import (
    DEFAULT_MEMORY_DIR,
    conversational_turn_journal_path,
    read_jsonl,
)
from app.services.conversation_turn_feedback import latest_feedback_by_turn_id


DATASET_DIRNAME = "datasets"
CONVERSATIONAL_TURN_DATASET_FILENAME = "conversational_turn_dataset.jsonl"

CATEGORY_LLM_CONTRACT_ROUTE_TURN = "llm_contract_route_turn"
CATEGORY_DETERMINISTIC_FALLBACK_TURN = "deterministic_fallback_turn"
CATEGORY_CONTRACT_REJECTION_TURN = "contract_rejection_turn"
CATEGORY_SAFE_PREVIEW_TURN = "safe_preview_turn"
CATEGORY_NEEDS_CLARIFICATION_TURN = "needs_clarification_turn"
CATEGORY_SAFETY_REVIEW = "safety_review"
CATEGORY_CORRECTION_NEEDED = "correction_needed"
CATEGORY_UNLABELED_TURN = "unlabeled_turn"

DATASET_REVIEW_FILTER_ALL = "all"
DATASET_REVIEW_FILTER_INCLUDED = "included"
DATASET_REVIEW_FILTER_EXCLUDED = "excluded"
DATASET_REVIEW_FILTER_FEEDBACK = "feedback"
DATASET_REVIEW_FILTER_CORRECTIONS = "corrections"
DATASET_REVIEW_FILTER_REVIEW_NEEDED = "review_needed"
DATASET_REVIEW_FILTER_CATEGORY = "category"

REVIEW_NEEDED_CATEGORIES = frozenset(
    {
        CATEGORY_SAFETY_REVIEW,
        CATEGORY_CONTRACT_REJECTION_TURN,
        CATEGORY_CORRECTION_NEEDED,
    }
)

POSITIVE_FEEDBACK_LABELS = frozenset({"useful"})
CORRECTION_FEEDBACK_LABELS = frozenset(
    {"not_useful", "wrong_intent", "wrong_route", "confusing", "corrected"}
)
SAFETY_REVIEW_FEEDBACK_LABELS = frozenset({"unsafe"})


def utc_now_iso() -> str:
    """
    Return an ISO-like UTC timestamp.
    """
    return datetime.now(timezone.utc).isoformat()


def build_dataset_id() -> str:
    """
    Build a compact unique dataset row id.
    """
    return f"turndata-{uuid4().hex}"


def resolve_memory_dir(memory_dir: str | Path | None = None) -> Path:
    """
    Resolve the memory directory used for turn journals and dataset output.
    """
    if memory_dir is None:
        return DEFAULT_MEMORY_DIR

    return Path(memory_dir)


def default_dataset_path(memory_dir: str | Path | None = None) -> Path:
    """
    Return the default conversational turn dataset JSONL path.
    """
    return (
        resolve_memory_dir(memory_dir)
        / DATASET_DIRNAME
        / CONVERSATIONAL_TURN_DATASET_FILENAME
    )


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """
    Write records to a JSONL file, replacing any previous export.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, sort_keys=True, ensure_ascii=False))
            file.write("\n")


def safe_dict(value: Any) -> dict[str, Any]:
    """
    Return value when it is a dictionary, otherwise an empty dictionary.
    """
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> list[Any]:
    """
    Return value when it is a list, otherwise an empty list.
    """
    return value if isinstance(value, list) else []


def feedback_to_payload(feedback: dict[str, Any] | None) -> dict[str, Any]:
    """
    Return a stable feedback payload for dataset rows.
    """
    if not feedback:
        return {
            "label": None,
            "note": None,
            "feedback_id": None,
        }

    return {
        "label": feedback.get("label"),
        "note": feedback.get("note"),
        "feedback_id": feedback.get("feedback_id"),
    }


def feedback_label(feedback: dict[str, Any] | None) -> str | None:
    """
    Return normalized feedback label when present.
    """
    if not feedback:
        return None

    label = feedback.get("label")

    if isinstance(label, str) and label:
        return label

    return None


def read_conversational_turn_records(
    *,
    memory_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Read conversational turn records in journal order.
    """
    records = read_jsonl(conversational_turn_journal_path(memory_dir))

    if limit is None:
        return records

    if limit <= 0:
        return []

    return records[-limit:]


def classify_turn_training_use(
    turn: dict[str, Any],
    feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Deterministically classify how a conversational turn should be used.
    """
    deterministic = safe_dict(turn.get("deterministic_result"))
    llm_route = safe_dict(turn.get("llm_route_result"))
    selected_handoff = safe_dict(turn.get("selected_route_handoff"))
    autorun_gate = safe_dict(turn.get("autorun_gate"))
    safety = safe_dict(turn.get("safety"))
    label = feedback_label(feedback)

    if label in SAFETY_REVIEW_FEEDBACK_LABELS:
        return {
            "include": False,
            "category": CATEGORY_SAFETY_REVIEW,
            "reason": "Operator marked this conversational turn as unsafe.",
        }

    if label in CORRECTION_FEEDBACK_LABELS:
        return {
            "include": False,
            "category": CATEGORY_CORRECTION_NEEDED,
            "reason": "Operator feedback indicates this turn needs correction.",
        }

    if (
        safety.get("executed") is True
        or safety.get("tool_execution") is True
        or safety.get("model_authority") is True
        or safety.get("os_mutation") is True
    ):
        return {
            "include": False,
            "category": CATEGORY_SAFETY_REVIEW,
            "reason": "Turn record contains impossible unsafe safety flags.",
        }

    if deterministic.get("status") in {"needs_clarification", "unknown"}:
        return {
            "include": False,
            "category": CATEGORY_NEEDS_CLARIFICATION_TURN,
            "reason": "The deterministic interpreter did not produce a usable route.",
        }

    if llm_route.get("status") == "invalid":
        return {
            "include": True,
            "category": CATEGORY_CONTRACT_REJECTION_TURN,
            "reason": "The turn includes a rejected model proposal and deterministic fallback.",
        }

    if (
        turn.get("selected_route_source") == "llm_contract"
        and selected_handoff.get("route_ready") is True
    ):
        return {
            "include": True,
            "category": CATEGORY_LLM_CONTRACT_ROUTE_TURN,
            "reason": "The model proposal passed contract validation and produced a route.",
        }

    if turn.get("selected_route_source") == "deterministic":
        return {
            "include": True,
            "category": CATEGORY_DETERMINISTIC_FALLBACK_TURN,
            "reason": "The deterministic route was selected for the conversational turn.",
        }

    if autorun_gate.get("status") == "ok" and autorun_gate.get("allowed") is True:
        return {
            "include": True,
            "category": CATEGORY_SAFE_PREVIEW_TURN,
            "reason": "The turn reached a safe read-only route but remained preview-only.",
        }

    return {
        "include": False,
        "category": CATEGORY_UNLABELED_TURN,
        "reason": "The turn does not yet have a decisive dataset category.",
    }


def build_dataset_record(
    turn: dict[str, Any],
    feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build one stable conversational turn dataset record.
    """
    deterministic = safe_dict(turn.get("deterministic_result"))
    llm_route = safe_dict(turn.get("llm_route_result"))
    selected_handoff = safe_dict(turn.get("selected_route_handoff"))
    autorun_gate = safe_dict(turn.get("autorun_gate"))
    safety = safe_dict(turn.get("safety"))
    validation = safe_dict(llm_route.get("validation"))
    normalized_proposal = safe_dict(validation.get("normalized_proposal"))

    return {
        "dataset_id": build_dataset_id(),
        "created_at": utc_now_iso(),
        "turn_id": turn.get("turn_id"),
        "input": {
            "original": turn.get("original_input"),
            "normalized": turn.get("normalized_input"),
        },
        "deterministic": {
            "status": deterministic.get("status"),
            "intent": deterministic.get("intent"),
            "interpreted_request": deterministic.get("interpreted_request"),
            "recommended_command": deterministic.get("recommended_command"),
        },
        "llm_route": {
            "status": llm_route.get("status"),
            "message": llm_route.get("message"),
            "model_used": llm_route.get("model_used"),
            "used_model": llm_route.get("used_model"),
            "contract_valid": validation.get("valid"),
            "proposed_intent": normalized_proposal.get("proposed_intent"),
            "interpreted_request": normalized_proposal.get("interpreted_request"),
        },
        "selected_route": {
            "source": turn.get("selected_route_source"),
            "route_ready": selected_handoff.get("route_ready"),
            "route_known": selected_handoff.get("route_known"),
            "intent": selected_handoff.get("intent"),
            "safety_class": selected_handoff.get("safety_class"),
            "command_family": selected_handoff.get("command_family"),
            "recommended_command": selected_handoff.get("recommended_command"),
            "engine_request": selected_handoff.get("engine_request"),
            "autorun_allowed": selected_handoff.get("autorun_allowed"),
            "manual_review_required": selected_handoff.get("manual_review_required"),
        },
        "autorun_gate": {
            "status": autorun_gate.get("status"),
            "allowed": autorun_gate.get("allowed"),
            "reason": autorun_gate.get("reason"),
            "engine_request": autorun_gate.get("engine_request"),
        },
        "outcome": {
            "preview_only": safety.get("preview_only"),
            "executed": safety.get("executed"),
            "tool_execution": safety.get("tool_execution"),
            "model_authority": safety.get("model_authority"),
            "os_mutation": safety.get("os_mutation"),
            "talkrun_integration": safety.get("talkrun_integration"),
        },
        "errors": (
            safe_list(deterministic.get("errors"))
            + safe_list(llm_route.get("errors"))
            + safe_list(autorun_gate.get("errors"))
        ),
        "warnings": (
            safe_list(deterministic.get("warnings"))
            + safe_list(llm_route.get("warnings"))
            + safe_list(autorun_gate.get("warnings"))
        ),
        "feedback": feedback_to_payload(feedback),
        "training_use": classify_turn_training_use(turn, feedback=feedback),
    }


def build_conversational_turn_dataset(
    *,
    memory_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Build conversational turn dataset records from the turn journal.
    """
    turns = read_conversational_turn_records(memory_dir=memory_dir, limit=limit)
    feedback_by_turn = latest_feedback_by_turn_id(memory_dir=memory_dir)

    records: list[dict[str, Any]] = []

    for turn in turns:
        turn_id = turn.get("turn_id")
        feedback = (
            feedback_by_turn.get(turn_id)
            if isinstance(turn_id, str)
            else None
        )
        records.append(build_dataset_record(turn, feedback=feedback))

    return records


def summarize_dataset(records: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Summarize dataset category counts.
    """
    category_counts: dict[str, int] = {}
    feedback_label_counts: dict[str, int] = {}
    included_count = 0
    feedback_count = 0

    for record in records:
        training_use = safe_dict(record.get("training_use"))
        category = training_use.get("category", CATEGORY_UNLABELED_TURN)
        category_counts[category] = category_counts.get(category, 0) + 1

        if training_use.get("include") is True:
            included_count += 1

        feedback = safe_dict(record.get("feedback"))
        feedback_label = feedback.get("label")

        if isinstance(feedback_label, str) and feedback_label:
            feedback_count += 1
            feedback_label_counts[feedback_label] = (
                feedback_label_counts.get(feedback_label, 0) + 1
            )

    review_needed = category_counts.get(CATEGORY_SAFETY_REVIEW, 0)
    review_needed += category_counts.get(CATEGORY_CONTRACT_REJECTION_TURN, 0)
    review_needed += category_counts.get(CATEGORY_CORRECTION_NEEDED, 0)

    return {
        "total_examples": len(records),
        "included_examples": included_count,
        "review_needed_examples": review_needed,
        "unlabeled_examples": category_counts.get(CATEGORY_UNLABELED_TURN, 0),
        "feedback_examples": feedback_count,
        "category_counts": category_counts,
        "feedback_label_counts": feedback_label_counts,
    }


def export_conversational_turn_dataset(
    *,
    memory_dir: str | Path | None = None,
    output_path: str | Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """
    Export conversational turn dataset records to JSONL.
    """
    try:
        records = build_conversational_turn_dataset(
            memory_dir=memory_dir,
            limit=limit,
        )
        resolved_output_path = (
            Path(output_path)
            if output_path is not None
            else default_dataset_path(memory_dir)
        )
        write_jsonl(resolved_output_path, records)
        summary = summarize_dataset(records)

        return {
            "status": "ok",
            "message": "Conversational turn dataset exported.",
            "data": {
                "output_path": str(resolved_output_path),
                **summary,
            },
            "errors": [],
            "warnings": [],
        }
    except OSError as error:
        return {
            "status": "error",
            "message": "Conversational turn dataset could not be exported.",
            "data": {
                "output_path": str(output_path) if output_path else None,
                "total_examples": 0,
                "included_examples": 0,
                "review_needed_examples": 0,
                "unlabeled_examples": 0,
                "feedback_examples": 0,
                "category_counts": {},
                "feedback_label_counts": {},
            },
            "errors": [str(error)],
            "warnings": [],
        }


def filter_conversational_turn_dataset_records(
    records: list[dict[str, Any]],
    *,
    filter_mode: str = DATASET_REVIEW_FILTER_ALL,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """
    Filter exported conversational turn dataset rows for review.

    This is read-only and operates on already-built dataset records.
    """
    normalized_filter = (filter_mode or DATASET_REVIEW_FILTER_ALL).strip().lower()

    if normalized_filter == DATASET_REVIEW_FILTER_ALL:
        return list(records)

    filtered: list[dict[str, Any]] = []

    for record in records:
        training_use = safe_dict(record.get("training_use"))
        feedback = safe_dict(record.get("feedback"))
        training_category = training_use.get("category")
        feedback_label = feedback.get("label")

        if (
            normalized_filter == DATASET_REVIEW_FILTER_INCLUDED
            and training_use.get("include") is True
        ):
            filtered.append(record)
            continue

        if (
            normalized_filter == DATASET_REVIEW_FILTER_EXCLUDED
            and training_use.get("include") is False
        ):
            filtered.append(record)
            continue

        if (
            normalized_filter == DATASET_REVIEW_FILTER_FEEDBACK
            and isinstance(feedback_label, str)
            and feedback_label
        ):
            filtered.append(record)
            continue

        if normalized_filter == DATASET_REVIEW_FILTER_CORRECTIONS and (
            training_category == CATEGORY_CORRECTION_NEEDED
            or feedback_label in CORRECTION_FEEDBACK_LABELS
        ):
            filtered.append(record)
            continue

        if (
            normalized_filter == DATASET_REVIEW_FILTER_REVIEW_NEEDED
            and training_category in REVIEW_NEEDED_CATEGORIES
        ):
            filtered.append(record)
            continue

        if (
            normalized_filter == DATASET_REVIEW_FILTER_CATEGORY
            and category
            and training_category == category
        ):
            filtered.append(record)
            continue

    return filtered


def read_conversational_turn_dataset_records(
    *,
    memory_dir: str | Path | None = None,
    dataset_path: str | Path | None = None,
    limit: int = 10,
    filter_mode: str = DATASET_REVIEW_FILTER_ALL,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """
    Read recent exported conversational turn dataset rows, newest first.

    This reviews the dataset artifact. It does not regenerate the export.
    """
    if limit <= 0:
        return []

    resolved_path = (
        Path(dataset_path)
        if dataset_path is not None
        else default_dataset_path(memory_dir)
    )

    records = list(reversed(read_jsonl(resolved_path)))
    filtered_records = filter_conversational_turn_dataset_records(
        records,
        filter_mode=filter_mode,
        category=category,
    )

    return filtered_records[:limit]


def format_conversational_turn_dataset_review_report(
    *,
    memory_dir: str | Path | None = None,
    dataset_path: str | Path | None = None,
    limit: int = 10,
    filter_mode: str = DATASET_REVIEW_FILTER_ALL,
    category: str | None = None,
) -> str:
    """
    Build a plain-text review report for exported conversational turn dataset rows.
    """
    resolved_path = (
        Path(dataset_path)
        if dataset_path is not None
        else default_dataset_path(memory_dir)
    )
    records = read_conversational_turn_dataset_records(
        memory_dir=memory_dir,
        dataset_path=dataset_path,
        limit=limit,
        filter_mode=filter_mode,
        category=category,
    )

    lines = [
        "LIGHTHOUSE CONVERSATIONAL TURN DATASET REVIEW",
        "-" * 52,
        f"Shown: {len(records)}",
        f"Filter: {filter_mode}",
    ]

    if filter_mode == DATASET_REVIEW_FILTER_CATEGORY:
        lines.append(f"Category: {category}")

    lines.append(f"Source: {resolved_path}")

    if not records:
        lines.append("No conversational turn dataset rows found.")
        lines.append("Run 'dataset turns' to regenerate the export first.")
        return "\n".join(lines)

    for record in records:
        input_payload = safe_dict(record.get("input"))
        deterministic = safe_dict(record.get("deterministic"))
        selected_route = safe_dict(record.get("selected_route"))
        training_use = safe_dict(record.get("training_use"))
        feedback = safe_dict(record.get("feedback"))

        lines.append("")
        lines.append(f"dataset_id: {record.get('dataset_id')}")
        lines.append(f"turn_id: {record.get('turn_id')}")
        lines.append(
            "input: "
            f"{input_payload.get('normalized') or input_payload.get('original')}"
        )
        lines.append(f"deterministic_intent: {deterministic.get('intent')}")
        lines.append(f"selected_route_source: {selected_route.get('source')}")
        lines.append(f"selected_intent: {selected_route.get('intent')}")
        lines.append(
            "training_include: "
            f"{'yes' if training_use.get('include') is True else 'no'}"
        )
        lines.append(f"training_category: {training_use.get('category')}")
        lines.append(f"feedback_label: {feedback.get('label')}")
        lines.append(f"feedback_note: {feedback.get('note')}")

    return "\n".join(lines)


def format_conversational_turn_dataset_export_report(result: dict[str, Any]) -> str:
    """
    Build a plain-text report for conversational turn dataset exports.
    """
    data = result.get("data", {})
    category_counts = data.get("category_counts", {})
    feedback_label_counts = data.get("feedback_label_counts", {})

    lines = [
        "LIGHTHOUSE CONVERSATIONAL TURN DATASET EXPORT",
        "-" * 52,
        f"Status: {result.get('status')}",
        f"Message: {result.get('message')}",
        f"Examples exported: {data.get('total_examples', 0)}",
        f"Included examples: {data.get('included_examples', 0)}",
        f"Review-needed examples: {data.get('review_needed_examples', 0)}",
        f"Unlabeled examples: {data.get('unlabeled_examples', 0)}",
        f"Feedback examples: {data.get('feedback_examples', 0)}",
        f"Output: {data.get('output_path')}",
    ]

    if category_counts:
        lines.append("Categories:")

        for category, count in sorted(category_counts.items()):
            lines.append(f"- {category}: {count}")

    if feedback_label_counts:
        lines.append("Feedback labels:")

        for label, count in sorted(feedback_label_counts.items()):
            lines.append(f"- {label}: {count}")

    errors = result.get("errors", [])

    if errors:
        lines.append("Errors:")
        lines.extend(f"- {error}" for error in errors)

    return "\n".join(lines)
