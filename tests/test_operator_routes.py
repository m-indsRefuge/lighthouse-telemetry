"""
Tests for deterministic Operator route registry.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.operator_routes import (
    COMMAND_FAMILY_DIRECT_CLI,
    COMMAND_FAMILY_NONE,
    COMMAND_FAMILY_RUNPLAN,
    COMMAND_FAMILY_RUNPLAN_PREVIEW_ONLY,
    INTENT_DESTRUCTIVE_ACTION_REQUEST,
    INTENT_DIRECT_COMMAND,
    INTENT_GENERAL_HEALTH_CHECK,
    INTENT_OS_ACTION_REQUEST,
    INTENT_PERFORMANCE_DIAGNOSTIC,
    INTENT_PROCESS_MEMORY_DIAGNOSTIC,
    INTENT_REPAIR_REQUEST,
    INTENT_UNKNOWN,
    SAFETY_CLASS_DESTRUCTIVE,
    SAFETY_CLASS_DIRECT_CLI_COMMAND,
    SAFETY_CLASS_NEEDS_CLARIFICATION,
    SAFETY_CLASS_OS_CHANGING,
    SAFETY_CLASS_READ_ONLY_DIAGNOSTIC,
    build_route_metadata,
    get_autorun_refusal_reason,
    get_operator_route,
    is_autorun_allowed_for_intent,
    is_known_operator_intent,
    iter_operator_routes,
    safety_class_for_intent,
)


REQUIRED_INTENTS = {
    INTENT_PERFORMANCE_DIAGNOSTIC,
    INTENT_PROCESS_MEMORY_DIAGNOSTIC,
    INTENT_GENERAL_HEALTH_CHECK,
    INTENT_OS_ACTION_REQUEST,
    INTENT_DESTRUCTIVE_ACTION_REQUEST,
    INTENT_REPAIR_REQUEST,
    INTENT_DIRECT_COMMAND,
    INTENT_UNKNOWN,
}


def test_registry_contains_all_required_intents() -> None:
    registered_intents = {route.intent for route in iter_operator_routes()}

    assert REQUIRED_INTENTS.issubset(registered_intents)


def test_read_only_diagnostic_routes_allow_autorun() -> None:
    for intent in {
        INTENT_PERFORMANCE_DIAGNOSTIC,
        INTENT_PROCESS_MEMORY_DIAGNOSTIC,
        INTENT_GENERAL_HEALTH_CHECK,
    }:
        route = get_operator_route(intent)

        assert route is not None
        assert route.safety_class == SAFETY_CLASS_READ_ONLY_DIAGNOSTIC
        assert route.command_family == COMMAND_FAMILY_RUNPLAN
        assert route.requires_engine_run is True
        assert route.autorun_allowed is True
        assert route.manual_review_required is False
        assert is_autorun_allowed_for_intent(intent) is True


def test_unsafe_routes_do_not_allow_autorun() -> None:
    unsafe_intents = {
        INTENT_OS_ACTION_REQUEST,
        INTENT_DESTRUCTIVE_ACTION_REQUEST,
        INTENT_REPAIR_REQUEST,
    }

    for intent in unsafe_intents:
        route = get_operator_route(intent)

        assert route is not None
        assert route.command_family == COMMAND_FAMILY_RUNPLAN_PREVIEW_ONLY
        assert route.requires_engine_run is True
        assert route.autorun_allowed is False
        assert route.manual_review_required is True
        assert is_autorun_allowed_for_intent(intent) is False
        assert "Only read-only diagnostic routes" in get_autorun_refusal_reason(intent)


def test_direct_command_route_is_registered_but_not_autorunnable() -> None:
    route = get_operator_route(INTENT_DIRECT_COMMAND)

    assert route is not None
    assert route.safety_class == SAFETY_CLASS_DIRECT_CLI_COMMAND
    assert route.command_family == COMMAND_FAMILY_DIRECT_CLI
    assert route.requires_engine_run is False
    assert route.autorun_allowed is False


def test_unknown_route_requires_clarification() -> None:
    route = get_operator_route(INTENT_UNKNOWN)

    assert route is not None
    assert route.safety_class == SAFETY_CLASS_NEEDS_CLARIFICATION
    assert route.command_family == COMMAND_FAMILY_NONE
    assert route.requires_engine_run is False
    assert route.autorun_allowed is False
    assert route.manual_review_required is True


def test_safety_class_for_intent_is_registry_backed() -> None:
    assert safety_class_for_intent(INTENT_PERFORMANCE_DIAGNOSTIC) == SAFETY_CLASS_READ_ONLY_DIAGNOSTIC
    assert safety_class_for_intent(INTENT_PROCESS_MEMORY_DIAGNOSTIC) == SAFETY_CLASS_READ_ONLY_DIAGNOSTIC
    assert safety_class_for_intent(INTENT_OS_ACTION_REQUEST) == SAFETY_CLASS_OS_CHANGING
    assert safety_class_for_intent(INTENT_DESTRUCTIVE_ACTION_REQUEST) == SAFETY_CLASS_DESTRUCTIVE
    assert safety_class_for_intent("unsupported_intent") == SAFETY_CLASS_NEEDS_CLARIFICATION


def test_build_route_metadata_for_known_intent() -> None:
    metadata = build_route_metadata(INTENT_PROCESS_MEMORY_DIAGNOSTIC)

    assert metadata["route_known"] is True
    assert metadata["intent"] == INTENT_PROCESS_MEMORY_DIAGNOSTIC
    assert metadata["safety_class"] == SAFETY_CLASS_READ_ONLY_DIAGNOSTIC
    assert metadata["command_family"] == COMMAND_FAMILY_RUNPLAN
    assert metadata["autorun_allowed"] is True
    assert metadata["manual_review_required"] is False


def test_build_route_metadata_for_unknown_intent() -> None:
    metadata = build_route_metadata("unsupported_intent")

    assert metadata["route_known"] is False
    assert metadata["intent"] == "unsupported_intent"
    assert metadata["safety_class"] == SAFETY_CLASS_NEEDS_CLARIFICATION
    assert metadata["command_family"] == COMMAND_FAMILY_NONE
    assert metadata["autorun_allowed"] is False
    assert metadata["manual_review_required"] is True


def test_is_known_operator_intent() -> None:
    assert is_known_operator_intent(INTENT_PERFORMANCE_DIAGNOSTIC) is True
    assert is_known_operator_intent(INTENT_UNKNOWN) is True
    assert is_known_operator_intent("unsupported_intent") is False


def test_route_contract_to_dict_is_stable() -> None:
    route = get_operator_route(INTENT_OS_ACTION_REQUEST)

    assert route is not None

    payload = route.to_dict()

    assert payload["intent"] == INTENT_OS_ACTION_REQUEST
    assert payload["safety_class"] == SAFETY_CLASS_OS_CHANGING
    assert payload["command_family"] == COMMAND_FAMILY_RUNPLAN_PREVIEW_ONLY
    assert payload["requires_engine_run"] is True
    assert payload["autorun_allowed"] is False
    assert payload["manual_review_required"] is True
    assert isinstance(payload["description"], str)
    assert isinstance(payload["refusal_reason"], str)
    assert isinstance(payload["example_inputs"], list)
