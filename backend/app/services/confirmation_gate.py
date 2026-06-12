"""
Confirmation gate for Lighthouse.

This module defines the safety process for future permission-gated tools.

It does not execute tools.
It does not change the operating system.
It only decides whether a tool requires confirmation and whether the Operator
typed the exact required confirmation phrase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.tool_registry import (
    RISK_BLOCKED,
    get_tool_by_name,
    get_tool_safety_summary,
)


CONFIRMATION_STATUS_REQUIRED = "confirmation_required"
CONFIRMATION_STATUS_NOT_REQUIRED = "confirmation_not_required"
CONFIRMATION_STATUS_ACCEPTED = "confirmation_accepted"
CONFIRMATION_STATUS_REFUSED = "confirmation_refused"
CONFIRMATION_STATUS_BLOCKED = "confirmation_blocked"
CONFIRMATION_STATUS_UNKNOWN_TOOL = "unknown_tool"
CONFIRMATION_STATUS_NEEDS_TARGET = "needs_target"

CONFIRMATION_PREFIX = "CONFIRM"


@dataclass(frozen=True)
class ConfirmationRequest:
    """
    Confirmation request for a future permission-gated tool.
    """

    status: str
    tool_name: str
    message: str
    required_phrase: str | None
    target: str | None
    risk_level: int | None
    requires_confirmation: bool
    requires_target: bool
    executable_after_confirmation: bool
    safety_summary: dict[str, object]

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable confirmation request shape.
        """
        return {
            "status": self.status,
            "tool_name": self.tool_name,
            "message": self.message,
            "required_phrase": self.required_phrase,
            "target": self.target,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "requires_target": self.requires_target,
            "executable_after_confirmation": self.executable_after_confirmation,
            "safety_summary": self.safety_summary,
        }


