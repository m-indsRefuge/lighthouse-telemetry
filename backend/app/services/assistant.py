"""
Assistant intent router for Lighthouse.

This module turns natural-language user input into known safe Lighthouse commands.

It does not execute actions directly.
It only classifies user intent and returns a canonical command that the CLI
is allowed to run.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AssistantIntent:
    """
    Result of classifying a user command.
    """

    status: str
    intent: str | None
    canonical_command: str | None
    confidence: float
    reason: str


def normalize_text(text: str) -> str:
    """
    Normalize user input for simple rule-based matching.
    """
    cleaned = text.lower().strip()

    replacements = {
        "?": "",
        "!": "",
        ".": "",
        ",": "",
        ":": "",
        ";": "",
        "'": "",
        '"': "",
    }

    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)

    return " ".join(cleaned.split())


def contains_any(text: str, phrases: list[str]) -> bool:
    """
    Return True if any phrase appears in the normalized user input.

    Single-word phrases must match whole words.
    Multi-word phrases can match as phrases.
    This prevents words like "saved" from incorrectly matching "save".
    """
    words = set(text.split())

    for phrase in phrases:
        if " " in phrase:
            if phrase in text:
                return True
        elif phrase in words:
            return True

    return False


def classify_user_intent(user_input: str) -> AssistantIntent:
    """
    Classify natural-language input into a known Lighthouse command.

    Allowed canonical commands:
    - snapshot
    - health
    - cpu
    - memory
    - disk
    - processes
    - diagnose
    - events
    - save
    - history
    - last
    - help
    - quit
    """
    text = normalize_text(user_input)

    if not text:
        return AssistantIntent(
            status="unknown",
            intent=None,
            canonical_command=None,
            confidence=0.0,
            reason="No input provided.",
        )

    if contains_any(text, ["quit", "exit", "close lighthouse", "stop lighthouse"]):
        return AssistantIntent(
            status="ok",
            intent="quit",
            canonical_command="quit",
            confidence=1.0,
            reason="User wants to exit Lighthouse.",
        )

    if contains_any(text, ["help", "commands", "what can you do", "how do i use this"]):
        return AssistantIntent(
            status="ok",
            intent="help",
            canonical_command="help",
            confidence=0.95,
            reason="User is asking for available commands.",
        )

    if contains_any(
        text,
        [
            "save",
            "save this",
            "save report",
            "save snapshot",
            "store this",
            "record this",
            "write this to file",
            "export snapshot",
        ],
    ):
        return AssistantIntent(
            status="ok",
            intent="save",
            canonical_command="save",
            confidence=0.95,
            reason="User wants to save a local snapshot.",
        )

    if contains_any(
        text,
        [
            "history",
            "show history",
            "saved reports",
            "saved snapshots",
            "previous snapshots",
            "list snapshots",
            "old reports",
        ],
    ):
        return AssistantIntent(
            status="ok",
            intent="history",
            canonical_command="history",
            confidence=0.95,
            reason="User wants to list saved snapshots.",
        )

    if contains_any(
        text,
        [
            "last report",
            "latest report",
            "last snapshot",
            "latest snapshot",
            "most recent report",
            "most recent snapshot",
            "show last",
            "show latest",
        ],
    ):
        return AssistantIntent(
            status="ok",
            intent="last",
            canonical_command="last",
            confidence=0.95,
            reason="User wants the most recent saved snapshot summary.",
        )

    if contains_any(
        text,
        [
            "crash",
            "crashed",
            "blue screen",
            "bsod",
            "unexpected shutdown",
            "shutdown unexpectedly",
            "restarted unexpectedly",
            "power loss",
            "event log",
            "events",
            "check events",
            "did my laptop crash",
            "did my pc crash",
        ],
    ):
        return AssistantIntent(
            status="ok",
            intent="events",
            canonical_command="events",
            confidence=0.9,
            reason="User is asking about crash or event-log evidence.",
        )

    if contains_any(
        text,
        [
            "slow",
            "sluggish",
            "lag",
            "lagging",
            "performance",
            "diagnose",
            "what is wrong",
            "whats wrong",
            "why is my laptop slow",
            "why is my pc slow",
            "is something wrong",
            "check my computer",
            "check my laptop",
            "check my pc",
        ],
    ):
        return AssistantIntent(
            status="ok",
            intent="diagnose",
            canonical_command="diagnose",
            confidence=0.9,
            reason="User is asking for a diagnostic explanation.",
        )

    if contains_any(
        text,
        [
            "healthy",
            "health",
            "is my laptop ok",
            "is my laptop okay",
            "is my pc ok",
            "is my computer ok",
            "system status",
            "overall status",
            "how is my computer",
            "how is my laptop",
        ],
    ):
        return AssistantIntent(
            status="ok",
            intent="health",
            canonical_command="health",
            confidence=0.85,
            reason="User is asking for overall system health.",
        )

    if contains_any(
        text,
        [
            "process",
            "processes",
            "top processes",
            "what is using memory",
            "what is using ram",
            "apps using memory",
            "programs using memory",
            "highest memory",
        ],
    ):
        return AssistantIntent(
            status="ok",
            intent="processes",
            canonical_command="processes",
            confidence=0.85,
            reason="User is asking about running processes.",
        )

    if contains_any(text, ["cpu", "processor", "cores", "core usage"]):
        return AssistantIntent(
            status="ok",
            intent="cpu",
            canonical_command="cpu",
            confidence=0.85,
            reason="User is asking about CPU telemetry.",
        )

    if contains_any(text, ["memory", "ram"]):
        return AssistantIntent(
            status="ok",
            intent="memory",
            canonical_command="memory",
            confidence=0.85,
            reason="User is asking about memory telemetry.",
        )

    if contains_any(
        text,
        [
            "disk",
            "storage",
            "drive",
            "free space",
            "space left",
            "system drive",
            "c drive",
        ],
    ):
        return AssistantIntent(
            status="ok",
            intent="disk",
            canonical_command="disk",
            confidence=0.85,
            reason="User is asking about disk telemetry.",
        )

    if contains_any(
        text,
        [
            "snapshot",
            "full report",
            "system report",
            "telemetry report",
            "run report",
            "show report",
            "full telemetry",
        ],
    ):
        return AssistantIntent(
            status="ok",
            intent="snapshot",
            canonical_command="snapshot",
            confidence=0.85,
            reason="User is asking for a full telemetry report.",
        )

    return AssistantIntent(
        status="unknown",
        intent=None,
        canonical_command=None,
        confidence=0.0,
        reason="No matching Lighthouse intent found.",
    )