"""
Tests for the Lighthouse V1.5 case-memory candidate preview boundary.

The preview reads operational turn/feedback evidence but must not create or
persist curated case memory.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))


from app.services.case_memory_candidate import (
    CASE_MEMORY_CANDIDATE_SCHEMA_VERSION,
    CaseMemoryCandidate,
    format_case_memory_candidate_preview_report,
    preview_case_memory_candidate,
)
from app.services.conversation_turn_dataset_export import (
    CATEGORY_CORRECTION_NEEDED,
)
from app.services.conversation_turn_feedback import record_turn_feedback
from app.services.conversational_engine_turn import (
    build_conversational_engine_turn,
    conversational_turn_journal_path,
    read_conversational_engine_turns,
)
from app.services.memory_cases import validate_case_memory


def valid_route_model(prompt: str) -> dict[str, str]:
    return {
        "response": json.dumps(
            {
                "schema_version": "llm_contract_v0",
                "proposed_intent": "performance_diagnostic",
                "interpreted_request": "why is my laptop slow",
                "confidence": 0.91,
                "reasoning_summary": "The request concerns slow performance.",
                "safety_notes": ["Read-only diagnostic route only."],
            }
        )
    }


def invalid_route_model(prompt: str) -> dict[str, str]:
    """Return a model response that the LLM contract must reject."""
    return {"response": "not a JSON contract"}


def failing_route_model(prompt: str) -> Any:
    """Simulate an attempted model call that returns no proposal evidence."""
    raise RuntimeError("injected model call failure")


def record_turn(
    memory_dir: Path,
    *,
    user_request: str = "why is my laptop slow",
    use_model: bool = False,
    model_callable: Callable[[str], Any] | None = None,
) -> dict:
    selected_model = model_callable

    if selected_model is None and use_model:
        selected_model = valid_route_model

    result = build_conversational_engine_turn(
        user_request,
        model_callable=selected_model,
        memory_dir=memory_dir,
    )

    assert result.turn_journal_result is not None
    turn_id = result.turn_journal_result["data"]["turn_id"]

    return next(
        record
        for record in read_conversational_engine_turns(memory_dir=memory_dir)
        if record["turn_id"] == turn_id
    )


def write_turn_records(memory_dir: Path, records: list[dict]) -> None:
    path = conversational_turn_journal_path(memory_dir)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def file_snapshot(directory: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(directory)): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def test_preview_builds_stable_candidate_from_exact_turn_without_writes(
    tmp_path: Path,
) -> None:
    """Catches a preview that substitutes another turn, uses random identity, or writes."""
    source_turn = record_turn(tmp_path, use_model=True)
    before = file_snapshot(tmp_path)

    first = preview_case_memory_candidate(
        source_turn["turn_id"],
        memory_dir=tmp_path,
    )
    second = preview_case_memory_candidate(
        source_turn["turn_id"],
        memory_dir=tmp_path,
    )

    assert first.status == "ok"
    assert first.candidate is not None
    assert isinstance(first.candidate, CaseMemoryCandidate)
    assert second.candidate is not None
    assert first.candidate.candidate_id == second.candidate.candidate_id
    assert first.candidate.schema_version == CASE_MEMORY_CANDIDATE_SCHEMA_VERSION
    assert first.candidate.source_turn_id == source_turn["turn_id"]
    assert first.candidate.source_turn_created_at == source_turn["created_at"]
    assert first.candidate.promotion == {
        "preview_only": True,
        "persisted": False,
        "operator_approval_required": True,
    }
    assert first.candidate.safety == {
        "model_authority": False,
        "tool_execution": False,
        "os_mutation": False,
        "memory_write": False,
    }
    assert first.candidate.validation.provenance_valid is True
    assert first.candidate.validation.case_valid is True
    assert (
        first.candidate.provenance["route"]["deterministic_interpretation"]["intent"]
        == "performance_diagnostic"
    )
    assert first.candidate.provenance["model_proposal"]["role"] == "proposal_only"
    assert first.candidate.provenance["model_proposal"]["authority"] is False
    assert first.candidate.proposed_case["status"] == "unresolved"
    assert first.candidate.proposed_case["confidence"] == "low"
    assert first.candidate.proposed_case["source"] == "system_generated"
    assert first.candidate.proposed_case["evidence"]["action_taken"].startswith(
        "Unknown"
    )
    assert first.candidate.proposed_case["evidence"]["outcome"].startswith("Unknown")
    assert validate_case_memory(first.candidate.proposed_case).valid is True
    assert file_snapshot(tmp_path) == before


def test_preview_marks_disabled_model_route_as_no_proposal(tmp_path: Path) -> None:
    """Catches a disabled no-model turn being represented as a model proposal."""
    source_turn = record_turn(tmp_path)

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.status == "ok"
    assert result.candidate is not None
    model_proposal = result.candidate.provenance["model_proposal"]
    assert model_proposal["present"] is False
    assert model_proposal["record"] is None
    assert model_proposal["role"] == "proposal_only"
    assert model_proposal["authority"] is False


def test_preview_retains_valid_model_route_as_proposal_only(tmp_path: Path) -> None:
    """Catches a valid model proposal losing its labelled no-authority provenance."""
    source_turn = record_turn(tmp_path, use_model=True)

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.status == "ok"
    assert result.candidate is not None
    assert result.candidate.validation.provenance_valid is True
    assert result.candidate.provenance["route"]["selected_source"] == "llm_contract"
    model_proposal = result.candidate.provenance["model_proposal"]
    assert model_proposal["present"] is True
    assert model_proposal["record"]["status"] == "ok"
    assert model_proposal["record"]["validation"]["valid"] is True
    assert model_proposal["role"] == "proposal_only"
    assert model_proposal["authority"] is False


def test_preview_retains_rejected_model_output_as_proposal_only(tmp_path: Path) -> None:
    """Catches rejected model material being discarded or granted authority."""
    source_turn = record_turn(tmp_path, model_callable=invalid_route_model)

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert source_turn["llm_route_result"]["status"] == "invalid"
    assert result.status == "ok"
    assert result.candidate is not None
    model_proposal = result.candidate.provenance["model_proposal"]
    assert model_proposal["present"] is True
    assert model_proposal["record"]["status"] == "invalid"
    assert model_proposal["record"]["validation"]["valid"] is False
    assert model_proposal["role"] == "proposal_only"
    assert model_proposal["authority"] is False


def test_preview_marks_failed_model_attempt_without_output_as_no_proposal(
    tmp_path: Path,
) -> None:
    """Catches a failed model attempt with no output being presented as a proposal."""
    source_turn = record_turn(tmp_path, model_callable=failing_route_model)

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert source_turn["llm_route_result"]["status"] == "error"
    assert source_turn["llm_route_result"]["raw_model_output"] is None
    assert result.status == "ok"
    assert result.candidate is not None
    model_proposal = result.candidate.provenance["model_proposal"]
    assert model_proposal["present"] is False
    assert model_proposal["record"] is None
    assert model_proposal["role"] == "proposal_only"
    assert model_proposal["authority"] is False


def test_preview_rejects_unknown_selected_route_source(tmp_path: Path) -> None:
    """Catches provenance that uses a source outside the turn-selection contract."""
    source_turn = record_turn(tmp_path)
    source_turn["selected_route_source"] = "unrecognized_source"
    write_turn_records(tmp_path, [source_turn])

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.status == "invalid"
    assert result.candidate is not None
    assert result.candidate.validation.provenance_valid is False
    assert any(
        "selected_route_source" in error and "recognized" in error
        for error in result.candidate.validation.errors
    )


def test_preview_rejects_none_source_with_selected_handoff(tmp_path: Path) -> None:
    """Catches a no-route source that still claims a selected handoff."""
    source_turn = record_turn(tmp_path)
    source_turn["selected_route_source"] = "none"
    write_turn_records(tmp_path, [source_turn])

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.status == "invalid"
    assert result.candidate is not None
    assert result.candidate.validation.provenance_valid is False
    assert any(
        "selected_route_source='none'" in error
        for error in result.candidate.validation.errors
    )


def test_preview_rejects_mismatched_deterministic_selected_handoff(
    tmp_path: Path,
) -> None:
    """Catches a selected deterministic handoff that differs from recorded evidence."""
    source_turn = record_turn(tmp_path)
    source_turn["selected_route_handoff"] = {}
    source_turn["autorun_gate"] = None
    write_turn_records(tmp_path, [source_turn])

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.status == "invalid"
    assert result.candidate is not None
    assert result.candidate.validation.provenance_valid is False
    assert any(
        "does not match deterministic" in error
        for error in result.candidate.validation.errors
    )


def test_preview_rejects_llm_contract_source_without_valid_handoff(
    tmp_path: Path,
) -> None:
    """Catches an LLM-selected handoff whose recorded contract evidence is invalid."""
    source_turn = record_turn(tmp_path, use_model=True)
    source_turn["llm_route_result"]["validation"]["valid"] = False
    write_turn_records(tmp_path, [source_turn])

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.status == "invalid"
    assert result.candidate is not None
    assert result.candidate.validation.provenance_valid is False
    assert any(
        "valid LLM contract" in error for error in result.candidate.validation.errors
    )


def test_preview_rejects_mismatched_llm_contract_selected_handoff(
    tmp_path: Path,
) -> None:
    """Catches a selected LLM handoff that differs from validated contract evidence."""
    source_turn = record_turn(tmp_path, use_model=True)
    source_turn["selected_route_handoff"] = {}
    source_turn["autorun_gate"] = None
    write_turn_records(tmp_path, [source_turn])

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.status == "invalid"
    assert result.candidate is not None
    assert result.candidate.validation.provenance_valid is False
    assert any(
        "does not match the valid LLM contract" in error
        for error in result.candidate.validation.errors
    )


def test_preview_rejects_autorun_gate_inconsistent_with_selected_handoff(
    tmp_path: Path,
) -> None:
    """Catches a recorded autorun decision that was not derived from its handoff."""
    source_turn = record_turn(tmp_path)
    source_turn["autorun_gate"]["allowed"] = False
    write_turn_records(tmp_path, [source_turn])

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.status == "invalid"
    assert result.candidate is not None
    assert result.candidate.validation.provenance_valid is False
    assert any(
        "autorun_gate does not match" in error
        for error in result.candidate.validation.errors
    )


def test_preview_accepts_consistent_deterministic_route_provenance(
    tmp_path: Path,
) -> None:
    """Catches valid deterministic evidence rejected by the consistency check."""
    source_turn = record_turn(tmp_path)

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.status == "ok"
    assert result.candidate is not None
    assert result.candidate.provenance["route"]["selected_source"] == "deterministic"
    assert result.candidate.validation.provenance_valid is True


def test_candidate_identity_changes_for_a_different_source_turn(tmp_path: Path) -> None:
    """Catches candidate identity that is not bound to its source turn."""
    first_turn = record_turn(tmp_path, user_request="why is my laptop slow")
    second_turn = record_turn(tmp_path, user_request="why is chrome eating memory")

    first = preview_case_memory_candidate(first_turn["turn_id"], memory_dir=tmp_path)
    second = preview_case_memory_candidate(second_turn["turn_id"], memory_dir=tmp_path)

    assert first.candidate is not None
    assert second.candidate is not None
    assert first.candidate.candidate_id != second.candidate.candidate_id


def test_candidate_contract_is_frozen_and_serializes_copies(tmp_path: Path) -> None:
    """Catches a mutable candidate identity or a serialization path that leaks internals."""
    source_turn = record_turn(tmp_path)
    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.candidate is not None

    with pytest.raises(FrozenInstanceError):
        result.candidate.candidate_id = "case_candidate_rewritten"

    serialized = result.candidate.to_dict()
    serialized["promotion"]["persisted"] = True

    assert result.candidate.promotion["persisted"] is False


def test_preview_joins_latest_feedback_and_reuses_turn_classification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a stale feedback join or a duplicated dataset-classification rule."""
    source_turn = record_turn(tmp_path)
    turn_id = source_turn["turn_id"]
    record_turn_feedback(
        turn_id=turn_id,
        label="useful",
        note="first judgment",
        memory_dir=tmp_path,
    )
    latest = record_turn_feedback(
        turn_id=turn_id,
        label="wrong_route",
        note="latest judgment",
        memory_dir=tmp_path,
    )

    import app.services.case_memory_candidate as candidate_service

    real_classify = candidate_service.classify_turn_training_use
    calls: list[tuple[str, str | None]] = []

    def classify_with_recorded_input(turn: dict, feedback: dict | None = None) -> dict:
        calls.append((turn.get("turn_id", ""), (feedback or {}).get("feedback_id")))
        return real_classify(turn, feedback=feedback)

    monkeypatch.setattr(
        candidate_service,
        "classify_turn_training_use",
        classify_with_recorded_input,
    )

    result = preview_case_memory_candidate(turn_id, memory_dir=tmp_path)

    assert result.candidate is not None
    assert result.candidate.provenance["operator_feedback"]["present"] is True
    assert (
        result.candidate.provenance["operator_feedback"]["record"]["feedback_id"]
        == (latest["data"]["feedback_id"])
    )
    assert result.candidate.provenance["operator_feedback"]["record"]["note"] == (
        "latest judgment"
    )
    assert result.candidate.provenance["dataset_classification"]["category"] == (
        CATEGORY_CORRECTION_NEEDED
    )
    assert calls == [(turn_id, latest["data"]["feedback_id"])]


