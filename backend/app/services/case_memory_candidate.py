"""
Read-only case-memory candidate previews from conversational-turn evidence.

This module creates an Operator-visible promotion preview between the append-only
operational ``memory/`` journals and curated ``data/memory/`` case memory. It
does not call a model, execute tools, mutate the operating system, or write
curated memory.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.conversation_turn_dataset_export import classify_turn_training_use
from app.services.conversation_turn_feedback import latest_feedback_by_turn_id
from app.services.conversational_engine_turn import (
    conversational_turn_journal_path,
    read_jsonl,
)
from app.services.memory_cases import (
    CASE_CONFIDENCE_LOW,
    CASE_SOURCE_SYSTEM_GENERATED,
    CASE_STATUS_UNRESOLVED,
    MEMORY_RESULT_NOT_USED,
    JsonDict,
    build_memory_usage_trace,
    validate_case_memory,
)
from app.services.memory_manager import build_case_memory
from app.services.operator_routes import validate_route_handoff_for_autorun

CASE_MEMORY_CANDIDATE_SCHEMA_VERSION = "case_memory_candidate_v1_5"
CASE_MEMORY_CANDIDATE_FINGERPRINT_VERSION = "case_candidate_fingerprint_v1"
CASE_MEMORY_CANDIDATE_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")

CASE_MEMORY_CANDIDATE_STATUS_OK = "ok"
CASE_MEMORY_CANDIDATE_STATUS_NOT_FOUND = "not_found"
CASE_MEMORY_CANDIDATE_STATUS_INVALID = "invalid"
CASE_MEMORY_CANDIDATE_STATUS_ERROR = "error"

REPORT_WIDTH = 60
SELECTED_ROUTE_SOURCES = frozenset({"deterministic", "llm_contract", "none"})
MODEL_PROPOSAL_STATUSES = frozenset({"ok", "invalid"})


@dataclass(frozen=True)
class CaseMemoryCandidateValidation:
    """
    Independent validation results for candidate provenance and case structure.
    """

    provenance_valid: bool
    case_valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> JsonDict:
        """Return a stable serializable validation payload."""
        return {
            "provenance_valid": self.provenance_valid,
            "case_valid": self.case_valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class CaseMemoryCandidate:
    """
    Immutable, preview-only C01 case-memory candidate contract.
    """

    schema_version: str
    candidate_id: str
    source_turn_id: str
    source_turn_created_at: str
    provenance: JsonDict
    proposed_case: JsonDict
    validation: CaseMemoryCandidateValidation
    promotion: JsonDict
    safety: JsonDict

    def to_dict(self) -> JsonDict:
        """Return a stable serializable candidate payload."""
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "source_turn_id": self.source_turn_id,
            "source_turn_created_at": self.source_turn_created_at,
            "provenance": deepcopy(self.provenance),
            "proposed_case": deepcopy(self.proposed_case),
            "validation": self.validation.to_dict(),
            "promotion": deepcopy(self.promotion),
            "safety": deepcopy(self.safety),
        }


@dataclass(frozen=True)
class CaseMemoryCandidatePreviewResult:
    """
    Stable result for one read-only candidate-preview request.
    """

    status: str
    message: str
    requested_turn_id: str
    candidate: CaseMemoryCandidate | None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> JsonDict:
        """Return a stable serializable preview result."""
        return {
            "status": self.status,
            "message": self.message,
            "requested_turn_id": self.requested_turn_id,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def build_case_memory_candidate_id(source_turn_id: str) -> str:
    """
    Derive a deterministic candidate identity from the C01 schema and turn id.
    """
    stable_source = f"{CASE_MEMORY_CANDIDATE_SCHEMA_VERSION}:{source_turn_id.strip()}"
    digest = hashlib.sha256(stable_source.encode("utf-8")).hexdigest()[:20]
    return f"case_candidate_{digest}"



def build_case_memory_candidate_fingerprint(
    candidate: CaseMemoryCandidate,
) -> str:
    """
    Return the deterministic SHA-256 identity of promotion-relevant candidate state.

    The fingerprint binds Operator approval to evidence provenance plus the exact
    proposed curated case. Derived validation, preview promotion flags, and
    preview safety flags are deliberately excluded.
    """
    payload = {
        "fingerprint_version": CASE_MEMORY_CANDIDATE_FINGERPRINT_VERSION,
        "candidate_schema_version": candidate.schema_version,
        "candidate_id": candidate.candidate_id,
        "source_turn_id": candidate.source_turn_id,
        "provenance": deepcopy(candidate.provenance),
        "proposed_case": deepcopy(candidate.proposed_case),
    }
    canonical_payload = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def normalize_case_memory_candidate_fingerprint(
    value: str,
) -> str | None:
    """
    Normalize one explicit Operator-supplied candidate fingerprint.

    Only a complete 64-character hexadecimal SHA-256 digest is accepted.
    """
    if not isinstance(value, str):
        return None

    cleaned = value.strip()

    if CASE_MEMORY_CANDIDATE_FINGERPRINT_PATTERN.fullmatch(cleaned) is None:
        return None

    return cleaned.lower()


def preview_case_memory_candidate(
    turn_id: str,
    *,
    memory_dir: str | Path | None = None,
) -> CaseMemoryCandidatePreviewResult:
    """
    Build a preview-only candidate for one exact conversational turn id.

    The function reads operational journals only. It never substitutes the
    latest turn, calls a model, invokes a tool executor, or writes curated case
    memory.
    """
    requested_turn_id = turn_id.strip() if isinstance(turn_id, str) else ""

    if not requested_turn_id:
        return CaseMemoryCandidatePreviewResult(
            status=CASE_MEMORY_CANDIDATE_STATUS_INVALID,
            message="A conversational turn id is required for case preview.",
            requested_turn_id=requested_turn_id,
            candidate=None,
            errors=("turn_id must be a non-empty string.",),
        )

    try:
        turns = read_jsonl(conversational_turn_journal_path(memory_dir))
    except OSError as error:
        return CaseMemoryCandidatePreviewResult(
            status=CASE_MEMORY_CANDIDATE_STATUS_ERROR,
            message="Conversational turn journal could not be read.",
            requested_turn_id=requested_turn_id,
            candidate=None,
            errors=(str(error),),
        )

    matches = [
        turn
        for turn in turns
        if isinstance(turn.get("turn_id"), str)
        and turn.get("turn_id") == requested_turn_id
    ]

    if not matches:
        return CaseMemoryCandidatePreviewResult(
            status=CASE_MEMORY_CANDIDATE_STATUS_NOT_FOUND,
            message="Requested conversational turn was not found.",
            requested_turn_id=requested_turn_id,
            candidate=None,
            errors=(f"No conversational turn exists for id: {requested_turn_id}",),
        )

    if len(matches) != 1:
        return CaseMemoryCandidatePreviewResult(
            status=CASE_MEMORY_CANDIDATE_STATUS_INVALID,
            message="Requested conversational turn has conflicting source records.",
            requested_turn_id=requested_turn_id,
            candidate=None,
            errors=(
                (
                    "Requested conversational turn id appears multiple times in the "
                    "operational journal."
                ),
            ),
        )

    source_turn = deepcopy(matches[0])
    provenance_errors, provenance_warnings = validate_turn_provenance(
        source_turn,
        requested_turn_id=requested_turn_id,
    )
    feedback, feedback_error = read_latest_turn_feedback(
        requested_turn_id,
        memory_dir=memory_dir,
    )

    if feedback_error:
        provenance_errors.append(feedback_error)

    classification = classify_turn_training_use(source_turn, feedback=feedback)
    provenance = build_candidate_provenance(
        source_turn,
        feedback=feedback,
        classification=classification,
    )
    candidate_id = build_case_memory_candidate_id(requested_turn_id)

    if provenance_errors:
        proposed_case: JsonDict = {}
        case_validation = validate_case_memory(proposed_case)
    else:
        proposed_case = build_proposed_case_memory(
            source_turn,
            candidate_id=candidate_id,
            feedback=feedback,
            classification=classification,
        )
        case_validation = validate_case_memory(proposed_case)

    validation_errors = tuple(provenance_errors) + case_validation.errors
    validation_warnings = tuple(provenance_warnings) + case_validation.warnings
    validation = CaseMemoryCandidateValidation(
        provenance_valid=not provenance_errors,
        case_valid=case_validation.valid,
        errors=validation_errors,
        warnings=validation_warnings,
    )
    candidate = CaseMemoryCandidate(
        schema_version=CASE_MEMORY_CANDIDATE_SCHEMA_VERSION,
        candidate_id=candidate_id,
        source_turn_id=requested_turn_id,
        source_turn_created_at=string_value(source_turn.get("created_at")),
        provenance=provenance,
        proposed_case=proposed_case,
        validation=validation,
        promotion=build_preview_promotion(),
        safety=build_preview_safety(),
    )

    if validation.provenance_valid and validation.case_valid:
        return CaseMemoryCandidatePreviewResult(
            status=CASE_MEMORY_CANDIDATE_STATUS_OK,
            message="Case memory candidate preview is ready for Operator review.",
            requested_turn_id=requested_turn_id,
            candidate=candidate,
            warnings=validation.warnings,
        )

    return CaseMemoryCandidatePreviewResult(
        status=CASE_MEMORY_CANDIDATE_STATUS_INVALID,
        message="Case memory candidate preview is invalid and was not persisted.",
        requested_turn_id=requested_turn_id,
        candidate=candidate,
        errors=validation.errors,
        warnings=validation.warnings,
    )


def validate_turn_provenance(
    source_turn: JsonDict,
    *,
    requested_turn_id: str,
) -> tuple[list[str], list[str]]:
    """Validate the evidence required to make a safe C01 preview."""
    errors: list[str] = []
    warnings: list[str] = []

    if source_turn.get("turn_id") != requested_turn_id:
        errors.append("Source turn id does not match the requested turn id.")

    if not string_value(source_turn.get("created_at")):
        errors.append("Source turn created_at must be a non-empty string.")

    if source_turn.get("mode") != "conversation_turn_preview":
        errors.append("Source turn mode must be conversation_turn_preview.")

    deterministic_result = source_turn.get("deterministic_result")
    llm_route_result = source_turn.get("llm_route_result")
    selected_route_handoff = source_turn.get("selected_route_handoff")
    selected_route_source = string_value(source_turn.get("selected_route_source"))
    autorun_gate = source_turn.get("autorun_gate")

    if not isinstance(deterministic_result, dict):
        errors.append("Source turn deterministic_result must be a dictionary.")

    if not isinstance(llm_route_result, dict):
        errors.append("Source turn llm_route_result must be a dictionary.")

    if not isinstance(selected_route_handoff, dict):
        errors.append("Source turn selected_route_handoff must be a dictionary.")

    if not selected_route_source:
        errors.append("Source turn selected_route_source must be a non-empty string.")
    elif selected_route_source not in SELECTED_ROUTE_SOURCES:
        errors.append(
            "Source turn selected_route_source is not a recognized "
            "conversational-turn source."
        )

    if autorun_gate is not None and not isinstance(autorun_gate, dict):
        errors.append("Source turn autorun_gate must be a dictionary or null.")

    if isinstance(selected_route_handoff, dict):
        if selected_route_source == "deterministic":
            deterministic_handoff = (
                deterministic_result.get("route_handoff")
                if isinstance(deterministic_result, dict)
                else None
            )

            if not isinstance(deterministic_handoff, dict):
                errors.append(
                    "Source turn deterministic_result.route_handoff must be a "
                    "dictionary "
                    "when selected_route_source='deterministic'."
                )
            elif selected_route_handoff != deterministic_handoff:
                errors.append(
                    "Source turn selected_route_handoff does not match "
                    "deterministic_result.route_handoff."
                )

        elif selected_route_source == "llm_contract":
            llm_validation = (
                llm_route_result.get("validation")
                if isinstance(llm_route_result, dict)
                else None
            )

            if (
                not isinstance(llm_validation, dict)
                or llm_validation.get("valid") is not True
            ):
                errors.append(
                    "Source turn selected_route_source='llm_contract' requires a valid "
                    "LLM contract validation."
                )
            else:
                llm_contract_handoff = llm_validation.get("route_handoff")

                if (
                    not isinstance(llm_contract_handoff, dict)
                    or not llm_contract_handoff
                ):
                    errors.append(
                        "Source turn valid LLM contract validation must include a "
                        "non-empty route_handoff."
                    )
                elif selected_route_handoff != llm_contract_handoff:
                    errors.append(
                        "Source turn selected_route_handoff does not match the valid "
                        "LLM contract route_handoff."
                    )

        elif selected_route_source == "none" and selected_route_handoff:
            errors.append(
                "Source turn selected_route_source='none' must not include a "
                "selected_route_handoff."
            )

        if isinstance(autorun_gate, dict):
            expected_autorun_gate = validate_route_handoff_for_autorun(
                selected_route_handoff
            ).to_dict()

            if autorun_gate != expected_autorun_gate:
                errors.append(
                    "Source turn autorun_gate does not match deterministic validation "
                    "of selected_route_handoff."
                )

    safety = source_turn.get("safety")

    if not isinstance(safety, dict):
        errors.append("Source turn safety envelope must be a dictionary.")
    else:
        if safety.get("preview_only") is not True:
            errors.append("Source turn safety.preview_only must be true.")

        for flag in ("executed", "tool_execution", "model_authority", "os_mutation"):
            if safety.get(flag) is not False:
                errors.append(
                    f"Source turn safety.{flag} must be false for C01 preview."
                )

        if safety.get("talkrun_integration") is True:
            errors.append(
                "Source turn safety.talkrun_integration must be false for C01 preview."
            )

    for flag in ("executed", "tool_execution", "model_authority", "os_mutation"):
        if flag in source_turn and source_turn.get(flag) is not False:
            errors.append(f"Source turn {flag} must be false for C01 preview.")

    if not string_value(source_turn.get("original_input")):
        warnings.append("Source turn original_input is unavailable.")

    if not string_value(source_turn.get("normalized_input")):
        warnings.append("Source turn normalized_input is unavailable.")

    return errors, warnings


def read_latest_turn_feedback(
    turn_id: str,
    *,
    memory_dir: str | Path | None = None,
) -> tuple[JsonDict | None, str | None]:
    """Read the latest append-only Operator feedback record for one turn."""
    try:
        feedback_by_turn = latest_feedback_by_turn_id(memory_dir=memory_dir)
    except OSError as error:
        return None, f"Operator feedback journal could not be read: {error}"

    feedback = feedback_by_turn.get(turn_id)

    if feedback is None:
        return None, None

    if not isinstance(feedback, dict):
        return None, "Latest Operator feedback record must be a dictionary."

    return deepcopy(feedback), None


def build_candidate_provenance(
    source_turn: JsonDict,
    *,
    feedback: JsonDict | None,
    classification: JsonDict,
) -> JsonDict:
    """Build auditable provenance with deterministic, Operator, and model roles."""
    deterministic_result = dictionary_value(source_turn.get("deterministic_result"))
    llm_route_result = dictionary_value(source_turn.get("llm_route_result"))
    model_proposal_present = has_model_proposal_evidence(llm_route_result)

    return {
        "turn_journal": {
            "schema_version": source_turn.get("schema_version"),
            "turn_id": source_turn.get("turn_id"),
            "created_at": source_turn.get("created_at"),
            "mode": source_turn.get("mode"),
            "original_input": source_turn.get("original_input"),
            "normalized_input": source_turn.get("normalized_input"),
        },
        "operator_feedback": {
            "present": feedback is not None,
            "record": deepcopy(feedback) if feedback is not None else None,
        },
        "route": {
            "deterministic_interpretation": deepcopy(deterministic_result),
            "deterministic_handoff": deepcopy(
                dictionary_value(deterministic_result.get("route_handoff"))
            ),
            "selected_source": source_turn.get("selected_route_source"),
            "selected_handoff": deepcopy(
                dictionary_value(source_turn.get("selected_route_handoff"))
            ),
        },
        "autorun_gate": deepcopy(dictionary_value(source_turn.get("autorun_gate"))),
        "turn_safety_envelope": deepcopy(dictionary_value(source_turn.get("safety"))),
        "dataset_classification": deepcopy(classification),
        "model_proposal": {
            "present": model_proposal_present,
            "role": "proposal_only",
            "authority": False,
            "record": deepcopy(llm_route_result) if model_proposal_present else None,
        },
    }


def has_model_proposal_evidence(llm_route_result: JsonDict) -> bool:
    """Return whether a turn contains a model proposal rather than an LLM call record."""
    return (
        llm_route_result.get("used_model") is True
        and string_value(llm_route_result.get("status")) in MODEL_PROPOSAL_STATUSES
        and llm_route_result.get("raw_model_output") is not None
        and isinstance(llm_route_result.get("validation"), dict)
    )


def build_proposed_case_memory(
    source_turn: JsonDict,
    *,
    candidate_id: str,
    feedback: JsonDict | None,
    classification: JsonDict,
) -> JsonDict:
    """Build a conservative structured case without inventing observed facts."""
    normalized_input = string_value(source_turn.get("normalized_input"))
    deterministic_result = dictionary_value(source_turn.get("deterministic_result"))
    selected_source = string_value(source_turn.get("selected_route_source"))
    intent = string_value(deterministic_result.get("intent"))
    category = string_value(classification.get("category"))
    feedback_text = format_operator_feedback(feedback)

    tags = ["conversation_turn"]

    if intent:
        tags.append(intent)

    diagnostic_steps = [
        "Read the source conversational turn journal record.",
        "Preserved the deterministic route interpretation as provenance.",
        "Recomputed conversational-turn dataset classification from current journals.",
    ]
    decision_notes = [
        f"Selected route source recorded as: {selected_source or 'unavailable'}.",
        f"Dataset classification recorded as: {category or 'unavailable'}.",
        "Model material is retained only as labelled proposal provenance.",
        "No action, outcome, resolution, or causal certainty is inferred from preview evidence.",
    ]

    return build_case_memory(
        case_id=f"case_preview_{candidate_id}",
        problem=normalized_input,
        symptoms=[f"Operator request: {normalized_input}"] if normalized_input else [],
        suspected_cause="Unknown; no causal evidence is recorded in the source turn.",
        lesson="Operator review is required before any curated-memory promotion.",
        tags=tags,
        telemetry_evidence={
            "availability": "not_observed",
            "source": "conversational_turn_journal",
            "source_turn_id": source_turn.get("turn_id"),
        },
        event_evidence={
            "availability": "not_observed",
            "source": "conversational_turn_journal",
            "source_turn_id": source_turn.get("turn_id"),
        },
        action_taken="Unknown; no observed action is recorded in the source turn.",
        outcome="Unknown; no observed outcome is recorded in the source turn.",
        diagnostic_steps=diagnostic_steps,
        decision_notes=decision_notes,
        operator_feedback=feedback_text,
        status=CASE_STATUS_UNRESOLVED,
        confidence=CASE_CONFIDENCE_LOW,
        source=CASE_SOURCE_SYSTEM_GENERATED,
        created_at=string_value(source_turn.get("created_at")),
        updated_at=string_value(source_turn.get("created_at")),
        memory_usage_trace=build_memory_usage_trace(
            memory_context_used=False,
            memory_result=MEMORY_RESULT_NOT_USED,
            memory_notes=["No curated memory was read or written by C01 preview."],
        ),
    )


def build_preview_promotion() -> JsonDict:
    """Return the fixed no-persistence promotion envelope."""
    return {
        "preview_only": True,
        "persisted": False,
        "operator_approval_required": True,
    }


def build_preview_safety() -> JsonDict:
    """Return the fixed no-side-effect C01 safety envelope."""
    return {
        "model_authority": False,
        "tool_execution": False,
        "os_mutation": False,
        "memory_write": False,
    }


def format_operator_feedback(feedback: JsonDict | None) -> str:
    """Format existing feedback without inferring a resolution or outcome."""
    if not feedback:
        return ""

    label = string_value(feedback.get("label"))
    note = string_value(feedback.get("note"))

    if label and note:
        return f"{label}: {note}"

    return label or note


def format_case_memory_candidate_preview_report(
    result: CaseMemoryCandidatePreviewResult,
) -> str:
    """Format an Operator-readable C01 preview report."""
    candidate = result.candidate
    candidate_fingerprint = (
        build_case_memory_candidate_fingerprint(candidate)
        if candidate is not None
        else "unavailable"
    )
    lines = [
        "LIGHTHOUSE CASE CANDIDATE PREVIEW",
        "=" * REPORT_WIDTH,
        "Mode: preview_only",
        "Persistence: disabled",
        "Operator approval required: yes",
        "",
        f"Status: {result.status}",
        f"Message: {result.message}",
        f"Source turn: {candidate.source_turn_id if candidate else result.requested_turn_id}",
        f"Candidate ID: {candidate.candidate_id if candidate else 'unavailable'}",
        f"Candidate fingerprint: {candidate_fingerprint}",
        "",
        "Provenance:",
    ]

    if candidate is None:
        lines.append("- No source candidate could be built.")
        lines.append("Provenance validation: invalid")
        lines.append("")
        lines.append("Proposed case:")
        lines.append("- unavailable")
        lines.append("Case validation: invalid")
    else:
        provenance = candidate.provenance
        feedback = dictionary_value(provenance.get("operator_feedback"))
        route = dictionary_value(provenance.get("route"))
        classification = dictionary_value(provenance.get("dataset_classification"))
        model_proposal = dictionary_value(provenance.get("model_proposal"))
        proposed_case = candidate.proposed_case
        case_card = dictionary_value(proposed_case.get("case_card"))
        evidence = dictionary_value(proposed_case.get("evidence"))

        lines.extend(
            [
                f"- Selected route source: {route.get('selected_source', 'unavailable')}",
                f"- Operator feedback: {'present' if feedback.get('present') else 'unavailable'}",
                f"- Dataset classification: {classification.get('category', 'unavailable')}",
                (
                    "- Model proposal: "
                    f"{'present' if model_proposal.get('present') else 'unavailable'} "
                    "(proposal only; no authority)"
                ),
                (
                    "Provenance validation: "
                    f"{'valid' if candidate.validation.provenance_valid else 'invalid'}"
                ),
                "",
                "Proposed case:",
                f"- Status: {proposed_case.get('status', 'unavailable')}",
                f"- Confidence: {proposed_case.get('confidence', 'unavailable')}",
                f"- Source: {proposed_case.get('source', 'unavailable')}",
                f"- Problem: {case_card.get('problem', 'unavailable')}",
                f"- Action taken: {evidence.get('action_taken', 'unavailable')}",
                f"- Outcome: {evidence.get('outcome', 'unavailable')}",
                (
                    "Case validation: "
                    f"{'valid' if candidate.validation.case_valid else 'invalid'}"
                ),
            ]
        )

    if (
        candidate is not None
        and result.status == CASE_MEMORY_CANDIDATE_STATUS_OK
        and candidate.validation.provenance_valid
        and candidate.validation.case_valid
    ):
        lines.extend(
            [
                "",
                "To approve this exact candidate:",
                (
                    f"case approve {candidate.source_turn_id} "
                    f"{candidate_fingerprint}"
                ),
            ]
        )

    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)

    if result.errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"- {error}" for error in result.errors)

    lines.extend(
        [
            "",
            "Safety:",
            "- model authority: no",
            "- tool execution: no",
            "- OS mutation: no",
            "- memory write: no",
            "",
            "No case memory was written.",
            "No tool was executed.",
            "No model was called.",
            "=" * REPORT_WIDTH,
        ]
    )
    return "\n".join(lines)


def dictionary_value(value: Any) -> JsonDict:
    """Return a shallow dictionary copy or an empty dictionary."""
    return dict(value) if isinstance(value, dict) else {}


def string_value(value: Any) -> str:
    """Return a stripped string or an empty string without coercing unknown data."""
    return value.strip() if isinstance(value, str) else ""
