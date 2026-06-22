"""
Tests for Operator Route Handoff Envelope V0.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.operator_routes import (
    COMMAND_FAMILY_NONE,
    COMMAND_FAMILY_RUNPLAN,
    COMMAND_FAMILY_RUNPLAN_PREVIEW_ONLY,
    INTENT_OS_ACTION_REQUEST,
    INTENT_PROCESS_MEMORY_DIAGNOSTIC,
    INTENT_UNKNOWN,
    SAFETY_CLASS_NEEDS_CLARIFICATION,
    build_route_handoff,
)


def test_read_only_runplan_handoff_is_ready_and_autorunnable() -> None:
    handoff = build_route_handoff(
        intent=INTENT_PROCESS_MEMORY_DIAGNOSTIC,
        recommended_command="runplan why is Chrome using memory",
        interpreted_request="why is Chrome using memory",
    ).to_dict()

    assert handoff["route_ready"] is True
    assert handoff["route_known"] is True
    assert handoff["intent"] == INTENT_PROCESS_MEMORY_DIAGNOSTIC
    assert handoff["command_family"] == COMMAND_FAMILY_RUNPLAN
    assert handoff["engine_request"] == "why is Chrome using memory"
    assert handoff["recommended_command"] == "runplan why is Chrome using memory"
    assert handoff["autorun_allowed"] is True
    assert handoff["manual_review_required"] is False
    assert handoff["errors"] == []


def test_preview_only_handoff_is_ready_but_not_autorunnable() -> None:
    handoff = build_route_handoff(
        intent=INTENT_OS_ACTION_REQUEST,
        recommended_command="runplan close Chrome because it may be using resources",
        interpreted_request="close Chrome because it may be using resources",
    ).to_dict()

    assert handoff["route_ready"] is True
    assert handoff["route_known"] is True
    assert handoff["intent"] == INTENT_OS_ACTION_REQUEST
    assert handoff["command_family"] == COMMAND_FAMILY_RUNPLAN_PREVIEW_ONLY
    assert handoff["engine_request"] == "close Chrome because it may be using resources"
    assert handoff["autorun_allowed"] is False
    assert handoff["manual_review_required"] is True


def test_unknown_handoff_is_not_ready() -> None:
    handoff = build_route_handoff(
        intent=INTENT_UNKNOWN,
        recommended_command=None,
        interpreted_request=None,
    ).to_dict()

    assert handoff["route_ready"] is False
    assert handoff["route_known"] is True
    assert handoff["intent"] == INTENT_UNKNOWN
    assert handoff["safety_class"] == SAFETY_CLASS_NEEDS_CLARIFICATION
    assert handoff["command_family"] == COMMAND_FAMILY_NONE
    assert handoff["engine_request"] is None
    assert handoff["autorun_allowed"] is False
    assert handoff["manual_review_required"] is True


def test_malformed_runplan_handoff_is_not_ready() -> None:
    handoff = build_route_handoff(
        intent=INTENT_PROCESS_MEMORY_DIAGNOSTIC,
        recommended_command="health",
        interpreted_request="why is Chrome using memory",
    ).to_dict()

    assert handoff["route_ready"] is False
    assert "Runplan route recommended command must start with 'runplan '." in handoff["errors"]


def test_runplan_handoff_uses_interpreted_request_as_engine_request() -> None:
    handoff = build_route_handoff(
        intent=INTENT_PROCESS_MEMORY_DIAGNOSTIC,
        recommended_command="runplan display string should not be sliced",
        interpreted_request="authoritative engine request",
    ).to_dict()

    assert handoff["engine_request"] == "authoritative engine request"
