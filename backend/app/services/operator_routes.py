"""
Deterministic Operator route registry for Lighthouse.

This module is the authority for Operator conversation route policy:
- known intents
- safety class
- command family
- autorun eligibility
- manual review requirements

It does not call the model.
It does not execute tools.
It does not mutate the operating system.
It does not write memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


INTENT_PERFORMANCE_DIAGNOSTIC = "performance_diagnostic"
INTENT_PROCESS_MEMORY_DIAGNOSTIC = "process_memory_diagnostic"
INTENT_REPAIR_REQUEST = "repair_request"
INTENT_OS_ACTION_REQUEST = "os_action_request"
INTENT_DESTRUCTIVE_ACTION_REQUEST = "destructive_action_request"
INTENT_GENERAL_HEALTH_CHECK = "general_health_check"
INTENT_DIRECT_COMMAND = "direct_command"
INTENT_UNKNOWN = "unknown"

SAFETY_CLASS_READ_ONLY_DIAGNOSTIC = "read_only_diagnostic"
SAFETY_CLASS_OS_CHANGING = "os_changing"
SAFETY_CLASS_DESTRUCTIVE = "destructive_or_data_changing"
SAFETY_CLASS_INSPECT_FIRST_REPAIR = "inspect_first_repair_request"
SAFETY_CLASS_DIRECT_CLI_COMMAND = "direct_cli_command"
SAFETY_CLASS_NEEDS_CLARIFICATION = "needs_clarification"

COMMAND_FAMILY_RUNPLAN = "runplan"
COMMAND_FAMILY_RUNPLAN_PREVIEW_ONLY = "runplan_preview_only"
COMMAND_FAMILY_DIRECT_CLI = "direct_cli"
COMMAND_FAMILY_NONE = "none"

READ_ONLY_AUTORUN_REFUSAL = (
    "Only read-only diagnostic routes may be auto-run. "
    "Action, destructive, repair, direct-command, and unknown intents "
    "must be reviewed manually first."
)


@dataclass(frozen=True)
class OperatorRouteContract:
    """
    Stable contract for one Operator conversation route.
    """

    intent: str
    safety_class: str
    command_family: str
    requires_engine_run: bool
    autorun_allowed: bool
    manual_review_required: bool
    description: str
    refusal_reason: str
    example_inputs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable route contract.
        """
        return {
            "intent": self.intent,
            "safety_class": self.safety_class,
            "command_family": self.command_family,
            "requires_engine_run": self.requires_engine_run,
            "autorun_allowed": self.autorun_allowed,
            "manual_review_required": self.manual_review_required,
            "description": self.description,
            "refusal_reason": self.refusal_reason,
            "example_inputs": list(self.example_inputs),
        }


