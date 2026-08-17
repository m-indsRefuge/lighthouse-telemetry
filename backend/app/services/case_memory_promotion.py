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

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.case_memory_candidate import (
    CASE_MEMORY_CANDIDATE_STATUS_OK,
    build_case_memory_candidate_fingerprint,
    normalize_case_memory_candidate_fingerprint,
    preview_case_memory_candidate,
)
from app.services.conversational_engine_turn import DEFAULT_MEMORY_DIR
from app.services.memory_cases import validate_case_memory
from app.services.memory_manager import (
    MEMORY_MANAGER_STATUS_OK,
    save_case_memory,
)
from app.services.memory_store import (
    MEMORY_STORE_STATUS_OK,
    read_case_memories,
)

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
    case_write_performed: bool = False,
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
        "case_write_performed": case_write_performed,
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

def _refused_promotion_result(
    *,
    message: str,
    source_turn_id: str,
    candidate_fingerprint: str = "",
    candidate_id: str = "",
    case_id: str = "",
    errors: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
) -> CaseMemoryPromotionResult:
    """Build a fail-closed result before the C02 persistence boundary."""
    return CaseMemoryPromotionResult(
        status="refused",
        decision="refused",
        message=message,
        source_turn_id=source_turn_id,
        candidate_id=candidate_id,
        candidate_fingerprint=candidate_fingerprint,
        promotion_id="",
        case_id=case_id,
        persisted=False,
        case_write_performed=False,
        audit_complete=False,
        errors=errors,
        warnings=warnings,
    )


