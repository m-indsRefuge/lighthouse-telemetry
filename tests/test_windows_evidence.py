"""
Tests for Windows evidence schema.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.windows_evidence import (
    CONFIDENCE_HIGH,
    PRIVACY_LOW,
    STATUS_OK,
    TRUST_TIER_1_READ_ONLY,
    build_windows_evidence_item,
    is_valid_windows_evidence_item,
    summarize_windows_evidence,
    validate_windows_evidence_item,
)


def test_build_windows_evidence_item_returns_valid_default_shape() -> None:
    item = build_windows_evidence_item(
        source="cim",
        collector="Win32_OperatingSystem",
        signal="last_boot_time",
        value="2026-06-22T08:13:00",
        plain_meaning="Windows last boot time was collected from CIM.",
    )

    assert item["source"] == "cim"
    assert item["collector"] == "Win32_OperatingSystem"
    assert item["signal"] == "last_boot_time"
    assert item["status"] == STATUS_OK
    assert item["confidence"] == CONFIDENCE_HIGH
    assert item["trust_tier"] == TRUST_TIER_1_READ_ONLY
    assert item["requires_admin"] is False
    assert item["privacy"] == PRIVACY_LOW
    assert item["permission_required"] is False
    assert item["errors"] == []
    assert item["warnings"] == []
    assert is_valid_windows_evidence_item(item) is True


def test_validate_windows_evidence_item_rejects_missing_required_string() -> None:
    item = build_windows_evidence_item(
        source="cim",
        collector="Win32_OperatingSystem",
        signal="last_boot_time",
        value="2026-06-22T08:13:00",
    )
    item["source"] = ""

    validation = validate_windows_evidence_item(item)

    assert validation["status"] == "invalid"
    assert validation["data"]["valid"] is False
    assert "source must be a non-empty string." in validation["errors"]


def test_validate_windows_evidence_item_rejects_invalid_enums() -> None:
    item = build_windows_evidence_item(
        source="cim",
        collector="Win32_OperatingSystem",
        signal="last_boot_time",
        value="2026-06-22T08:13:00",
    )
    item["status"] = "good"
    item["confidence"] = "certain"
    item["trust_tier"] = "trusted"
    item["privacy"] = "none"

    validation = validate_windows_evidence_item(item)

    assert validation["status"] == "invalid"
    assert any("status must be one of" in error for error in validation["errors"])
    assert any("confidence must be one of" in error for error in validation["errors"])
    assert any("trust_tier must be one of" in error for error in validation["errors"])
    assert any("privacy must be one of" in error for error in validation["errors"])


def test_validate_windows_evidence_item_rejects_wrong_boolean_types() -> None:
    item = build_windows_evidence_item(
        source="cim",
        collector="Win32_OperatingSystem",
        signal="last_boot_time",
        value="2026-06-22T08:13:00",
    )
    item["requires_admin"] = "false"
    item["permission_required"] = "false"

    validation = validate_windows_evidence_item(item)

    assert validation["status"] == "invalid"
    assert "requires_admin must be a boolean." in validation["errors"]
    assert "permission_required must be a boolean." in validation["errors"]


def test_summarize_windows_evidence_counts_by_source_status_and_tier() -> None:
    first = build_windows_evidence_item(
        source="cim",
        collector="Win32_OperatingSystem",
        signal="os_caption",
        value="Windows 11",
    )
    second = build_windows_evidence_item(
        source="cim",
        collector="Win32_Processor",
        signal="processor_name",
        value="Intel CPU",
    )

    summary = summarize_windows_evidence([first, second])

    assert summary["status"] == "ok"
    assert summary["data"]["total_items"] == 2
    assert summary["data"]["by_source"] == {"cim": 2}
    assert summary["data"]["by_status"] == {"ok": 2}
    assert summary["data"]["by_trust_tier"] == {"tier_1_read_only": 2}
    assert summary["errors"] == []


def test_summarize_windows_evidence_reports_invalid_items() -> None:
    item = build_windows_evidence_item(
        source="cim",
        collector="Win32_OperatingSystem",
        signal="os_caption",
        value="Windows 11",
    )
    item["collector"] = ""

    summary = summarize_windows_evidence([item])

    assert summary["status"] == "invalid"
    assert summary["data"]["valid"] is False
    assert any("collector must be a non-empty string" in error for error in summary["errors"])