def test_preview_marks_absent_feedback_as_unavailable(tmp_path: Path) -> None:
    """Catches fabricated Operator feedback when none was recorded."""
    source_turn = record_turn(tmp_path)

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.candidate is not None
    assert result.candidate.provenance["operator_feedback"] == {
        "present": False,
        "record": None,
    }
    assert result.candidate.proposed_case["process_trace"]["operator_feedback"] == ""


def test_preview_keeps_unobserved_facts_unknown_after_useful_feedback(
    tmp_path: Path,
) -> None:
    """Catches feedback or a suggested route being mistaken for a completed case."""
    source_turn = record_turn(tmp_path)
    record_turn_feedback(
        turn_id=source_turn["turn_id"],
        label="useful",
        note="Helpful route suggestion.",
        memory_dir=tmp_path,
    )

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.status == "ok"
    assert result.candidate is not None
    proposed_case = result.candidate.proposed_case
    evidence = proposed_case["evidence"]
    assert proposed_case["status"] == "unresolved"
    assert evidence["telemetry_evidence"]["availability"] == "not_observed"
    assert evidence["event_evidence"]["availability"] == "not_observed"
    assert evidence["action_taken"].startswith("Unknown")
    assert evidence["outcome"].startswith("Unknown")
    assert proposed_case["case_card"]["suspected_cause"].startswith("Unknown")


