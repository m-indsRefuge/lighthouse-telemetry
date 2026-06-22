"""
Deterministic Operator dataset export for Lighthouse.

This module converts Operator interaction traces and Operator feedback into a
clean JSONL dataset that can support later evaluation, review, and model
translation-layer design.

It does not call the model.
It does not execute tools.
It does not mutate the operating system.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.operator_interaction_journal import (
    DEFAULT_MEMORY_DIR,
    read_operator_feedback,
    read_operator_interactions,
)


DATASET_DIRNAME = "datasets"
OPERATOR_ROUTE_DATASET_FILENAME = "operator_route_dataset.jsonl"

CATEGORY_POSITIVE_ROUTE_EXAMPLE = "positive_route_example"
CATEGORY_SAFE_REFUSAL_EXAMPLE = "safe_refusal_example"
CATEGORY_CORRECTION_NEEDED = "correction_needed"
CATEGORY_SAFETY_REVIEW = "safety_failure_review"
CATEGORY_UNLABELED_TRACE = "unlabeled_trace"

CORRECTION_LABELS = frozenset({"wrong_intent", "wrong_route", "confusing", "corrected"})
SAFETY_REVIEW_LABELS = frozenset({"unsafe"})
POSITIVE_LABELS = frozenset({"useful"})
NEGATIVE_LABELS = frozenset({"not_useful"})


def utc_now_iso() -> str:
    """
    Return an ISO-like UTC timestamp.
    """
    return datetime.now(timezone.utc).isoformat()


def build_dataset_id() -> str:
    """
    Build a compact unique dataset row id.
    """
    return f"opdata-{uuid4().hex}"


def resolve_memory_dir(memory_dir: str | Path | None = None) -> Path:
    """
    Resolve the memory directory used for source journals and dataset output.
    """
    if memory_dir is None:
        return DEFAULT_MEMORY_DIR

    return Path(memory_dir)


def default_dataset_path(memory_dir: str | Path | None = None) -> Path:
    """
    Return the default Operator route dataset JSONL path.
    """
    return (
        resolve_memory_dir(memory_dir)
        / DATASET_DIRNAME
        / OPERATOR_ROUTE_DATASET_FILENAME
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


def latest_feedback_by_trace_id(
    feedback_records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """
    Return the latest feedback record per trace id.
    """
    latest: dict[str, dict[str, Any]] = {}

    for record in feedback_records:
        trace_id = record.get("trace_id")

        if isinstance(trace_id, str) and trace_id:
            latest[trace_id] = record

    return latest


def classify_training_use(
    *,
    interaction: dict[str, Any],
    feedback: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Deterministically classify how a trace should be used in a dataset.
    """
    execution = interaction.get("execution", {})
    route_handoff = interaction.get("route_handoff", {})
    autorun_gate = interaction.get("autorun_gate") or {}

    refused = bool(execution.get("refused")) if isinstance(execution, dict) else False
    executed = bool(execution.get("executed")) if isinstance(execution, dict) else False

    label = None

    if feedback:
        raw_label = feedback.get("label")

        if isinstance(raw_label, str):
            label = raw_label

    if label in SAFETY_REVIEW_LABELS:
        return {
            "include": False,
            "category": CATEGORY_SAFETY_REVIEW,
            "reason": "Operator marked this trace as unsafe.",
        }

    if label in CORRECTION_LABELS:
        return {
            "include": False,
            "category": CATEGORY_CORRECTION_NEEDED,
            "reason": "Operator feedback indicates the route needs correction.",
        }

    if refused:
        return {
            "include": True,
            "category": CATEGORY_SAFE_REFUSAL_EXAMPLE,
            "reason": "The route was refused by Lighthouse safety gates.",
        }

    if label in POSITIVE_LABELS and executed:
        return {
            "include": True,
            "category": CATEGORY_POSITIVE_ROUTE_EXAMPLE,
            "reason": "Operator marked an executed route as useful.",
        }

    if label in NEGATIVE_LABELS:
        return {
            "include": False,
            "category": CATEGORY_CORRECTION_NEEDED,
            "reason": "Operator marked this trace as not useful.",
        }

    if (
        isinstance(route_handoff, dict)
        and route_handoff.get("autorun_allowed") is True
        and executed
    ):
        return {
            "include": True,
            "category": CATEGORY_POSITIVE_ROUTE_EXAMPLE,
            "reason": "Executed read-only route without negative feedback.",
        }

    if isinstance(autorun_gate, dict) and autorun_gate.get("allowed") is False:
        return {
            "include": True,
            "category": CATEGORY_SAFE_REFUSAL_EXAMPLE,
            "reason": "Autorun gate refused this route.",
        }

    return {
        "include": False,
        "category": CATEGORY_UNLABELED_TRACE,
        "reason": "No decisive feedback or safety outcome is available yet.",
    }


