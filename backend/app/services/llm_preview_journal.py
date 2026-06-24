"""
Append-only LLM route preview journal for Lighthouse.

This journal captures preview-only model route proposal evidence.

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


DEFAULT_MEMORY_DIR = Path(__file__).resolve().parents[3] / "memory"
LLM_PREVIEW_JOURNAL_FILENAME = "llm_route_previews.jsonl"


def utc_now_iso() -> str:
    """
    Return an ISO-like UTC timestamp.
    """
    return datetime.now(timezone.utc).isoformat()


def build_preview_id() -> str:
    """
    Build a compact unique id for an LLM route preview.
    """
    return f"llmprev-{uuid4().hex}"


def resolve_memory_dir(memory_dir: str | Path | None = None) -> Path:
    """
    Resolve the memory directory used for LLM preview journals.
    """
    if memory_dir is None:
        return DEFAULT_MEMORY_DIR

    return Path(memory_dir)


def llm_preview_journal_path(memory_dir: str | Path | None = None) -> Path:
    """
    Return the LLM route preview JSONL path.
    """
    return resolve_memory_dir(memory_dir) / LLM_PREVIEW_JOURNAL_FILENAME


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


def result_to_payload(preview_result: Any) -> dict[str, Any]:
    """
    Convert an LLMRouteCallResult-like object to a dictionary.
    """
    if hasattr(preview_result, "to_dict"):
        payload = preview_result.to_dict()

        if isinstance(payload, dict):
            return payload

    if isinstance(preview_result, dict):
        return dict(preview_result)

    return {}


def build_llm_preview_record(
    *,
    user_request: str,
    preview_result: Any,
) -> dict[str, Any]:
    """
    Build one structured LLM route preview journal record.
    """
    preview_payload = result_to_payload(preview_result)
    validation = preview_payload.get("validation")

    if not isinstance(validation, dict):
        validation = None

    return {
        "preview_id": build_preview_id(),
        "created_at": utc_now_iso(),
        "mode": "llm_preview",
        "original_input": user_request,
        "normalized_input": user_request.strip(),
        "status": preview_payload.get("status"),
        "message": preview_payload.get("message"),
        "model_used": preview_payload.get("model_used"),
        "used_model": bool(preview_payload.get("used_model", False)),
        "validation_status": validation.get("status") if validation else None,
        "contract_valid": validation.get("valid") if validation else None,
        "proposed_intent": (
            validation.get("normalized_proposal", {}).get("proposed_intent")
            if validation
            else None
        ),
        "interpreted_request": (
            validation.get("normalized_proposal", {}).get("interpreted_request")
            if validation
            else None
        ),
        "route_handoff": validation.get("route_handoff", {}) if validation else {},
        "errors": list(preview_payload.get("errors", [])),
        "warnings": list(preview_payload.get("warnings", [])),
        "safety": {
            "preview_only": True,
            "executed": False,
            "talk_integration": False,
            "talkrun_integration": False,
            "model_authority": False,
            "os_mutation": False,
        },
    }


def record_llm_route_preview(
    *,
    user_request: str,
    preview_result: Any,
    memory_dir: str | Path | None = None,
) -> dict[str, Any]:
    """
    Record one preview-only LLM route proposal trace.
    """
    try:
        record = build_llm_preview_record(
            user_request=user_request,
            preview_result=preview_result,
        )
        append_jsonl(llm_preview_journal_path(memory_dir), record)

        return {
            "status": "ok",
            "message": "LLM route preview recorded.",
            "data": {
                "preview_id": record["preview_id"],
                "saved": True,
                "record": record,
            },
            "errors": [],
            "warnings": [],
        }
    except OSError as error:
        return {
            "status": "error",
            "message": "LLM route preview could not be recorded.",
            "data": {"preview_id": None, "saved": False},
            "errors": [str(error)],
            "warnings": [],
        }


def read_llm_route_previews(
    *,
    limit: int = 10,
    memory_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """
    Read recent LLM route preview records, newest first.
    """
    if limit <= 0:
        return []

    records = read_jsonl(llm_preview_journal_path(memory_dir))
    return list(reversed(records))[:limit]


def format_llm_route_previews_report(
    *,
    limit: int = 10,
    memory_dir: str | Path | None = None,
) -> str:
    """
    Build a plain-text report of recent LLM route previews.
    """
    previews = read_llm_route_previews(limit=limit, memory_dir=memory_dir)

    lines = [
        "LIGHTHOUSE LLM ROUTE PREVIEWS",
        "-" * 52,
        f"Shown: {len(previews)}",
    ]

    if not previews:
        lines.append("No LLM route previews recorded yet.")
        return "\n".join(lines)

    for record in previews:
        safety = record.get("safety", {})
        route_handoff = record.get("route_handoff", {})

        lines.append("")
        lines.append(f"preview_id: {record.get('preview_id')}")
        lines.append(f"created_at: {record.get('created_at')}")
        lines.append(f"status: {record.get('status')}")
        lines.append(f"contract_valid: {record.get('contract_valid')}")
        lines.append(f"proposed_intent: {record.get('proposed_intent')}")
        lines.append(f"interpreted_request: {record.get('interpreted_request')}")

        if isinstance(route_handoff, dict):
            lines.append(
                "recommended_command: "
                f"{route_handoff.get('recommended_command')}"
            )

        if isinstance(safety, dict):
            lines.append(f"executed: {'yes' if safety.get('executed') else 'no'}")
            lines.append(
                "preview_only: "
                f"{'yes' if safety.get('preview_only') else 'no'}"
            )

    return "\n".join(lines)
