"""
Memory policy for Lighthouse.

This module decides what is safe, useful, and appropriate to store as memory.

The engine owns memory decisions.
The model may suggest memory candidates, but this policy must approve, reject,
or require Operator review before storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any


MEMORY_POLICY_SCHEMA_VERSION = 1
MEMORY_POLICY_VERSION = "memory_policy_v1"

MEMORY_POLICY_STATUS_APPROVED = "approved"
MEMORY_POLICY_STATUS_REJECTED = "rejected"
MEMORY_POLICY_STATUS_NEEDS_OPERATOR_REVIEW = "needs_operator_review"

MEMORY_TYPE_BASELINE = "baseline"
MEMORY_TYPE_OPERATOR_PREFERENCE = "operator_preference"
MEMORY_TYPE_CASE = "case"
MEMORY_TYPE_KNOWLEDGE = "knowledge"

SUPPORTED_MEMORY_TYPES = {
    MEMORY_TYPE_BASELINE,
    MEMORY_TYPE_OPERATOR_PREFERENCE,
    MEMORY_TYPE_CASE,
    MEMORY_TYPE_KNOWLEDGE,
}

DIRECT_APPROVAL_SOURCES = {
    "operator",
    "engine",
    "telemetry",
    "journal",
    "system_baseline",
    "knowledge_base",
}

REVIEW_REQUIRED_SOURCES = {
    "model",
    "model_suggestion",
    "llm",
    "assistant",
}

MAX_CONTENT_LENGTH = 5000

SENSITIVE_PATTERNS = (
    r"\bpassword\b",
    r"\bapi[_\s-]?key\b",
    r"\bsecret[_\s-]?key\b",
    r"\bprivate[_\s-]?key\b",
    r"\baccess[_\s-]?token\b",
    r"\brefresh[_\s-]?token\b",
    r"\bbearer[_\s-]?token\b",
    r"\bcredential\b",
)

SAFETY_OVERRIDE_PATTERNS = (
    r"\bbypass confirmation\b",
    r"\bdisable confirmation\b",
    r"\bignore confirmation\b",
    r"\bwithout confirmation\b",
    r"\bskip confirmation\b",
    r"\bignore safety\b",
    r"\bdisable safety\b",
    r"\balways execute\b",
    r"\bdelete automatically\b",
    r"\brun raw command\b",
)


@dataclass(frozen=True)
class MemoryCandidate:
    """
    Candidate memory submitted for policy evaluation.
    """

    memory_type: str
    content: str | dict[str, Any]
    source: str
    confidence: float = 0.5
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] | None = None
    operator_visible: bool = True
    explicit_operator_approved: bool = False

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable memory candidate shape.
        """
        return {
            "memory_type": self.memory_type,
            "content": self.content,
            "source": self.source,
            "confidence": self.confidence,
            "tags": list(self.tags),
            "metadata": self.metadata or {},
            "operator_visible": self.operator_visible,
            "explicit_operator_approved": self.explicit_operator_approved,
        }


