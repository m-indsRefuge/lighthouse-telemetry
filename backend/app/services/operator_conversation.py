"""
Deterministic Operator conversation bridge for Lighthouse.

This module translates natural Operator language into safe Lighthouse routes.
It is intentionally deterministic for V0.

It does not call the model.
It does not execute tools.
It does not mutate the operating system.
It does not write memory.
It only interprets Operator input and recommends a safe CLI/engine route.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.assistant import classify_user_intent, contains_any, normalize_text


CONVERSATION_STATUS_OK = "ok"
CONVERSATION_STATUS_NEEDS_CLARIFICATION = "needs_clarification"

INTENT_PERFORMANCE_DIAGNOSTIC = "performance_diagnostic"
INTENT_PROCESS_MEMORY_DIAGNOSTIC = "process_memory_diagnostic"
INTENT_REPAIR_REQUEST = "repair_request"
INTENT_OS_ACTION_REQUEST = "os_action_request"
INTENT_DESTRUCTIVE_ACTION_REQUEST = "destructive_action_request"
INTENT_GENERAL_HEALTH_CHECK = "general_health_check"
INTENT_DIRECT_COMMAND = "direct_command"
INTENT_UNKNOWN = "unknown"

ACTION_WORDS = [
    "close",
    "kill",
    "stop",
    "end task",
    "terminate",
    "restart",
    "disable",
    "enable",
    "change",
    "fix",
    "repair",
    "optimize",
]

DESTRUCTIVE_WORDS = [
    "delete",
    "remove files",
    "erase",
    "wipe",
    "format",
    "clean disk",
    "clear disk",
    "free up space",
]

PROCESS_WORDS = [
    "chrome",
    "browser",
    "edge",
    "firefox",
    "process",
    "app",
    "application",
    "program",
    "task",
]

MEMORY_WORDS = [
    "memory",
    "ram",
    "usage",
    "eating memory",
    "using memory",
    "using ram",
    "memory pressure",
]

SLOWNESS_WORDS = [
    "slow",
    "sluggish",
    "lag",
    "lagging",
    "weird",
    "hanging",
    "freezing",
    "stuttering",
    "performance",
]

HEALTH_WORDS = [
    "healthy",
    "health",
    "anything wrong",
    "something wrong",
    "is my laptop ok",
    "is my pc ok",
    "is my computer ok",
    "check my laptop",
    "check my pc",
    "check my computer",
]

REPAIR_WORDS = [
    "fix my pc",
    "fix my laptop",
    "fix my computer",
    "repair my pc",
    "repair my laptop",
    "make it faster",
    "sort this out",
    "solve this",
]


@dataclass(frozen=True)
class OperatorConversationResult:
    """
    Stable result returned by the deterministic Operator conversation bridge.
    """

    status: str
    message: str
    original_input: str
    normalized_input: str
    intent: str
    interpreted_request: str | None
    recommended_command: str | None
    requires_engine_run: bool
    requires_clarification: bool
    clarifying_question: str | None
    safety_note: str
    confidence: float
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable conversation result shape.
        """
        return {
            "status": self.status,
            "message": self.message,
            "original_input": self.original_input,
            "normalized_input": self.normalized_input,
            "intent": self.intent,
            "interpreted_request": self.interpreted_request,
            "recommended_command": self.recommended_command,
            "requires_engine_run": self.requires_engine_run,
            "requires_clarification": self.requires_clarification,
            "clarifying_question": self.clarifying_question,
            "safety_note": self.safety_note,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def build_result(
    *,
    status: str,
    message: str,
    original_input: str,
    normalized_input: str,
    intent: str,
    interpreted_request: str | None,
    recommended_command: str | None,
    requires_engine_run: bool,
    requires_clarification: bool,
    clarifying_question: str | None,
    safety_note: str,
    confidence: float,
    warnings: tuple[str, ...] = (),
    errors: tuple[str, ...] = (),
) -> OperatorConversationResult:
    """
    Build a stable OperatorConversationResult.
    """
    return OperatorConversationResult(
        status=status,
        message=message,
        original_input=original_input,
        normalized_input=normalized_input,
        intent=intent,
        interpreted_request=interpreted_request,
        recommended_command=recommended_command,
        requires_engine_run=requires_engine_run,
        requires_clarification=requires_clarification,
        clarifying_question=clarifying_question,
        safety_note=safety_note,
        confidence=confidence,
        warnings=warnings,
        errors=errors,
    )


def has_any(text: str, phrases: list[str]) -> bool:
    """
    Return True when normalized text contains any phrase.
    """
    return contains_any(text, phrases)


def build_runplan_command(interpreted_request: str) -> str:
    """
    Build a runplan command for a safe engine route.
    """
    return f"runplan {interpreted_request}".strip()


def infer_process_target(text: str) -> str | None:
    """
    Infer a simple process target from common Operator wording.
    """
    if "chrome" in text:
        return "Chrome"

    if "edge" in text:
        return "Edge"

    if "firefox" in text:
        return "Firefox"

    if "browser" in text:
        return "the browser"

    return None


def interpret_destructive_action(
    original_input: str,
    normalized_input: str,
) -> OperatorConversationResult:
    """
    Interpret a destructive or data-changing request.
    """
    interpreted_request = original_input.strip()

    return build_result(
        status=CONVERSATION_STATUS_OK,
        message="This sounds like a destructive or data-changing request. Lighthouse can inspect and explain safe options first.",
        original_input=original_input,
        normalized_input=normalized_input,
        intent=INTENT_DESTRUCTIVE_ACTION_REQUEST,
        interpreted_request=interpreted_request,
        recommended_command=build_runplan_command(interpreted_request),
        requires_engine_run=True,
        requires_clarification=False,
        clarifying_question=None,
        safety_note=(
            "This route must remain behind Lighthouse safety gates. "
            "No files should be deleted and no settings should be changed from this conversation bridge."
        ),
        confidence=0.9,
        warnings=("Destructive or data-changing wording detected.",),
    )


def interpret_os_action(
    original_input: str,
    normalized_input: str,
) -> OperatorConversationResult:
    """
    Interpret an OS-changing request such as closing a process.
    """
    target = infer_process_target(normalized_input)

    if target:
        interpreted_request = f"close {target} because it may be using resources"
    else:
        interpreted_request = original_input.strip()

    return build_result(
        status=CONVERSATION_STATUS_OK,
        message="This sounds like an OS-changing request. Lighthouse can inspect and prepare a confirmation-gated route first.",
        original_input=original_input,
        normalized_input=normalized_input,
        intent=INTENT_OS_ACTION_REQUEST,
        interpreted_request=interpreted_request,
        recommended_command=build_runplan_command(interpreted_request),
        requires_engine_run=True,
        requires_clarification=False,
        clarifying_question=None,
        safety_note=(
            "Lighthouse may inspect the target, but it must not close, kill, restart, "
            "or change anything without explicit Operator confirmation."
        ),
        confidence=0.88,
        warnings=("OS-changing wording detected.",),
    )


def interpret_process_memory_diagnostic(
    original_input: str,
    normalized_input: str,
) -> OperatorConversationResult:
    """
    Interpret process or memory pressure wording.
    """
    target = infer_process_target(normalized_input)

    if target:
        interpreted_request = f"why is {target} using memory"
    else:
        interpreted_request = "what is using memory on my computer"

    return build_result(
        status=CONVERSATION_STATUS_OK,
        message="Lighthouse understood this as a process or memory diagnostic request.",
        original_input=original_input,
        normalized_input=normalized_input,
        intent=INTENT_PROCESS_MEMORY_DIAGNOSTIC,
        interpreted_request=interpreted_request,
        recommended_command=build_runplan_command(interpreted_request),
        requires_engine_run=True,
        requires_clarification=False,
        clarifying_question=None,
        safety_note="This is a read-only diagnostic route. No process will be closed from this conversation bridge.",
        confidence=0.87,
    )


def interpret_performance_diagnostic(
    original_input: str,
    normalized_input: str,
) -> OperatorConversationResult:
    """
    Interpret general slowness/performance wording.
    """
    return build_result(
        status=CONVERSATION_STATUS_OK,
        message="Lighthouse understood this as a performance diagnostic request.",
        original_input=original_input,
        normalized_input=normalized_input,
        intent=INTENT_PERFORMANCE_DIAGNOSTIC,
        interpreted_request="why is my laptop slow",
        recommended_command="runplan why is my laptop slow",
        requires_engine_run=True,
        requires_clarification=False,
        clarifying_question=None,
        safety_note="This is a read-only diagnostic route. Lighthouse will inspect before recommending action.",
        confidence=0.86,
    )


def interpret_repair_request(
    original_input: str,
    normalized_input: str,
) -> OperatorConversationResult:
    """
    Interpret broad repair/fix wording as inspect-first.
    """
    return build_result(
        status=CONVERSATION_STATUS_OK,
        message="Lighthouse understood this as a broad repair request and will route it to inspection first.",
        original_input=original_input,
        normalized_input=normalized_input,
        intent=INTENT_REPAIR_REQUEST,
        interpreted_request="inspect my computer before suggesting fixes",
        recommended_command="runplan inspect my computer before suggesting fixes",
        requires_engine_run=True,
        requires_clarification=False,
        clarifying_question=None,
        safety_note="Lighthouse should inspect first. Fixes or changes require later confirmation and deterministic safety checks.",
        confidence=0.82,
        warnings=("Broad repair wording was routed to read-only inspection first.",),
    )


def interpret_general_health_check(
    original_input: str,
    normalized_input: str,
) -> OperatorConversationResult:
    """
    Interpret general health/check wording.
    """
    return build_result(
        status=CONVERSATION_STATUS_OK,
        message="Lighthouse understood this as a general system health check.",
        original_input=original_input,
        normalized_input=normalized_input,
        intent=INTENT_GENERAL_HEALTH_CHECK,
        interpreted_request="is anything wrong with my computer",
        recommended_command="runplan is anything wrong with my computer",
        requires_engine_run=True,
        requires_clarification=False,
        clarifying_question=None,
        safety_note="This route is read-only and should only inspect current system evidence.",
        confidence=0.84,
    )


def interpret_direct_command(
    original_input: str,
    normalized_input: str,
) -> OperatorConversationResult | None:
    """
    Reuse the existing simple CLI intent router for direct commands.
    """
    assistant_intent = classify_user_intent(original_input)

    if assistant_intent.status != "ok" or not assistant_intent.canonical_command:
        return None

    # For diagnostic/health-like direct matches, prefer the engine route so the
    # Operator gets memory, explanation, safety, and journal context.
    if assistant_intent.intent in {"diagnose", "health"}:
        return None

    return build_result(
        status=CONVERSATION_STATUS_OK,
        message="Lighthouse matched this to an existing safe CLI command.",
        original_input=original_input,
        normalized_input=normalized_input,
        intent=INTENT_DIRECT_COMMAND,
        interpreted_request=assistant_intent.reason,
        recommended_command=assistant_intent.canonical_command,
        requires_engine_run=False,
        requires_clarification=False,
        clarifying_question=None,
        safety_note="This route uses an existing Lighthouse CLI command and does not grant extra authority.",
        confidence=assistant_intent.confidence,
    )


def interpret_operator_input(user_input: str) -> OperatorConversationResult:
    """
    Interpret Operator input and recommend a safe Lighthouse route.
    """
    normalized_input = normalize_text(user_input)

    if not normalized_input:
        return build_result(
            status=CONVERSATION_STATUS_NEEDS_CLARIFICATION,
            message="I need a clearer request before routing this safely.",
            original_input=user_input,
            normalized_input=normalized_input,
            intent=INTENT_UNKNOWN,
            interpreted_request=None,
            recommended_command=None,
            requires_engine_run=False,
            requires_clarification=True,
            clarifying_question="What would you like Lighthouse to inspect or explain?",
            safety_note="No command was selected because the input was empty or unclear.",
            confidence=0.0,
        )

    if has_any(normalized_input, DESTRUCTIVE_WORDS):
        return interpret_destructive_action(user_input, normalized_input)

    if has_any(normalized_input, ACTION_WORDS) and has_any(normalized_input, PROCESS_WORDS):
        return interpret_os_action(user_input, normalized_input)

    if has_any(normalized_input, PROCESS_WORDS) and has_any(normalized_input, MEMORY_WORDS):
        return interpret_process_memory_diagnostic(user_input, normalized_input)

    if has_any(normalized_input, REPAIR_WORDS):
        return interpret_repair_request(user_input, normalized_input)

    if has_any(normalized_input, SLOWNESS_WORDS):
        return interpret_performance_diagnostic(user_input, normalized_input)

    if has_any(normalized_input, HEALTH_WORDS):
        return interpret_general_health_check(user_input, normalized_input)

    direct_command_result = interpret_direct_command(user_input, normalized_input)

    if direct_command_result is not None:
        return direct_command_result

    return build_result(
        status=CONVERSATION_STATUS_NEEDS_CLARIFICATION,
        message="I could not safely map this to a Lighthouse route yet.",
        original_input=user_input,
        normalized_input=normalized_input,
        intent=INTENT_UNKNOWN,
        interpreted_request=None,
        recommended_command=None,
        requires_engine_run=False,
        requires_clarification=True,
        clarifying_question=(
            "Do you want Lighthouse to check health, investigate slowness, "
            "review processes, inspect events, or show saved reports?"
        ),
        safety_note="No command was selected because the intent was ambiguous.",
        confidence=0.0,
    )


def build_operator_response(result: OperatorConversationResult) -> str:
    """
    Build a plain-language Operator response from a conversation result.
    """
    lines = [
        "LIGHTHOUSE OPERATOR BRIDGE",
        "-" * 52,
        f"Status: {result.status}",
        f"Intent: {result.intent}",
        f"Message: {result.message}",
    ]

    if result.interpreted_request:
        lines.append(f"Interpreted request: {result.interpreted_request}")

    if result.recommended_command:
        lines.append(f"Recommended command: {result.recommended_command}")

    lines.append(f"Requires engine run: {'yes' if result.requires_engine_run else 'no'}")

    if result.requires_clarification and result.clarifying_question:
        lines.append(f"Clarifying question: {result.clarifying_question}")

    if result.safety_note:
        lines.append(f"Safety note: {result.safety_note}")

    if result.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)

    return "\n".join(lines)