def promote_case_memory_candidate(
    turn_id: str,
    fingerprint: str,
    *,
    operational_memory_dir: str | Path | None = None,
    curated_memory_dir: str | Path | None = None,
) -> CaseMemoryPromotionResult:
    """
    Validate one explicit exact-fingerprint promotion request.

    This Task 4A implementation deliberately stops before audit or curated
    persistence. It establishes the fail-closed authority boundary first.
    """
    clean_turn_id = turn_id.strip() if isinstance(turn_id, str) else ""
    normalized_fingerprint = normalize_case_memory_candidate_fingerprint(
        fingerprint
    )

    if not clean_turn_id or normalized_fingerprint is None:
        return _refused_promotion_result(
            message=(
                "Case promotion requires an exact conversational turn ID and "
                "64-character candidate fingerprint."
            ),
            source_turn_id=clean_turn_id,
            candidate_fingerprint=normalized_fingerprint or "",
            errors=(
                ("turn_id must be non-empty and fingerprint must be exactly "
                "64 hexadecimal characters."),
            ),
        )

    preview = preview_case_memory_candidate(
        clean_turn_id,
        memory_dir=operational_memory_dir,
    )

    if (
        preview.status != CASE_MEMORY_CANDIDATE_STATUS_OK
        or preview.candidate is None
    ):
        return _refused_promotion_result(
            message=(
                "Current case candidate preview is not valid for promotion. "
                "Re-run case preview before approving."
            ),
            source_turn_id=clean_turn_id,
            candidate_fingerprint=normalized_fingerprint,
            errors=tuple(preview.errors),
            warnings=tuple(preview.warnings),
        )

    candidate = preview.candidate
    candidate_id = candidate.candidate_id
    case_id = str(candidate.proposed_case.get("case_id", ""))

    if (
        not candidate.validation.provenance_valid
        or not candidate.validation.case_valid
    ):
        return _refused_promotion_result(
            message=(
                "Current case candidate validation is not valid for promotion. "
                "Re-run case preview before approving."
            ),
            source_turn_id=clean_turn_id,
            candidate_fingerprint=normalized_fingerprint,
            candidate_id=candidate_id,
            case_id=case_id,
            errors=tuple(candidate.validation.errors),
            warnings=tuple(candidate.validation.warnings),
        )

    current_fingerprint = build_case_memory_candidate_fingerprint(candidate)

    if current_fingerprint != normalized_fingerprint:
        return _refused_promotion_result(
            message=(
                "Candidate fingerprint no longer matches the current preview. "
                "Re-run case preview and approve the new exact fingerprint."
            ),
            source_turn_id=clean_turn_id,
            candidate_fingerprint=normalized_fingerprint,
            candidate_id=candidate_id,
            case_id=case_id,
            errors=(
                "Approved fingerprint does not match current candidate contents.",
            ),
            warnings=tuple(candidate.validation.warnings),
        )

    case_validation = validate_case_memory(candidate.proposed_case)

    if not case_validation.valid:
        return _refused_promotion_result(
            message=(
                "Proposed case failed independent validation immediately "
                "before promotion."
            ),
            source_turn_id=clean_turn_id,
            candidate_fingerprint=normalized_fingerprint,
            candidate_id=candidate_id,
            case_id=case_id,
            errors=tuple(case_validation.errors),
            warnings=tuple(case_validation.warnings),
        )

    promotion_id = build_case_promotion_id(
        candidate_id,
        normalized_fingerprint,
    )

    existing_result = read_case_memories(
        limit=None,
        memory_dir=curated_memory_dir,
    )

    if existing_result.status != MEMORY_STORE_STATUS_OK:
        return CaseMemoryPromotionResult(
            status="error",
            decision="error",
            message="Curated case store could not be read safely.",
            source_turn_id=clean_turn_id,
            candidate_id=candidate_id,
            candidate_fingerprint=normalized_fingerprint,
            promotion_id=promotion_id,
            case_id=case_id,
            persisted=False,
            case_write_performed=False,
            audit_complete=False,
            errors=(
                existing_result.error
                or existing_result.message
                or "Unknown curated-memory read error.",
            ),
            warnings=tuple(case_validation.warnings),
        )

    existing_data = existing_result.data
    existing_cases = (
        existing_data.get("entries", [])
        if isinstance(existing_data, dict)
        else []
    )

    same_id_cases = [
        existing_case
        for existing_case in existing_cases
        if existing_case.get("case_id") == case_id
    ]

    persistence_decision = "new"

    if same_id_cases:
        if all(
            case_records_equivalent(
                existing_case,
                candidate.proposed_case,
            )
            for existing_case in same_id_cases
        ):
            persistence_decision = "duplicate"
        else:
            persistence_decision = "conflict"

    attempt_event = build_case_promotion_audit_event(
        promotion_id=promotion_id,
        source_turn_id=clean_turn_id,
        candidate_id=candidate_id,
        candidate_fingerprint=normalized_fingerprint,
        case_id=case_id,
        event_type="attempt",
        decision="attempting",
        persisted=False,
        case_write_performed=False,
        reason=(
            "Explicit exact-fingerprint Operator approval entered the "
            "controlled persistence gate."
        ),
    )

    try:
        append_case_promotion_audit_event(
            attempt_event,
            memory_dir=operational_memory_dir,
        )
    except OSError as error:
        return CaseMemoryPromotionResult(
            status="error",
            decision="error",
            message=(
                "Promotion audit attempt could not be recorded; "
                "curated case was not written."
            ),
            source_turn_id=clean_turn_id,
            candidate_id=candidate_id,
            candidate_fingerprint=normalized_fingerprint,
            promotion_id=promotion_id,
            case_id=case_id,
            persisted=False,
            case_write_performed=False,
            audit_complete=False,
            errors=(str(error),),
            warnings=tuple(case_validation.warnings),
        )

    if persistence_decision == "duplicate":
        outcome_event = build_case_promotion_audit_event(
            promotion_id=promotion_id,
            source_turn_id=clean_turn_id,
            candidate_id=candidate_id,
            candidate_fingerprint=normalized_fingerprint,
            case_id=case_id,
            event_type="outcome",
            decision="duplicate",
            persisted=True,
            case_write_performed=False,
            reason=(
                "An equivalent case with the same case_id already exists; "
                "no second curated case was written."
            ),
        )

        append_case_promotion_audit_event(
            outcome_event,
            memory_dir=operational_memory_dir,
        )

        return CaseMemoryPromotionResult(
            status="duplicate",
            decision="duplicate",
            message=(
                "Exact approved case already exists in curated memory; "
                "no duplicate case was written."
            ),
            source_turn_id=clean_turn_id,
            candidate_id=candidate_id,
            candidate_fingerprint=normalized_fingerprint,
            promotion_id=promotion_id,
            case_id=case_id,
            persisted=True,
            case_write_performed=False,
            audit_complete=True,
            warnings=tuple(case_validation.warnings),
        )

    if persistence_decision == "conflict":
        outcome_event = build_case_promotion_audit_event(
            promotion_id=promotion_id,
            source_turn_id=clean_turn_id,
            candidate_id=candidate_id,
            candidate_fingerprint=normalized_fingerprint,
            case_id=case_id,
            event_type="outcome",
            decision="conflict",
            persisted=False,
            case_write_performed=False,
            reason=(
                "A case with the same case_id exists with different "
                "meaningful domain content."
            ),
        )

        append_case_promotion_audit_event(
            outcome_event,
            memory_dir=operational_memory_dir,
        )

        return CaseMemoryPromotionResult(
            status="conflict",
            decision="conflict",
            message=(
                "Case promotion refused because the case_id already exists "
                "with different curated content."
            ),
            source_turn_id=clean_turn_id,
            candidate_id=candidate_id,
            candidate_fingerprint=normalized_fingerprint,
            promotion_id=promotion_id,
            case_id=case_id,
            persisted=False,
            case_write_performed=False,
            audit_complete=True,
            errors=(
                "Existing case_id conflicts with the exact approved case.",
            ),
            warnings=tuple(case_validation.warnings),
        )

    save_result = save_case_memory(
        candidate.proposed_case,
        memory_dir=curated_memory_dir,
    )

    if save_result.status != MEMORY_MANAGER_STATUS_OK:
        error_outcome_event = build_case_promotion_audit_event(
            promotion_id=promotion_id,
            source_turn_id=clean_turn_id,
            candidate_id=candidate_id,
            candidate_fingerprint=normalized_fingerprint,
            case_id=case_id,
            event_type="outcome",
            decision="error",
            persisted=False,
            case_write_performed=False,
            reason=(
                "Curated case persistence failed after the audited "
                "promotion attempt."
            ),
        )

        audit_complete = True
        audit_errors: tuple[str, ...] = ()

        try:
            append_case_promotion_audit_event(
                error_outcome_event,
                memory_dir=operational_memory_dir,
            )
        except OSError as error:
            audit_complete = False
            audit_errors = (
                f"Promotion error outcome audit failed: {error}",
            )

        return CaseMemoryPromotionResult(
            status="error",
            decision="error",
            message=(
                "Curated case persistence failed; error outcome was "
                "recorded."
                if audit_complete
                else (
                    "Curated case persistence failed and the error "
                    "outcome audit also failed."
                )
            ),
            source_turn_id=clean_turn_id,
            candidate_id=candidate_id,
            candidate_fingerprint=normalized_fingerprint,
            promotion_id=promotion_id,
            case_id=case_id,
            persisted=False,
            case_write_performed=False,
            audit_complete=audit_complete,
            errors=tuple(save_result.errors) + audit_errors,
            warnings=(
                tuple(case_validation.warnings)
                + tuple(save_result.warnings)
            ),
        )

    outcome_event = build_case_promotion_audit_event(
        promotion_id=promotion_id,
        source_turn_id=clean_turn_id,
        candidate_id=candidate_id,
        candidate_fingerprint=normalized_fingerprint,
        case_id=case_id,
        event_type="outcome",
        decision="promoted",
        persisted=True,
        case_write_performed=True,
        reason="Exact approved case was appended to curated CaseMemory.",
    )

    try:
        append_case_promotion_audit_event(
            outcome_event,
            memory_dir=operational_memory_dir,
        )
    except OSError as error:
        return CaseMemoryPromotionResult(
            status="partial",
            decision="promoted",
            message=(
                "Exact approved case was persisted, but the final "
                "promotion outcome audit could not be recorded."
            ),
            source_turn_id=clean_turn_id,
            candidate_id=candidate_id,
            candidate_fingerprint=normalized_fingerprint,
            promotion_id=promotion_id,
            case_id=case_id,
            persisted=True,
            case_write_performed=True,
            audit_complete=False,
            errors=(str(error),),
            warnings=tuple(case_validation.warnings),
        )

    return CaseMemoryPromotionResult(
        status="ok",
        decision="promoted",
        message="Exact approved case was promoted to curated memory.",
        source_turn_id=clean_turn_id,
        candidate_id=candidate_id,
        candidate_fingerprint=normalized_fingerprint,
        promotion_id=promotion_id,
        case_id=case_id,
        persisted=True,
        case_write_performed=True,
        audit_complete=True,
        warnings=tuple(case_validation.warnings),
    )

