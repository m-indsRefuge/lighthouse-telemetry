"""Tests for the Lighthouse C02 controlled case-promotion primitives."""

from __future__ import annotations

import json
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))


def load_promotion_service():
    """Import the C02 service inside tests so the missing module produces RED."""
    from app.services import case_memory_promotion

    return case_memory_promotion


def test_case_memory_promotion_result_is_frozen_and_truthful() -> None:
    service = load_promotion_service()

    result = service.CaseMemoryPromotionResult(
        status="partial",
        decision="promoted",
        message="Case persisted but final audit outcome failed.",
        source_turn_id="turn-1",
        candidate_id="candidate-1",
        candidate_fingerprint="a" * 64,
        promotion_id="promotion-1",
        case_id="case-1",
        persisted=True,
        case_write_performed=True,
        audit_complete=False,
    )

    assert result.status == "partial"
    assert result.decision == "promoted"
    assert result.persisted is True
    assert result.case_write_performed is True
    assert result.audit_complete is False
    assert result.errors == ()
    assert result.warnings == ()

    with pytest.raises(FrozenInstanceError):
        result.persisted = False


def test_case_records_equivalent_ignores_only_store_schema_version() -> None:
    service = load_promotion_service()

    proposed = {
        "case_id": "case-1",
        "created_at": "2026-08-16T07:00:00+00:00",
        "updated_at": "2026-08-16T07:00:00+00:00",
        "status": "unresolved",
        "confidence": "low",
        "source": "system_generated",
    }

    stored = dict(proposed, schema_version=1)

    assert service.case_records_equivalent(stored, proposed) is True

    changed_status = dict(stored, status="resolved")
    assert service.case_records_equivalent(changed_status, proposed) is False

    changed_created = dict(
        stored,
        created_at="2026-08-16T08:00:00+00:00",
    )
    assert service.case_records_equivalent(changed_created, proposed) is False


def test_promotion_id_is_stable_and_bound_to_candidate_and_fingerprint() -> None:
    service = load_promotion_service()

    first = service.build_case_promotion_id("candidate-1", "a" * 64)
    second = service.build_case_promotion_id("candidate-1", "a" * 64)

    assert first == second
    assert len(first) == 64
    assert first == first.lower()

    assert (
        service.build_case_promotion_id("candidate-2", "a" * 64)
        != first
    )
    assert (
        service.build_case_promotion_id("candidate-1", "b" * 64)
        != first
    )


def test_case_promotion_audit_is_append_only_and_carries_authority_fields(
    tmp_path: Path,
) -> None:
    service = load_promotion_service()

    first = service.build_case_promotion_audit_event(
        promotion_id="promotion-1",
        source_turn_id="turn-1",
        candidate_id="candidate-1",
        candidate_fingerprint="a" * 64,
        case_id="case-1",
        event_type="attempt",
        decision="attempting",
        persisted=False,
        reason="Explicit exact-fingerprint approval entered persistence gate.",
    )

    second = service.build_case_promotion_audit_event(
        promotion_id="promotion-1",
        source_turn_id="turn-1",
        candidate_id="candidate-1",
        candidate_fingerprint="a" * 64,
        case_id="case-1",
        event_type="outcome",
        decision="promoted",
        persisted=True,
        reason="Curated case persisted.",
    )

    assert first["schema_version"] == service.CASE_PROMOTION_AUDIT_SCHEMA_VERSION
    assert first["policy_version"] == service.CASE_PROMOTION_POLICY_VERSION
    assert first["operator_approved"] is True
    assert (
        first["approval_method"]
        == service.CASE_PROMOTION_APPROVAL_METHOD
    )
    assert first["event_id"] != second["event_id"]
    assert first["created_at"]
    assert second["created_at"]

    service.append_case_promotion_audit_event(
        first,
        memory_dir=tmp_path,
    )
    service.append_case_promotion_audit_event(
        second,
        memory_dir=tmp_path,
    )

    journal_path = service.case_promotion_journal_path(tmp_path)

    assert journal_path == tmp_path / "case_promotions.jsonl"
    assert journal_path.exists()

    raw_lines = journal_path.read_text(encoding="utf-8").splitlines()

    assert len(raw_lines) == 2
    assert json.loads(raw_lines[0]) == first
    assert json.loads(raw_lines[1]) == second

    records = service.read_case_promotion_audit_events(
        memory_dir=tmp_path,
    )

    assert records == [first, second]

# === C02 TASK 4A: EXACT-APPROVAL REFUSAL GATE ===