def format_operator_response(result: OperatorConversationResult) -> str:
    """
    Format an Operator conversation result for CLI display.
    """
    return build_operator_response(result)

SAFE_AUTORUN_INTENTS = {
    INTENT_PERFORMANCE_DIAGNOSTIC,
    INTENT_PROCESS_MEMORY_DIAGNOSTIC,
    INTENT_GENERAL_HEALTH_CHECK,
}


def is_safe_to_autorun(result: OperatorConversationResult) -> tuple[bool, str]:
    """
    Decide whether a conversation result may be auto-run by talkrun.

    This does not execute anything.
    It only checks whether the route is safe enough for CLI handoff.
    """
    if result.status != CONVERSATION_STATUS_OK:
        return False, "The conversation result is not ok."

    if result.requires_clarification:
        return False, "The request still needs clarification."

    if not result.requires_engine_run:
        return False, "The recommended route is not an engine run."

    if not result.recommended_command:
        return False, "No recommended command was produced."

    if not result.recommended_command.lower().startswith("runplan "):
        return False, "Only runplan routes may be auto-run."

    if result.intent not in SAFE_AUTORUN_INTENTS:
        return False, (
            "Only read-only diagnostic routes may be auto-run. "
            "Action, destructive, repair, direct-command, and unknown intents "
            "must be reviewed manually first."
        )

    return True, "Safe read-only diagnostic route may be auto-run."

