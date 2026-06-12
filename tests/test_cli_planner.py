"""
CLI tests for the Lighthouse tool planner command.

These tests ensure the planner is visible from the CLI layer without executing
any tools.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.cli import print_tool_plan_report, run_canonical_command


def test_print_tool_plan_report_for_safe_request(capsys) -> None:
    """
    Safe optimization requests should print a read-only tool plan.
    """
    print_tool_plan_report("please optimize RAM usage")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE TOOL PLAN" in output
    assert "Status: ok" in output
    assert "Intent: slow_laptop_diagnostics" in output
    assert "Requires confirmation: no" in output
    assert "collect_snapshot" in output
    assert "inspect_memory_usage" in output
    assert "list_top_processes" in output


def test_print_tool_plan_report_for_blocked_request(capsys) -> None:
    """
    File deletion requests should print a blocked plan and safe alternatives.
    """
    print_tool_plan_report("delete files to make space")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE TOOL PLAN" in output
    assert "Status: blocked" in output
    assert "Intent: blocked_file_deletion" in output
    assert "delete_user_files" in output
    assert "collect_snapshot" in output
    assert "inspect_disk_usage" in output


def test_print_tool_plan_report_for_confirmation_request(capsys) -> None:
    """
    Process-closing requests should show confirmation is required.
    """
    print_tool_plan_report("close Chrome because it is using memory")

    output = capsys.readouterr().out

    assert "LIGHTHOUSE TOOL PLAN" in output
    assert "Status: needs_confirmation" in output
    assert "Intent: close_process_request" in output
    assert "Requires confirmation: yes" in output
    assert "close_selected_process" in output
    assert "collect_snapshot" in output
    assert "list_top_processes" in output


def test_run_canonical_command_handles_plan_command(capsys) -> None:
    """
    The interactive CLI router should handle plan commands directly.
    """
    result = run_canonical_command("plan please optimize RAM usage")

    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE TOOL PLAN" in output
    assert "Status: ok" in output
    assert "collect_snapshot" in output


def test_run_canonical_command_handles_empty_plan_command(capsys) -> None:
    """
    The plan command with no request should show usage guidance.
    """
    result = run_canonical_command("plan")

    output = capsys.readouterr().out

    assert result == "handled"
    assert "Status: needs_clarification" in output
    assert "please optimize RAM usage" in output