"""
Append-only feedback journal for Lighthouse conversational engine turns.

This module captures Operator feedback for full conversational turn records.

It does not call the model.
It does not execute tools.
It does not mutate the operating system.
It does not rewrite turn journal records.
It does not give memory or feedback authority over routing or execution.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.conversational_engine_turn import DEFAULT_MEMORY_DIR


TURN_FEEDBACK_JOURNAL_FILENAME = "conversation_turn_feedback.jsonl"

ALLOWED_TURN_FEEDBACK_LABELS = frozenset(
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
    return datetime.now(timezone.utc).isoformat()


def build_feedback_id() -> str:
    return f"turnfb-{uuid4().hex}"


def resolve_memory_dir(memory_dir: str | Path | None = None) -> Path:
    if memory_dir is None:
        return DEFAULT_MEMORY_DIR
    return Path(memory_dir)


def turn_feedback_journal_path(memory_dir: str | Path | None = None) -> Path:
    return resolve_memory_dir(memory_dir) / TURN_FEEDBACK_JOURNAL_FILENAME


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, sort_keys=True, ensure_ascii=False))
        file.write("\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
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


def normalize_turn_feedback_label(label: str) -> str:
    return label.strip().lower().replace("-", "_")


def list_turn_feedback_labels() -> list[str]:
    return sorted(ALLOWED_TURN_FEEDBACK_LABELS)


def build_turn_feedback_record(
    *,
    turn_id: str,
    label: str,
    note: str = "",
) -> dict[str, Any]:
    return {
        "feedback_id": build_feedback_id(),
        "turn_id": turn_id.strip(),
        "created_at": utc_now_iso(),
        "label": normalize_turn_feedback_label(label),
        "note": note.strip(),
    }


def record_turn_feedback(
    *,
    turn_id: str,
    label: str,
    note: str = "",
    memory_dir: str | Path | None = None,
) -> dict[str, Any]:
    cleaned_turn_id = turn_id.strip()
    normalized_label = normalize_turn_feedback_label(label)

    if not cleaned_turn_id:
        return {
            "status": "invalid",
            "message": "Turn ID is required.",
            "data": {"saved": False, "turn_id": cleaned_turn_id},
            "errors": ["turn_id must be a non-empty string."],
            "warnings": [],
        }

    if normalized_label not in ALLOWED_TURN_FEEDBACK_LABELS:
        return {
            "status": "invalid",
            "message": "Unsupported conversational turn feedback label.",
            "data": {
                "saved": False,
                "turn_id": cleaned_turn_id,
                "label": normalized_label,
                "allowed_labels": list_turn_feedback_labels(),
            },
            "errors": [f"Unsupported feedback label: {normalized_label}"],
            "warnings": [],
        }

    try:
        record = build_turn_feedback_record(
            turn_id=cleaned_turn_id,
            label=normalized_label,
            note=note,
        )
        append_jsonl(turn_feedback_journal_path(memory_dir), record)
        return {
            "status": "ok",
            "message": "Conversational turn feedback recorded.",
            "data": {
                "saved": True,
                "turn_id": cleaned_turn_id,
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
            "message": "Conversational turn feedback could not be recorded.",
            "data": {"saved": False, "turn_id": cleaned_turn_id},
            "errors": [str(error)],
            "warnings": [],
        }


def read_turn_feedback(
    *,
    turn_id: str | None = None,
    limit: int = 10,
    memory_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    records = read_jsonl(turn_feedback_journal_path(memory_dir))
    if turn_id:
        records = [
            record for record in records if record.get("turn_id") == turn_id
        ]
    if limit <= 0:
        return []
    return list(reversed(records))[:limit]


def latest_feedback_by_turn_id(
    *,
    memory_dir: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    latest_by_turn: dict[str, dict[str, Any]] = {}
    for record in read_jsonl(turn_feedback_journal_path(memory_dir)):
        turn_id = record.get("turn_id")
        if isinstance(turn_id, str) and turn_id:
            latest_by_turn[turn_id] = record
    return latest_by_turn


def format_turn_feedback_labels_report() -> str:
    lines = [
        "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK LABELS",
        "-" * 52,
    ]
    lines.extend(f"- {label}" for label in list_turn_feedback_labels())
    return "\n".join(lines)


def format_turn_feedback_result(result: dict[str, Any]) -> str:
    data = result.get("data", {})
    lines = [
        "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK",
        "-" * 52,
        f"Status: {result.get('status')}",
        f"Message: {result.get('message')}",
        f"Turn ID: {data.get('turn_id')}",
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


def format_turn_feedback_report(
    *,
    limit: int = 10,
    memory_dir: str | Path | None = None,
) -> str:
    records = read_turn_feedback(limit=limit, memory_dir=memory_dir)
    lines = [
        "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK",
        "-" * 52,
        f"Shown: {len(records)}",
    ]

    if not records:
        lines.append("No conversational turn feedback recorded yet.")
        return "\n".join(lines)

    for record in records:
        lines.append("")
        lines.append(f"feedback_id: {record.get('feedback_id')}")
        lines.append(f"turn_id: {record.get('turn_id')}")
        lines.append(f"created_at: {record.get('created_at')}")
        lines.append(f"label: {record.get('label')}")
        lines.append(f"note: {record.get('note')}")

    return "\n".join(lines)
