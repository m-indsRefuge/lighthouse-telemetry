"""
Tests for Operator interaction and feedback journal.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.operator_interaction_journal import (
    format_feedback_labels_report,
    read_operator_feedback,
    read_operator_interactions,
    record_operator_feedback,
    record_operator_interaction,
)


def build_fake_result() -> dict:
    return {
        "status": "ok",
        "message": "ok",
        "original_input": "why is chrome eating memory",
        "normalized_input": "why is chrome eating memory",
        "intent": "process_memory_diagnostic",
        "interpreted_request": "why is Chrome using memory",
        "recommended_command": "runplan why is Chrome using memory",
        "requires_engine_run": True,
        "requires_clarification": False,
        "clarifying_question": None,
        "safety_note": "read-only",
        "confidence": 0.9,
        "decision_trace": {"selected_intent": "process_memory_diagnostic"},
        "route_handoff": {
            "route_ready": True,
            "command_family": "runplan",
            "engine_request": "why is Chrome using memory",
            "autorun_allowed": True,
            "manual_review_required": False,
        },
        "warnings": [],
        "errors": [],
    }


def test_record_operator_interaction_writes_jsonl(tmp_path) -> None:
    result = record_operator_interaction(
        mode="talk",
        result=build_fake_result(),
        execution={
            "attempted": False,
            "executed": False,
            "refused": False,
            "engine_request": None,
        },
        memory_dir=tmp_path,
    )

    assert result["status"] == "ok"
    assert result["data"]["saved"] is True
    assert result["data"]["trace_id"].startswith("optrace-")

    records = read_operator_interactions(memory_dir=tmp_path)

    assert len(records) == 1
    assert records[0]["trace_id"] == result["data"]["trace_id"]
    assert records[0]["mode"] == "talk"
    assert records[0]["intent"] == "process_memory_diagnostic"


def test_read_operator_interactions_respects_limit_newest_first(tmp_path) -> None:
    first = record_operator_interaction(
        mode="talk",
        result=build_fake_result(),
        memory_dir=tmp_path,
    )
    second = record_operator_interaction(
        mode="talkrun",
        result=build_fake_result(),
        memory_dir=tmp_path,
    )

    records = read_operator_interactions(limit=1, memory_dir=tmp_path)

    assert len(records) == 1
    assert records[0]["trace_id"] == second["data"]["trace_id"]
    assert records[0]["trace_id"] != first["data"]["trace_id"]


def test_record_operator_feedback_accepts_allowed_label(tmp_path) -> None:
    interaction = record_operator_interaction(
        mode="talk",
        result=build_fake_result(),
        memory_dir=tmp_path,
    )

    feedback = record_operator_feedback(
        trace_id=interaction["data"]["trace_id"],
        label="useful",
        note="routed correctly",
        memory_dir=tmp_path,
    )

    assert feedback["status"] == "ok"
    assert feedback["data"]["saved"] is True
    assert feedback["data"]["label"] == "useful"

    records = read_operator_feedback(memory_dir=tmp_path)

    assert len(records) == 1
    assert records[0]["trace_id"] == interaction["data"]["trace_id"]
    assert records[0]["note"] == "routed correctly"


def test_record_operator_feedback_rejects_invalid_label(tmp_path) -> None:
    feedback = record_operator_feedback(
        trace_id="optrace-test",
        label="excellent",
        note="not an allowed label",
        memory_dir=tmp_path,
    )

    assert feedback["status"] == "invalid"
    assert feedback["data"]["saved"] is False
    assert "Unsupported feedback label" in feedback["errors"][0]


def test_feedback_labels_report_lists_allowed_labels() -> None:
    report = format_feedback_labels_report()

    assert "LIGHTHOUSE OPERATOR FEEDBACK LABELS" in report
    assert "useful" in report
    assert "wrong_intent" in report
    assert "unsafe" in report
