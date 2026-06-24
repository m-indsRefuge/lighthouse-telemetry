"""
Tests for Lighthouse LLM Contract V0.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.llm_contract import (
    LLM_CONTRACT_SCHEMA_VERSION,
    validate_llm_route_proposal,
)


def valid_read_only_payload() -> dict:
    return {
        "schema_version": LLM_CONTRACT_SCHEMA_VERSION,
        "proposed_intent": "performance_diagnostic",
        "interpreted_request": "why is my laptop slow",
        "confidence": 0.82,
        "reasoning_summary": "The user described slowness.",
        "safety_notes": ["Read-only diagnostic route only."],
    }


def test_validate_llm_route_proposal_accepts_read_only_route() -> None:
    result = validate_llm_route_proposal(valid_read_only_payload())

    data = result.to_dict()

    assert data["status"] == "ok"
    assert data["valid"] is True
    assert data["normalized_proposal"]["proposed_intent"] == "performance_diagnostic"
    assert data["route_handoff"]["route_ready"] is True
    assert data["route_handoff"]["safety_class"] == "read_only_diagnostic"
    assert data["route_handoff"]["command_family"] == "runplan"
    assert data["route_handoff"]["engine_request"] == "why is my laptop slow"
    assert data["route_handoff"]["recommended_command"] == "runplan why is my laptop slow"


def test_validate_llm_route_proposal_accepts_json_string() -> None:
    payload = """
    {
      "schema_version": "llm_contract_v0",
      "proposed_intent": "general_health_check",
      "interpreted_request": "is anything wrong with my computer",
      "confidence": 0.74
    }
    """

    result = validate_llm_route_proposal(payload)

    assert result.valid is True
    assert result.route_handoff["engine_request"] == "is anything wrong with my computer"


def test_validate_llm_route_proposal_rejects_malformed_json() -> None:
    result = validate_llm_route_proposal("{not-json")

    assert result.status == "invalid"
    assert result.valid is False
    assert "not valid JSON" in result.errors[0]


def test_validate_llm_route_proposal_rejects_non_object_json() -> None:
    result = validate_llm_route_proposal('["not", "object"]')

    assert result.status == "invalid"
    assert result.valid is False
    assert result.errors == ("LLM contract JSON must decode to an object.",)


def test_validate_llm_route_proposal_rejects_missing_schema_version() -> None:
    payload = valid_read_only_payload()
    payload.pop("schema_version")

    result = validate_llm_route_proposal(payload)

    assert result.valid is False
    assert "schema_version must be 'llm_contract_v0'." in result.errors


def test_validate_llm_route_proposal_rejects_unknown_intent() -> None:
    payload = valid_read_only_payload()
    payload["proposed_intent"] = "invented_intent"

    result = validate_llm_route_proposal(payload)

    assert result.valid is False
    assert "Unknown proposed_intent: invented_intent" in result.errors


def test_validate_llm_route_proposal_rejects_direct_command_intent() -> None:
    payload = {
        "schema_version": LLM_CONTRACT_SCHEMA_VERSION,
        "proposed_intent": "direct_command",
        "interpreted_request": "windows",
        "confidence": 0.9,
    }

    result = validate_llm_route_proposal(payload)

    assert result.valid is False
    assert "LLM contract may not propose direct CLI commands." in result.errors


def test_validate_llm_route_proposal_rejects_missing_interpreted_request_for_runplan() -> None:
    payload = valid_read_only_payload()
    payload["interpreted_request"] = "   "

    result = validate_llm_route_proposal(payload)

    assert result.valid is False
    assert "interpreted_request is required for runplan routes." in result.errors


def test_validate_llm_route_proposal_rejects_out_of_range_confidence() -> None:
    payload = valid_read_only_payload()
    payload["confidence"] = 1.5

    result = validate_llm_route_proposal(payload)

    assert result.valid is False
    assert "confidence must be between 0.0 and 1.0." in result.errors


def test_validate_llm_route_proposal_rejects_non_numeric_confidence() -> None:
    payload = valid_read_only_payload()
    payload["confidence"] = "very sure"

    result = validate_llm_route_proposal(payload)

    assert result.valid is False
    assert "confidence must be a number from 0.0 to 1.0." in result.errors


def test_validate_llm_route_proposal_rejects_forbidden_authority_fields() -> None:
    payload = valid_read_only_payload()
    payload["tool_name"] = "delete_files"
    payload["approved"] = True
    payload["shell_command"] = "Remove-Item C:\\temp"

    result = validate_llm_route_proposal(payload)

    assert result.valid is False
    assert any("forbidden authority field" in error for error in result.errors)
    assert "approved" in result.errors[0]
    assert "shell_command" in result.errors[0]
    assert "tool_name" in result.errors[0]


def test_validate_llm_route_proposal_rejects_unknown_fields() -> None:
    payload = valid_read_only_payload()
    payload["extra"] = "not allowed"

    result = validate_llm_route_proposal(payload)

    assert result.valid is False
    assert "LLM contract payload contains unknown field(s): extra" in result.errors


def test_validate_llm_route_proposal_allows_destructive_classification_but_not_autorun() -> None:
    payload = {
        "schema_version": LLM_CONTRACT_SCHEMA_VERSION,
        "proposed_intent": "destructive_action_request",
        "interpreted_request": "delete files to make space",
        "confidence": 0.77,
        "reasoning_summary": "The user asked for a data-changing action.",
        "safety_notes": ["Must remain behind manual review."],
    }

    result = validate_llm_route_proposal(payload)

    assert result.valid is True
    assert result.route_handoff["route_ready"] is True
    assert result.route_handoff["autorun_allowed"] is False
    assert result.route_handoff["manual_review_required"] is True
    assert result.route_handoff["safety_class"] == "destructive_or_data_changing"
    assert result.route_handoff["command_family"] == "runplan_preview_only"


def test_validate_llm_route_proposal_accepts_unknown_intent_as_non_executable() -> None:
    payload = {
        "schema_version": LLM_CONTRACT_SCHEMA_VERSION,
        "proposed_intent": "unknown",
        "interpreted_request": None,
        "confidence": 0.22,
        "reasoning_summary": "The model could not classify the request.",
        "safety_notes": ["Ask for clarification."],
    }

    result = validate_llm_route_proposal(payload)

    assert result.valid is True
    assert result.route_handoff["route_ready"] is False
    assert result.route_handoff["command_family"] == "none"
    assert result.route_handoff["engine_request"] is None
    assert result.warnings
