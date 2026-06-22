"""
Tests for Windows evidence report formatter.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.windows_evidence import build_windows_evidence_item
from app.services.windows_evidence_report import format_windows_evidence_report


def test_format_windows_evidence_report_includes_core_sections() -> None:
    items = [
        build_windows_evidence_item(
            source="cim",
            collector="Win32_OperatingSystem",
            signal="os_caption",
            value="Microsoft Windows 11 Pro",
        ),
        build_windows_evidence_item(
            source="cim",
            collector="Win32_OperatingSystem",
            signal="last_boot_time",
            value="2026-06-22T08:13:00",
        ),
        build_windows_evidence_item(
            source="cim",
            collector="Win32_ComputerSystem",
            signal="computer_model",
            value="Example Model",
        ),
        build_windows_evidence_item(
            source="cim",
            collector="Win32_Processor",
            signal="processor_name",
            value="Example CPU",
        ),
        build_windows_evidence_item(
            source="cim",
            collector="Win32_LogicalDisk",
            signal="logical_disk_device_id",
            value="C:",
        ),
        build_windows_evidence_item(
            source="cim",
            collector="Win32_LogicalDisk",
            signal="logical_disk_size_bytes",
            value=1024 ** 3,
        ),
        build_windows_evidence_item(
            source="cim",
            collector="Win32_LogicalDisk",
            signal="logical_disk_free_space_bytes",
            value=512 * 1024 ** 2,
        ),
    ]

    report = format_windows_evidence_report(
        {
            "status": "ok",
            "message": "CIM evidence collection completed.",
            "source": "cim",
            "evidence_items": items,
            "summary": {
                "data": {
                    "valid": True,
                }
            },
            "errors": [],
            "warnings": [],
        }
    )

    assert "LIGHTHOUSE WINDOWS EVIDENCE" in report
    assert "Status: ok" in report
    assert "Operating system:" in report
    assert "Microsoft Windows 11 Pro" in report
    assert "Computer:" in report
    assert "Example Model" in report
    assert "Processor:" in report
    assert "Example CPU" in report
    assert "Logical disks:" in report
    assert "C:" in report
    assert "C::" not in report
