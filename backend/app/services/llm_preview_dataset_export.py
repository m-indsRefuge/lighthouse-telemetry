"""
Deterministic LLM preview dataset export for Lighthouse.

This module converts preview-only LLM route proposal journal records into a
clean JSONL dataset for later evaluation, review, and translation-layer design.

It does not call the model.
It does not execute tools.
It does not mutate the operating system.
It does not give model output authority over routing or execution.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.llm_preview_journal import (
    DEFAULT_MEMORY_DIR,
    read_llm_route_previews,
)


DATASET_DIRNAME = "datasets"
LLM_PREVIEW_DATASET_FILENAME = "llm_preview_route_dataset.jsonl"

CATEGORY_VALID_ROUTE_PREVIEW = "valid_route_preview"
CATEGORY_INVALID_CONTRACT_EXAMPLE = "invalid_contract_example"
CATEGORY_SAFE_UNCERTAIN_PREVIEW = "safe_uncertain_preview"
CATEGORY_NO_MODEL_OUTPUT = "no_model_output"
CATEGORY_BOUNDARY_ERROR_REVIEW = "boundary_error_review"
CATEGORY_SAFETY_REVIEW = "safety_review"
CATEGORY_UNLABELED_PREVIEW = "unlabeled_preview"


def utc_now_iso() -> str:
    """
    Return an ISO-like UTC timestamp.
    """
    return datetime.now(timezone.utc).isoformat()


def build_dataset_id() -> str:
    """
    Build a compact unique dataset row id.
    """
    return f"llmprevdata-{uuid4().hex}"


def resolve_memory_dir(memory_dir: str | Path | None = None) -> Path:
    """
    Resolve the memory directory used for preview journals and dataset output.
    """
    if memory_dir is None:
        return DEFAULT_MEMORY_DIR

    return Path(memory_dir)


def default_dataset_path(memory_dir: str | Path | None = None) -> Path:
    """
    Return the default LLM preview dataset JSONL path.
    """
    return (
        resolve_memory_dir(memory_dir)
        / DATASET_DIRNAME
        / LLM_PREVIEW_DATASET_FILENAME
    )


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """
    Write records to a JSONL file, replacing any previous export.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def safe_dict(value: Any) -> dict[str, Any]:
    """
    Return value when it is a dictionary, otherwise an empty dictionary.
    """
    return value if isinstance(value, dict) else {}


def classify_preview_training_use(preview: dict[str, Any]) -> dict[str, Any]:
    """
    Deterministically classify how an LLM preview record should be used.
    """
    safety = safe_dict(preview.get("safety"))
    route_handoff = safe_dict(preview.get("route_handoff"))

    if (
        safety.get("executed") is True
        or safety.get("model_authority") is True
        or safety.get("os_mutation") is True
    ):
        return {
            "include": False,
            "category": CATEGORY_SAFETY_REVIEW,
            "reason": "Preview record contains impossible unsafe safety flags.",
        }

    status = preview.get("status")
    contract_valid = preview.get("contract_valid")
    proposed_intent = preview.get("proposed_intent")

    if status == "disabled":
        return {
            "include": False,
            "category": CATEGORY_NO_MODEL_OUTPUT,
            "reason": "No model proposal was produced.",
        }

    if status == "error":
        return {
            "include": False,
            "category": CATEGORY_BOUNDARY_ERROR_REVIEW,
            "reason": "The model boundary returned an error.",
        }

    if status == "invalid" or contract_valid is False:
        return {
            "include": True,
            "category": CATEGORY_INVALID_CONTRACT_EXAMPLE,
            "reason": "The preview is a useful negative example for contract validation.",
        }

    if contract_valid is True and route_handoff.get("route_ready") is True:
        return {
            "include": True,
            "category": CATEGORY_VALID_ROUTE_PREVIEW,
            "reason": "The preview passed contract validation and produced a route handoff.",
        }

    if contract_valid is True and proposed_intent == "unknown":
        return {
            "include": True,
            "category": CATEGORY_SAFE_UNCERTAIN_PREVIEW,
            "reason": "The model safely expressed uncertainty without executable authority.",
        }

    return {
        "include": False,
        "category": CATEGORY_UNLABELED_PREVIEW,
        "reason": "The preview does not yet have a decisive dataset category.",
    }


