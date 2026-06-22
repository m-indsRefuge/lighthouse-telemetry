"""
Windows-native evidence schema for Lighthouse.

This module defines the normalized evidence shape used by Windows-native
collectors such as CIM/WMI, performance counters, Event Logs, Defender, and
power diagnostics.

It does not collect telemetry by itself.
It does not call the model.
It does not execute tools.
It does not mutate the operating system.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"
STATUS_UNKNOWN = "unknown"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_UNKNOWN = "unknown"

TRUST_TIER_1_READ_ONLY = "tier_1_read_only"
TRUST_TIER_2_PERMISSIONED_DIAGNOSTIC = "tier_2_permissioned_diagnostic"
TRUST_TIER_3_PERMISSIONED_REPAIR_OR_ACTION = "tier_3_permissioned_repair_or_action"

PRIVACY_LOW = "low"
PRIVACY_MEDIUM = "medium"
PRIVACY_HIGH = "high"

ALLOWED_STATUSES = frozenset(
    {
        STATUS_OK,
        STATUS_WARNING,
        STATUS_ERROR,
        STATUS_UNKNOWN,
    }
)

ALLOWED_CONFIDENCE_VALUES = frozenset(
    {
        CONFIDENCE_HIGH,
        CONFIDENCE_MEDIUM,
        CONFIDENCE_LOW,
        CONFIDENCE_UNKNOWN,
    }
)

ALLOWED_TRUST_TIERS = frozenset(
    {
        TRUST_TIER_1_READ_ONLY,
        TRUST_TIER_2_PERMISSIONED_DIAGNOSTIC,
        TRUST_TIER_3_PERMISSIONED_REPAIR_OR_ACTION,
    }
)

ALLOWED_PRIVACY_VALUES = frozenset(
    {
        PRIVACY_LOW,
        PRIVACY_MEDIUM,
        PRIVACY_HIGH,
    }
)

REQUIRED_STRING_FIELDS = frozenset(
    {
        "source",
        "collector",
        "signal",
        "status",
        "confidence",
        "trust_tier",
        "privacy",
        "collected_at",
    }
)

REQUIRED_BOOLEAN_FIELDS = frozenset(
    {
        "requires_admin",
        "permission_required",
    }
)


def utc_now_iso() -> str:
    """
    Return an ISO-like UTC timestamp.
    """
    return datetime.now(timezone.utc).isoformat()


def normalize_string(value: Any) -> str:
    """
    Normalize any value to a stripped string.
    """
    if value is None:
        return ""

    return str(value).strip()


def normalize_string_list(values: list[Any] | tuple[Any, ...] | None) -> list[str]:
    """
    Normalize a sequence into a list of non-empty strings.
    """
    if values is None:
        return []

    normalized: list[str] = []

    for value in values:
        text = normalize_string(value)

        if text:
            normalized.append(text)

    return normalized


def build_windows_evidence_item(
    *,
    source: str,
    collector: str,
    signal: str,
    value: Any,
    status: str = STATUS_OK,
    confidence: str = CONFIDENCE_HIGH,
    trust_tier: str = TRUST_TIER_1_READ_ONLY,
    requires_admin: bool = False,
    privacy: str = PRIVACY_LOW,
    permission_required: bool = False,
    plain_meaning: str = "",
    recommended_next_step: str | None = None,
    raw: dict[str, Any] | None = None,
    errors: list[Any] | tuple[Any, ...] | None = None,
    warnings: list[Any] | tuple[Any, ...] | None = None,
    collected_at: str | None = None,
) -> dict[str, Any]:
    """
    Build one normalized Windows evidence item.
    """
    return {
        "source": normalize_string(source),
        "collector": normalize_string(collector),
        "signal": normalize_string(signal),
        "value": value,
        "status": normalize_string(status) or STATUS_UNKNOWN,
        "confidence": normalize_string(confidence) or CONFIDENCE_UNKNOWN,
        "trust_tier": normalize_string(trust_tier) or TRUST_TIER_1_READ_ONLY,
        "requires_admin": bool(requires_admin),
        "privacy": normalize_string(privacy) or PRIVACY_LOW,
        "permission_required": bool(permission_required),
        "plain_meaning": normalize_string(plain_meaning),
        "recommended_next_step": (
            normalize_string(recommended_next_step)
            if recommended_next_step is not None
            else None
        ),
        "raw": raw or {},
        "errors": normalize_string_list(errors),
        "warnings": normalize_string_list(warnings),
        "collected_at": collected_at or utc_now_iso(),
    }


def validate_windows_evidence_item(item: dict[str, Any]) -> dict[str, Any]:
    """
    Validate one normalized Windows evidence item.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(item, dict):
        return {
            "status": "invalid",
            "message": "Windows evidence item must be a dictionary.",
            "data": {"valid": False},
            "errors": ["item must be a dictionary."],
            "warnings": [],
        }

    for field in REQUIRED_STRING_FIELDS:
        value = item.get(field)

        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field} must be a non-empty string.")

    for field in REQUIRED_BOOLEAN_FIELDS:
        if not isinstance(item.get(field), bool):
            errors.append(f"{field} must be a boolean.")

    if item.get("status") not in ALLOWED_STATUSES:
        errors.append(f"status must be one of {sorted(ALLOWED_STATUSES)}.")

    if item.get("confidence") not in ALLOWED_CONFIDENCE_VALUES:
        errors.append(
            f"confidence must be one of {sorted(ALLOWED_CONFIDENCE_VALUES)}."
        )

    if item.get("trust_tier") not in ALLOWED_TRUST_TIERS:
        errors.append(f"trust_tier must be one of {sorted(ALLOWED_TRUST_TIERS)}.")

    if item.get("privacy") not in ALLOWED_PRIVACY_VALUES:
        errors.append(f"privacy must be one of {sorted(ALLOWED_PRIVACY_VALUES)}.")

    if item.get("recommended_next_step") is not None and not isinstance(
        item.get("recommended_next_step"),
        str,
    ):
        errors.append("recommended_next_step must be null or a string.")

    if not isinstance(item.get("raw"), dict):
        errors.append("raw must be a dictionary.")

    if not isinstance(item.get("errors"), list):
        errors.append("errors must be a list.")

    if not isinstance(item.get("warnings"), list):
        errors.append("warnings must be a list.")

    status = "invalid" if errors else "ok"
    message = (
        "Windows evidence item failed validation."
        if errors
        else "Windows evidence item is valid."
    )

    return {
        "status": status,
        "message": message,
        "data": {"valid": not errors},
        "errors": errors,
        "warnings": warnings,
    }


