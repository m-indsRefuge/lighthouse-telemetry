"""
Confirmation journaling for Lighthouse.

This module records target-resolution and confirmation-gate decisions into the
existing Lighthouse action journal.

It does not execute tools.
It does not accept confirmation input from the CLI.
It does not change the operating system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.action_journal import append_journal_entry, utc_timestamp
from app.services.confirmation_gate import ConfirmationRequest, ConfirmationResult
from app.services.target_resolver import TargetResolution


EVENT_TYPE_TARGET_CONFIRMATION_PREVIEW = "target_confirmation_preview"
EVENT_TYPE_CONFIRMATION_RESULT = "confirmation_result"

CONFIRMATION_JOURNAL_STATUS_OK = "ok"
CONFIRMATION_JOURNAL_STATUS_ERROR = "error"

CONFIRMATION_JOURNAL_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ConfirmationJournalWriteResult:
    """
    Result of writing a confirmation-related journal entry.
    """

    status: str
    message: str
    path: str
    entry: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable result shape.
        """
        return {
            "status": self.status,
            "message": self.message,
            "path": self.path,
            "entry": self.entry,
        }


def _safe_append_journal_entry(entry: dict[str, Any]) -> ConfirmationJournalWriteResult:
    """
    Append a journal entry and normalize the result shape.
    """
    write_result = append_journal_entry(entry)

    status = getattr(write_result, "status", CONFIRMATION_JOURNAL_STATUS_ERROR)
    message = getattr(write_result, "message", "Unable to write journal entry.")
    path = str(getattr(write_result, "path", ""))

    if status == CONFIRMATION_JOURNAL_STATUS_OK:
        return ConfirmationJournalWriteResult(
            status=CONFIRMATION_JOURNAL_STATUS_OK,
            message=message,
            path=path,
            entry=entry,
        )

    return ConfirmationJournalWriteResult(
        status=CONFIRMATION_JOURNAL_STATUS_ERROR,
        message=message,
        path=path,
        entry=entry,
    )


def build_target_confirmation_preview_entry(
    *,
    user_request: str,
    tool_name: str,
    target_resolution: TargetResolution,
    confirmation_request: ConfirmationRequest,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """
    Build a journal entry for a target-aware confirmation preview.

    This records what Lighthouse showed to the Operator before any future
    confirmation or action execution.
    """
    return {
        "schema_version": CONFIRMATION_JOURNAL_SCHEMA_VERSION,
        "event_type": EVENT_TYPE_TARGET_CONFIRMATION_PREVIEW,
        "timestamp": timestamp or utc_timestamp(),
        "user_request": user_request,
        "tool_name": tool_name,
        "target_resolution": {
            "status": target_resolution.status,
            "target": target_resolution.target,
            "display_name": target_resolution.display_name,
            "confidence": target_resolution.confidence,
            "requires_operator_review": target_resolution.requires_operator_review,
            "candidate_count": len(target_resolution.candidates),
            "candidates": [
                {
                    "target": candidate.target,
                    "display_name": candidate.display_name,
                    "confidence": candidate.confidence,
                    "reason": candidate.reason,
                    "source": candidate.source,
                }
                for candidate in target_resolution.candidates
            ],
        },
        "confirmation_request": {
            "status": confirmation_request.status,
            "required_phrase": confirmation_request.required_phrase,
            "target": confirmation_request.target,
            "risk_level": confirmation_request.risk_level,
            "requires_confirmation": confirmation_request.requires_confirmation,
            "requires_target": confirmation_request.requires_target,
            "executable_after_confirmation": (
                confirmation_request.executable_after_confirmation
            ),
        },
        "safety": {
            "action_executed": False,
            "confirmation_input_accepted": False,
            "preview_only": True,
        },
    }


def record_target_confirmation_preview(
    *,
    user_request: str,
    tool_name: str,
    target_resolution: TargetResolution,
    confirmation_request: ConfirmationRequest,
) -> ConfirmationJournalWriteResult:
    """
    Record a target-aware confirmation preview in the action journal.
    """
    entry = build_target_confirmation_preview_entry(
        user_request=user_request,
        tool_name=tool_name,
        target_resolution=target_resolution,
        confirmation_request=confirmation_request,
    )

    return _safe_append_journal_entry(entry)


def build_confirmation_result_entry(
    *,
    user_request: str,
    confirmation_result: ConfirmationResult,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """
    Build a journal entry for a future confirmation validation result.

    This can record accepted or refused confirmation input, but it does not
    execute the action.
    """
    return {
        "schema_version": CONFIRMATION_JOURNAL_SCHEMA_VERSION,
        "event_type": EVENT_TYPE_CONFIRMATION_RESULT,
        "timestamp": timestamp or utc_timestamp(),
        "user_request": user_request,
        "tool_name": confirmation_result.tool_name,
        "target": confirmation_result.target,
        "confirmation_result": {
            "status": confirmation_result.status,
            "accepted": confirmation_result.accepted,
            "message": confirmation_result.message,
            "required_phrase": confirmation_result.required_phrase,
        },
        "confirmation_request": {
            "status": confirmation_result.request.status,
            "target": confirmation_result.request.target,
            "risk_level": confirmation_result.request.risk_level,
            "requires_confirmation": confirmation_result.request.requires_confirmation,
            "requires_target": confirmation_result.request.requires_target,
            "executable_after_confirmation": (
                confirmation_result.request.executable_after_confirmation
            ),
        },
        "safety": {
            "action_executed": False,
            "confirmation_input_accepted": confirmation_result.accepted,
            "preview_only": False,
        },
    }


def record_confirmation_result(
    *,
    user_request: str,
    confirmation_result: ConfirmationResult,
) -> ConfirmationJournalWriteResult:
    """
    Record a future confirmation validation result in the action journal.
    """
    entry = build_confirmation_result_entry(
        user_request=user_request,
        confirmation_result=confirmation_result,
    )

    return _safe_append_journal_entry(entry)