"""
Target resolver for Lighthouse.

The target resolver turns an Operator's natural-language request into a
candidate target for a specific tool.

It does not execute tools.
It does not confirm actions.
It does not change the operating system.
It only identifies candidate targets that still require Operator review.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from app.services.tool_registry import (
    RISK_BLOCKED,
    get_tool_by_name,
    get_tool_safety_summary,
)


TARGET_STATUS_CANDIDATE_FOUND = "candidate_found"
TARGET_STATUS_NO_TARGET_FOUND = "no_target_found"
TARGET_STATUS_AMBIGUOUS_TARGET = "ambiguous_target"
TARGET_STATUS_NO_TARGET_NEEDED = "no_target_needed"
TARGET_STATUS_UNSUPPORTED_TOOL = "unsupported_tool"
TARGET_STATUS_BLOCKED_TOOL = "blocked_tool"
TARGET_STATUS_UNKNOWN_TOOL = "unknown_tool"

TARGET_CONFIDENCE_HIGH = "high"
TARGET_CONFIDENCE_MEDIUM = "medium"
TARGET_CONFIDENCE_LOW = "low"
TARGET_CONFIDENCE_NONE = "none"

SUPPORTED_TARGET_TOOLS = {
    "close_selected_process",
}


@dataclass(frozen=True)
class TargetAlias:
    """
    Static alias mapping for a target.

    Example:
        "Chrome" -> "chrome.exe"
    """

    target: str
    display_name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class TargetCandidate:
    """
    Candidate target detected from an Operator request.
    """

    target: str
    display_name: str
    confidence: str
    reason: str
    source: str = "alias_table"

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable target candidate shape.
        """
        return {
            "target": self.target,
            "display_name": self.display_name,
            "confidence": self.confidence,
            "reason": self.reason,
            "source": self.source,
        }