def test_promote_case_memory_candidate_rejects_malformed_fingerprint_before_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = load_promotion_service()

    def forbidden_preview(*args, **kwargs):
        raise AssertionError(
            "Malformed fingerprint must stop before candidate preview."
        )

    monkeypatch.setattr(
        service,
        "preview_case_memory_candidate",
        forbidden_preview,
        raising=False,
    )

    result = service.promote_case_memory_candidate(
        "turn-1",
        "not-a-valid-fingerprint",
        operational_memory_dir=tmp_path / "operational",
        curated_memory_dir=tmp_path / "curated",
    )

    assert result.status == "refused"
    assert result.decision == "refused"
    assert result.persisted is False
    assert result.case_write_performed is False
    assert result.audit_complete is False

    assert not service.case_promotion_journal_path(
        tmp_path / "operational"
    ).exists()
    assert not (tmp_path / "curated" / "cases.jsonl").exists()


def test_promote_case_memory_candidate_refuses_invalid_preview_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    service = load_promotion_service()

    monkeypatch.setattr(
        service,
        "preview_case_memory_candidate",
        lambda *args, **kwargs: SimpleNamespace(
            status="invalid",
            candidate=None,
            errors=("candidate invalid",),
            warnings=(),
        ),
        raising=False,
    )

    def forbidden_write(*args, **kwargs):
        raise AssertionError(
            "Invalid preview must not cross a write boundary."
        )

    monkeypatch.setattr(
        service,
        "append_case_promotion_audit_event",
        forbidden_write,
    )
    monkeypatch.setattr(
        service,
        "save_case_memory",
        forbidden_write,
        raising=False,
    )

    result = service.promote_case_memory_candidate(
        "turn-1",
        "a" * 64,
        operational_memory_dir=tmp_path / "operational",
        curated_memory_dir=tmp_path / "curated",
    )

    assert result.status == "refused"
    assert result.decision == "refused"
    assert result.persisted is False
    assert result.case_write_performed is False


def test_promote_case_memory_candidate_refuses_invalid_candidate_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    service = load_promotion_service()

    candidate = SimpleNamespace(
        schema_version="case_memory_candidate_v1_5",
        candidate_id="candidate-1",
        source_turn_id="turn-1",
        provenance={"source": "test"},
        proposed_case={"case_id": "case-1"},
        validation=SimpleNamespace(
            provenance_valid=False,
            case_valid=True,
            errors=("provenance invalid",),
            warnings=(),
        ),
    )

    monkeypatch.setattr(
        service,
        "preview_case_memory_candidate",
        lambda *args, **kwargs: SimpleNamespace(
            status="ok",
            candidate=candidate,
            errors=(),
            warnings=(),
        ),
        raising=False,
    )

    def forbidden_write(*args, **kwargs):
        raise AssertionError(
            "Invalid candidate must not cross a write boundary."
        )

    monkeypatch.setattr(
        service,
        "append_case_promotion_audit_event",
        forbidden_write,
    )
    monkeypatch.setattr(
        service,
        "save_case_memory",
        forbidden_write,
        raising=False,
    )

    result = service.promote_case_memory_candidate(
        "turn-1",
        "a" * 64,
        operational_memory_dir=tmp_path / "operational",
        curated_memory_dir=tmp_path / "curated",
    )

    assert result.status == "refused"
    assert result.decision == "refused"
    assert result.persisted is False
    assert result.case_write_performed is False


def test_promote_case_memory_candidate_refuses_stale_fingerprint_before_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from app.services.case_memory_candidate import (
        build_case_memory_candidate_fingerprint,
    )

    service = load_promotion_service()

    candidate = SimpleNamespace(
        schema_version="case_memory_candidate_v1_5",
        candidate_id="candidate-1",
        source_turn_id="turn-1",
        provenance={
            "operator_feedback": {
                "present": True,
                "record": {"label": "corrected"},
            }
        },
        proposed_case={
            "case_id": "case-1",
            "status": "unresolved",
        },
        validation=SimpleNamespace(
            provenance_valid=True,
            case_valid=True,
            errors=(),
            warnings=(),
        ),
    )

    current_fingerprint = build_case_memory_candidate_fingerprint(candidate)
    stale_fingerprint = "a" * 64

    assert current_fingerprint != stale_fingerprint

    monkeypatch.setattr(
        service,
        "preview_case_memory_candidate",
        lambda *args, **kwargs: SimpleNamespace(
            status="ok",
            candidate=candidate,
            errors=(),
            warnings=(),
        ),
        raising=False,
    )

    def forbidden_write(*args, **kwargs):
        raise AssertionError(
            "Stale approval must stop before audit or persistence."
        )

    monkeypatch.setattr(
        service,
        "append_case_promotion_audit_event",
        forbidden_write,
    )
    monkeypatch.setattr(
        service,
        "save_case_memory",
        forbidden_write,
        raising=False,
    )

    result = service.promote_case_memory_candidate(
        "turn-1",
        stale_fingerprint,
        operational_memory_dir=tmp_path / "operational",
        curated_memory_dir=tmp_path / "curated",
    )

    assert result.status == "refused"
    assert result.decision == "refused"
    assert result.persisted is False
    assert result.case_write_performed is False
    assert "preview" in result.message.lower()

