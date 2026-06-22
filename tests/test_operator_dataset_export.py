"""
Tests for Operator Dataset Export V0.
"""

from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.operator_dataset_export import (
    CATEGORY_CORRECTION_NEEDED,
    CATEGORY_POSITIVE_ROUTE_EXAMPLE,
    CATEGORY_SAFE_REFUSAL_EXAMPLE,
    CATEGORY_SAFETY_REVIEW,
    CATEGORY_UNLABELED_TRACE,
    build_operator_route_dataset,
    export_operator_route_dataset,
    format_operator_dataset_export_report,
)
from app.services.operator_interaction_journal import (
    record_operator_feedback,
    record_operator_interaction,
)


def build_interaction_result(intent: str = "process_memory_diagnostic") -> dict:
    return {
        "status": "ok",
        "message": "ok",
        "original_input": "why is chrome eating memory",
        "normalized_input": "why is chrome eating memory",
        "intent": intent,
        "interpreted_request": "why is Chrome using memory",
        "recommended_command": "runplan why is Chrome using memory",
        "requires_engine_run": True,
        "requires_clarification": False,
        "clarifying_question": None,
        "safety_note": "read-only",
        "confidence": 0.9,
        "decision_trace": {"selected_intent": intent},
        "route_handoff": {
            "route_ready": True,
            "route_known": True,
            "intent": intent,
            "safety_class": "read_only_diagnostic",
            "command_family": "runplan",
            "recommended_command": "runplan why is Chrome using memory",
            "engine_request": "why is Chrome using memory",
            "autorun_allowed": True,
            "manual_review_required": False,
            "refusal_reason": "",
            "errors": [],
        },
        "warnings": [],
        "errors": [],
    }


def test_build_operator_route_dataset_joins_feedback_by_trace_id(tmp_path) -> None:
    interaction_result = record_operator_interaction(
        mode="talkrun",
        result=build_interaction_result(),
        autorun_gate={"status": "ok", "allowed": True},
        execution={
            "attempted": True,
            "executed": True,
            "refused": False,
            "engine_request": "why is Chrome using memory",
        },
        memory_dir=tmp_path,
    )
    trace_id = interaction_result["data"]["trace_id"]

    record_operator_feedback(
        trace_id=trace_id,
        label="useful",
        note="routed correctly",
        memory_dir=tmp_path,
    )

    records = build_operator_route_dataset(memory_dir=tmp_path)

    assert len(records) == 1
    record = records[0]
    assert record["trace_id"] == trace_id
    assert record["input"]["original"] == "why is chrome eating memory"
    assert record["target"]["intent"] == "process_memory_diagnostic"
    assert record["target"]["engine_request"] == "why is Chrome using memory"
    assert record["feedback"]["label"] == "useful"
    assert record["feedback"]["note"] == "routed correctly"
    assert record["training_use"]["include"] is True
    assert record["training_use"]["category"] == CATEGORY_POSITIVE_ROUTE_EXAMPLE


def test_dataset_classifies_refused_route_as_safe_refusal(tmp_path) -> None:
    record_operator_interaction(
        mode="talkrun",
        result=build_interaction_result(intent="os_action_request"),
        autorun_gate={"status": "refused", "allowed": False},
        execution={
            "attempted": True,
            "executed": False,
            "refused": True,
            "engine_request": None,
        },
        memory_dir=tmp_path,
    )

    records = build_operator_route_dataset(memory_dir=tmp_path)

    assert len(records) == 1
    assert records[0]["training_use"]["include"] is True
    assert records[0]["training_use"]["category"] == CATEGORY_SAFE_REFUSAL_EXAMPLE


