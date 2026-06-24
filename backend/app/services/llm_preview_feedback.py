"""
Append-only feedback journal for Lighthouse LLM route previews.

This module captures Operator feedback for preview-only model route proposals.

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

from app.services.llm_preview_journal import DEFAULT_MEMORY_DIR


PREVIEW_FEEDBACK_JOURNAL_FILENAME = "llm_preview_feedback.jsonl"

ALLOWED_PREVIEW_FEEDBACK_LABELS = frozenset(
    {
        "useful",
        "not_useful",
        "wrong_intent",
        "wrong_route",
        "unsafe",
        "confusing",
        "corrected",
        "other",
    }
)


def utc_now_iso() -> str:
    """
    Return an ISO-like UTC timestamp.
    """
    return datetime.now(timezone.utc).isoformat()


def build_feedback_id() -> str:
    """
    Build a compact unique id for LLM preview feedback.
    """
    return f"llmprevfb-{uuid4().hex}"


def resolve_memory_dir(memory_dir: str | Path | None = None) -> Path:
    """
    Resolve the memory directory used for LLM preview feedback.
    """
    if memory_dir is None:
        return DEFAULT_MEMORY_DIR

    return Path(memory_dir)


def preview_feedback_journal_path(memory_dir: str | Path | None = None) -> Path:
    """
    Return the LLM preview feedback JSONL path.
    """
    return resolve_memory_dir(memory_dir) / PREVIEW_FEEDBACK_JOURNAL_FILENAME


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """
    Append one JSON object to a JSONL file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, sort_keys=True, ensure_ascii=False))
        file.write("\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """
    Read a JSONL file. Malformed rows are skipped rather than breaking review.
    """
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped_line = line.strip()

            if not stripped_line:
                continue

            try:
                parsed = json.loads(stripped_line)
            except json.JSONDecodeError:
                continue

            if isinstance(parsed, dict):
                records.append(parsed)

    return records


def normalize_preview_feedback_label(label: str) -> str:
    """
    Normalize an LLM preview feedback label.
    """
    return label.strip().lower().replace("-", "_")


def list_preview_feedback_labels() -> list[str]:
    """
    Return valid LLM preview feedback labels.
    """
    return sorted(ALLOWED_PREVIEW_FEEDBACK_LABELS)


def build_llm_preview_feedback_record(
    *,
    preview_id: str,
    label: str,
    note: str = "",
) -> dict[str, Any]:
    """
    Build one LLM preview feedback record.
    """
    return {
        "feedback_id": build_feedback_id(),
        "preview_id": preview_id.strip(),
        "created_at": utc_now_iso(),
        "label": normalize_preview_feedback_label(label),
        "note": note.strip(),
    }


def record_llm_preview_feedback(
    *,
    preview_id: str,
    label: str,
    note: str = "",
    memory_dir: str | Path | None = None,
) -> dict[str, Any]:
    """
    Record Operator feedback for a previous LLM preview id.
    """
    cleaned_preview_id = preview_id.strip()
    normalized_label = normalize_preview_feedback_label(label)

    if not cleaned_preview_id:
        return {
            "status": "invalid",
            "message": "Preview ID is required.",
            "data": {"saved": False, "preview_id": cleaned_preview_id},
            "errors": ["preview_id must be a non-empty string."],
            "warnings": [],
        }

    if normalized_label not in ALLOWED_PREVIEW_FEEDBACK_LABELS:
        return {
            "status": "invalid",
            "message": "Unsupported LLM preview feedback label.",
            "data": {
                "saved": False,
                "preview_id": cleaned_preview_id,
                "label": normalized_label,
                "allowed_labels": list_preview_feedback_labels(),
            },
            "errors": [f"Unsupported feedback label: {normalized_label}"],
            "warnings": [],
        }

    try:
        record = build_llm_preview_feedback_record(
            preview_id=cleaned_preview_id,
            label=normalized_label,
            note=note,
        )
        append_jsonl(preview_feedback_journal_path(memory_dir), record)

        return {
            "status": "ok",
            "message": "LLM preview feedback recorded.",
            "data": {
                "saved": True,
                "preview_id": cleaned_preview_id,
                "feedback_id": record["feedback_id"],
                "label": normalized_label,
                "record": record,
            },
            "errors": [],
            "warnings": [],
        }
    except OSError as error:
        return {
            "status": "error",
            "message": "LLM preview feedback could not be recorded.",
            "data": {"saved": False, "preview_id": cleaned_preview_id},
            "errors": [str(error)],
            "warnings": [],
        }


def read_llm_preview_feedback(
    *,
    preview_id: str | None = None,
    limit: int = 10,
    memory_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """
    Read recent LLM preview feedback, optionally filtered by preview id.
    """
    records = read_jsonl(preview_feedback_journal_path(memory_dir))

    if preview_id:
        records = [
            record
            for record in records
            if record.get("preview_id") == preview_id
        ]

    if limit <= 0:
        return []

    return list(reversed(records))[:limit]


def latest_feedback_by_preview_id(
    *,
    memory_dir: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Return latest feedback per LLM preview id.
    """
    feedback_records = read_jsonl(preview_feedback_journal_path(memory_dir))
    latest_by_preview: dict[str, dict[str, Any]] = {}

    for record in feedback_records:
        preview_id = record.get("preview_id")

        if isinstance(preview_id, str) and preview_id:
            latest_by_preview[preview_id] = record

    return latest_by_preview


def format_preview_feedback_labels_report() -> str:
    """
    Build a plain-text report of allowed LLM preview feedback labels.
    """
    lines = [
        "LIGHTHOUSE LLM PREVIEW FEEDBACK LABELS",
        "-" * 52,
    ]

    lines.extend(f"- {label}" for label in list_preview_feedback_labels())

    return "\n".join(lines)


def format_llm_preview_feedback_result(result: dict[str, Any]) -> str:
    """
    Build a plain-text report for LLM preview feedback save results.
    """
    data = result.get("data", {})

    lines = [
        "LIGHTHOUSE LLM PREVIEW FEEDBACK",
        "-" * 52,
        f"Status: {result.get('status')}",
        f"Message: {result.get('message')}",
        f"Preview ID: {data.get('preview_id')}",
        f"Saved: {'yes' if data.get('saved') else 'no'}",
    ]

    if data.get("label"):
        lines.append(f"Label: {data.get('label')}")

    if data.get("feedback_id"):
        lines.append(f"Feedback ID: {data.get('feedback_id')}")

    errors = result.get("errors", [])

    if errors:
        lines.append("Errors:")
        lines.extend(f"- {error}" for error in errors)

    allowed_labels = data.get("allowed_labels")

    if allowed_labels:
        lines.append("Allowed labels:")
        lines.extend(f"- {label}" for label in allowed_labels)

    return "\n".join(lines)


def format_llm_preview_feedback_report(
    *,
    limit: int = 10,
    memory_dir: str | Path | None = None,
) -> str:
    """
    Build a plain-text report of recent LLM preview feedback records.
    """
    records = read_llm_preview_feedback(limit=limit, memory_dir=memory_dir)

    lines = [
        "LIGHTHOUSE LLM PREVIEW FEEDBACK",
        "-" * 52,
        f"Shown: {len(records)}",
    ]

    if not records:
        lines.append("No LLM preview feedback recorded yet.")
        return "\n".join(lines)

    for record in records:
        lines.append("")
        lines.append(f"feedback_id: {record.get('feedback_id')}")
        lines.append(f"preview_id: {record.get('preview_id')}")
        lines.append(f"created_at: {record.get('created_at')}")
        lines.append(f"label: {record.get('label')}")
        lines.append(f"note: {record.get('note')}")

    return "\n".join(lines)
