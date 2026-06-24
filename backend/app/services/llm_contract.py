"""
LLM Contract V0 for Lighthouse.

This module defines and validates the only structured shape a model may return
when proposing a Lighthouse route.

The contract is intentionally narrow:
- the model may propose an intent
- the model may provide an interpreted request
- the deterministic route registry builds the handoff
- the model may not execute tools
- the model may not authorize actions
- the model may not provide shell commands, tool calls, or approval flags

This module does not call the model.
This module does not execute tools.
This module does not mutate the operating system.
This module does not write memory.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from app.services.operator_routes import (
    COMMAND_FAMILY_DIRECT_CLI,
    COMMAND_FAMILY_NONE,
    COMMAND_FAMILY_RUNPLAN,
    COMMAND_FAMILY_RUNPLAN_PREVIEW_ONLY,
    INTENT_DIRECT_COMMAND,
    INTENT_UNKNOWN,
    build_route_handoff,
    build_route_metadata,
    is_known_operator_intent,
)


LLM_CONTRACT_SCHEMA_VERSION = "llm_contract_v0"

LLM_CONTRACT_STATUS_OK = "ok"
LLM_CONTRACT_STATUS_INVALID = "invalid"

MIN_AUTOMATION_CONFIDENCE = 0.55
MAX_INTERPRETED_REQUEST_LENGTH = 300
MAX_REASONING_SUMMARY_LENGTH = 500
MAX_SAFETY_NOTE_LENGTH = 300

ALLOWED_LLM_CONTRACT_FIELDS = frozenset(
    {
        "schema_version",
        "proposed_intent",
        "interpreted_request",
        "confidence",
        "reasoning_summary",
        "safety_notes",
    }
)

FORBIDDEN_LLM_CONTRACT_FIELDS = frozenset(
    {
        "command",
        "recommended_command",
        "shell_command",
        "powershell",
        "cmd",
        "tool",
        "tool_name",
        "tool_args",
        "tool_arguments",
        "execute",
        "execution",
        "approved",
        "approval",
        "autorun",
        "autorun_allowed",
        "manual_review_required",
        "permission_granted",
        "mutate_os",
        "write_file",
        "delete_file",
        "registry_change",
    }
)


@dataclass(frozen=True)
class LLMContractValidationResult:
    """
    Stable result returned by LLM Contract V0 validation.
    """

    status: str
    valid: bool
    message: str
    normalized_proposal: dict[str, Any]
    route_handoff: dict[str, Any]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable validation result.
        """
        return {
            "status": self.status,
            "valid": self.valid,
            "message": self.message,
            "normalized_proposal": self.normalized_proposal,
            "route_handoff": self.route_handoff,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def invalid_result(
    *,
    message: str,
    errors: list[str],
    normalized_proposal: dict[str, Any] | None = None,
    route_handoff: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> LLMContractValidationResult:
    """
    Build a stable invalid validation result.
    """
    return LLMContractValidationResult(
        status=LLM_CONTRACT_STATUS_INVALID,
        valid=False,
        message=message,
        normalized_proposal=normalized_proposal or {},
        route_handoff=route_handoff or {},
        errors=tuple(errors),
        warnings=tuple(warnings or []),
    )


def parse_llm_contract_payload(payload: dict[str, Any] | str) -> tuple[dict[str, Any] | None, list[str]]:
    """
    Parse an LLM contract payload from a dict or JSON object string.
    """
    if isinstance(payload, dict):
        return dict(payload), []

    if not isinstance(payload, str):
        return None, ["LLM contract payload must be a dictionary or JSON object string."]

    cleaned_payload = payload.strip()

    if not cleaned_payload:
        return None, ["LLM contract payload is empty."]

    try:
        decoded = json.loads(cleaned_payload)
    except json.JSONDecodeError as error:
        return None, [f"LLM contract payload is not valid JSON: {error}"]

    if not isinstance(decoded, dict):
        return None, ["LLM contract JSON must decode to an object."]

    return decoded, []


def clean_text(value: Any) -> str:
    """
    Normalize a text value.
    """
    if not isinstance(value, str):
        return ""

    return value.strip()


def normalize_confidence(value: Any) -> tuple[float | None, str | None]:
    """
    Normalize confidence into a bounded float.
    """
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None, "confidence must be a number from 0.0 to 1.0."

    if confidence < 0.0 or confidence > 1.0:
        return None, "confidence must be between 0.0 and 1.0."

    return confidence, None


def normalize_safety_notes(value: Any) -> tuple[list[str], list[str]]:
    """
    Normalize optional safety notes.
    """
    if value is None:
        return [], []

    if not isinstance(value, list):
        return [], ["safety_notes must be a list of strings when provided."]

    notes: list[str] = []
    errors: list[str] = []

    for index, note in enumerate(value):
        if not isinstance(note, str):
            errors.append(f"safety_notes[{index}] must be a string.")
            continue

        cleaned_note = note.strip()

        if not cleaned_note:
            continue

        if len(cleaned_note) > MAX_SAFETY_NOTE_LENGTH:
            errors.append(
                f"safety_notes[{index}] must be {MAX_SAFETY_NOTE_LENGTH} characters or fewer."
            )
            continue

        notes.append(cleaned_note)

    return notes, errors


def forbidden_fields_in(proposal: dict[str, Any]) -> list[str]:
    """
    Return forbidden fields present in a model proposal.
    """
    return sorted(set(proposal) & FORBIDDEN_LLM_CONTRACT_FIELDS)


def unknown_fields_in(proposal: dict[str, Any]) -> list[str]:
    """
    Return fields outside the strict LLM Contract V0 schema.
    """
    return sorted(set(proposal) - ALLOWED_LLM_CONTRACT_FIELDS)


def build_recommended_command(
    *,
    intent: str,
    interpreted_request: str | None,
) -> str | None:
    """
    Build the display command from deterministic route metadata.
    """
    route_metadata = build_route_metadata(intent)
    command_family = route_metadata.get("command_family")

    if command_family in {
        COMMAND_FAMILY_RUNPLAN,
        COMMAND_FAMILY_RUNPLAN_PREVIEW_ONLY,
    }:
        if not interpreted_request:
            return None

        return f"runplan {interpreted_request}".strip()

    return None


def validate_llm_route_proposal(
    payload: dict[str, Any] | str,
) -> LLMContractValidationResult:
    """
    Validate an LLM-proposed Lighthouse route against LLM Contract V0.
    """
    proposal, parse_errors = parse_llm_contract_payload(payload)

    if proposal is None:
        return invalid_result(
            message="LLM contract payload could not be parsed.",
            errors=parse_errors,
        )

    errors: list[str] = []
    warnings: list[str] = []

    forbidden_fields = forbidden_fields_in(proposal)

    if forbidden_fields:
        errors.append(
            "LLM contract payload contains forbidden authority field(s): "
            + ", ".join(forbidden_fields)
        )

    unknown_fields = unknown_fields_in(proposal)

    if unknown_fields:
        errors.append(
            "LLM contract payload contains unknown field(s): "
            + ", ".join(unknown_fields)
        )

    schema_version = clean_text(proposal.get("schema_version"))

    if schema_version != LLM_CONTRACT_SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {LLM_CONTRACT_SCHEMA_VERSION!r}."
        )

    proposed_intent = clean_text(proposal.get("proposed_intent"))

    if not proposed_intent:
        errors.append("proposed_intent is required.")
    elif not is_known_operator_intent(proposed_intent):
        errors.append(f"Unknown proposed_intent: {proposed_intent}")
    elif proposed_intent == INTENT_DIRECT_COMMAND:
        errors.append("LLM contract may not propose direct CLI commands.")

    confidence, confidence_error = normalize_confidence(proposal.get("confidence"))

    if confidence_error:
        errors.append(confidence_error)

    interpreted_request = clean_text(proposal.get("interpreted_request"))

    if len(interpreted_request) > MAX_INTERPRETED_REQUEST_LENGTH:
        errors.append(
            f"interpreted_request must be {MAX_INTERPRETED_REQUEST_LENGTH} characters or fewer."
        )

    reasoning_summary = clean_text(proposal.get("reasoning_summary"))

    if len(reasoning_summary) > MAX_REASONING_SUMMARY_LENGTH:
        errors.append(
            f"reasoning_summary must be {MAX_REASONING_SUMMARY_LENGTH} characters or fewer."
        )

    safety_notes, safety_note_errors = normalize_safety_notes(
        proposal.get("safety_notes")
    )
    errors.extend(safety_note_errors)

    route_metadata = (
        build_route_metadata(proposed_intent)
        if proposed_intent and is_known_operator_intent(proposed_intent)
        else {}
    )
    command_family = route_metadata.get("command_family")

    requires_interpreted_request = command_family in {
        COMMAND_FAMILY_RUNPLAN,
        COMMAND_FAMILY_RUNPLAN_PREVIEW_ONLY,
    }

    if requires_interpreted_request and not interpreted_request:
        errors.append("interpreted_request is required for runplan routes.")

    if command_family == COMMAND_FAMILY_DIRECT_CLI:
        errors.append("LLM contract may not produce direct CLI route handoffs.")

    if command_family == COMMAND_FAMILY_NONE and interpreted_request:
        errors.append("No-route proposals must not include interpreted_request.")

    normalized_proposal = {
        "schema_version": schema_version,
        "proposed_intent": proposed_intent,
        "interpreted_request": interpreted_request or None,
        "confidence": confidence,
        "reasoning_summary": reasoning_summary or None,
        "safety_notes": safety_notes,
    }

    recommended_command = build_recommended_command(
        intent=proposed_intent,
        interpreted_request=interpreted_request or None,
    )

    route_handoff = (
        build_route_handoff(
            intent=proposed_intent,
            recommended_command=recommended_command,
            interpreted_request=interpreted_request or None,
        ).to_dict()
        if proposed_intent and is_known_operator_intent(proposed_intent)
        else {}
    )

    if route_handoff.get("errors"):
        errors.extend(str(error) for error in route_handoff["errors"])

    if confidence is not None and confidence < MIN_AUTOMATION_CONFIDENCE:
        warnings.append(
            "LLM proposal confidence is low; deterministic systems should treat it as weak routing evidence."
        )

    if errors:
        return invalid_result(
            message="LLM route proposal failed contract validation.",
            errors=errors,
            normalized_proposal=normalized_proposal,
            route_handoff=route_handoff,
            warnings=warnings,
        )

    if proposed_intent == INTENT_UNKNOWN:
        warnings.append("LLM proposed unknown intent; this is safe but not executable.")

    return LLMContractValidationResult(
        status=LLM_CONTRACT_STATUS_OK,
        valid=True,
        message="LLM route proposal passed contract validation.",
        normalized_proposal=normalized_proposal,
        route_handoff=route_handoff,
        errors=(),
        warnings=tuple(warnings),
    )
