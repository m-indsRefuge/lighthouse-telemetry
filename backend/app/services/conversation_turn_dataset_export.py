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


DATASET_DIRNAME = "datasets"
CONVERSATIONAL_TURN_DATASET_FILENAME = "conversational_turn_dataset.jsonl"

CATEGORY_LLM_CONTRACT_ROUTE_TURN = "llm_contract_route_turn"
CATEGORY_DETERMINISTIC_FALLBACK_TURN = "deterministic_fallback_turn"
CATEGORY_CONTRACT_REJECTION_TURN = "contract_rejection_turn"
CATEGORY_SAFE_PREVIEW_TURN = "safe_preview_turn"
CATEGORY_NEEDS_CLARIFICATION_TURN = "needs_clarification_turn"
CATEGORY_SAFETY_REVIEW = "safety_review"
CATEGORY_UNLABELED_TURN = "unlabeled_turn"


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


def classify_turn_training_use(turn: dict[str, Any]) -> dict[str, Any]:
    """
    Deterministically classify how a conversational turn should be used.
    """
    deterministic = safe_dict(turn.get("deterministic_result"))
    llm_route = safe_dict(turn.get("llm_route_result"))
    selected_handoff = safe_dict(turn.get("selected_route_handoff"))
    autorun_gate = safe_dict(turn.get("autorun_gate"))
    safety = safe_dict(turn.get("safety"))

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


def build_dataset_record(turn: dict[str, Any]) -> dict[str, Any]:
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
        "training_use": classify_turn_training_use(turn),
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
    return [build_dataset_record(turn) for turn in turns]


def summarize_dataset(records: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Summarize dataset category counts.
    """
    category_counts: dict[str, int] = {}
    included_count = 0

    for record in records:
        training_use = safe_dict(record.get("training_use"))
        category = training_use.get("category", CATEGORY_UNLABELED_TURN)
        category_counts[category] = category_counts.get(category, 0) + 1

        if training_use.get("include") is True:
            included_count += 1

    review_needed = category_counts.get(CATEGORY_SAFETY_REVIEW, 0)
    review_needed += category_counts.get(CATEGORY_CONTRACT_REJECTION_TURN, 0)

    return {
        "total_examples": len(records),
        "included_examples": included_count,
        "review_needed_examples": review_needed,
        "unlabeled_examples": category_counts.get(CATEGORY_UNLABELED_TURN, 0),
        "category_counts": category_counts,
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
                "category_counts": {},
            },
            "errors": [str(error)],
            "warnings": [],
        }


def format_conversational_turn_dataset_export_report(result: dict[str, Any]) -> str:
    """
    Build a plain-text report for conversational turn dataset exports.
    """
    data = result.get("data", {})
    category_counts = data.get("category_counts", {})

    lines = [
        "LIGHTHOUSE CONVERSATIONAL TURN DATASET EXPORT",
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
