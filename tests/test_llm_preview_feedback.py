"""
Tests for LLM preview feedback capture.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.llm_preview_feedback import (
    list_preview_feedback_labels,
    normalize_preview_feedback_label,
    record_llm_preview_feedback,
    read_llm_preview_feedback,
    latest_feedback_by_preview_id,
    format_llm_preview_feedback_result,
    format_preview_feedback_labels_report,
)


def test_preview_feedback_labels_are_stable() -> None:
    labels = list_preview_feedback_labels()

    assert "useful" in labels
    assert "not_useful" in labels
    assert "wrong_intent" in labels
    assert "wrong_route" in labels
    assert "unsafe" in labels
    assert "confusing" in labels
    assert "corrected" in labels
    assert "other" in labels


def test_normalize_preview_feedback_label() -> None:
    assert normalize_preview_feedback_label("Wrong-Intent") == "wrong_intent"
    assert normalize_preview_feedback_label(" useful ") == "useful"


def test_record_preview_feedback_rejects_empty_preview_id(tmp_path: Path) -> None:
    result = record_llm_preview_feedback(
        preview_id="",
        label="useful",
        memory_dir=tmp_path,
    )

    assert result["status"] == "invalid"
    assert result["data"]["saved"] is False
    assert "preview_id" in result["errors"][0]


def test_record_preview_feedback_rejects_bad_label(tmp_path: Path) -> None:
    result = record_llm_preview_feedback(
        preview_id="llmprev-1",
        label="bad_label",
        memory_dir=tmp_path,
    )

    assert result["status"] == "invalid"
    assert result["data"]["saved"] is False
    assert result["data"]["allowed_labels"]


def test_record_and_read_preview_feedback(tmp_path: Path) -> None:
    result = record_llm_preview_feedback(
        preview_id="llmprev-1",
        label="wrong-route",
        note="should have stayed unknown",
        memory_dir=tmp_path,
    )

    assert result["status"] == "ok"
    assert result["data"]["saved"] is True
    assert result["data"]["label"] == "wrong_route"

    records = read_llm_preview_feedback(memory_dir=tmp_path)

    assert len(records) == 1
    assert records[0]["preview_id"] == "llmprev-1"
    assert records[0]["label"] == "wrong_route"
    assert records[0]["note"] == "should have stayed unknown"


def test_latest_feedback_by_preview_id_keeps_latest(tmp_path: Path) -> None:
    record_llm_preview_feedback(
        preview_id="llmprev-1",
        label="confusing",
        memory_dir=tmp_path,
    )
    record_llm_preview_feedback(
        preview_id="llmprev-1",
        label="useful",
        memory_dir=tmp_path,
    )

    latest = latest_feedback_by_preview_id(memory_dir=tmp_path)

    assert latest["llmprev-1"]["label"] == "useful"


def test_format_preview_feedback_labels_report() -> None:
    report = format_preview_feedback_labels_report()

    assert "LIGHTHOUSE LLM PREVIEW FEEDBACK LABELS" in report
    assert "- useful" in report
    assert "- unsafe" in report


def test_format_llm_preview_feedback_result() -> None:
    report = format_llm_preview_feedback_result(
        {
            "status": "ok",
            "message": "LLM preview feedback recorded.",
            "data": {
                "saved": True,
                "preview_id": "llmprev-1",
                "feedback_id": "llmprevfb-1",
                "label": "useful",
            },
            "errors": [],
            "warnings": [],
        }
    )

    assert "LIGHTHOUSE LLM PREVIEW FEEDBACK" in report
    assert "Status: ok" in report
    assert "Preview ID: llmprev-1" in report
    assert "Label: useful" in report
