"""
Deterministic explanation composer for Lighthouse.

This module converts a Lighthouse Engine result into a beginner-friendly,
plain-language explanation.

It does not call the model.
It does not execute tools.
It does not mutate the operating system.
It does not write memory.
It only formats already-produced engine facts into a human-facing explanation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


EXPLANATION_STATUS_OK = "ok"
EXPLANATION_STATUS_ERROR = "error"

EXPLANATION_TITLE = "LIGHTHOUSE EXPLANATION"
EXPLANATION_SEPARATOR = "-" * 52


@dataclass(frozen=True)
class LighthouseExplanationResult:
    """
    Stable result returned by the deterministic explanation composer.
    """

    status: str
    message: str
    user_request: str
    text: str
    sections: dict[str, list[str]]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable explanation result shape.
        """
        return {
            "status": self.status,
            "message": self.message,
            "user_request": self.user_request,
            "text": self.text,
            "sections": self.sections,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def get_value(source: Any, name: str, default: Any = None) -> Any:
    """
    Read an attribute or dictionary key from an engine-like object.
    """
    if isinstance(source, dict):
        return source.get(name, default)

    return getattr(source, name, default)


def get_sequence(source: Any, name: str) -> tuple[Any, ...]:
    """
    Return an attribute/key as a tuple.
    """
    value = get_value(source, name, ())

    if value is None:
        return ()

    if isinstance(value, tuple):
        return value

    if isinstance(value, list):
        return tuple(value)

    return (value,)


def get_tool_name(tool: Any) -> str:
    """
    Return a tool name from a tool-like object.
    """
    return str(get_value(tool, "tool_name", "unknown_tool"))


def get_execution_result(engine_result: Any) -> Any | None:
    """
    Return the nested execution result from an engine result.
    """
    return get_value(engine_result, "execution_result")


def get_executed_tool_names(engine_result: Any) -> tuple[str, ...]:
    """
    Return executed tool names from an engine result.
    """
    execution_result = get_execution_result(engine_result)

    if execution_result is None:
        return ()

    return tuple(
        get_tool_name(tool)
        for tool in get_sequence(execution_result, "executed_tools")
    )


def get_refused_tool_names(engine_result: Any) -> tuple[str, ...]:
    """
    Return refused tool names from an engine result.
    """
    execution_result = get_execution_result(engine_result)

    if execution_result is None:
        return ()

    return tuple(
        get_tool_name(tool)
        for tool in get_sequence(execution_result, "refused_tools")
    )


def get_blocked_tool_names(engine_result: Any) -> tuple[str, ...]:
    """
    Return blocked tool names from an engine result.
    """
    execution_result = get_execution_result(engine_result)

    if execution_result is None:
        return ()

    blocked_tools = get_sequence(execution_result, "blocked_tools")

    return tuple(str(tool) for tool in blocked_tools)


def get_safe_alternatives(engine_result: Any) -> tuple[str, ...]:
    """
    Return safe alternatives from an engine result.
    """
    execution_result = get_execution_result(engine_result)

    if execution_result is None:
        return ()

    return tuple(str(tool) for tool in get_sequence(execution_result, "safe_alternatives"))


def has_useful_memory_context(engine_result: Any) -> bool:
    """
    Return True when the engine attached useful memory context.
    """
    memory_context = get_value(engine_result, "memory_context")

    if memory_context is None:
        return False

    enabled = bool(get_value(memory_context, "enabled", False))
    status = str(get_value(memory_context, "status", ""))
    context_text = str(get_value(memory_context, "context_text", ""))

    return enabled and status == "ok" and bool(context_text.strip())


def is_memory_disabled(engine_result: Any) -> bool:
    """
    Return True when memory context was explicitly disabled.
    """
    memory_context = get_value(engine_result, "memory_context")

    if memory_context is None:
        return False

    return bool(get_value(memory_context, "enabled", True)) is False


def get_memory_warnings(engine_result: Any) -> tuple[str, ...]:
    """
    Return memory-context warnings from an engine result.
    """
    memory_context = get_value(engine_result, "memory_context")

    if memory_context is None:
        return ()

    return tuple(str(warning) for warning in get_sequence(memory_context, "warnings"))


def get_engine_errors(engine_result: Any) -> tuple[str, ...]:
    """
    Return engine errors as strings.
    """
    return tuple(str(error) for error in get_sequence(engine_result, "errors"))


def build_checked_lines(engine_result: Any) -> list[str]:
    """
    Build the 'What I checked' section.
    """
    user_request = str(get_value(engine_result, "user_request", "")).strip()
    lines = []

    if user_request:
        lines.append(f'I reviewed your request: "{user_request}".')
    else:
        lines.append("I checked the request, but it was empty or unclear.")

    lines.append("I reviewed the Lighthouse engine result.")

    if get_execution_result(engine_result) is not None:
        lines.append("I reviewed the tool-plan execution result.")
    else:
        lines.append("No tool execution result was available to review.")

    memory_context = get_value(engine_result, "memory_context")

    if memory_context is not None:
        lines.append("I checked whether Lighthouse memory had useful context.")

    return lines


def build_found_lines(engine_result: Any) -> list[str]:
    """
    Build the 'What I found' section.
    """
    status = str(get_value(engine_result, "status", "unknown"))
    plan_status = str(get_value(engine_result, "plan_status", "unknown"))
    execution_status = str(get_value(engine_result, "execution_status", "unknown"))
    executed_tools = get_executed_tool_names(engine_result)
    refused_tools = get_refused_tool_names(engine_result)
    blocked_tools = get_blocked_tool_names(engine_result)
    lines: list[str] = []

    if status == "needs_clarification" or plan_status == "needs_clarification":
        lines.append("The request needs clarification, so Lighthouse did not run tools.")
        return lines

    if status == "error" or plan_status == "error":
        lines.append("Lighthouse reported an error while preparing this result.")

    if blocked_tools or plan_status == "blocked":
        lines.append("This request includes a blocked action. Lighthouse will not run it.")

    if plan_status == "needs_confirmation":
        lines.append("This request needs explicit Operator confirmation before any action can run.")

    if refused_tools or execution_status == "refused":
        lines.append("Lighthouse refused to execute one or more requested tools.")
        lines.append("I did not close anything, delete anything, or change the computer.")

    if executed_tools:
        lines.append("Lighthouse ran safe read-only diagnostic tools.")
        lines.append("Executed tools: " + ", ".join(executed_tools) + ".")
    elif execution_status == "ok":
        lines.append("Lighthouse handled this as a safe read-only result.")

    if has_useful_memory_context(engine_result):
        lines.append("Lighthouse found relevant memory context from previous cases.")
    elif is_memory_disabled(engine_result):
        lines.append("Lighthouse memory context was disabled for this run.")

    if not lines:
        lines.append("Lighthouse returned a structured result, but no specific finding was available.")

    return lines


def build_meaning_lines(engine_result: Any) -> list[str]:
    """
    Build the 'What this means' section.
    """
    plan_status = str(get_value(engine_result, "plan_status", "unknown"))
    execution_status = str(get_value(engine_result, "execution_status", "unknown"))
    errors = get_engine_errors(engine_result)
    memory_warnings = get_memory_warnings(engine_result)
    lines: list[str] = []

    if plan_status == "needs_clarification":
        lines.append("Lighthouse needs a clearer request before it can choose a safe path.")
    elif plan_status == "needs_confirmation":
        lines.append("The requested action is not read-only, so it must stay behind confirmation.")
    elif plan_status == "blocked":
        lines.append("Blocked actions are outside Lighthouse's allowed safety boundary.")
    elif execution_status == "ok":
        lines.append("The result is based on deterministic Lighthouse engine data.")
    elif execution_status == "refused":
        lines.append("The refusal is part of the safety system, not a failure to understand the request.")
    else:
        lines.append("The result should be reviewed before using it as guidance.")

    if has_useful_memory_context(engine_result):
        lines.append("Memory is supporting context only. Current telemetry and safety gates remain the authority.")

    if memory_warnings:
        lines.append("Some memory context warnings were reported and should be treated as caution signals.")

    if errors:
        lines.append("One or more engine errors were reported and should be reviewed.")

    return lines


def build_next_step_lines(engine_result: Any) -> list[str]:
    """
    Build the 'Safe next step' section.
    """
    plan_status = str(get_value(engine_result, "plan_status", "unknown"))
    execution_status = str(get_value(engine_result, "execution_status", "unknown"))
    safe_alternatives = get_safe_alternatives(engine_result)
    lines: list[str] = []

    if plan_status == "needs_clarification":
        lines.append("Ask a more specific question about what feels wrong or what you want checked.")
    elif plan_status == "needs_confirmation":
        lines.append("Review the target and confirmation preview before approving anything.")
        lines.append("Only continue if you intentionally want Lighthouse to prepare that action.")
    elif plan_status == "blocked":
        lines.append("Do not try to force this action through Lighthouse.")

        if safe_alternatives:
            lines.append("Use the listed safe alternatives instead: " + ", ".join(safe_alternatives) + ".")
    elif execution_status == "refused":
        lines.append("Use the safe alternatives or ask Lighthouse to inspect the issue first.")
    else:
        lines.append("Review the current health summary and top processes before taking action.")

    return lines


def format_section(title: str, lines: list[str]) -> list[str]:
    """
    Format a named explanation section.
    """
    section_lines = [f"{title}:"]

    if not lines:
        section_lines.append("- none")
        return section_lines

    section_lines.extend(f"- {line}" for line in lines)

    return section_lines


def build_explanation_text(sections: dict[str, list[str]]) -> str:
    """
    Build final explanation text from sections.
    """
    lines = [
        EXPLANATION_TITLE,
        EXPLANATION_SEPARATOR,
    ]

    ordered_titles = [
        "What I checked",
        "What I found",
        "What this means",
        "Safe next step",
    ]

    for index, title in enumerate(ordered_titles):
        if index > 0:
            lines.append("")

        lines.extend(format_section(title, sections.get(title, [])))

    return "\n".join(lines)


def compose_engine_explanation(engine_result: Any) -> LighthouseExplanationResult:
    """
    Compose a deterministic user-facing explanation from an engine result.
    """
    user_request = str(get_value(engine_result, "user_request", ""))
    engine_errors = get_engine_errors(engine_result)
    memory_warnings = get_memory_warnings(engine_result)

    sections = {
        "What I checked": build_checked_lines(engine_result),
        "What I found": build_found_lines(engine_result),
        "What this means": build_meaning_lines(engine_result),
        "Safe next step": build_next_step_lines(engine_result),
    }
    text = build_explanation_text(sections)

    status = EXPLANATION_STATUS_ERROR if get_value(engine_result, "status") == "error" else EXPLANATION_STATUS_OK

    return LighthouseExplanationResult(
        status=status,
        message="Explanation composed successfully.",
        user_request=user_request,
        text=text,
        sections=sections,
        errors=engine_errors,
        warnings=memory_warnings,
    )
