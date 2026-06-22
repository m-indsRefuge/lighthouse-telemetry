"""
Tests for Lighthouse CLI Operator route policy inspector command.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import cli


def test_print_operator_routes_report(capsys) -> None:
    cli.print_operator_routes_report()

    output = capsys.readouterr().out

    assert "LIGHTHOUSE OPERATOR ROUTES" in output
    assert "Status: ok" in output
    assert "Registered routes: 8" in output
    assert "performance_diagnostic" in output
    assert "os_action_request" in output
    assert "destructive_action_request" in output


def test_run_canonical_command_handles_routes(capsys) -> None:
    result = cli.run_canonical_command("routes")

    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE OPERATOR ROUTES" in output
    assert "Status: ok" in output


def test_run_canonical_command_handles_route_policy_alias(capsys) -> None:
    result = cli.run_canonical_command("route policy")

    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE OPERATOR ROUTES" in output
    assert "Registered routes: 8" in output


def test_help_lists_routes_command(capsys) -> None:
    cli.print_help()

    output = capsys.readouterr().out

    assert "routes" in output
    assert "Operator route registry" in output
