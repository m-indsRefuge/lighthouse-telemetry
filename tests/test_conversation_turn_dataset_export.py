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


def test_dataset_summary_counts_feedback_labels(tmp_path: Path) -> None:
    first_turn = build_conversational_engine_turn(
        "why is my laptop slow",
        memory_dir=tmp_path,
    )
    second_turn = build_conversational_engine_turn(
        "why is chrome eating memory",
        memory_dir=tmp_path,
    )

    assert first_turn.turn_journal_result is not None
    assert second_turn.turn_journal_result is not None

    first_turn_id = first_turn.turn_journal_result["data"]["turn_id"]
    second_turn_id = second_turn.turn_journal_result["data"]["turn_id"]

    from app.services.conversation_turn_feedback import record_turn_feedback

    record_turn_feedback(
        turn_id=first_turn_id,
        label="useful",
        note="good route",
        memory_dir=tmp_path,
    )
    record_turn_feedback(
        turn_id=second_turn_id,
        label="wrong_route",
        note="should route differently",
        memory_dir=tmp_path,
    )

    result = export_conversational_turn_dataset(memory_dir=tmp_path)

    assert result["status"] == "ok"
    assert result["data"]["feedback_examples"] == 2
    assert result["data"]["feedback_label_counts"] == {
        "useful": 1,
        "wrong_route": 1,
    }


