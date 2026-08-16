"""
Controlled case-memory promotion primitives for Lighthouse V1.5 C02.

This module defines the deterministic promotion result contract, append-only
promotion audit journal, stable promotion identity, and exact stored-case
equivalence rules.

It does not call a model.
It does not execute tools.
It does not mutate the operating system.
It does not itself persist curated case memory.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.conversational_engine_turn import DEFAULT_MEMORY_DIR


CASE_PROMOTION_AUDIT_SCHEMA_VERSION = 1
CASE_PROMOTION_POLICY_VERSION = "case_promotion_v1_5"
CASE_PROMOTION_AUDIT_FILENAME = "case_promotions.jsonl"
CASE_PROMOTION_APPROVAL_METHOD = "explicit_candidate_fingerprint"


@dataclass(frozen=True)
class CaseMemoryPromotionResult:
    """Stable truth-bearing result for one C02 case-promotion attempt."""

    status: str
    decision: str
    message: str
    source_turn_id: str
    candidate_id: str
    candidate_fingerprint: str
    promotion_id: str
    case_id: str
    persisted: bool
    case_write_performed: bool
    audit_complete: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def build_case_promotion_id(
    candidate_id: str,
    candidate_fingerprint: str,
) -> str:
    """
    Build a deterministic promotion identity for one exact candidate approval.

    The policy version is included so a future promotion-policy revision cannot
    silently reuse identities created under an older policy.
    """
    payload = {
        "policy_version": CASE_PROMOTION_POLICY_VERSION,
        "candidate_id": candidate_id,
        "candidate_fingerprint": candidate_fingerprint,
    }
    canonical_payload = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def resolve_operational_memory_dir(
    memory_dir: str | Path | None = None,
) -> Path:
    """Resolve the operational Lighthouse memory directory."""
    if memory_dir is None:
        return DEFAULT_MEMORY_DIR
    return Path(memory_dir)


def case_promotion_journal_path(
    memory_dir: str | Path | None = None,
) -> Path:
    """Return the append-only C02 promotion-audit journal path."""
    return (
        resolve_operational_memory_dir(memory_dir)
        / CASE_PROMOTION_AUDIT_FILENAME
    )


def build_case_promotion_audit_event(
    *,
    promotion_id: str,
    source_turn_id: str,
    candidate_id: str,
    candidate_fingerprint: str,
    case_id: str,
    event_type: str,
    decision: str,
    persisted: bool,
    reason: str,
) -> dict[str, Any]:
    """Build one append-only C02 promotion audit event."""
    return {
        "schema_version": CASE_PROMOTION_AUDIT_SCHEMA_VERSION,
        "policy_version": CASE_PROMOTION_POLICY_VERSION,
        "event_id": uuid4().hex,
        "promotion_id": promotion_id,
        "created_at": utc_now_iso(),
        "event_type": event_type,
        "source_turn_id": source_turn_id,
        "candidate_id": candidate_id,
        "candidate_fingerprint": candidate_fingerprint,
        "case_id": case_id,
        "operator_approved": True,
        "approval_method": CASE_PROMOTION_APPROVAL_METHOD,
        "decision": decision,
        "persisted": persisted,
        "reason": reason,
    }


def append_case_promotion_audit_event(
    event: dict[str, Any],
    *,
    memory_dir: str | Path | None = None,
) -> None:
    """Append one promotion audit event without rewriting earlier records."""
    path = case_promotion_journal_path(memory_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    serialized = json.dumps(
        event,
        ensure_ascii=False,
        sort_keys=True,
    )

    with path.open("a", encoding="utf-8") as file:
        file.write(serialized)
        file.write("\n")


def read_case_promotion_audit_events(
    *,
    memory_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """
    Read promotion audit events in append order.

    Blank, malformed, or non-object lines are ignored consistently with the
    existing Lighthouse operational-journal readers.
    """
    path = case_promotion_journal_path(memory_dir)

    if not path.exists():
        return []

    records: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()

            if not line:
                continue

            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue

            if isinstance(parsed, dict):
                records.append(parsed)

    return records


def case_records_equivalent(
    existing_case: dict[str, Any],
    proposed_case: dict[str, Any],
) -> bool:
    """
    Compare stored and proposed CaseMemory domain content exactly.

    The low-level curated store may inject a top-level ``schema_version`` into
    the stored JSONL record. That field is ignored only when it was not part of
    the proposed CaseMemory domain object. Every other field remains
    comparison-significant, including timestamps, lifecycle, status,
    confidence, evidence, and process trace.
    """
    existing = deepcopy(existing_case)
    proposed = deepcopy(proposed_case)

    if "schema_version" not in proposed:
        existing.pop("schema_version", None)

    return existing == proposed