def is_valid_windows_evidence_item(item: dict[str, Any]) -> bool:
    """
    Return True when an evidence item passes validation.
    """
    return validate_windows_evidence_item(item)["status"] == "ok"


def summarize_windows_evidence(items: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Summarize a list of Windows evidence items.
    """
    by_source: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_trust_tier: dict[str, int] = {}
    by_privacy: dict[str, int] = {}
    validation_errors: list[str] = []

    for index, item in enumerate(items):
        validation = validate_windows_evidence_item(item)

        if validation["status"] != "ok":
            for error in validation["errors"]:
                validation_errors.append(f"item[{index}]: {error}")

        source = item.get("source", STATUS_UNKNOWN)
        status = item.get("status", STATUS_UNKNOWN)
        trust_tier = item.get("trust_tier", STATUS_UNKNOWN)
        privacy = item.get("privacy", STATUS_UNKNOWN)

        by_source[source] = by_source.get(source, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        by_trust_tier[trust_tier] = by_trust_tier.get(trust_tier, 0) + 1
        by_privacy[privacy] = by_privacy.get(privacy, 0) + 1

    return {
        "status": "invalid" if validation_errors else "ok",
        "message": (
            "Windows evidence summary contains invalid items."
            if validation_errors
            else "Windows evidence summary built."
        ),
        "data": {
            "total_items": len(items),
            "by_source": by_source,
            "by_status": by_status,
            "by_trust_tier": by_trust_tier,
            "by_privacy": by_privacy,
            "valid": not validation_errors,
        },
        "errors": validation_errors,
        "warnings": [],
    }