def test_preview_returns_not_found_for_a_missing_exact_turn(tmp_path: Path) -> None:
    """Catches a preview that silently substitutes the latest journal turn."""
    record_turn(tmp_path)

    result = preview_case_memory_candidate("turn-missing", memory_dir=tmp_path)

    assert result.status == "not_found"
    assert result.candidate is None
    assert "not found" in result.message.lower()


def test_preview_rejects_duplicate_turn_identity(tmp_path: Path) -> None:
    """Catches ambiguous provenance when a requested source identity is duplicated."""
    source_turn = record_turn(tmp_path)
    write_turn_records(tmp_path, [source_turn, source_turn])

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.status == "invalid"
    assert result.candidate is None
    assert any("multiple" in error.lower() for error in result.errors)


@pytest.mark.parametrize(
    "unsafe_flag", ["executed", "tool_execution", "model_authority", "os_mutation"]
)
def test_preview_marks_impossible_turn_safety_flags_invalid(
    tmp_path: Path,
    unsafe_flag: str,
) -> None:
    """Catches a candidate path that accepts a source contradicting preview safety."""
    source_turn = record_turn(tmp_path)
    source_turn["safety"][unsafe_flag] = True
    write_turn_records(tmp_path, [source_turn])

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.status == "invalid"
    assert result.candidate is not None
    assert result.candidate.validation.provenance_valid is False
    assert any(unsafe_flag in error for error in result.candidate.validation.errors)
    assert result.candidate.safety["tool_execution"] is False
    assert result.candidate.safety["memory_write"] is False


