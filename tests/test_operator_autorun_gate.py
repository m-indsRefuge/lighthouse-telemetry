"""
Tests for Operator Autorun Gate V0.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.operator_routes import (
    COMMAND_FAMILY_DIRECT_CLI,
    COMMAND_FAMILY_RUNPLAN,
    COMMAND_FAMILY_RUNPLAN_PREVIEW_ONLY,
    INTENT_DIRECT_COMMAND,
    INTENT_OS_ACTION_REQUEST,
    INTENT_PROCESS_MEMORY_DIAGNOSTIC,
    SAFETY_CLASS_DIRECT_CLI_COMMAND,
    SAFETY_CLASS_OS_CHANGING,
    SAFETY_CLASS_READ_ONLY_DIAGNOSTIC,
    build_route_handoff,
    validate_route_handoff_for_autorun,
)


def test_gate_allows_ready_read_only_runplan_handoff() -> None:
    handoff = build_route_handoff(
        intent=INTENT_PROCESS_MEMORY_DIAGNOSTIC,
        recommended_command="runplan why is Chrome using memory",
        interpreted_request="why is Chrome using memory",
    ).to_dict()

    result = validate_route_handoff_for_autorun(handoff)

    assert result.status == "ok"
    assert result.allowed is True
    assert "Safe read-only diagnostic route" in result.reason
    assert result.engine_request == "why is Chrome using memory"
    assert result.errors == ()


def test_gate_refuses_preview_only_handoff() -> None:
    handoff = build_route_handoff(
        intent=INTENT_OS_ACTION_REQUEST,
        recommended_command="runplan close Chrome because it may be using resources",
        interpreted_request="close Chrome because it may be using resources",
    ).to_dict()

    result = validate_route_handoff_for_autorun(handoff)

    assert result.status == "refused"
    assert result.allowed is False
    assert "Only read-only diagnostic routes" in result.reason
    assert result.engine_request is None
    assert "autorun_allowed must be true." in result.errors


def test_gate_refuses_missing_handoff() -> None:
    result = validate_route_handoff_for_autorun(None)

    assert result.status == "refused"
    assert result.allowed is False
    assert "missing or malformed" in result.reason
    assert result.engine_request is None


def test_gate_refuses_not_ready_handoff() -> None:
    handoff = build_route_handoff(
        intent=INTENT_PROCESS_MEMORY_DIAGNOSTIC,
        recommended_command="health",
        interpreted_request="why is Chrome using memory",
    ).to_dict()

    result = validate_route_handoff_for_autorun(handoff)

    assert result.status == "refused"
    assert result.allowed is False
    assert "not ready" in result.reason
    assert "route_ready must be true." in result.errors


def test_gate_refuses_direct_cli_handoff_even_if_route_ready() -> None:
    handoff = build_route_handoff(
        intent=INTENT_DIRECT_COMMAND,
        recommended_command="history",
        interpreted_request="show saved reports",
    ).to_dict()

    result = validate_route_handoff_for_autorun(handoff)

    assert handoff["route_ready"] is True
    assert handoff["command_family"] == COMMAND_FAMILY_DIRECT_CLI
    assert result.status == "refused"
    assert result.allowed is False
    assert "autorun_allowed must be true." in result.errors


def test_gate_refuses_wrong_safety_class_even_if_other_fields_claim_safe() -> None:
    handoff = {
        "route_ready": True,
        "route_known": True,
        "intent": INTENT_OS_ACTION_REQUEST,
        "safety_class": SAFETY_CLASS_OS_CHANGING,
        "command_family": COMMAND_FAMILY_RUNPLAN,
        "recommended_command": "runplan close Chrome",
        "engine_request": "close Chrome",
        "autorun_allowed": True,
        "manual_review_required": False,
        "refusal_reason": "Unsafe test route.",
        "errors": [],
    }

    result = validate_route_handoff_for_autorun(handoff)

    assert result.status == "refused"
    assert result.allowed is False
    assert "safety_class must be read_only_diagnostic." in result.errors


def test_gate_refuses_manual_review_required_even_if_autorun_claimed() -> None:
    handoff = {
        "route_ready": True,
        "route_known": True,
        "intent": INTENT_PROCESS_MEMORY_DIAGNOSTIC,
        "safety_class": SAFETY_CLASS_READ_ONLY_DIAGNOSTIC,
        "command_family": COMMAND_FAMILY_RUNPLAN,
        "recommended_command": "runplan why is Chrome using memory",
        "engine_request": "why is Chrome using memory",
        "autorun_allowed": True,
        "manual_review_required": True,
        "refusal_reason": "Manual review required.",
        "errors": [],
    }

    result = validate_route_handoff_for_autorun(handoff)

    assert result.status == "refused"
    assert result.allowed is False
    assert "manual_review_required must be false." in result.errors


def test_gate_refuses_missing_engine_request() -> None:
    handoff = {
        "route_ready": True,
        "route_known": True,
        "intent": INTENT_PROCESS_MEMORY_DIAGNOSTIC,
        "safety_class": SAFETY_CLASS_READ_ONLY_DIAGNOSTIC,
        "command_family": COMMAND_FAMILY_RUNPLAN,
        "recommended_command": "runplan why is Chrome using memory",
        "engine_request": "",
        "autorun_allowed": True,
        "manual_review_required": False,
        "refusal_reason": "",
        "errors": [],
    }

    result = validate_route_handoff_for_autorun(handoff)

    assert result.status == "refused"
    assert result.allowed is False
    assert "engine_request must be a non-empty string." in result.errors
