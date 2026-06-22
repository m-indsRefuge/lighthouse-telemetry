"""
Tests for Windows evidence CLI wiring.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import cli
from app.services.windows_evidence import build_windows_evidence_item


def fake_windows_evidence_result() -> dict:
    return {
        "status": "ok",
        "message": "CIM evidence collection completed.",
        "source": "cim",
        "evidence_items": [
            build_windows_evidence_item(
                source="cim",
                collector="Win32_OperatingSystem",
                signal="os_caption",
                value="Microsoft Windows 11 Pro",
            ),
            build_windows_evidence_item(
                source="cim",
                collector="Win32_Processor",
                signal="processor_name",
                value="Example CPU",
            ),
        ],
        "summary": {
            "data": {
                "valid": True,
            }
        },
        "errors": [],
        "warnings": [],
    }


def test_run_canonical_command_handles_windows(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "collect_windows_cim_evidence",
        fake_windows_evidence_result,
    )

    result = cli.run_canonical_command("windows")

    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE WINDOWS EVIDENCE" in output
    assert "Status: ok" in output
    assert "Source: cim" in output
    assert "Microsoft Windows 11 Pro" in output
    assert "Example CPU" in output


def test_run_canonical_command_handles_cim_alias(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "collect_windows_cim_evidence",
        fake_windows_evidence_result,
    )

    result = cli.run_canonical_command("cim evidence")

    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE WINDOWS EVIDENCE" in output


def test_help_mentions_windows_command(capsys) -> None:
    cli.print_help()

    output = capsys.readouterr().out

    assert "windows" in output
    assert "Show Windows-native CIM evidence" in output
