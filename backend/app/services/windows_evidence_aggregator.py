"""
Windows evidence aggregation service for Lighthouse.

This module safely calls the completed Windows-native collectors and combines
their normalized WindowsEvidenceItem outputs into one deterministic result.

It does not call the model.
It does not execute repair commands.
It does not mutate the operating system.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.collectors.windows.cim import collect_windows_cim_evidence
from app.collectors.windows.perf_counters import collect_windows_performance_counters
from app.collectors.windows.win_events import collect_windows_event_evidence
from app.services.windows_evidence import (
    build_windows_evidence_item,
    is_valid_windows_evidence_item,
    summarize_windows_evidence,
)


CollectorFunction = Callable[[], dict[str, Any]]

WINDOWS_COLLECTOR_CIM = "cim"
WINDOWS_COLLECTOR_PERFORMANCE_COUNTERS = "performance_counters"
WINDOWS_COLLECTOR_EVENTS = "events"

DEFAULT_WINDOWS_EVIDENCE_COLLECTORS: dict[str, CollectorFunction] = {
    WINDOWS_COLLECTOR_CIM: collect_windows_cim_evidence,
    WINDOWS_COLLECTOR_PERFORMANCE_COUNTERS: collect_windows_performance_counters,
    WINDOWS_COLLECTOR_EVENTS: collect_windows_event_evidence,
}

COLLECTOR_OK_STATUSES = frozenset({"ok", "empty"})
COLLECTOR_NON_OK_STATUSES = frozenset({"partial", "warning", "error", "invalid"})


def normalize_collector_status(status: Any) -> str:
    """
    Normalize collector status into a stable string.
    """
    text = str(status or "").strip().lower()

    if not text:
        return "unknown"

    return text


def build_collector_summary(
    collector_name: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Build a compact collector result summary.
    """
    evidence_items = result.get("evidence_items", [])

    if not isinstance(evidence_items, list):
        evidence_count = 0
    else:
        evidence_count = len(evidence_items)

    errors = result.get("errors", [])
    warnings = result.get("warnings", [])

    return {
        "collector": collector_name,
        "status": normalize_collector_status(result.get("status")),
        "message": str(result.get("message") or "").strip(),
        "source": str(result.get("source") or collector_name).strip(),
        "evidence_count": evidence_count,
        "errors": errors if isinstance(errors, list) else [str(errors)],
        "warnings": warnings if isinstance(warnings, list) else [str(warnings)],
    }


def build_collector_exception_result(
    collector_name: str,
    error: BaseException,
) -> dict[str, Any]:
    """
    Convert a collector exception into a stable collector result.
    """
    error_message = str(error).strip() or f"{collector_name} collector failed."

    error_item = build_windows_evidence_item(
        source=collector_name,
        collector=collector_name,
        signal=f"{collector_name}_collection_exception",
        value=None,
        status="error",
        confidence="unknown",
        trust_tier="tier_1_read_only",
        requires_admin=False,
        privacy="low",
        permission_required=False,
        plain_meaning=f"Lighthouse could not collect evidence from {collector_name}.",
        errors=[error_message],
    )

    return {
        "status": "error",
        "message": f"{collector_name} collector failed.",
        "source": collector_name,
        "evidence_items": [error_item],
        "errors": [error_message],
        "warnings": [],
    }


def extract_valid_evidence_items(
    collector_name: str,
    result: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Extract valid WindowsEvidenceItem dictionaries from a collector result.
    """
    evidence_items = result.get("evidence_items", [])
    valid_items: list[dict[str, Any]] = []
    validation_errors: list[str] = []

    if not isinstance(evidence_items, list):
        return [], [f"{collector_name} evidence_items must be a list."]

    for index, item in enumerate(evidence_items):
        if is_valid_windows_evidence_item(item):
            valid_items.append(item)
        else:
            validation_errors.append(
                f"{collector_name} evidence item {index} failed WindowsEvidenceItem validation."
            )

    return valid_items, validation_errors


def aggregate_collector_results(
    collector_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    Aggregate collector results into one deterministic Windows evidence result.
    """
    collector_summaries: list[dict[str, Any]] = []
    evidence_items: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    ok_collectors = 0
    failed_collectors = 0

    for collector_name, result in collector_results.items():
        summary = build_collector_summary(collector_name, result)
        collector_summaries.append(summary)

        status = summary["status"]

        if status in COLLECTOR_OK_STATUSES:
            ok_collectors += 1
        elif status in COLLECTOR_NON_OK_STATUSES:
            failed_collectors += 1
        else:
            failed_collectors += 1
            warnings.append(f"{collector_name} returned unknown status: {status}")

        valid_items, validation_errors = extract_valid_evidence_items(
            collector_name,
            result,
        )

        evidence_items.extend(valid_items)
        errors.extend(summary["errors"])
        warnings.extend(summary["warnings"])
        warnings.extend(validation_errors)

    if failed_collectors == 0:
        status = "ok"
        message = "Windows evidence aggregation completed."
    elif ok_collectors > 0 or evidence_items:
        status = "partial"
        message = "Windows evidence aggregation completed with partial results."
    else:
        status = "error"
        message = "Windows evidence aggregation failed."

    return {
        "status": status,
        "message": message,
        "collector_results": collector_summaries,
        "collector_count": len(collector_results),
        "ok_collector_count": ok_collectors,
        "failed_collector_count": failed_collectors,
        "evidence_items": evidence_items,
        "summary": summarize_windows_evidence(evidence_items),
        "errors": errors,
        "warnings": warnings,
    }


def collect_windows_evidence(
    collectors: dict[str, CollectorFunction] | None = None,
) -> dict[str, Any]:
    """
    Collect and aggregate Windows evidence from registered safe collectors.
    """
    selected_collectors = collectors or DEFAULT_WINDOWS_EVIDENCE_COLLECTORS
    collector_results: dict[str, dict[str, Any]] = {}

    for collector_name, collector in selected_collectors.items():
        try:
            result = collector()

            if not isinstance(result, dict):
                result = {
                    "status": "error",
                    "message": f"{collector_name} collector returned non-dictionary result.",
                    "source": collector_name,
                    "evidence_items": [],
                    "errors": [
                        f"{collector_name} collector returned non-dictionary result."
                    ],
                    "warnings": [],
                }

            collector_results[collector_name] = result
        except Exception as error:
            collector_results[collector_name] = build_collector_exception_result(
                collector_name,
                error,
            )

    return aggregate_collector_results(collector_results)