OPERATOR_ROUTE_REGISTRY: dict[str, OperatorRouteContract] = {
    INTENT_PERFORMANCE_DIAGNOSTIC: OperatorRouteContract(
        intent=INTENT_PERFORMANCE_DIAGNOSTIC,
        safety_class=SAFETY_CLASS_READ_ONLY_DIAGNOSTIC,
        command_family=COMMAND_FAMILY_RUNPLAN,
        requires_engine_run=True,
        autorun_allowed=True,
        manual_review_required=False,
        description="Read-only performance diagnostic route.",
        refusal_reason="This route is allowed to auto-run because it is read-only.",
        example_inputs=(
            "my laptop feels slow",
            "my computer is lagging",
        ),
    ),
    INTENT_PROCESS_MEMORY_DIAGNOSTIC: OperatorRouteContract(
        intent=INTENT_PROCESS_MEMORY_DIAGNOSTIC,
        safety_class=SAFETY_CLASS_READ_ONLY_DIAGNOSTIC,
        command_family=COMMAND_FAMILY_RUNPLAN,
        requires_engine_run=True,
        autorun_allowed=True,
        manual_review_required=False,
        description="Read-only process or memory diagnostic route.",
        refusal_reason="This route is allowed to auto-run because it is read-only.",
        example_inputs=(
            "why is chrome eating memory",
            "what is using my RAM",
        ),
    ),
    INTENT_GENERAL_HEALTH_CHECK: OperatorRouteContract(
        intent=INTENT_GENERAL_HEALTH_CHECK,
        safety_class=SAFETY_CLASS_READ_ONLY_DIAGNOSTIC,
        command_family=COMMAND_FAMILY_RUNPLAN,
        requires_engine_run=True,
        autorun_allowed=True,
        manual_review_required=False,
        description="Read-only general health check route.",
        refusal_reason="This route is allowed to auto-run because it is read-only.",
        example_inputs=(
            "is anything wrong",
            "check my computer",
        ),
    ),
    INTENT_OS_ACTION_REQUEST: OperatorRouteContract(
        intent=INTENT_OS_ACTION_REQUEST,
        safety_class=SAFETY_CLASS_OS_CHANGING,
        command_family=COMMAND_FAMILY_RUNPLAN_PREVIEW_ONLY,
        requires_engine_run=True,
        autorun_allowed=False,
        manual_review_required=True,
        description="OS-changing request that must remain confirmation-gated.",
        refusal_reason=READ_ONLY_AUTORUN_REFUSAL,
        example_inputs=(
            "close chrome",
            "restart this process",
        ),
    ),
    INTENT_DESTRUCTIVE_ACTION_REQUEST: OperatorRouteContract(
        intent=INTENT_DESTRUCTIVE_ACTION_REQUEST,
        safety_class=SAFETY_CLASS_DESTRUCTIVE,
        command_family=COMMAND_FAMILY_RUNPLAN_PREVIEW_ONLY,
        requires_engine_run=True,
        autorun_allowed=False,
        manual_review_required=True,
        description="Destructive or data-changing request that must not auto-run.",
        refusal_reason=READ_ONLY_AUTORUN_REFUSAL,
        example_inputs=(
            "delete files to make space",
            "clean disk",
        ),
    ),
    INTENT_REPAIR_REQUEST: OperatorRouteContract(
        intent=INTENT_REPAIR_REQUEST,
        safety_class=SAFETY_CLASS_INSPECT_FIRST_REPAIR,
        command_family=COMMAND_FAMILY_RUNPLAN_PREVIEW_ONLY,
        requires_engine_run=True,
        autorun_allowed=False,
        manual_review_required=True,
        description="Broad repair wording routed to inspect-first behavior.",
        refusal_reason=READ_ONLY_AUTORUN_REFUSAL,
        example_inputs=(
            "fix my pc",
            "repair my laptop",
        ),
    ),
    INTENT_DIRECT_COMMAND: OperatorRouteContract(
        intent=INTENT_DIRECT_COMMAND,
        safety_class=SAFETY_CLASS_DIRECT_CLI_COMMAND,
        command_family=COMMAND_FAMILY_DIRECT_CLI,
        requires_engine_run=False,
        autorun_allowed=False,
        manual_review_required=False,
        description="Existing direct CLI command route.",
        refusal_reason="Direct CLI commands are not auto-run through talkrun.",
        example_inputs=(
            "show my saved snapshots",
            "show the last report",
        ),
    ),
    INTENT_UNKNOWN: OperatorRouteContract(
        intent=INTENT_UNKNOWN,
        safety_class=SAFETY_CLASS_NEEDS_CLARIFICATION,
        command_family=COMMAND_FAMILY_NONE,
        requires_engine_run=False,
        autorun_allowed=False,
        manual_review_required=True,
        description="Unknown or ambiguous route that requires clarification.",
        refusal_reason="Unknown or ambiguous requests cannot be auto-run.",
        example_inputs=(
            "banana window purple",
        ),
    ),
}


def get_operator_route(intent: str) -> OperatorRouteContract | None:
    """
    Return the route contract for an Operator intent.
    """
    return OPERATOR_ROUTE_REGISTRY.get(intent)


def iter_operator_routes() -> tuple[OperatorRouteContract, ...]:
    """
    Return all registered Operator route contracts.
    """
    return tuple(OPERATOR_ROUTE_REGISTRY.values())


def is_known_operator_intent(intent: str) -> bool:
    """
    Return True when the intent has a registered route contract.
    """
    return intent in OPERATOR_ROUTE_REGISTRY


def safety_class_for_intent(intent: str) -> str:
    """
    Return the registered safety class for an Operator intent.
    """
    route = get_operator_route(intent)

    if route is None:
        return SAFETY_CLASS_NEEDS_CLARIFICATION

    return route.safety_class


def is_autorun_allowed_for_intent(intent: str) -> bool:
    """
    Return True when the route contract allows talkrun autorun.
    """
    route = get_operator_route(intent)

    if route is None:
        return False

    return route.autorun_allowed


def get_autorun_refusal_reason(intent: str) -> str:
    """
    Return the registered refusal reason for an Operator intent.
    """
    route = get_operator_route(intent)

    if route is None:
        return "Unknown or unsupported intents cannot be auto-run."

    return route.refusal_reason


def build_route_metadata(intent: str) -> dict[str, Any]:
    """
    Build a compact route metadata dictionary for decision trace use.
    """
    route = get_operator_route(intent)

    if route is None:
        return {
            "route_known": False,
            "intent": intent,
            "safety_class": SAFETY_CLASS_NEEDS_CLARIFICATION,
            "command_family": COMMAND_FAMILY_NONE,
            "requires_engine_run": False,
            "autorun_allowed": False,
            "manual_review_required": True,
            "description": "Unknown route.",
        }

    metadata = route.to_dict()
    metadata["route_known"] = True
    return metadata