def test_dataset_export_report_shows_feedback_summary(tmp_path: Path) -> None:
    turn_result = build_conversational_engine_turn(
        "why is my laptop slow",
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

    result = export_conversational_turn_dataset(memory_dir=tmp_path)
    report = format_conversational_turn_dataset_export_report(result)

    assert "Feedback examples: 1" in report
    assert "Feedback labels:" in report
    assert "- useful: 1" in report


def test_read_conversational_turn_dataset_records_reads_export_newest_first(
    tmp_path: Path,
) -> None:
    build_conversational_engine_turn(
        "why is my laptop slow",
        memory_dir=tmp_path,
    )
    build_conversational_engine_turn(
        "why is chrome eating memory",
        memory_dir=tmp_path,
    )
    export_conversational_turn_dataset(memory_dir=tmp_path)

    from app.services.conversation_turn_dataset_export import (
        read_conversational_turn_dataset_records,
    )

    records = read_conversational_turn_dataset_records(
        memory_dir=tmp_path,
        limit=1,
    )

    assert len(records) == 1
    assert records[0]["input"]["normalized"] == "why is chrome eating memory"


def test_format_conversational_turn_dataset_review_report_shows_rows(
    tmp_path: Path,
) -> None:
    turn_result = build_conversational_engine_turn(
        "why is my laptop slow",
        memory_dir=tmp_path,
    )
    assert turn_result.turn_journal_result is not None
    turn_id = turn_result.turn_journal_result["data"]["turn_id"]

    from app.services.conversation_turn_feedback import record_turn_feedback
    from app.services.conversation_turn_dataset_export import (
        format_conversational_turn_dataset_review_report,
    )

    record_turn_feedback(
        turn_id=turn_id,
        label="useful",
        note="good route",
        memory_dir=tmp_path,
    )
    export_conversational_turn_dataset(memory_dir=tmp_path)

    report = format_conversational_turn_dataset_review_report(memory_dir=tmp_path)

    assert "LIGHTHOUSE CONVERSATIONAL TURN DATASET REVIEW" in report
    assert "Shown: 1" in report
    assert f"turn_id: {turn_id}" in report
    assert "input: why is my laptop slow" in report
    assert "deterministic_intent: performance_diagnostic" in report
    assert "selected_route_source: deterministic" in report
    assert "training_include: yes" in report
    assert "training_category: deterministic_fallback_turn" in report
    assert "feedback_label: useful" in report
    assert "feedback_note: good route" in report


def test_format_conversational_turn_dataset_review_report_handles_missing_export(
    tmp_path: Path,
) -> None:
    from app.services.conversation_turn_dataset_export import (
        format_conversational_turn_dataset_review_report,
    )

    report = format_conversational_turn_dataset_review_report(memory_dir=tmp_path)

    assert "LIGHTHOUSE CONVERSATIONAL TURN DATASET REVIEW" in report
    assert "Shown: 0" in report
    assert "No conversational turn dataset rows found." in report
    assert "Run 'dataset turns' to regenerate the export first." in report


def test_dataset_review_filter_included_rows(tmp_path: Path) -> None:
    build_conversational_engine_turn(
        "why is my laptop slow",
        memory_dir=tmp_path,
    )
    build_conversational_engine_turn(
        "feedback",
        memory_dir=tmp_path,
    )
    export_conversational_turn_dataset(memory_dir=tmp_path)

    from app.services.conversation_turn_dataset_export import (
        read_conversational_turn_dataset_records,
    )

    records = read_conversational_turn_dataset_records(
        memory_dir=tmp_path,
        filter_mode="included",
    )

    assert len(records) == 1
    assert records[0]["training_use"]["include"] is True
    assert records[0]["input"]["normalized"] == "why is my laptop slow"


def test_dataset_review_filter_excluded_rows(tmp_path: Path) -> None:
    build_conversational_engine_turn(
        "why is my laptop slow",
        memory_dir=tmp_path,
    )
    build_conversational_engine_turn(
        "feedback",
        memory_dir=tmp_path,
    )
    export_conversational_turn_dataset(memory_dir=tmp_path)

    from app.services.conversation_turn_dataset_export import (
        read_conversational_turn_dataset_records,
    )

    records = read_conversational_turn_dataset_records(
        memory_dir=tmp_path,
        filter_mode="excluded",
    )

    assert len(records) == 1
    assert records[0]["training_use"]["include"] is False
    assert records[0]["training_use"]["category"] == "needs_clarification_turn"


def test_dataset_review_filter_feedback_rows(tmp_path: Path) -> None:
    first_turn = build_conversational_engine_turn(
        "why is my laptop slow",
        memory_dir=tmp_path,
    )
    build_conversational_engine_turn(
        "why is chrome eating memory",
        memory_dir=tmp_path,
    )

    assert first_turn.turn_journal_result is not None
    turn_id = first_turn.turn_journal_result["data"]["turn_id"]

    from app.services.conversation_turn_feedback import record_turn_feedback
    from app.services.conversation_turn_dataset_export import (
        read_conversational_turn_dataset_records,
    )

    record_turn_feedback(
        turn_id=turn_id,
        label="useful",
        note="good route",
        memory_dir=tmp_path,
    )
    export_conversational_turn_dataset(memory_dir=tmp_path)

    records = read_conversational_turn_dataset_records(
        memory_dir=tmp_path,
        filter_mode="feedback",
    )

    assert len(records) == 1
    assert records[0]["turn_id"] == turn_id
    assert records[0]["feedback"]["label"] == "useful"


def test_dataset_review_filter_corrections_rows(tmp_path: Path) -> None:
    turn_result = build_conversational_engine_turn(
        "why is my laptop slow",
        memory_dir=tmp_path,
    )

    assert turn_result.turn_journal_result is not None
    turn_id = turn_result.turn_journal_result["data"]["turn_id"]

    from app.services.conversation_turn_feedback import record_turn_feedback
    from app.services.conversation_turn_dataset_export import (
        read_conversational_turn_dataset_records,
    )

    record_turn_feedback(
        turn_id=turn_id,
        label="wrong_route",
        note="should route differently",
        memory_dir=tmp_path,
    )
    export_conversational_turn_dataset(memory_dir=tmp_path)

    records = read_conversational_turn_dataset_records(
        memory_dir=tmp_path,
        filter_mode="corrections",
    )

    assert len(records) == 1
    assert records[0]["turn_id"] == turn_id
    assert records[0]["training_use"]["category"] == "correction_needed"


def test_dataset_review_filter_category_rows(tmp_path: Path) -> None:
    build_conversational_engine_turn(
        "why is my laptop slow",
        memory_dir=tmp_path,
    )
    build_conversational_engine_turn(
        "feedback",
        memory_dir=tmp_path,
    )
    export_conversational_turn_dataset(memory_dir=tmp_path)

    from app.services.conversation_turn_dataset_export import (
        read_conversational_turn_dataset_records,
    )

    records = read_conversational_turn_dataset_records(
        memory_dir=tmp_path,
        filter_mode="category",
        category="needs_clarification_turn",
    )

    assert len(records) == 1
    assert records[0]["training_use"]["category"] == "needs_clarification_turn"


def test_dataset_review_filter_handles_empty_matches(tmp_path: Path) -> None:
    build_conversational_engine_turn(
        "why is my laptop slow",
        memory_dir=tmp_path,
    )
    export_conversational_turn_dataset(memory_dir=tmp_path)

    from app.services.conversation_turn_dataset_export import (
        format_conversational_turn_dataset_review_report,
    )

    report = format_conversational_turn_dataset_review_report(
        memory_dir=tmp_path,
        filter_mode="category",
        category="does_not_exist",
    )

    assert "LIGHTHOUSE CONVERSATIONAL TURN DATASET REVIEW" in report
    assert "Shown: 0" in report
    assert "Filter: category" in report
    assert "Category: does_not_exist" in report
    assert "No conversational turn dataset rows found." in report