@dataclass(frozen=True)
class MemoryPolicyResult:
    """
    Result of evaluating a memory candidate.
    """

    status: str
    message: str
    memory_type: str
    approved: bool
    requires_operator_review: bool
    reasons: tuple[str, ...]
    normalized_entry: dict[str, Any] | None
    candidate: MemoryCandidate

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable policy result shape.
        """
        return {
            "status": self.status,
            "message": self.message,
            "memory_type": self.memory_type,
            "approved": self.approved,
            "requires_operator_review": self.requires_operator_review,
            "reasons": list(self.reasons),
            "normalized_entry": self.normalized_entry,
            "candidate": self.candidate.to_dict(),
        }


def utc_timestamp() -> str:
    """
    Return a UTC timestamp in ISO-8601 format.
    """
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_memory_type(memory_type: str) -> str:
    """
    Normalize memory type names.
    """
    return memory_type.strip().lower()


def normalize_source(source: str) -> str:
    """
    Normalize memory source names.
    """
    return source.strip().lower()


def normalize_tag(tag: str) -> str:
    """
    Normalize one memory tag.
    """
    lowered = tag.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", lowered)
    normalized = re.sub(r"_+", "_", normalized)

    return normalized.strip("_")


def normalize_tags(tags: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    """
    Normalize and deduplicate memory tags.
    """
    if not tags:
        return ()

    normalized_tags = {
        normalize_tag(tag)
        for tag in tags
        if isinstance(tag, str) and normalize_tag(tag)
    }

    return tuple(sorted(normalized_tags))


def content_to_text(content: str | dict[str, Any]) -> str:
    """
    Convert memory content into text for policy checks and hashing.
    """
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False, sort_keys=True)

    return ""


def is_valid_confidence(confidence: float) -> bool:
    """
    Return True when confidence is in the accepted range.
    """
    return 0.0 <= confidence <= 1.0


def contains_pattern(value: str, patterns: tuple[str, ...]) -> bool:
    """
    Return True if a value matches any policy pattern.
    """
    lowered = value.lower()

    return any(re.search(pattern, lowered) is not None for pattern in patterns)


def build_memory_id(
    *,
    memory_type: str,
    source: str,
    content_text: str,
) -> str:
    """
    Build a stable compact memory id from memory content.
    """
    payload = json.dumps(
        {
            "memory_type": memory_type,
            "source": source,
            "content": content_text,
        },
        ensure_ascii=False,
        sort_keys=True,
    )

    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    return f"mem_{digest}"


def build_normalized_entry(candidate: MemoryCandidate) -> dict[str, Any]:
    """
    Build the normalized memory entry that may be stored later.
    """
    memory_type = normalize_memory_type(candidate.memory_type)
    source = normalize_source(candidate.source)
    content_text = content_to_text(candidate.content)
    tags = normalize_tags(candidate.tags)

    return {
        "schema_version": MEMORY_POLICY_SCHEMA_VERSION,
        "policy_version": MEMORY_POLICY_VERSION,
        "memory_id": build_memory_id(
            memory_type=memory_type,
            source=source,
            content_text=content_text,
        ),
        "memory_type": memory_type,
        "content": candidate.content,
        "content_text": content_text,
        "source": source,
        "confidence": candidate.confidence,
        "tags": list(tags),
        "metadata": candidate.metadata or {},
        "operator_visible": candidate.operator_visible,
        "created_at": utc_timestamp(),
    }


def build_policy_result(
    *,
    status: str,
    message: str,
    candidate: MemoryCandidate,
    reasons: tuple[str, ...],
    normalized_entry: dict[str, Any] | None,
) -> MemoryPolicyResult:
    """
    Build a memory policy result.
    """
    return MemoryPolicyResult(
        status=status,
        message=message,
        memory_type=normalize_memory_type(candidate.memory_type),
        approved=status == MEMORY_POLICY_STATUS_APPROVED,
        requires_operator_review=(
            status == MEMORY_POLICY_STATUS_NEEDS_OPERATOR_REVIEW
        ),
        reasons=reasons,
        normalized_entry=normalized_entry,
        candidate=candidate,
    )


def reject_memory(
    *,
    candidate: MemoryCandidate,
    message: str,
    reasons: tuple[str, ...],
) -> MemoryPolicyResult:
    """
    Build a rejected memory policy result.
    """
    return build_policy_result(
        status=MEMORY_POLICY_STATUS_REJECTED,
        message=message,
        candidate=candidate,
        reasons=reasons,
        normalized_entry=None,
    )


def approve_memory(
    *,
    candidate: MemoryCandidate,
    message: str,
    reasons: tuple[str, ...],
) -> MemoryPolicyResult:
    """
    Build an approved memory policy result.
    """
    return build_policy_result(
        status=MEMORY_POLICY_STATUS_APPROVED,
        message=message,
        candidate=candidate,
        reasons=reasons,
        normalized_entry=build_normalized_entry(candidate),
    )


def require_operator_review(
    *,
    candidate: MemoryCandidate,
    message: str,
    reasons: tuple[str, ...],
) -> MemoryPolicyResult:
    """
    Build a memory policy result that requires Operator review.
    """
    return build_policy_result(
        status=MEMORY_POLICY_STATUS_NEEDS_OPERATOR_REVIEW,
        message=message,
        candidate=candidate,
        reasons=reasons,
        normalized_entry=build_normalized_entry(candidate),
    )


def evaluate_memory_candidate(candidate: MemoryCandidate) -> MemoryPolicyResult:
    """
    Evaluate a memory candidate.

    This function does not store memory. It only decides whether a candidate is
    safe enough to store, must be rejected, or needs Operator review.
    """
    memory_type = normalize_memory_type(candidate.memory_type)
    source = normalize_source(candidate.source)
    content_text = content_to_text(candidate.content)

    if memory_type not in SUPPORTED_MEMORY_TYPES:
        return reject_memory(
            candidate=candidate,
            message="Unsupported memory type.",
            reasons=(f"Unsupported memory type: {candidate.memory_type}",),
        )

    if not source:
        return reject_memory(
            candidate=candidate,
            message="Memory source is required.",
            reasons=("Memory source was empty.",),
        )

    if not content_text:
        return reject_memory(
            candidate=candidate,
            message="Memory content is required.",
            reasons=("Memory content was empty.",),
        )

    if len(content_text) > MAX_CONTENT_LENGTH:
        return reject_memory(
            candidate=candidate,
            message="Memory content is too long.",
            reasons=(
                f"Memory content exceeded {MAX_CONTENT_LENGTH} characters.",
            ),
        )

    if not is_valid_confidence(candidate.confidence):
        return reject_memory(
            candidate=candidate,
            message="Memory confidence must be between 0.0 and 1.0.",
            reasons=("Memory confidence was outside the accepted range.",),
        )

    if contains_pattern(content_text, SENSITIVE_PATTERNS):
        return reject_memory(
            candidate=candidate,
            message="Memory appears to contain sensitive credential material.",
            reasons=("Credential-like content must not be stored in memory.",),
        )

    if contains_pattern(content_text, SAFETY_OVERRIDE_PATTERNS):
        return reject_memory(
            candidate=candidate,
            message="Memory attempts to override Lighthouse safety policy.",
            reasons=("Safety or confirmation policy cannot be overridden by memory.",),
        )

    if candidate.explicit_operator_approved:
        return approve_memory(
            candidate=candidate,
            message="Memory approved by explicit Operator approval.",
            reasons=("Explicit Operator approval was provided.",),
        )

    if source in DIRECT_APPROVAL_SOURCES:
        return approve_memory(
            candidate=candidate,
            message="Memory approved by policy.",
            reasons=(f"Source '{source}' is allowed for direct memory storage.",),
        )

    if source in REVIEW_REQUIRED_SOURCES:
        return require_operator_review(
            candidate=candidate,
            message="Memory requires Operator review before storage.",
            reasons=(f"Source '{source}' requires Operator review.",),
        )

    return require_operator_review(
        candidate=candidate,
        message="Unknown memory source requires Operator review before storage.",
        reasons=(f"Source '{source}' is not directly trusted.",),
    )


def memory_candidate_from_dict(data: dict[str, Any]) -> MemoryCandidate:
    """
    Build a MemoryCandidate from a dictionary.
    """
    raw_tags = data.get("tags", ())

    if isinstance(raw_tags, list):
        tags = tuple(str(tag) for tag in raw_tags)
    elif isinstance(raw_tags, tuple):
        tags = tuple(str(tag) for tag in raw_tags)
    else:
        tags = ()

    raw_confidence = data.get("confidence", 0.5)

    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        confidence = -1.0

    content = data.get("content", "")

    if not isinstance(content, str) and not isinstance(content, dict):
        content = ""

    metadata = data.get("metadata")

    if not isinstance(metadata, dict):
        metadata = {}

    return MemoryCandidate(
        memory_type=str(data.get("memory_type", "")),
        content=content,
        source=str(data.get("source", "")),
        confidence=confidence,
        tags=normalize_tags(tags),
        metadata=metadata,
        operator_visible=bool(data.get("operator_visible", True)),
        explicit_operator_approved=bool(
            data.get("explicit_operator_approved", False)
        ),
    )


def evaluate_memory_candidate_dict(data: dict[str, Any]) -> MemoryPolicyResult:
    """
    Evaluate a memory candidate represented as a dictionary.
    """
    return evaluate_memory_candidate(memory_candidate_from_dict(data))