def build_dataset_record(
    *,
    interaction: dict[str, Any],
    feedback: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Build one stable Operator route dataset record.
    """
    route_handoff = interaction.get("route_handoff", {})
    execution = interaction.get("execution", {})
    autorun_gate = interaction.get("autorun_gate") or {}

    if not isinstance(route_handoff, dict):
        route_handoff = {}

    if not isinstance(execution, dict):
        execution = {}

    if not isinstance(autorun_gate, dict):
        autorun_gate = {}

    feedback_payload = {
        "label": None,
        "note": None,
        "feedback_id": None,
    }

    if feedback:
        feedback_payload = {
            "label": feedback.get("label"),
            "note": feedback.get("note"),
            "feedback_id": feedback.get("feedback_id"),
        }

    return {
        "dataset_id": build_dataset_id(),
        "created_at": utc_now_iso(),
        "trace_id": interaction.get("trace_id"),
        "input": {
            "original": interaction.get("original_input"),
            "normalized": interaction.get("normalized_input"),
        },
        "target": {
            "intent": interaction.get("intent"),
            "interpreted_request": interaction.get("interpreted_request"),
            "command_family": route_handoff.get("command_family"),
            "engine_request": route_handoff.get("engine_request"),
            "safety_class": route_handoff.get("safety_class"),
            "autorun_allowed": route_handoff.get("autorun_allowed"),
            "manual_review_required": route_handoff.get("manual_review_required"),
        },
        "outcome": {
            "executed": execution.get("executed"),
            "refused": execution.get("refused"),
            "attempted": execution.get("attempted"),
            "autorun_gate_status": autorun_gate.get("status"),
            "autorun_gate_allowed": autorun_gate.get("allowed"),
        },
        "feedback": feedback_payload,
        "training_use": classify_training_use(
            interaction=interaction,
            feedback=feedback,
        ),
    }


def build_operator_route_dataset(
    *,
    memory_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Build Operator route dataset records from interaction and feedback journals.
    """
    interaction_limit = limit if limit is not None else 100000
    interactions = list(
        reversed(
            read_operator_interactions(
                limit=interaction_limit,
                memory_dir=memory_dir,
            )
        )
    )
    feedback_records = list(
        reversed(
            read_operator_feedback(
                limit=100000,
                memory_dir=memory_dir,
            )
        )
    )
    feedback_by_trace = latest_feedback_by_trace_id(feedback_records)

    records: list[dict[str, Any]] = []

    for interaction in interactions:
        trace_id = interaction.get("trace_id")
        feedback = feedback_by_trace.get(trace_id) if isinstance(trace_id, str) else None
        records.append(
            build_dataset_record(
                interaction=interaction,
                feedback=feedback,
            )
        )

    return records


def summarize_dataset(records: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Summarize dataset category counts.
    """
    category_counts: dict[str, int] = {}
    included_count = 0

    for record in records:
        training_use = record.get("training_use", {})
        category = training_use.get("category", CATEGORY_UNLABELED_TRACE)
        category_counts[category] = category_counts.get(category, 0) + 1

        if training_use.get("include") is True:
            included_count += 1

    return {
        "total_examples": len(records),
        "included_examples": included_count,
        "review_needed_examples": category_counts.get(CATEGORY_CORRECTION_NEEDED, 0)
        + category_counts.get(CATEGORY_SAFETY_REVIEW, 0),
        "unlabeled_examples": category_counts.get(CATEGORY_UNLABELED_TRACE, 0),
        "category_counts": category_counts,
    }


def export_operator_route_dataset(
    *,
    memory_dir: str | Path | None = None,
    output_path: str | Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """
    Export Operator route dataset records to JSONL.
    """
    try:
        records = build_operator_route_dataset(memory_dir=memory_dir, limit=limit)
        resolved_output_path = (
            Path(output_path)
            if output_path is not None
            else default_dataset_path(memory_dir)
        )
        write_jsonl(resolved_output_path, records)
        summary = summarize_dataset(records)

        return {
            "status": "ok",
            "message": "Operator route dataset exported.",
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
            "message": "Operator route dataset could not be exported.",
            "data": {
                "output_path": str(output_path) if output_path else None,
                "total_examples": 0,
                "included_examples": 0,
                "review_needed_examples": 0,
                "unlabeled_examples": 0,
                "category_counts": {},
            },
            "errors": [str(error)],
            "warnings": [],
        }


def format_operator_dataset_export_report(result: dict[str, Any]) -> str:
    """
    Build a plain-text report for Operator dataset exports.
    """
    data = result.get("data", {})
    category_counts = data.get("category_counts", {})

    lines = [
        "LIGHTHOUSE OPERATOR DATASET EXPORT",
        "-" * 52,
        f"Status: {result.get('status')}",
        f"Message: {result.get('message')}",
        f"Examples exported: {data.get('total_examples', 0)}",
        f"Included examples: {data.get('included_examples', 0)}",
        f"Review-needed examples: {data.get('review_needed_examples', 0)}",
        f"Unlabeled examples: {data.get('unlabeled_examples', 0)}",
        f"Output: {data.get('output_path')}",
    ]

    if category_counts:
        lines.append("Categories:")

        for category, count in sorted(category_counts.items()):
            lines.append(f"- {category}: {count}")

    errors = result.get("errors", [])

    if errors:
        lines.append("Errors:")
        lines.extend(f"- {error}" for error in errors)

    return "\n".join(lines)
