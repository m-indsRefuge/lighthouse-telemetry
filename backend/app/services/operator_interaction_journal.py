"""
Append-only Operator interaction and feedback journal for Lighthouse.

This module captures structured Operator traces that can later support:
- deterministic memory
- evaluation datasets
- route-quality review
- future model training or fine-tuning analysis

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


ALLOWED_INTERACTION_MODES = frozenset({"talk", "talkrun"})

ALLOWED_FEEDBACK_LABELS = frozenset(
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

DEFAULT_MEMORY_DIR = Path(__file__).resolve().parents[3] / "memory"
INTERACTION_JOURNAL_FILENAME = "operator_interactions.jsonl"
FEEDBACK_JOURNAL_FILENAME = "operator_feedback.jsonl"


def utc_now_iso() -> str:
    """
    Return an ISO-like UTC timestamp.
    """
    return datetime.now(timezone.utc).isoformat()


def build_trace_id() -> str:
    """
    Build a compact unique trace id for an Operator interaction.
    """
    return f"optrace-{uuid4().hex}"


def build_feedback_id() -> str:
    """
    Build a compact unique id for Operator feedback.
    """
    return f"opfb-{uuid4().hex}"


def resolve_memory_dir(memory_dir: str | Path | None = None) -> Path:
    """
    Resolve the memory directory used for Operator journals.
    """
    if memory_dir is None:
        return DEFAULT_MEMORY_DIR

    return Path(memory_dir)


def interaction_journal_path(memory_dir: str | Path | None = None) -> Path:
    """
    Return the Operator interaction JSONL path.
    """
    return resolve_memory_dir(memory_dir) / INTERACTION_JOURNAL_FILENAME


def feedback_journal_path(memory_dir: str | Path | None = None) -> Path:
    """
    Return the Operator feedback JSONL path.
    """
    return resolve_memory_dir(memory_dir) / FEEDBACK_JOURNAL_FILENAME


def ensure_memory_dir(memory_dir: str | Path | None = None) -> Path:
    """
    Ensure the memory directory exists.
    """
    resolved_dir = resolve_memory_dir(memory_dir)
    resolved_dir.mkdir(parents=True, exist_ok=True)
    return resolved_dir


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
    Read a JSONL file. Malformed rows are skipped rather than breaking recall.
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


def result_to_payload(result: Any) -> dict[str, Any]:
    """
    Convert an OperatorConversationResult-like object to a dictionary.
    """
    if hasattr(result, "to_dict"):
        payload = result.to_dict()

        if isinstance(payload, dict):
            return payload

    if isinstance(result, dict):
        return dict(result)

    return {}


def gate_to_payload(autorun_gate: Any) -> dict[str, Any] | None:
    """
    Convert an autorun gate result to a dictionary when present.
    """
    if autorun_gate is None:
        return None

    if hasattr(autorun_gate, "to_dict"):
        payload = autorun_gate.to_dict()

        if isinstance(payload, dict):
            return payload

    if isinstance(autorun_gate, dict):
        return dict(autorun_gate)

    return None


def normalize_execution(execution: dict[str, Any] | None) -> dict[str, Any]:
    """
    Normalize execution metadata for a trace record.
    """
    execution_payload = execution or {}

    return {
        "attempted": bool(execution_payload.get("attempted", False)),
        "executed": bool(execution_payload.get("executed", False)),
        "refused": bool(execution_payload.get("refused", False)),
        "engine_request": execution_payload.get("engine_request"),
    }


def build_operator_interaction_record(
    *,
    mode: str,
    result: Any,
    autorun_gate: Any = None,
    execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build one structured Operator interaction trace record.
    """
    normalized_mode = mode.strip().lower()
    result_payload = result_to_payload(result)

    if normalized_mode not in ALLOWED_INTERACTION_MODES:
        normalized_mode = "talk"

    return {
        "trace_id": build_trace_id(),
        "created_at": utc_now_iso(),
        "mode": normalized_mode,
        "original_input": result_payload.get("original_input"),
        "normalized_input": result_payload.get("normalized_input"),
        "status": result_payload.get("status"),
        "intent": result_payload.get("intent"),
        "interpreted_request": result_payload.get("interpreted_request"),
        "recommended_command": result_payload.get("recommended_command"),
        "decision_trace": result_payload.get("decision_trace", {}),
        "route_handoff": result_payload.get("route_handoff", {}),
        "autorun_gate": gate_to_payload(autorun_gate),
        "execution": normalize_execution(execution),
        "operator_feedback": None,
    }


def record_operator_interaction(
    *,
    mode: str,
    result: Any,
    autorun_gate: Any = None,
    execution: dict[str, Any] | None = None,
    memory_dir: str | Path | None = None,
) -> dict[str, Any]:
    """
    Record one Operator interaction trace.
    """
    try:
        ensure_memory_dir(memory_dir)
        record = build_operator_interaction_record(
            mode=mode,
            result=result,
            autorun_gate=autorun_gate,
            execution=execution,
        )
        append_jsonl(interaction_journal_path(memory_dir), record)

        return {
            "status": "ok",
            "message": "Operator interaction recorded.",
            "data": {
                "trace_id": record["trace_id"],
                "saved": True,
                "record": record,
            },
            "errors": [],
            "warnings": [],
        }
    except OSError as error:
        return {
            "status": "error",
            "message": "Operator interaction could not be recorded.",
            "data": {"trace_id": None, "saved": False},
            "errors": [str(error)],
            "warnings": [],
        }


