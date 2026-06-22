"""
Tests for Operator Route Policy Inspector V0.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.operator_routes import (
    INTENT_DESTRUCTIVE_ACTION_REQUEST,
    INTENT_DIRECT_COMMAND,
    INTENT_GENERAL_HEALTH_CHECK,
    INTENT_OS_ACTION_REQUEST,
    INTENT_PERFORMANCE_DIAGNOSTIC,
    INTENT_PROCESS_MEMORY_DIAGNOSTIC,
    INTENT_REPAIR_REQUEST,
    INTENT_UNKNOWN,
    build_operator_routes_report,
    validate_operator_route_registry,
)


def test_validate_operator_route_registry_returns_ok() -> None:
    result = validate_operator_route_registry()

    assert result["status"] == "ok", result
    assert result["message"] == "Operator route registry is valid."
    assert result["route_count"] == 8
    assert result["errors"] == []


def test_validate_operator_route_registry_covers_required_routes() -> None:
    report = build_operator_routes_report()

    assert INTENT_PERFORMANCE_DIAGNOSTIC in report
    assert INTENT_PROCESS_MEMORY_DIAGNOSTIC in report
    assert INTENT_GENERAL_HEALTH_CHECK in report
    assert INTENT_OS_ACTION_REQUEST in report
    assert INTENT_DESTRUCTIVE_ACTION_REQUEST in report
    assert INTENT_REPAIR_REQUEST in report
    assert INTENT_DIRECT_COMMAND in report
    assert INTENT_UNKNOWN in report


def test_operator_routes_report_includes_policy_fields() -> None:
    report = build_operator_routes_report()

    assert "LIGHTHOUSE OPERATOR ROUTES" in report
    assert "Status: ok" in report
    assert "Registered routes: 8" in report
    assert "- safety_class:" in report
    assert "- command_family:" in report
    assert "- requires_engine_run:" in report
    assert "- autorun_allowed:" in report
    assert "- manual_review_required:" in report


def test_operator_routes_report_marks_read_only_routes_autorunnable() -> None:
    report = build_operator_routes_report()

    assert "performance_diagnostic" in report
    assert "process_memory_diagnostic" in report
    assert "general_health_check" in report
    assert "read_only_diagnostic" in report
    assert "- autorun_allowed: yes" in report


def test_operator_routes_report_marks_unsafe_routes_manual_review() -> None:
    report = build_operator_routes_report()

    assert "os_action_request" in report
    assert "destructive_action_request" in report
    assert "repair_request" in report
    assert "runplan_preview_only" in report
    assert "- manual_review_required: yes" in report