# === C02 TASK 4B: AUDITED PERSISTENCE AND IDEMPOTENCY ===


def build_task4_valid_candidate(
    *,
    case_id: str = "case-task4-1",
):
    from types import SimpleNamespace

    from app.services.case_memory_candidate import (
        build_case_memory_candidate_fingerprint,
    )
    from app.services.memory_cases import (
        CASE_CONFIDENCE_LOW,
        CASE_SOURCE_SYSTEM_GENERATED,
        CASE_STATUS_UNRESOLVED,
    )
    from app.services.memory_manager import build_case_memory

    proposed_case = build_case_memory(
        case_id=case_id,
        problem="Operator asked for a deterministic diagnostic preview.",
        symptoms=["Operator requested diagnostic interpretation."],
        suspected_cause="Unknown; no causal conclusion was established.",
        lesson="Operator review is required before treating this case as resolved.",
        tags=["conversation_turn", "task4"],
        telemetry_evidence={
            "availability": "not_observed",
            "source": "conversation_turn_journal",
        },
        event_evidence={
            "availability": "not_observed",
            "source": "conversation_turn_journal",
        },
        action_taken="Unknown; no observed action was recorded.",
        outcome="Unknown; no observed outcome was recorded.",
        diagnostic_steps=[
            "Read deterministic conversational-turn evidence.",
        ],
        decision_notes=[
            "No resolution or causal certainty was inferred.",
        ],
        operator_feedback="",
        status=CASE_STATUS_UNRESOLVED,
        confidence=CASE_CONFIDENCE_LOW,
        source=CASE_SOURCE_SYSTEM_GENERATED,
        created_at="2026-08-16T07:00:00+00:00",
        updated_at="2026-08-16T07:00:00+00:00",
    )

    candidate = SimpleNamespace(
        schema_version="case_memory_candidate_v1_5",
        candidate_id="candidate-task4-1",
        source_turn_id="turn-task4-1",
        provenance={
            "turn_journal": {
                "turn_id": "turn-task4-1",
                "created_at": "2026-08-16T07:00:00+00:00",
            },
            "operator_feedback": {
                "present": False,
                "record": None,
            },
        },
        proposed_case=proposed_case,
        validation=SimpleNamespace(
            provenance_valid=True,
            case_valid=True,
            errors=(),
            warnings=(),
        ),
    )

    fingerprint = build_case_memory_candidate_fingerprint(candidate)

    preview = SimpleNamespace(
        status="ok",
        candidate=candidate,
        errors=(),
        warnings=(),
    )

    return candidate, fingerprint, preview


def test_exact_candidate_approval_persists_once_with_attempt_and_outcome_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.memory_store import read_case_memories

    service = load_promotion_service()
    candidate, fingerprint, preview = build_task4_valid_candidate()

    operational_dir = tmp_path / "operational"
    curated_dir = tmp_path / "curated"

    monkeypatch.setattr(
        service,
        "preview_case_memory_candidate",
        lambda *args, **kwargs: preview,
    )

    result = service.promote_case_memory_candidate(
        candidate.source_turn_id,
        fingerprint,
        operational_memory_dir=operational_dir,
        curated_memory_dir=curated_dir,
    )

    assert result.status == "ok"
    assert result.decision == "promoted"
    assert result.persisted is True
    assert result.case_write_performed is True
    assert result.audit_complete is True
    assert result.candidate_fingerprint == fingerprint
    assert result.promotion_id == service.build_case_promotion_id(
        candidate.candidate_id,
        fingerprint,
    )

    stored_result = read_case_memories(
        limit=None,
        newest_first=False,
        memory_dir=curated_dir,
    )
    stored_cases = stored_result.data["entries"]

    assert len(stored_cases) == 1
    assert service.case_records_equivalent(
        stored_cases[0],
        candidate.proposed_case,
    )

    audit = service.read_case_promotion_audit_events(
        memory_dir=operational_dir,
    )

    assert [event["event_type"] for event in audit] == [
        "attempt",
        "outcome",
    ]
    assert [event["decision"] for event in audit] == [
        "attempting",
        "promoted",
    ]
    assert audit[0]["persisted"] is False
    assert audit[0]["case_write_performed"] is False
    assert audit[1]["persisted"] is True
    assert audit[1]["case_write_performed"] is True


