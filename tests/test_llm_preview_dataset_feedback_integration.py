"""
Tests for LLM preview dataset export feedback integration.
"""

from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.llm_preview_dataset_export import (
    CATEGORY_CORRECTION_NEEDED,
    CATEGORY_POSITIVE_PREVIEW_EXAMPLE,
    CATEGORY_SAFETY_REVIEW,
    build_llm_preview_dataset,
    export_llm_preview_dataset,
)
from app.services.llm_preview_feedback import record_llm_preview_feedback
from app.services.llm_preview_journal import append_jsonl, llm_preview_journal_path


def valid_preview(preview_id: str = "llmprev-valid") -> dict:
    return {
        "preview_id": preview_id,
        "created_at": "2026-01-01T00:00:00+00:00",
        "mode": "llm_preview",
        "original_input": "my laptop is slow",
        "normalized_input": "my laptop is slow",
        "status": "ok",
        "message": "passed",
        "model_used": "injected_model",
        "used_model": True,
        "validation_status": "ok",
        "contract_valid": True,
        "proposed_intent": "performance_diagnostic",
        "interpreted_request": "why is my laptop slow",
        "route_handoff": {
            "route_ready": True,
            "route_known": True,
            "intent": "performance_diagnostic",
            "safety_class": "read_only_diagnostic",
            "command_family": "runplan",
            "recommended_command": "runplan why is my laptop slow",
            "engine_request": "why is my laptop slow",
            "autorun_allowed": True,
            "manual_review_required": False,
        },
        "errors": [],
        "warnings": [],
        "safety": {
            "preview_only": True,
            "executed": False,
            "talk_integration": False,
            "talkrun_integration": False,
            "model_authority": False,
            "os_mutation": False,
        },
    }


def test_dataset_record_includes_latest_preview_feedback(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    append_jsonl(llm_preview_journal_path(memory_dir), valid_preview("llmprev-1"))

    record_llm_preview_feedback(
        preview_id="llmprev-1",
        label="confusing",
        note="first note",
        memory_dir=memory_dir,
    )
    record_llm_preview_feedback(
        preview_id="llmprev-1",
        label="useful",
        note="latest note",
        memory_dir=memory_dir,
    )

    records = build_llm_preview_dataset(memory_dir=memory_dir)

    assert len(records) == 1
    assert records[0]["feedback"]["label"] == "useful"
    assert records[0]["feedback"]["note"] == "latest note"
    assert records[0]["training_use"]["category"] == CATEGORY_POSITIVE_PREVIEW_EXAMPLE
    assert records[0]["training_use"]["include"] is True


def test_wrong_route_feedback_overrides_valid_preview_category(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    append_jsonl(llm_preview_journal_path(memory_dir), valid_preview("llmprev-2"))

    record_llm_preview_feedback(
        preview_id="llmprev-2",
        label="wrong_route",
        note="should not have routed",
        memory_dir=memory_dir,
    )

    records = build_llm_preview_dataset(memory_dir=memory_dir)

    assert records[0]["feedback"]["label"] == "wrong_route"
    assert records[0]["training_use"]["category"] == CATEGORY_CORRECTION_NEEDED
    assert records[0]["training_use"]["include"] is False


def test_unsafe_feedback_marks_safety_review(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    append_jsonl(llm_preview_journal_path(memory_dir), valid_preview("llmprev-3"))

    record_llm_preview_feedback(
        preview_id="llmprev-3",
        label="unsafe",
        note="unsafe routing proposal",
        memory_dir=memory_dir,
    )

    records = build_llm_preview_dataset(memory_dir=memory_dir)

    assert records[0]["feedback"]["label"] == "unsafe"
    assert records[0]["training_use"]["category"] == CATEGORY_SAFETY_REVIEW
    assert records[0]["training_use"]["include"] is False


def test_export_summary_counts_feedback_review_categories(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    append_jsonl(llm_preview_journal_path(memory_dir), valid_preview("llmprev-4"))
    append_jsonl(llm_preview_journal_path(memory_dir), valid_preview("llmprev-5"))

    record_llm_preview_feedback(
        preview_id="llmprev-4",
        label="wrong_intent",
        memory_dir=memory_dir,
    )
    record_llm_preview_feedback(
        preview_id="llmprev-5",
        label="unsafe",
        memory_dir=memory_dir,
    )

    result = export_llm_preview_dataset(memory_dir=memory_dir)

    assert result["status"] == "ok"
    assert result["data"]["total_examples"] == 2
    assert result["data"]["included_examples"] == 0
    assert result["data"]["review_needed_examples"] == 2

    output_path = Path(result["data"]["output_path"])
    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]

    assert {row["feedback"]["label"] for row in rows} == {"wrong_intent", "unsafe"}