def build_dataset_record(preview: dict[str, Any]) -> dict[str, Any]:
    """
    Build one stable LLM preview dataset record.
    """
    route_handoff = safe_dict(preview.get("route_handoff"))
    safety = safe_dict(preview.get("safety"))

    return {
        "dataset_id": build_dataset_id(),
        "created_at": utc_now_iso(),
        "preview_id": preview.get("preview_id"),
        "input": {
            "original": preview.get("original_input"),
            "normalized": preview.get("normalized_input"),
        },
        "model": {
            "model_used": preview.get("model_used"),
            "used_model": preview.get("used_model"),
        },
        "contract": {
            "preview_status": preview.get("status"),
            "validation_status": preview.get("validation_status"),
            "valid": preview.get("contract_valid"),
            "proposed_intent": preview.get("proposed_intent"),
            "interpreted_request": preview.get("interpreted_request"),
        },
        "route_handoff": {
            "route_ready": route_handoff.get("route_ready"),
            "route_known": route_handoff.get("route_known"),
            "intent": route_handoff.get("intent"),
            "safety_class": route_handoff.get("safety_class"),
            "command_family": route_handoff.get("command_family"),
            "recommended_command": route_handoff.get("recommended_command"),
            "engine_request": route_handoff.get("engine_request"),
            "autorun_allowed": route_handoff.get("autorun_allowed"),
            "manual_review_required": route_handoff.get("manual_review_required"),
        },
        "outcome": {
            "preview_only": safety.get("preview_only"),
            "executed": safety.get("executed"),
            "talk_integration": safety.get("talk_integration"),
            "talkrun_integration": safety.get("talkrun_integration"),
            "model_authority": safety.get("model_authority"),
            "os_mutation": safety.get("os_mutation"),
        },
        "errors": list(preview.get("errors", [])),
        "warnings": list(preview.get("warnings", [])),
        "training_use": classify_preview_training_use(preview),
    }


def build_llm_preview_dataset(
    *,
    memory_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Build LLM preview dataset records from the preview journal.
    """
    preview_limit = limit if limit is not None else 100000
    previews = list(
        reversed(
            read_llm_route_previews(
                limit=preview_limit,
                memory_dir=memory_dir,
            )
        )
    )

    return [build_dataset_record(preview) for preview in previews]


def summarize_dataset(records: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Summarize dataset category counts.
    """
    category_counts: dict[str, int] = {}
    included_count = 0

    for record in records:
        training_use = safe_dict(record.get("training_use"))
        category = training_use.get("category", CATEGORY_UNLABELED_PREVIEW)
        category_counts[category] = category_counts.get(category, 0) + 1

        if training_use.get("include") is True:
            included_count += 1

    return {
        "total_examples": len(records),
        "included_examples": included_count,
        "review_needed_examples": category_counts.get(CATEGORY_SAFETY_REVIEW, 0)
        + category_counts.get(CATEGORY_BOUNDARY_ERROR_REVIEW, 0),
        "unlabeled_examples": category_counts.get(CATEGORY_UNLABELED_PREVIEW, 0),
        "category_counts": category_counts,
    }


def export_llm_preview_dataset(
    *,
    memory_dir: str | Path | None = None,
    output_path: str | Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """
    Export LLM preview dataset records to JSONL.
    """
    try:
        records = build_llm_preview_dataset(memory_dir=memory_dir, limit=limit)
        resolved_output_path = (
            Path(output_path)
            if output_path is not None
            else default_dataset_path(memory_dir)
        )
        write_jsonl(resolved_output_path, records)
        summary = summarize_dataset(records)

        return {
            "status": "ok",
            "message": "LLM preview dataset exported.",
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
            "message": "LLM preview dataset could not be exported.",
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


def format_llm_preview_dataset_export_report(result: dict[str, Any]) -> str:
    """
    Build a plain-text report for LLM preview dataset exports.
    """
    data = result.get("data", {})
    category_counts = data.get("category_counts", {})

    lines = [
        "LIGHTHOUSE LLM PREVIEW DATASET EXPORT",
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