def format_case_memory_promotion_result(
    result: CaseMemoryPromotionResult,
) -> str:
    """Format one truthful Operator-visible C02 promotion result."""

    def yes_no(value: bool) -> str:
        return "yes" if value else "no"

    lines = [
        "LIGHTHOUSE CASE PROMOTION",
        "=" * 60,
        f"Status: {result.status}",
        f"Decision: {result.decision}",
        f"Message: {result.message}",
        "",
        f"Source turn: {result.source_turn_id or 'unavailable'}",
        f"Candidate ID: {result.candidate_id or 'unavailable'}",
        (
            "Candidate fingerprint: "
            f"{result.candidate_fingerprint or 'unavailable'}"
        ),
        f"Promotion ID: {result.promotion_id or 'unavailable'}",
        f"Case ID: {result.case_id or 'unavailable'}",
        "",
        f"Persisted: {yes_no(result.persisted)}",
        f"Case write performed: {yes_no(result.case_write_performed)}",
        f"Audit complete: {yes_no(result.audit_complete)}",
    ]

    if result.warnings:
        lines.extend(
            [
                "",
                "Warnings:",
                *(f"- {warning}" for warning in result.warnings),
            ]
        )

    if result.errors:
        lines.extend(
            [
                "",
                "Errors:",
                *(f"- {error}" for error in result.errors),
            ]
        )

    lines.append("=" * 60)

    return "\n".join(lines)