@dataclass(frozen=True)
class ConfirmationResult:
    """
    Result of validating Operator confirmation input.
    """

    status: str
    accepted: bool
    tool_name: str
    message: str
    required_phrase: str | None
    operator_input: str
    target: str | None
    request: ConfirmationRequest

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable confirmation result shape.
        """
        return {
            "status": self.status,
            "accepted": self.accepted,
            "tool_name": self.tool_name,
            "message": self.message,
            "required_phrase": self.required_phrase,
            "operator_input": self.operator_input,
            "target": self.target,
            "request": self.request.to_dict(),
        }


def normalize_tool_name(tool_name: str) -> str:
    """
    Normalize tool names for lookup.
    """
    return tool_name.strip().lower()


def build_confirmation_phrase(tool_name: str) -> str:
    """
    Build the exact confirmation phrase for a tool.

    The target is intentionally not embedded in the phrase. The target remains
    a separate explicit field so Lighthouse can show it clearly and validate it
    separately before future action execution.
    """
    normalized_name = normalize_tool_name(tool_name)
    phrase_name = normalized_name.replace("_", " ").upper()

    return f"{CONFIRMATION_PREFIX} {phrase_name}"


def _clean_target(target: str | None) -> str | None:
    """
    Normalize a target value without inventing one.
    """
    if target is None:
        return None

    cleaned_target = target.strip()

    if not cleaned_target:
        return None

    return cleaned_target


def build_confirmation_request(
    tool_name: str,
    target: str | None = None,
) -> ConfirmationRequest:
    """
    Build a confirmation request for a registered tool.

    Blocked tools cannot be confirmed.
    Unknown tools cannot be confirmed.
    Tools requiring a target must receive one before confirmation can proceed.
    """
    normalized_name = normalize_tool_name(tool_name)
    tool = get_tool_by_name(normalized_name)
    safety_summary = get_tool_safety_summary(normalized_name)
    cleaned_target = _clean_target(target)

    if tool is None:
        return ConfirmationRequest(
            status=CONFIRMATION_STATUS_UNKNOWN_TOOL,
            tool_name=normalized_name,
            message="Unknown tools cannot be confirmed.",
            required_phrase=None,
            target=cleaned_target,
            risk_level=None,
            requires_confirmation=False,
            requires_target=False,
            executable_after_confirmation=False,
            safety_summary={
                **safety_summary,
                "confirmation_allowed": False,
                "reason": "Unknown tools cannot be confirmed.",
            },
        )

    if tool.risk_level == RISK_BLOCKED:
        return ConfirmationRequest(
            status=CONFIRMATION_STATUS_BLOCKED,
            tool_name=normalized_name,
            message="Blocked tools cannot be confirmed or executed.",
            required_phrase=None,
            target=cleaned_target,
            risk_level=tool.risk_level,
            requires_confirmation=tool.requires_confirmation,
            requires_target=tool.requires_target,
            executable_after_confirmation=False,
            safety_summary={
                **safety_summary,
                "confirmation_allowed": False,
                "reason": "Blocked tools cannot be confirmed or executed.",
            },
        )

    if not tool.requires_confirmation:
        return ConfirmationRequest(
            status=CONFIRMATION_STATUS_NOT_REQUIRED,
            tool_name=normalized_name,
            message="This tool does not require Operator confirmation.",
            required_phrase=None,
            target=cleaned_target,
            risk_level=tool.risk_level,
            requires_confirmation=False,
            requires_target=tool.requires_target,
            executable_after_confirmation=False,
            safety_summary={
                **safety_summary,
                "confirmation_allowed": False,
                "reason": "This tool does not require Operator confirmation.",
            },
        )

    if tool.requires_target and cleaned_target is None:
        return ConfirmationRequest(
            status=CONFIRMATION_STATUS_NEEDS_TARGET,
            tool_name=normalized_name,
            message=(
                "This tool requires a specific target before Lighthouse can "
                "ask for confirmation."
            ),
            required_phrase=None,
            target=None,
            risk_level=tool.risk_level,
            requires_confirmation=True,
            requires_target=True,
            executable_after_confirmation=False,
            safety_summary={
                **safety_summary,
                "confirmation_allowed": False,
                "reason": "A specific target is required before confirmation.",
            },
        )

    required_phrase = build_confirmation_phrase(normalized_name)

    return ConfirmationRequest(
        status=CONFIRMATION_STATUS_REQUIRED,
        tool_name=normalized_name,
        message=(
            "This tool requires explicit Operator confirmation before any "
            "future action executor may run it."
        ),
        required_phrase=required_phrase,
        target=cleaned_target,
        risk_level=tool.risk_level,
        requires_confirmation=True,
        requires_target=tool.requires_target,
        executable_after_confirmation=True,
        safety_summary={
            **safety_summary,
            "confirmation_allowed": True,
            "reason": "Exact Operator confirmation is required.",
        },
    )


def validate_confirmation_input(
    request: ConfirmationRequest,
    operator_input: str,
) -> ConfirmationResult:
    """
    Validate Operator input against a confirmation request.

    The phrase must match exactly after trimming leading/trailing whitespace.
    Case is not normalized. The exact phrase matters.
    """
    cleaned_input = operator_input.strip()

    if request.status != CONFIRMATION_STATUS_REQUIRED:
        return ConfirmationResult(
            status=CONFIRMATION_STATUS_REFUSED,
            accepted=False,
            tool_name=request.tool_name,
            message="Confirmation refused because the request is not confirmable.",
            required_phrase=request.required_phrase,
            operator_input=operator_input,
            target=request.target,
            request=request,
        )

    if request.required_phrase is None:
        return ConfirmationResult(
            status=CONFIRMATION_STATUS_REFUSED,
            accepted=False,
            tool_name=request.tool_name,
            message="Confirmation refused because no confirmation phrase exists.",
            required_phrase=None,
            operator_input=operator_input,
            target=request.target,
            request=request,
        )

    if cleaned_input != request.required_phrase:
        return ConfirmationResult(
            status=CONFIRMATION_STATUS_REFUSED,
            accepted=False,
            tool_name=request.tool_name,
            message="Confirmation refused because the phrase did not match exactly.",
            required_phrase=request.required_phrase,
            operator_input=operator_input,
            target=request.target,
            request=request,
        )

    return ConfirmationResult(
        status=CONFIRMATION_STATUS_ACCEPTED,
        accepted=True,
        tool_name=request.tool_name,
        message="Confirmation accepted.",
        required_phrase=request.required_phrase,
        operator_input=operator_input,
        target=request.target,
        request=request,
    )


def validate_confirmation_for_tool(
    tool_name: str,
    operator_input: str,
    target: str | None = None,
) -> ConfirmationResult:
    """
    Build a confirmation request and validate Operator input in one step.
    """
    request = build_confirmation_request(
        tool_name=tool_name,
        target=target,
    )

    return validate_confirmation_input(
        request=request,
        operator_input=operator_input,
    )


def format_confirmation_request(request: ConfirmationRequest) -> str:
    """
    Format a confirmation request for CLI display.
    """
    lines = [
        "",
        "LIGHTHOUSE CONFIRMATION GATE",
        "=" * 52,
        f"Status: {request.status}",
        f"Tool: {request.tool_name}",
        f"Message: {request.message}",
        f"Risk level: {request.risk_level if request.risk_level is not None else 'unknown'}",
        f"Requires confirmation: {'yes' if request.requires_confirmation else 'no'}",
        f"Requires target: {'yes' if request.requires_target else 'no'}",
        f"Target: {request.target if request.target else 'none'}",
    ]

    if request.required_phrase:
        lines.extend(
            [
                "",
                "Required phrase:",
                request.required_phrase,
            ]
        )

    lines.append("=" * 52)

    return "\n".join(lines)


def format_confirmation_result(result: ConfirmationResult) -> str:
    """
    Format a confirmation validation result for CLI display.
    """
    lines = [
        "",
        "LIGHTHOUSE CONFIRMATION RESULT",
        "=" * 52,
        f"Status: {result.status}",
        f"Accepted: {'yes' if result.accepted else 'no'}",
        f"Tool: {result.tool_name}",
        f"Target: {result.target if result.target else 'none'}",
        f"Message: {result.message}",
    ]

    if result.required_phrase:
        lines.append(f"Required phrase: {result.required_phrase}")

    lines.append("=" * 52)

    return "\n".join(lines)