def read_operator_interactions(
    *,
    limit: int = 10,
    memory_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """
    Read recent Operator interaction traces, newest first.
    """
    records = read_jsonl(interaction_journal_path(memory_dir))

    if limit <= 0:
        return []

    return list(reversed(records))[:limit]


def list_feedback_labels() -> list[str]:
    """
    Return valid Operator feedback labels.
    """
    return sorted(ALLOWED_FEEDBACK_LABELS)


def normalize_feedback_label(label: str) -> str:
    """
    Normalize an Operator feedback label.
    """
    return label.strip().lower().replace("-", "_")


def build_operator_feedback_record(
    *,
    trace_id: str,
    label: str,
    note: str = "",
) -> dict[str, Any]:
    """
    Build one Operator feedback record.
    """
    return {
        "feedback_id": build_feedback_id(),
        "trace_id": trace_id.strip(),
        "created_at": utc_now_iso(),
        "label": normalize_feedback_label(label),
        "note": note.strip(),
    }


def record_operator_feedback(
    *,
    trace_id: str,
    label: str,
    note: str = "",
    memory_dir: str | Path | None = None,
) -> dict[str, Any]:
    """
    Record Operator feedback for a previous interaction trace.
    """
    cleaned_trace_id = trace_id.strip()
    normalized_label = normalize_feedback_label(label)

    if not cleaned_trace_id:
        return {
            "status": "invalid",
            "message": "Trace ID is required.",
            "data": {"saved": False, "trace_id": cleaned_trace_id},
            "errors": ["trace_id must be a non-empty string."],
            "warnings": [],
        }

    if normalized_label not in ALLOWED_FEEDBACK_LABELS:
        return {
            "status": "invalid",
            "message": "Unsupported feedback label.",
            "data": {
                "saved": False,
                "trace_id": cleaned_trace_id,
                "label": normalized_label,
                "allowed_labels": list_feedback_labels(),
            },
            "errors": [f"Unsupported feedback label: {normalized_label}"],
            "warnings": [],
        }

    try:
        ensure_memory_dir(memory_dir)
        record = build_operator_feedback_record(
            trace_id=cleaned_trace_id,
            label=normalized_label,
            note=note,
        )
        append_jsonl(feedback_journal_path(memory_dir), record)

        return {
            "status": "ok",
            "message": "Operator feedback recorded.",
            "data": {
                "saved": True,
                "trace_id": cleaned_trace_id,
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
            "message": "Operator feedback could not be recorded.",
            "data": {"saved": False, "trace_id": cleaned_trace_id},
            "errors": [str(error)],
            "warnings": [],
        }


def read_operator_feedback(
    *,
    trace_id: str | None = None,
    limit: int = 10,
    memory_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """
    Read recent Operator feedback, optionally filtered by trace id.
    """
    records = read_jsonl(feedback_journal_path(memory_dir))

    if trace_id:
        records = [
            record
            for record in records
            if record.get("trace_id") == trace_id
        ]

    if limit <= 0:
        return []

    return list(reversed(records))[:limit]


def latest_feedback_by_trace_id(
    *,
    memory_dir: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Return latest feedback per trace id.
    """
    feedback_records = read_jsonl(feedback_journal_path(memory_dir))
    latest_by_trace: dict[str, dict[str, Any]] = {}

    for record in feedback_records:
        trace_id = record.get("trace_id")

        if isinstance(trace_id, str) and trace_id:
            latest_by_trace[trace_id] = record

    return latest_by_trace


def format_operator_interactions_report(
    *,
    limit: int = 10,
    memory_dir: str | Path | None = None,
) -> str:
    """
    Build a plain-text report of recent Operator interactions.
    """
    interactions = read_operator_interactions(limit=limit, memory_dir=memory_dir)
    feedback_by_trace = latest_feedback_by_trace_id(memory_dir=memory_dir)

    lines = [
        "LIGHTHOUSE OPERATOR INTERACTIONS",
        "-" * 52,
        f"Shown: {len(interactions)}",
    ]

    if not interactions:
        lines.append("No Operator interactions recorded yet.")
        return "\n".join(lines)

    for record in interactions:
        trace_id = record.get("trace_id", "")
        feedback = feedback_by_trace.get(trace_id)
        feedback_label = feedback.get("label") if feedback else "none"

        lines.append("")
        lines.append(f"trace_id: {trace_id}")
        lines.append(f"created_at: {record.get('created_at')}")
        lines.append(f"mode: {record.get('mode')}")
        lines.append(f"status: {record.get('status')}")
        lines.append(f"intent: {record.get('intent')}")
        lines.append(f"feedback: {feedback_label}")

        execution = record.get("execution", {})

        if isinstance(execution, dict):
            lines.append(f"executed: {'yes' if execution.get('executed') else 'no'}")
            lines.append(f"refused: {'yes' if execution.get('refused') else 'no'}")

    return "\n".join(lines)


def format_feedback_labels_report() -> str:
    """
    Build a plain-text report of allowed feedback labels.
    """
    lines = [
        "LIGHTHOUSE OPERATOR FEEDBACK LABELS",
        "-" * 52,
    ]

    lines.extend(f"- {label}" for label in list_feedback_labels())

    return "\n".join(lines)


def format_operator_feedback_result(result: dict[str, Any]) -> str:
    """
    Build a plain-text report for feedback save results.
    """
    data = result.get("data", {})

    lines = [
        "LIGHTHOUSE OPERATOR FEEDBACK",
        "-" * 52,
        f"Status: {result.get('status')}",
        f"Message: {result.get('message')}",
        f"Trace ID: {data.get('trace_id')}",
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