@dataclass(frozen=True)
class TargetResolution:
    """
    Result of resolving a target for a tool request.
    """

    status: str
    tool_name: str
    user_request: str
    target: str | None
    display_name: str | None
    confidence: str
    candidates: tuple[TargetCandidate, ...]
    requires_operator_review: bool
    message: str
    requires_target: bool
    safety_summary: dict[str, object]

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable target resolution shape.
        """
        return {
            "status": self.status,
            "tool_name": self.tool_name,
            "user_request": self.user_request,
            "target": self.target,
            "display_name": self.display_name,
            "confidence": self.confidence,
            "candidates": [
                candidate.to_dict()
                for candidate in self.candidates
            ],
            "requires_operator_review": self.requires_operator_review,
            "message": self.message,
            "requires_target": self.requires_target,
            "safety_summary": self.safety_summary,
        }


PROCESS_TARGET_ALIASES: tuple[TargetAlias, ...] = (
    TargetAlias(
        target="chrome.exe",
        display_name="Google Chrome",
        aliases=(
            "chrome",
            "google chrome",
            "chrome.exe",
        ),
    ),
    TargetAlias(
        target="msedge.exe",
        display_name="Microsoft Edge",
        aliases=(
            "edge",
            "microsoft edge",
            "msedge",
            "msedge.exe",
        ),
    ),
    TargetAlias(
        target="firefox.exe",
        display_name="Mozilla Firefox",
        aliases=(
            "firefox",
            "mozilla firefox",
            "firefox.exe",
        ),
    ),
    TargetAlias(
        target="brave.exe",
        display_name="Brave",
        aliases=(
            "brave",
            "brave browser",
            "brave.exe",
        ),
    ),
    TargetAlias(
        target="Code.exe",
        display_name="Visual Studio Code",
        aliases=(
            "vscode",
            "vs code",
            "visual studio code",
            "code.exe",
        ),
    ),
    TargetAlias(
        target="notepad.exe",
        display_name="Notepad",
        aliases=(
            "notepad",
            "notepad.exe",
        ),
    ),
    TargetAlias(
        target="discord.exe",
        display_name="Discord",
        aliases=(
            "discord",
            "discord.exe",
        ),
    ),
    TargetAlias(
        target="spotify.exe",
        display_name="Spotify",
        aliases=(
            "spotify",
            "spotify.exe",
        ),
    ),
    TargetAlias(
        target="teams.exe",
        display_name="Microsoft Teams",
        aliases=(
            "teams",
            "microsoft teams",
            "teams.exe",
            "ms teams",
        ),
    ),
)

AMBIGUOUS_PROCESS_PHRASES = (
    "browser",
    "the browser",
    "web browser",
    "internet browser",
)


def normalize_tool_name(tool_name: str) -> str:
    """
    Normalize tool names for lookup.
    """
    return tool_name.strip().lower()


def normalize_text_for_matching(value: str) -> str:
    """
    Normalize user text for conservative alias matching.
    """
    lowered = value.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", lowered)
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized.strip()


def contains_phrase(normalized_text: str, phrase: str) -> bool:
    """
    Return True when a normalized phrase appears as a whole phrase.
    """
    normalized_phrase = normalize_text_for_matching(phrase)

    if not normalized_phrase:
        return False

    pattern = rf"(?<![a-z0-9]){re.escape(normalized_phrase)}(?![a-z0-9])"

    return re.search(pattern, normalized_text) is not None


def get_alias_confidence(alias: str) -> str:
    """
    Return a conservative confidence score for an alias match.
    """
    cleaned_alias = alias.strip().lower()

    if cleaned_alias.endswith(".exe"):
        return TARGET_CONFIDENCE_HIGH

    if " " in cleaned_alias:
        return TARGET_CONFIDENCE_MEDIUM

    return TARGET_CONFIDENCE_MEDIUM


def get_confidence_rank(confidence: str) -> int:
    """
    Convert confidence labels into sortable ranks.
    """
    if confidence == TARGET_CONFIDENCE_HIGH:
        return 3

    if confidence == TARGET_CONFIDENCE_MEDIUM:
        return 2

    if confidence == TARGET_CONFIDENCE_LOW:
        return 1

    return 0


def build_candidate_from_alias(
    target_alias: TargetAlias,
    matched_alias: str,
) -> TargetCandidate:
    """
    Build a candidate from a static alias match.
    """
    return TargetCandidate(
        target=target_alias.target,
        display_name=target_alias.display_name,
        confidence=get_alias_confidence(matched_alias),
        reason=f"Matched alias '{matched_alias}'.",
    )


def deduplicate_candidates(
    candidates: list[TargetCandidate],
) -> tuple[TargetCandidate, ...]:
    """
    Keep the highest-confidence candidate for each target.
    """
    unique: dict[str, TargetCandidate] = {}

    for candidate in candidates:
        existing_candidate = unique.get(candidate.target)

        if existing_candidate is None:
            unique[candidate.target] = candidate
            continue

        if get_confidence_rank(candidate.confidence) > get_confidence_rank(
            existing_candidate.confidence
        ):
            unique[candidate.target] = candidate

    return tuple(unique.values())


def find_process_candidates(user_request: str) -> tuple[TargetCandidate, ...]:
    """
    Find process candidates from the known process alias table.

    All aliases are checked so that a more specific alias such as chrome.exe
    can outrank a broader alias such as chrome.
    """
    normalized_request = normalize_text_for_matching(user_request)
    candidates: list[TargetCandidate] = []

    for target_alias in PROCESS_TARGET_ALIASES:
        for alias in target_alias.aliases:
            if contains_phrase(normalized_request, alias):
                candidates.append(
                    build_candidate_from_alias(
                        target_alias=target_alias,
                        matched_alias=alias,
                    )
                )

    return deduplicate_candidates(candidates)


def build_ambiguous_browser_candidates() -> tuple[TargetCandidate, ...]:
    """
    Return common browser candidates for a generic browser request.
    """
    browser_targets = {
        "chrome.exe",
        "msedge.exe",
        "firefox.exe",
        "brave.exe",
    }

    candidates = [
        TargetCandidate(
            target=target_alias.target,
            display_name=target_alias.display_name,
            confidence=TARGET_CONFIDENCE_LOW,
            reason="The request mentioned a browser, but did not specify which one.",
        )
        for target_alias in PROCESS_TARGET_ALIASES
        if target_alias.target in browser_targets
    ]

    return tuple(candidates)


def request_mentions_generic_browser(user_request: str) -> bool:
    """
    Return True when the request refers to a browser without naming one.
    """
    normalized_request = normalize_text_for_matching(user_request)

    return any(
        contains_phrase(normalized_request, phrase)
        for phrase in AMBIGUOUS_PROCESS_PHRASES
    )


def _unknown_tool_resolution(
    tool_name: str,
    user_request: str,
) -> TargetResolution:
    """
    Return an unknown-tool target resolution.
    """
    return TargetResolution(
        status=TARGET_STATUS_UNKNOWN_TOOL,
        tool_name=tool_name,
        user_request=user_request,
        target=None,
        display_name=None,
        confidence=TARGET_CONFIDENCE_NONE,
        candidates=(),
        requires_operator_review=True,
        message="Unknown tools cannot have targets resolved.",
        requires_target=False,
        safety_summary={
            **get_tool_safety_summary(tool_name),
            "target_resolution_allowed": False,
            "reason": "Unknown tools cannot have targets resolved.",
        },
    )


def _blocked_tool_resolution(
    tool_name: str,
    user_request: str,
    requires_target: bool,
) -> TargetResolution:
    """
    Return a blocked-tool target resolution.
    """
    return TargetResolution(
        status=TARGET_STATUS_BLOCKED_TOOL,
        tool_name=tool_name,
        user_request=user_request,
        target=None,
        display_name=None,
        confidence=TARGET_CONFIDENCE_NONE,
        candidates=(),
        requires_operator_review=True,
        message="Blocked tools cannot have executable targets resolved.",
        requires_target=requires_target,
        safety_summary={
            **get_tool_safety_summary(tool_name),
            "target_resolution_allowed": False,
            "reason": "Blocked tools cannot have executable targets resolved.",
        },
    )


def _no_target_needed_resolution(
    tool_name: str,
    user_request: str,
) -> TargetResolution:
    """
    Return a no-target-needed resolution.
    """
    return TargetResolution(
        status=TARGET_STATUS_NO_TARGET_NEEDED,
        tool_name=tool_name,
        user_request=user_request,
        target=None,
        display_name=None,
        confidence=TARGET_CONFIDENCE_NONE,
        candidates=(),
        requires_operator_review=False,
        message="This tool does not require a target.",
        requires_target=False,
        safety_summary={
            **get_tool_safety_summary(tool_name),
            "target_resolution_allowed": False,
            "reason": "This tool does not require a target.",
        },
    )


def _unsupported_tool_resolution(
    tool_name: str,
    user_request: str,
    requires_target: bool,
) -> TargetResolution:
    """
    Return an unsupported-tool target resolution.
    """
    return TargetResolution(
        status=TARGET_STATUS_UNSUPPORTED_TOOL,
        tool_name=tool_name,
        user_request=user_request,
        target=None,
        display_name=None,
        confidence=TARGET_CONFIDENCE_NONE,
        candidates=(),
        requires_operator_review=True,
        message="Target resolution is not yet supported for this tool.",
        requires_target=requires_target,
        safety_summary={
            **get_tool_safety_summary(tool_name),
            "target_resolution_allowed": False,
            "reason": "Target resolution is not yet supported for this tool.",
        },
    )


def _no_target_found_resolution(
    tool_name: str,
    user_request: str,
) -> TargetResolution:
    """
    Return a no-target-found resolution.
    """
    return TargetResolution(
        status=TARGET_STATUS_NO_TARGET_FOUND,
        tool_name=tool_name,
        user_request=user_request,
        target=None,
        display_name=None,
        confidence=TARGET_CONFIDENCE_NONE,
        candidates=(),
        requires_operator_review=True,
        message="No candidate target was detected. Operator clarification is required.",
        requires_target=True,
        safety_summary={
            **get_tool_safety_summary(tool_name),
            "target_resolution_allowed": True,
            "reason": "No candidate target was detected.",
        },
    )


def _ambiguous_target_resolution(
    tool_name: str,
    user_request: str,
    candidates: tuple[TargetCandidate, ...],
) -> TargetResolution:
    """
    Return an ambiguous-target resolution.
    """
    return TargetResolution(
        status=TARGET_STATUS_AMBIGUOUS_TARGET,
        tool_name=tool_name,
        user_request=user_request,
        target=None,
        display_name=None,
        confidence=TARGET_CONFIDENCE_LOW,
        candidates=candidates,
        requires_operator_review=True,
        message="Multiple possible targets were detected. Operator review is required.",
        requires_target=True,
        safety_summary={
            **get_tool_safety_summary(tool_name),
            "target_resolution_allowed": True,
            "reason": "Multiple possible targets were detected.",
        },
    )


def _candidate_found_resolution(
    tool_name: str,
    user_request: str,
    candidate: TargetCandidate,
) -> TargetResolution:
    """
    Return a single-candidate target resolution.
    """
    return TargetResolution(
        status=TARGET_STATUS_CANDIDATE_FOUND,
        tool_name=tool_name,
        user_request=user_request,
        target=candidate.target,
        display_name=candidate.display_name,
        confidence=candidate.confidence,
        candidates=(candidate,),
        requires_operator_review=True,
        message=(
            "A candidate target was detected. Operator review is still required "
            "before confirmation or execution."
        ),
        requires_target=True,
        safety_summary={
            **get_tool_safety_summary(tool_name),
            "target_resolution_allowed": True,
            "reason": "A candidate target was detected.",
        },
    )


def resolve_process_target(
    tool_name: str,
    user_request: str,
) -> TargetResolution:
    """
    Resolve a process target from an Operator request.
    """
    candidates = find_process_candidates(user_request)

    if len(candidates) == 1:
        return _candidate_found_resolution(
            tool_name=tool_name,
            user_request=user_request,
            candidate=candidates[0],
        )

    if len(candidates) > 1:
        return _ambiguous_target_resolution(
            tool_name=tool_name,
            user_request=user_request,
            candidates=candidates,
        )

    if request_mentions_generic_browser(user_request):
        return _ambiguous_target_resolution(
            tool_name=tool_name,
            user_request=user_request,
            candidates=build_ambiguous_browser_candidates(),
        )

    return _no_target_found_resolution(
        tool_name=tool_name,
        user_request=user_request,
    )


def resolve_target_for_tool(
    tool_name: str,
    user_request: str,
) -> TargetResolution:
    """
    Resolve a candidate target for a specific tool request.

    The returned target is never treated as confirmed. It is only a candidate
    that future layers may show to the Operator for review.
    """
    normalized_tool_name = normalize_tool_name(tool_name)
    tool = get_tool_by_name(normalized_tool_name)

    if tool is None:
        return _unknown_tool_resolution(
            tool_name=normalized_tool_name,
            user_request=user_request,
        )

    if tool.risk_level == RISK_BLOCKED:
        return _blocked_tool_resolution(
            tool_name=normalized_tool_name,
            user_request=user_request,
            requires_target=tool.requires_target,
        )

    if not tool.requires_target:
        return _no_target_needed_resolution(
            tool_name=normalized_tool_name,
            user_request=user_request,
        )

    if normalized_tool_name not in SUPPORTED_TARGET_TOOLS:
        return _unsupported_tool_resolution(
            tool_name=normalized_tool_name,
            user_request=user_request,
            requires_target=tool.requires_target,
        )

    if normalized_tool_name == "close_selected_process":
        return resolve_process_target(
            tool_name=normalized_tool_name,
            user_request=user_request,
        )

    return _unsupported_tool_resolution(
        tool_name=normalized_tool_name,
        user_request=user_request,
        requires_target=tool.requires_target,
    )


def format_target_resolution(resolution: TargetResolution) -> str:
    """
    Format a target resolution for CLI display.
    """
    lines = [
        "",
        "LIGHTHOUSE TARGET RESOLUTION",
        "=" * 52,
        f"Status: {resolution.status}",
        f"Tool: {resolution.tool_name}",
        f"Message: {resolution.message}",
        f"Requires target: {'yes' if resolution.requires_target else 'no'}",
        (
            "Operator review required: "
            f"{'yes' if resolution.requires_operator_review else 'no'}"
        ),
        f"Confidence: {resolution.confidence}",
        f"Target: {resolution.target if resolution.target else 'none'}",
        (
            "Display name: "
            f"{resolution.display_name if resolution.display_name else 'none'}"
        ),
    ]

    if resolution.candidates:
        lines.extend(
            [
                "",
                "Candidate targets:",
                "-" * 52,
            ]
        )

        for candidate in resolution.candidates:
            lines.append(f"- {candidate.display_name} ({candidate.target})")
            lines.append(f"  Confidence: {candidate.confidence}")
            lines.append(f"  Reason: {candidate.reason}")

    lines.append("=" * 52)

    return "\n".join(lines)