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


@dataclass(frozen=True)
class OperatorRouteHandoff:
    """
    Structured handoff envelope from Operator conversation routing to CLI/engine.

    This object is the executable route contract.
    Display strings such as "runplan ..." are retained for the Operator, but
    they are not the source of authority for talkrun.
    """

    route_ready: bool
    route_known: bool
    intent: str
    safety_class: str
    command_family: str
    recommended_command: str | None
    engine_request: str | None
    autorun_allowed: bool
    manual_review_required: bool
    refusal_reason: str
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable handoff envelope.
        """
        return {
            "route_ready": self.route_ready,
            "route_known": self.route_known,
            "intent": self.intent,
            "safety_class": self.safety_class,
            "command_family": self.command_family,
            "recommended_command": self.recommended_command,
            "engine_request": self.engine_request,
            "autorun_allowed": self.autorun_allowed,
            "manual_review_required": self.manual_review_required,
            "refusal_reason": self.refusal_reason,
            "errors": list(self.errors),
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


def build_route_handoff(
    *,
    intent: str,
    recommended_command: str | None,
    interpreted_request: str | None,
) -> OperatorRouteHandoff:
    """
    Build a structured handoff envelope for an Operator route.

    The engine_request is derived from the interpreted request, not by slicing
    the display command. This keeps the handoff deterministic and auditable.
    """
    route = get_operator_route(intent)
    errors: list[str] = []

    if route is None:
        return OperatorRouteHandoff(
            route_ready=False,
            route_known=False,
            intent=intent,
            safety_class=SAFETY_CLASS_NEEDS_CLARIFICATION,
            command_family=COMMAND_FAMILY_NONE,
            recommended_command=recommended_command,
            engine_request=None,
            autorun_allowed=False,
            manual_review_required=True,
            refusal_reason="Unknown or unsupported intents cannot be handed off.",
            errors=("Unknown or unsupported Operator intent.",),
        )

    cleaned_recommended_command = (
        recommended_command.strip()
        if isinstance(recommended_command, str) and recommended_command.strip()
        else None
    )
    cleaned_interpreted_request = (
        interpreted_request.strip()
        if isinstance(interpreted_request, str) and interpreted_request.strip()
        else None
    )

    engine_request: str | None = None

    if route.command_family in {
        COMMAND_FAMILY_RUNPLAN,
        COMMAND_FAMILY_RUNPLAN_PREVIEW_ONLY,
    }:
        engine_request = cleaned_interpreted_request

        if not engine_request:
            errors.append("Runplan route has no interpreted engine request.")

        if not cleaned_recommended_command:
            errors.append("Runplan route has no recommended command.")
        elif not cleaned_recommended_command.lower().startswith("runplan "):
            errors.append("Runplan route recommended command must start with 'runplan '.")

    elif route.command_family == COMMAND_FAMILY_DIRECT_CLI:
        if not cleaned_recommended_command:
            errors.append("Direct CLI route has no recommended command.")

    elif route.command_family == COMMAND_FAMILY_NONE:
        if cleaned_recommended_command or cleaned_interpreted_request:
            errors.append("No-route handoff should not contain an executable request.")

    else:
        errors.append(f"Unsupported command family: {route.command_family}")

    route_ready = not errors and (
        route.command_family in {
            COMMAND_FAMILY_RUNPLAN,
            COMMAND_FAMILY_RUNPLAN_PREVIEW_ONLY,
            COMMAND_FAMILY_DIRECT_CLI,
        }
    )

    return OperatorRouteHandoff(
        route_ready=route_ready,
        route_known=True,
        intent=route.intent,
        safety_class=route.safety_class,
        command_family=route.command_family,
        recommended_command=cleaned_recommended_command,
        engine_request=engine_request,
        autorun_allowed=route.autorun_allowed,
        manual_review_required=route.manual_review_required,
        refusal_reason=route.refusal_reason,
        errors=tuple(errors),
    )


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


REQUIRED_OPERATOR_INTENTS = frozenset(
    {
        INTENT_PERFORMANCE_DIAGNOSTIC,
        INTENT_PROCESS_MEMORY_DIAGNOSTIC,
        INTENT_GENERAL_HEALTH_CHECK,
        INTENT_OS_ACTION_REQUEST,
        INTENT_DESTRUCTIVE_ACTION_REQUEST,
        INTENT_REPAIR_REQUEST,
        INTENT_DIRECT_COMMAND,
        INTENT_UNKNOWN,
    }
)

VALID_SAFETY_CLASSES = frozenset(
    {
        SAFETY_CLASS_READ_ONLY_DIAGNOSTIC,
        SAFETY_CLASS_OS_CHANGING,
        SAFETY_CLASS_DESTRUCTIVE,
        SAFETY_CLASS_INSPECT_FIRST_REPAIR,
        SAFETY_CLASS_DIRECT_CLI_COMMAND,
        SAFETY_CLASS_NEEDS_CLARIFICATION,
    }
)

VALID_COMMAND_FAMILIES = frozenset(
    {
        COMMAND_FAMILY_RUNPLAN,
        COMMAND_FAMILY_RUNPLAN_PREVIEW_ONLY,
        COMMAND_FAMILY_DIRECT_CLI,
        COMMAND_FAMILY_NONE,
    }
)


def validate_operator_route_registry() -> dict[str, Any]:
    """
    Validate the Operator route registry for internal consistency.

    This is a deterministic policy integrity check.
    It does not execute routes.
    """
    errors: list[str] = []
    warnings: list[str] = []

    registered_intents = set(OPERATOR_ROUTE_REGISTRY)
    missing_intents = sorted(REQUIRED_OPERATOR_INTENTS - registered_intents)
    unexpected_intents = sorted(registered_intents - REQUIRED_OPERATOR_INTENTS)

    for intent in missing_intents:
        errors.append(f"Missing required Operator route: {intent}")

    for intent in unexpected_intents:
        warnings.append(f"Unexpected Operator route is registered: {intent}")

    for registry_key, route in OPERATOR_ROUTE_REGISTRY.items():
        if registry_key != route.intent:
            errors.append(
                "Registry key does not match route intent: "
                f"{registry_key} != {route.intent}"
            )

        if not route.intent:
            errors.append(f"Route has empty intent: {registry_key}")

        if route.safety_class not in VALID_SAFETY_CLASSES:
            errors.append(
                f"Route {registry_key} has invalid safety_class: "
                f"{route.safety_class}"
            )

        if route.command_family not in VALID_COMMAND_FAMILIES:
            errors.append(
                f"Route {registry_key} has invalid command_family: "
                f"{route.command_family}"
            )

        if not route.description:
            warnings.append(f"Route {registry_key} has no description.")

        if not route.refusal_reason:
            warnings.append(f"Route {registry_key} has no refusal reason.")

        if route.autorun_allowed:
            if route.safety_class != SAFETY_CLASS_READ_ONLY_DIAGNOSTIC:
                errors.append(
                    f"Route {registry_key} allows autorun but is not read-only."
                )

            if route.command_family != COMMAND_FAMILY_RUNPLAN:
                errors.append(
                    f"Route {registry_key} allows autorun but is not a runplan route."
                )

            if not route.requires_engine_run:
                errors.append(
                    f"Route {registry_key} allows autorun but does not require engine run."
                )

            if route.manual_review_required:
                errors.append(
                    f"Route {registry_key} allows autorun but also requires manual review."
                )

        if (
            route.safety_class != SAFETY_CLASS_READ_ONLY_DIAGNOSTIC
            and route.autorun_allowed
        ):
            errors.append(
                f"Route {registry_key} is non-read-only but allows autorun."
            )

    unknown_route = OPERATOR_ROUTE_REGISTRY.get(INTENT_UNKNOWN)

    if unknown_route is None:
        errors.append("Unknown route contract is missing.")
    else:
        if unknown_route.autorun_allowed:
            errors.append("Unknown route must not allow autorun.")

        if not unknown_route.manual_review_required:
            errors.append("Unknown route must require manual review.")

        if unknown_route.requires_engine_run:
            errors.append("Unknown route must not require engine run.")

    direct_route = OPERATOR_ROUTE_REGISTRY.get(INTENT_DIRECT_COMMAND)

    if direct_route is None:
        errors.append("Direct command route contract is missing.")
    else:
        if direct_route.requires_engine_run:
            errors.append("Direct command route must not require engine run.")

        if direct_route.autorun_allowed:
            errors.append("Direct command route must not allow autorun.")

    status = "ok" if not errors else "invalid"

    return {
        "status": status,
        "message": (
            "Operator route registry is valid."
            if status == "ok"
            else "Operator route registry failed validation."
        ),
        "route_count": len(OPERATOR_ROUTE_REGISTRY),
        "errors": errors,
        "warnings": warnings,
    }


def build_operator_routes_report() -> str:
    """
    Build a plain-text report of Operator route policy.
    """
    validation = validate_operator_route_registry()

    lines = [
        "LIGHTHOUSE OPERATOR ROUTES",
        "-" * 52,
        f"Status: {validation['status']}",
        f"Message: {validation['message']}",
        f"Registered routes: {validation['route_count']}",
    ]

    if validation["errors"]:
        lines.append("Errors:")
        lines.extend(f"- {error}" for error in validation["errors"])

    if validation["warnings"]:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in validation["warnings"])

    lines.append("")
    lines.append("Routes:")

    for route in iter_operator_routes():
        lines.append("")
        lines.append(route.intent)
        lines.append(f"- safety_class: {route.safety_class}")
        lines.append(f"- command_family: {route.command_family}")
        lines.append(
            f"- requires_engine_run: {'yes' if route.requires_engine_run else 'no'}"
        )
        lines.append(
            f"- autorun_allowed: {'yes' if route.autorun_allowed else 'no'}"
        )
        lines.append(
            f"- manual_review_required: "
            f"{'yes' if route.manual_review_required else 'no'}"
        )
        lines.append(f"- description: {route.description}")

    return "\n".join(lines)
