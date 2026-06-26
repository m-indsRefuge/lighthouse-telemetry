"""
Tests for conversational turn dataset export.
"""

from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.conversational_engine_turn import build_conversational_engine_turn
from app.services.conversation_turn_dataset_export import (
    CATEGORY_CONTRACT_REJECTION_TURN,
    CATEGORY_DETERMINISTIC_FALLBACK_TURN,
    CATEGORY_LLM_CONTRACT_ROUTE_TURN,
    build_conversational_turn_dataset,
    export_conversational_turn_dataset,
    format_conversational_turn_dataset_export_report,
)


def valid_route_model(prompt: str) -> dict[str, str]:
    return {
        "response": json.dumps(
            {
                "schema_version": "llm_contract_v0",
                "proposed_intent": "performance_diagnostic",
                "interpreted_request": "why is my laptop slow",
                "confidence": 0.91,
                "reasoning_summary": "The user is asking about slow performance.",
                "safety_notes": ["Read-only diagnostic route only."],
            }
        )
    }


def invalid_authority_model(prompt: str) -> dict[str, str]:
    return {
        "response": json.dumps(
            {
                "schema_version": "llm_contract_v0",
                "proposed_intent": "performance_diagnostic",
                "interpreted_request": "why is my laptop slow",
                "confidence": 0.91,
                "reasoning_summary": "The user is asking about slow performance.",
                "safety_notes": ["Read-only diagnostic route only."],
                "command": "runplan why is my laptop slow",
            }
        )
    }


def test_build_dataset_from_valid_llm_contract_turn(tmp_path: Path) -> None:
    build_conversational_engine_turn(
        "why is my laptop slow",
        model_callable=valid_route_model,
        memory_dir=tmp_path,
    )

    records = build_conversational_turn_dataset(memory_dir=tmp_path)

    assert len(records) == 1
    record = records[0]

    assert record["turn_id"].startswith("turn-")
    assert record["input"]["normalized"] == "why is my laptop slow"
    assert record["deterministic"]["intent"] == "performance_diagnostic"
    assert record["llm_route"]["contract_valid"] is True
    assert record["selected_route"]["source"] == "llm_contract"
    assert record["outcome"]["executed"] is False
    assert record["outcome"]["preview_only"] is True
    assert record["training_use"]["include"] is True
    assert record["training_use"]["category"] == CATEGORY_LLM_CONTRACT_ROUTE_TURN


def test_invalid_model_contract_turn_is_negative_example(tmp_path: Path) -> None:
    build_conversational_engine_turn(
        "why is my laptop slow",
        model_callable=invalid_authority_model,
        memory_dir=tmp_path,
    )

    record = build_conversational_turn_dataset(memory_dir=tmp_path)[0]

    assert record["llm_route"]["status"] == "invalid"
    assert record["selected_route"]["source"] == "deterministic"
    assert record["training_use"]["include"] is True
    assert record["training_use"]["category"] == CATEGORY_CONTRACT_REJECTION_TURN


def test_disabled_llm_turn_becomes_deterministic_fallback_dataset_row(
    tmp_path: Path,
) -> None:
    build_conversational_engine_turn(
        "why is chrome eating memory",
        memory_dir=tmp_path,
    )

    record = build_conversational_turn_dataset(memory_dir=tmp_path)[0]

    assert record["llm_route"]["status"] == "disabled"
    assert record["selected_route"]["source"] == "deterministic"
    assert record["training_use"]["include"] is True
    assert record["training_use"]["category"] == CATEGORY_DETERMINISTIC_FALLBACK_TURN


def test_export_conversational_turn_dataset_writes_jsonl(tmp_path: Path) -> None:
    build_conversational_engine_turn(
        "why is my laptop slow",
        model_callable=valid_route_model,
        memory_dir=tmp_path,
    )

    result = export_conversational_turn_dataset(memory_dir=tmp_path)

    assert result["status"] == "ok"
    assert result["data"]["total_examples"] == 1
    assert result["data"]["included_examples"] == 1

    output_path = Path(result["data"]["output_path"])
    assert output_path.exists()

    rows = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["input"]["normalized"] == "why is my laptop slow"


def test_format_conversational_turn_dataset_export_report(tmp_path: Path) -> None:
    build_conversational_engine_turn(
        "why is my laptop slow",
        model_callable=valid_route_model,
        memory_dir=tmp_path,
    )

    result = export_conversational_turn_dataset(memory_dir=tmp_path)
    report = format_conversational_turn_dataset_export_report(result)

    assert "LIGHTHOUSE CONVERSATIONAL TURN DATASET EXPORT" in report
    assert "Status: ok" in report
    assert "Examples exported: 1" in report
    assert "Included examples: 1" in report
    assert "Output:" in report


def test_dataset_includes_latest_turn_feedback(tmp_path: Path) -> None:
    turn_result = build_conversational_engine_turn(
        "why is chrome eating memory",
        memory_dir=tmp_path,
    )
    assert turn_result.turn_journal_result is not None
    turn_id = turn_result.turn_journal_result["data"]["turn_id"]

    from app.services.conversation_turn_feedback import record_turn_feedback

    record_turn_feedback(
        turn_id=turn_id,
        label="useful",
        note="good route",
        memory_dir=tmp_path,
    )

    record = build_conversational_turn_dataset(memory_dir=tmp_path)[0]

    assert record["feedback"]["label"] == "useful"
    assert record["feedback"]["note"] == "good route"
    assert record["feedback"]["feedback_id"].startswith("turnfb-")


def test_dataset_feedback_label_can_mark_turn_for_correction(tmp_path: Path) -> None:
    turn_result = build_conversational_engine_turn(
        "why is chrome eating memory",
        memory_dir=tmp_path,
    )
    assert turn_result.turn_journal_result is not None
    turn_id = turn_result.turn_journal_result["data"]["turn_id"]

    from app.services.conversation_turn_feedback import record_turn_feedback

    record_turn_feedback(
        turn_id=turn_id,
        label="wrong_route",
        note="should route differently",
        memory_dir=tmp_path,
    )

    record = build_conversational_turn_dataset(memory_dir=tmp_path)[0]

    assert record["feedback"]["label"] == "wrong_route"
    assert record["training_use"]["include"] is False
    assert record["training_use"]["category"] == "correction_needed"