def test_repeat_exact_approval_is_duplicate_without_second_case_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.memory_store import read_case_memories

    service = load_promotion_service()
    candidate, fingerprint, preview = build_task4_valid_candidate()

    operational_dir = tmp_path / "operational"
    curated_dir = tmp_path / "curated"

    monkeypatch.setattr(
        service,
        "preview_case_memory_candidate",
        lambda *args, **kwargs: preview,
    )

    first = service.promote_case_memory_candidate(
        candidate.source_turn_id,
        fingerprint,
        operational_memory_dir=operational_dir,
        curated_memory_dir=curated_dir,
    )
    second = service.promote_case_memory_candidate(
        candidate.source_turn_id,
        fingerprint,
        operational_memory_dir=operational_dir,
        curated_memory_dir=curated_dir,
    )

    assert first.status == "ok"

    assert second.status == "duplicate"
    assert second.decision == "duplicate"
    assert second.persisted is True
    assert second.case_write_performed is False
    assert second.audit_complete is True

    stored_result = read_case_memories(
        limit=None,
        memory_dir=curated_dir,
    )
    assert len(stored_result.data["entries"]) == 1

    audit = service.read_case_promotion_audit_events(
        memory_dir=operational_dir,
    )

    assert len(audit) == 4
    assert audit[-2]["event_type"] == "attempt"
    assert audit[-2]["decision"] == "attempting"
    assert audit[-1]["event_type"] == "outcome"
    assert audit[-1]["decision"] == "duplicate"
    assert audit[-1]["persisted"] is True
    assert audit[-1]["case_write_performed"] is False


def test_same_case_id_with_different_meaningful_content_is_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from copy import deepcopy

    from app.services.memory_manager import save_case_memory
    from app.services.memory_store import read_case_memories

    service = load_promotion_service()
    candidate, fingerprint, preview = build_task4_valid_candidate()

    operational_dir = tmp_path / "operational"
    curated_dir = tmp_path / "curated"

    conflicting_case = deepcopy(candidate.proposed_case)
    conflicting_case["case_card"]["lesson"] = (
        "This existing case has materially different curated content."
    )

    preexisting = save_case_memory(
        conflicting_case,
        memory_dir=curated_dir,
    )
    assert preexisting.status == "ok"

    monkeypatch.setattr(
        service,
        "preview_case_memory_candidate",
        lambda *args, **kwargs: preview,
    )

    result = service.promote_case_memory_candidate(
        candidate.source_turn_id,
        fingerprint,
        operational_memory_dir=operational_dir,
        curated_memory_dir=curated_dir,
    )

    assert result.status == "conflict"
    assert result.decision == "conflict"
    assert result.persisted is False
    assert result.case_write_performed is False
    assert result.audit_complete is True

    stored_result = read_case_memories(
        limit=None,
        memory_dir=curated_dir,
    )
    assert len(stored_result.data["entries"]) == 1

    audit = service.read_case_promotion_audit_events(
        memory_dir=operational_dir,
    )
    assert [event["decision"] for event in audit] == [
        "attempting",
        "conflict",
    ]
    assert audit[-1]["case_write_performed"] is False


def test_promotion_revalidates_proposed_case_before_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from copy import deepcopy
    from types import SimpleNamespace

    from app.services.case_memory_candidate import (
        build_case_memory_candidate_fingerprint,
    )

    service = load_promotion_service()
    candidate, _, _ = build_task4_valid_candidate()

    invalid_case = deepcopy(candidate.proposed_case)
    invalid_case["case_card"]["lesson"] = ""

    invalid_candidate = SimpleNamespace(
        schema_version=candidate.schema_version,
        candidate_id=candidate.candidate_id,
        source_turn_id=candidate.source_turn_id,
        provenance=candidate.provenance,
        proposed_case=invalid_case,
        validation=SimpleNamespace(
            provenance_valid=True,
            case_valid=True,
            errors=(),
            warnings=(),
        ),
    )

    fingerprint = build_case_memory_candidate_fingerprint(
        invalid_candidate
    )

    preview = SimpleNamespace(
        status="ok",
        candidate=invalid_candidate,
        errors=(),
        warnings=(),
    )

    monkeypatch.setattr(
        service,
        "preview_case_memory_candidate",
        lambda *args, **kwargs: preview,
    )

    result = service.promote_case_memory_candidate(
        invalid_candidate.source_turn_id,
        fingerprint,
        operational_memory_dir=tmp_path / "operational",
        curated_memory_dir=tmp_path / "curated",
    )

    assert result.status == "refused"
    assert result.decision == "refused"
    assert result.persisted is False
    assert result.case_write_performed is False
    assert any("lesson" in error.lower() for error in result.errors)

    assert not service.case_promotion_journal_path(
        tmp_path / "operational"
    ).exists()
    assert not (tmp_path / "curated" / "cases.jsonl").exists()
