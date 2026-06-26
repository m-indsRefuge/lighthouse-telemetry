"""
Tests for conversational turn feedback capture.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.conversation_turn_feedback import (
    format_turn_feedback_labels_report,
    format_turn_feedback_result,
    latest_feedback_by_turn_id,
    list_turn_feedback_labels,
    read_turn_feedback,
    record_turn_feedback,
)


def test_record_turn_feedback_writes_append_only_record(tmp_path: Path) -> None:
    result = record_turn_feedback(
        turn_id="turn-example",
        label="useful",
        note="routed correctly",
        memory_dir=tmp_path,
    )

    assert result["status"] == "ok"
    assert result["data"]["saved"] is True
    assert result["data"]["turn_id"] == "turn-example"
    assert result["data"]["label"] == "useful"

    records = read_turn_feedback(memory_dir=tmp_path)

    assert len(records) == 1
    assert records[0]["turn_id"] == "turn-example"
    assert records[0]["label"] == "useful"
    assert records[0]["note"] == "routed correctly"


def test_turn_feedback_rejects_unknown_label(tmp_path: Path) -> None:
    result = record_turn_feedback(
        turn_id="turn-example",
        label="bad-label",
        memory_dir=tmp_path,
    )

    assert result["status"] == "invalid"
    assert result["data"]["saved"] is False
    assert "bad_label" in result["errors"][0]
    assert "useful" in result["data"]["allowed_labels"]


def test_latest_feedback_by_turn_id_uses_most_recent_record(tmp_path: Path) -> None:
    record_turn_feedback(
        turn_id="turn-example",
        label="confusing",
        note="first",
        memory_dir=tmp_path,
    )
    record_turn_feedback(
        turn_id="turn-example",
        label="corrected",
        note="second",
        memory_dir=tmp_path,
    )

    latest = latest_feedback_by_turn_id(memory_dir=tmp_path)

    assert latest["turn-example"]["label"] == "corrected"
    assert latest["turn-example"]["note"] == "second"


def test_format_turn_feedback_labels_report() -> None:
    report = format_turn_feedback_labels_report()

    assert "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK LABELS" in report

    for label in list_turn_feedback_labels():
        assert f"- {label}" in report


def test_format_turn_feedback_result() -> None:
    result = {
        "status": "ok",
        "message": "Conversational turn feedback recorded.",
        "data": {
            "saved": True,
            "turn_id": "turn-example",
            "feedback_id": "turnfb-example",
            "label": "useful",
        },
        "errors": [],
        "warnings": [],
    }

    report = format_turn_feedback_result(result)

    assert "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK" in report
    assert "Status: ok" in report
    assert "Turn ID: turn-example" in report
    assert "Saved: yes" in report
    assert "Label: useful" in report


def test_format_turn_feedback_report_lists_recent_records(tmp_path: Path) -> None:
    record_turn_feedback(
        turn_id="turn-one",
        label="useful",
        note="first note",
        memory_dir=tmp_path,
    )
    record_turn_feedback(
        turn_id="turn-two",
        label="wrong_route",
        note="second note",
        memory_dir=tmp_path,
    )

    from app.services.conversation_turn_feedback import format_turn_feedback_report

    report = format_turn_feedback_report(memory_dir=tmp_path)

    assert "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK" in report
    assert "Shown: 2" in report
    assert "turn_id: turn-two" in report
    assert "label: wrong_route" in report
    assert "note: second note" in report
    assert "turn_id: turn-one" in report


def test_format_turn_feedback_report_handles_empty_journal(tmp_path: Path) -> None:
    from app.services.conversation_turn_feedback import format_turn_feedback_report

    report = format_turn_feedback_report(memory_dir=tmp_path)

    assert "LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK" in report
    assert "Shown: 0" in report
    assert "No conversational turn feedback recorded yet." in report