@pytest.mark.parametrize(
    "unsafe_flag",
    ["executed", "tool_execution", "model_authority", "os_mutation"],
)
def test_preview_rejects_contradictory_top_level_safety_flags(
    tmp_path: Path,
    unsafe_flag: str,
) -> None:
    """Catches malformed records that hide unsafe flags outside the envelope."""
    source_turn = record_turn(tmp_path)
    source_turn[unsafe_flag] = True
    write_turn_records(tmp_path, [source_turn])

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.status == "invalid"
    assert result.candidate is not None
    assert result.candidate.validation.provenance_valid is False
    assert any(unsafe_flag in error for error in result.candidate.validation.errors)


@pytest.mark.parametrize(
    "safety_flag",
    ["executed", "tool_execution", "model_authority", "os_mutation"],
)
def test_preview_rejects_malformed_top_level_safety_flags(
    tmp_path: Path,
    safety_flag: str,
) -> None:
    """Catches malformed top-level safety values that could hide contradictory data."""
    source_turn = record_turn(tmp_path)
    source_turn[safety_flag] = "false"
    write_turn_records(tmp_path, [source_turn])

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.status == "invalid"
    assert result.candidate is not None
    assert result.candidate.validation.provenance_valid is False
    assert any(safety_flag in error for error in result.candidate.validation.errors)