def test_dataset_classifies_wrong_intent_feedback_as_correction_needed(tmp_path) -> None:
    interaction_result = record_operator_interaction(
        mode="talkrun",
        result=build_interaction_result(),
        autorun_gate={"status": "ok", "allowed": True},
        execution={
            "attempted": True,
            "executed": True,
            "refused": False,
            "engine_request": "why is Chrome using memory",
        },
        memory_dir=tmp_path,
    )

    record_operator_feedback(
        trace_id=interaction_result["data"]["trace_id"],
        label="wrong_intent",
        note="should have asked a clarifying question",
        memory_dir=tmp_path,
    )

    records = build_operator_route_dataset(memory_dir=tmp_path)

    assert records[0]["training_use"]["include"] is False
    assert records[0]["training_use"]["category"] == CATEGORY_CORRECTION_NEEDED


def test_dataset_classifies_unsafe_feedback_as_safety_review(tmp_path) -> None:
    interaction_result = record_operator_interaction(
        mode="talkrun",
        result=build_interaction_result(),
        autorun_gate={"status": "ok", "allowed": True},
        execution={
            "attempted": True,
            "executed": True,
            "refused": False,
            "engine_request": "why is Chrome using memory",
        },
        memory_dir=tmp_path,
    )

    record_operator_feedback(
        trace_id=interaction_result["data"]["trace_id"],
        label="unsafe",
        note="this should not have run",
        memory_dir=tmp_path,
    )

    records = build_operator_route_dataset(memory_dir=tmp_path)

    assert records[0]["training_use"]["include"] is False
    assert records[0]["training_use"]["category"] == CATEGORY_SAFETY_REVIEW


def test_dataset_marks_unlabeled_non_executed_trace_as_unlabeled(tmp_path) -> None:
    record_operator_interaction(
        mode="talk",
        result=build_interaction_result(),
        autorun_gate=None,
        execution={
            "attempted": False,
            "executed": False,
            "refused": False,
            "engine_request": None,
        },
        memory_dir=tmp_path,
    )

    records = build_operator_route_dataset(memory_dir=tmp_path)

    assert records[0]["training_use"]["include"] is False
    assert records[0]["training_use"]["category"] == CATEGORY_UNLABELED_TRACE


def test_export_operator_route_dataset_writes_jsonl(tmp_path) -> None:
    interaction_result = record_operator_interaction(
        mode="talkrun",
        result=build_interaction_result(),
        autorun_gate={"status": "ok", "allowed": True},
        execution={
            "attempted": True,
            "executed": True,
            "refused": False,
            "engine_request": "why is Chrome using memory",
        },
        memory_dir=tmp_path,
    )
    record_operator_feedback(
        trace_id=interaction_result["data"]["trace_id"],
        label="useful",
        note="good route",
        memory_dir=tmp_path,
    )

    output_path = tmp_path / "datasets" / "operator_route_dataset.jsonl"
    result = export_operator_route_dataset(
        memory_dir=tmp_path,
        output_path=output_path,
    )

    assert result["status"] == "ok"
    assert result["data"]["total_examples"] == 1
    assert result["data"]["included_examples"] == 1
    assert output_path.exists()

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    exported = json.loads(lines[0])
    assert exported["feedback"]["label"] == "useful"


def test_format_operator_dataset_export_report() -> None:
    report = format_operator_dataset_export_report(
        {
            "status": "ok",
            "message": "Operator route dataset exported.",
            "data": {
                "output_path": "memory/datasets/operator_route_dataset.jsonl",
                "total_examples": 2,
                "included_examples": 1,
                "review_needed_examples": 1,
                "unlabeled_examples": 0,
                "category_counts": {
                    CATEGORY_POSITIVE_ROUTE_EXAMPLE: 1,
                    CATEGORY_CORRECTION_NEEDED: 1,
                },
            },
            "errors": [],
            "warnings": [],
        }
    )

    assert "LIGHTHOUSE OPERATOR DATASET EXPORT" in report
    assert "Status: ok" in report
    assert "Examples exported: 2" in report
    assert "Included examples: 1" in report
    assert "positive_route_example: 1" in report
