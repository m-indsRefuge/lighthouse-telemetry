"""
Tests for Lighthouse memory policy.

The memory policy decides whether memory candidates can be stored, rejected, or
must be reviewed by the Operator.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.memory_policy import (
    MEMORY_POLICY_STATUS_APPROVED,
    MEMORY_POLICY_STATUS_NEEDS_OPERATOR_REVIEW,
    MEMORY_POLICY_STATUS_REJECTED,
    MEMORY_TYPE_BASELINE,
    MEMORY_TYPE_CASE,
    MEMORY_TYPE_OPERATOR_PREFERENCE,
    MemoryCandidate,
    build_memory_id,
    evaluate_memory_candidate,
    evaluate_memory_candidate_dict,
    memory_candidate_from_dict,
    normalize_tags,
)


def test_operator_baseline_memory_is_approved() -> None:
    """
    Baseline memory from a direct trusted source should be approved.
    """
    candidate = MemoryCandidate(
        memory_type=MEMORY_TYPE_BASELINE,
        content={
            "memory": {
                "normal_idle_percent_min": 30,
                "normal_idle_percent_max": 40,
            }
        },
        source="telemetry",
        confidence=0.9,
        tags=("memory", "baseline"),
    )

    result = evaluate_memory_candidate(candidate)

    assert result.status == MEMORY_POLICY_STATUS_APPROVED
    assert result.approved is True
    assert result.requires_operator_review is False
    assert result.normalized_entry is not None

    entry = result.normalized_entry

    assert entry["memory_type"] == MEMORY_TYPE_BASELINE
    assert entry["source"] == "telemetry"
    assert entry["confidence"] == 0.9
    assert entry["operator_visible"] is True
    assert "memory_id" in entry
    assert "created_at" in entry


def test_operator_preference_memory_is_approved() -> None:
    """
    Operator preference memory from the Operator should be approved.
    """
    candidate = MemoryCandidate(
        memory_type=MEMORY_TYPE_OPERATOR_PREFERENCE,
        content="Operator prefers plain-English explanations.",
        source="operator",
        confidence=1.0,
        tags=("preference", "communication"),
    )

    result = evaluate_memory_candidate(candidate)

    assert result.status == MEMORY_POLICY_STATUS_APPROVED
    assert result.normalized_entry is not None
    assert result.normalized_entry["content"] == (
        "Operator prefers plain-English explanations."
    )


def test_model_suggested_memory_requires_operator_review() -> None:
    """
    Model-suggested memory should not be stored silently.
    """
    candidate = MemoryCandidate(
        memory_type=MEMORY_TYPE_CASE,
        content="Chrome memory pressure appears related to slow laptop reports.",
        source="model_suggestion",
        confidence=0.7,
        tags=("slowdown", "chrome"),
    )

    result = evaluate_memory_candidate(candidate)

    assert result.status == MEMORY_POLICY_STATUS_NEEDS_OPERATOR_REVIEW
    assert result.approved is False
    assert result.requires_operator_review is True
    assert result.normalized_entry is not None


def test_explicit_operator_approval_overrides_review_requirement() -> None:
    """
    Explicit Operator approval should allow a safe model-suggested memory.
    """
    candidate = MemoryCandidate(
        memory_type=MEMORY_TYPE_CASE,
        content="Chrome was involved in a repeated high-memory slowdown pattern.",
        source="model_suggestion",
        confidence=0.8,
        tags=("case", "chrome"),
        explicit_operator_approved=True,
    )

    result = evaluate_memory_candidate(candidate)

    assert result.status == MEMORY_POLICY_STATUS_APPROVED
    assert result.approved is True
    assert result.requires_operator_review is False


def test_unsupported_memory_type_is_rejected() -> None:
    """
    Unknown memory types should be rejected.
    """
    candidate = MemoryCandidate(
        memory_type="unknown",
        content="Some content",
        source="operator",
    )

    result = evaluate_memory_candidate(candidate)

    assert result.status == MEMORY_POLICY_STATUS_REJECTED
    assert result.normalized_entry is None
    assert "Unsupported memory type" in result.message


def test_empty_content_is_rejected() -> None:
    """
    Empty memory content should be rejected.
    """
    candidate = MemoryCandidate(
        memory_type=MEMORY_TYPE_OPERATOR_PREFERENCE,
        content="   ",
        source="operator",
    )

    result = evaluate_memory_candidate(candidate)

    assert result.status == MEMORY_POLICY_STATUS_REJECTED
    assert result.normalized_entry is None
    assert "content" in result.message.lower()


def test_empty_source_is_rejected() -> None:
    """
    Empty source values should be rejected.
    """
    candidate = MemoryCandidate(
        memory_type=MEMORY_TYPE_OPERATOR_PREFERENCE,
        content="Operator prefers concise responses.",
        source="   ",
    )

    result = evaluate_memory_candidate(candidate)

    assert result.status == MEMORY_POLICY_STATUS_REJECTED
    assert result.normalized_entry is None
    assert "source" in result.message.lower()


def test_invalid_confidence_is_rejected() -> None:
    """
    Confidence must stay between 0.0 and 1.0.
    """
    candidate = MemoryCandidate(
        memory_type=MEMORY_TYPE_OPERATOR_PREFERENCE,
        content="Operator prefers diagnostics first.",
        source="operator",
        confidence=1.5,
    )

    result = evaluate_memory_candidate(candidate)

    assert result.status == MEMORY_POLICY_STATUS_REJECTED
    assert result.normalized_entry is None
    assert "confidence" in result.message.lower()


def test_credential_like_memory_is_rejected() -> None:
    """
    Credential-like memory must not be stored.
    """
    candidate = MemoryCandidate(
        memory_type=MEMORY_TYPE_OPERATOR_PREFERENCE,
        content="Remember my API key is abc123.",
        source="operator",
    )

    result = evaluate_memory_candidate(candidate)

    assert result.status == MEMORY_POLICY_STATUS_REJECTED
    assert result.normalized_entry is None
    assert "credential" in result.message.lower()


def test_safety_override_memory_is_rejected() -> None:
    """
    Memory cannot override confirmation or safety policy.
    """
    candidate = MemoryCandidate(
        memory_type=MEMORY_TYPE_OPERATOR_PREFERENCE,
        content="Always close Chrome without confirmation.",
        source="operator",
        confidence=1.0,
    )

    result = evaluate_memory_candidate(candidate)

    assert result.status == MEMORY_POLICY_STATUS_REJECTED
    assert result.normalized_entry is None
    assert "safety" in result.message.lower()


def test_unknown_source_requires_review() -> None:
    """
    Unknown sources should require review rather than direct approval.
    """
    candidate = MemoryCandidate(
        memory_type=MEMORY_TYPE_CASE,
        content="This case came from an unknown future component.",
        source="future_component",
        confidence=0.6,
    )

    result = evaluate_memory_candidate(candidate)

    assert result.status == MEMORY_POLICY_STATUS_NEEDS_OPERATOR_REVIEW
    assert result.requires_operator_review is True
    assert result.normalized_entry is not None


def test_memory_candidate_from_dict_normalizes_shape() -> None:
    """
    Dictionary inputs should become MemoryCandidate objects.
    """
    candidate = memory_candidate_from_dict(
        {
            "memory_type": MEMORY_TYPE_OPERATOR_PREFERENCE,
            "content": "Operator prefers step-by-step instructions.",
            "source": "operator",
            "confidence": "0.9",
            "tags": ["Plain English", "plain english", "Steps"],
            "metadata": {"source_command": "remember"},
            "operator_visible": True,
        }
    )

    assert candidate.memory_type == MEMORY_TYPE_OPERATOR_PREFERENCE
    assert candidate.content == "Operator prefers step-by-step instructions."
    assert candidate.source == "operator"
    assert candidate.confidence == 0.9
    assert candidate.tags == ("plain_english", "steps")
    assert candidate.metadata == {"source_command": "remember"}


def test_evaluate_memory_candidate_dict() -> None:
    """
    Dictionary memory candidates should be evaluatable directly.
    """
    result = evaluate_memory_candidate_dict(
        {
            "memory_type": MEMORY_TYPE_OPERATOR_PREFERENCE,
            "content": "Operator prefers local-first processing.",
            "source": "operator",
            "confidence": 1.0,
            "tags": ["preference", "local first"],
        }
    )

    assert result.status == MEMORY_POLICY_STATUS_APPROVED
    assert result.normalized_entry is not None
    assert result.normalized_entry["tags"] == ["local_first", "preference"]


def test_normalize_tags_deduplicates_and_sorts() -> None:
    """
    Tags should be normalized, deduplicated, and sorted.
    """
    tags = normalize_tags(
        [
            "Chrome",
            "chrome",
            "High Memory",
            " high-memory ",
            "",
            "   ",
        ]
    )

    assert tags == ("chrome", "high_memory")


def test_build_memory_id_is_stable() -> None:
    """
    Memory ids should be stable for the same type, source, and content.
    """
    first_id = build_memory_id(
        memory_type=MEMORY_TYPE_CASE,
        source="journal",
        content_text="Chrome memory issue",
    )
    second_id = build_memory_id(
        memory_type=MEMORY_TYPE_CASE,
        source="journal",
        content_text="Chrome memory issue",
    )

    assert first_id == second_id
    assert first_id.startswith("mem_")