def test_preview_handles_a_malformed_source_without_writing(tmp_path: Path) -> None:
    """Catches malformed source records that otherwise crash or produce a false preview."""
    malformed = {
        "turn_id": "turn-malformed",
        "created_at": "2026-08-13T08:00:00+00:00",
        "safety": {
            "preview_only": True,
            "executed": False,
            "tool_execution": False,
            "model_authority": False,
            "os_mutation": False,
        },
    }
    write_turn_records(tmp_path, [malformed])
    before = file_snapshot(tmp_path)

    result = preview_case_memory_candidate("turn-malformed", memory_dir=tmp_path)

    assert result.status == "invalid"
    assert result.candidate is not None
    assert result.candidate.validation.provenance_valid is False
    assert result.candidate.validation.errors
    assert file_snapshot(tmp_path) == before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("llm_route_result", "not-a-proposal-record"),
        ("selected_route_source", ""),
    ],
)
def test_preview_rejects_malformed_required_provenance_fields(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    """Catches malformed evidence being silently treated as unavailable."""
    source_turn = record_turn(tmp_path)
    source_turn[field] = value
    write_turn_records(tmp_path, [source_turn])

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.status == "invalid"
    assert result.candidate is not None
    assert result.candidate.validation.provenance_valid is False
    assert any(field in error for error in result.candidate.validation.errors)


def test_preview_surfaces_invalid_proposed_case_validation(tmp_path: Path) -> None:
    """Catches a preview that masks an invalid structured case as valid."""
    source_turn = record_turn(tmp_path)
    source_turn["normalized_input"] = ""
    source_turn["original_input"] = ""
    write_turn_records(tmp_path, [source_turn])

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.status == "invalid"
    assert result.candidate is not None
    assert result.candidate.validation.case_valid is False
    assert any(
        "case_card.problem" in error for error in result.candidate.validation.errors
    )


def test_preview_does_not_call_model_executor_or_memory_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a C01 preview that crosses a model, executor, or curated-write boundary."""
    source_turn = record_turn(tmp_path)

    from app.services import (
        llm_route_engine,
        memory_manager,
        memory_store,
        tool_executor,
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("C01 preview crossed a forbidden side-effect boundary")

    monkeypatch.setattr(llm_route_engine, "build_llm_route_call", fail_if_called)
    monkeypatch.setattr(memory_manager, "save_case_memory", fail_if_called)
    monkeypatch.setattr(memory_store, "append_case_memory", fail_if_called)
    monkeypatch.setattr(tool_executor, "execute_tool_plan", fail_if_called)
    monkeypatch.setattr(Path, "mkdir", fail_if_called)
    monkeypatch.setattr(Path, "write_text", fail_if_called)
    monkeypatch.setattr(Path, "write_bytes", fail_if_called)
    monkeypatch.setattr(Path, "unlink", fail_if_called)
    monkeypatch.setattr(Path, "rename", fail_if_called)

    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    assert result.status == "ok"
    assert result.candidate is not None


def test_preview_report_states_preview_only_and_no_side_effects(tmp_path: Path) -> None:
    """Catches an Operator report that omits the no-write/no-execution boundary."""
    source_turn = record_turn(tmp_path, use_model=True)
    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)

    report = format_case_memory_candidate_preview_report(result)

    assert "LIGHTHOUSE CASE CANDIDATE PREVIEW" in report
    assert "Mode: preview_only" in report
    assert "Persistence: disabled" in report
    assert "Operator approval required: yes" in report
    assert f"Source turn: {source_turn['turn_id']}" in report
    assert "Selected route source: llm_contract" in report
    assert "Deterministic route source:" not in report
    assert "Provenance validation: valid" in report
    assert "Case validation: valid" in report
    assert "No case memory was written." in report
    assert "No tool was executed." in report
    assert "No model was called." in report
