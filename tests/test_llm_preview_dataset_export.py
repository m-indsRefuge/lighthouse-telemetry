"""
Tests for LLM preview dataset export.
"""

from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.llm_preview_dataset_export import (
    CATEGORY_BOUNDARY_ERROR_REVIEW,
    CATEGORY_INVALID_CONTRACT_EXAMPLE,
    CATEGORY_NO_MODEL_OUTPUT,
    CATEGORY_SAFE_UNCERTAIN_PREVIEW,
    CATEGORY_SAFETY_REVIEW,
    CATEGORY_VALID_ROUTE_PREVIEW,
    build_dataset_record,
    classify_preview_training_use,
    export_llm_preview_dataset,
    format_llm_preview_dataset_export_report,
)
from app.services.llm_preview_journal import append_jsonl, llm_preview_journal_path


def valid_preview() -> dict:
    return {
        "preview_id": "llmprev-valid",
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


def test_classifies_valid_route_preview() -> None:
    result = classify_preview_training_use(valid_preview())

    assert result["include"] is True
    assert result["category"] == CATEGORY_VALID_ROUTE_PREVIEW


def test_classifies_invalid_contract_example() -> None:
    preview = valid_preview()
    preview["status"] = "invalid"
    preview["contract_valid"] = False
    preview["errors"] = ["forbidden authority field: tool_name"]

    result = classify_preview_training_use(preview)

    assert result["include"] is True
    assert result["category"] == CATEGORY_INVALID_CONTRACT_EXAMPLE


def test_classifies_safe_uncertain_preview() -> None:
    preview = valid_preview()
    preview["proposed_intent"] = "unknown"
    preview["interpreted_request"] = None
    preview["route_handoff"] = {"route_ready": False}

    result = classify_preview_training_use(preview)

    assert result["include"] is True
    assert result["category"] == CATEGORY_SAFE_UNCERTAIN_PREVIEW


def test_classifies_disabled_without_model_output() -> None:
    preview = valid_preview()
    preview["status"] = "disabled"
    preview["contract_valid"] = None

    result = classify_preview_training_use(preview)

    assert result["include"] is False
    assert result["category"] == CATEGORY_NO_MODEL_OUTPUT


def test_classifies_boundary_error_for_review() -> None:
    preview = valid_preview()
    preview["status"] = "error"
    preview["contract_valid"] = None

    result = classify_preview_training_use(preview)

    assert result["include"] is False
    assert result["category"] == CATEGORY_BOUNDARY_ERROR_REVIEW


def test_classifies_impossible_safety_flags_for_review() -> None:
    preview = valid_preview()
    preview["safety"]["executed"] = True

    result = classify_preview_training_use(preview)

    assert result["include"] is False
    assert result["category"] == CATEGORY_SAFETY_REVIEW


def test_build_dataset_record_preserves_safe_target_fields() -> None:
    record = build_dataset_record(valid_preview())

    assert record["preview_id"] == "llmprev-valid"
    assert record["input"]["normalized"] == "my laptop is slow"
    assert record["contract"]["valid"] is True
    assert record["contract"]["proposed_intent"] == "performance_diagnostic"
    assert record["route_handoff"]["recommended_command"] == "runplan why is my laptop slow"
    assert record["outcome"]["preview_only"] is True
    assert record["outcome"]["executed"] is False
    assert record["outcome"]["model_authority"] is False
    assert record["training_use"]["category"] == CATEGORY_VALID_ROUTE_PREVIEW


def test_export_llm_preview_dataset_writes_jsonl(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    append_jsonl(llm_preview_journal_path(memory_dir), valid_preview())

    result = export_llm_preview_dataset(memory_dir=memory_dir)

    assert result["status"] == "ok"
    assert result["data"]["total_examples"] == 1
    assert result["data"]["included_examples"] == 1

    output_path = Path(result["data"]["output_path"])
    lines = output_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 1
    exported = json.loads(lines[0])

    assert exported["preview_id"] == "llmprev-valid"
    assert exported["training_use"]["category"] == CATEGORY_VALID_ROUTE_PREVIEW


def test_format_llm_preview_dataset_export_report() -> None:
    report = format_llm_preview_dataset_export_report(
        {
            "status": "ok",
            "message": "LLM preview dataset exported.",
            "data": {
                "output_path": "memory/datasets/llm_preview_route_dataset.jsonl",
                "total_examples": 2,
                "included_examples": 1,
                "review_needed_examples": 0,
                "unlabeled_examples": 1,
                "category_counts": {
                    CATEGORY_VALID_ROUTE_PREVIEW: 1,
                    "unlabeled_preview": 1,
                },
            },
            "errors": [],
            "warnings": [],
        }
    )

    assert "LIGHTHOUSE LLM PREVIEW DATASET EXPORT" in report
    assert "Status: ok" in report
    assert "Examples exported: 2" in report
    assert "Included examples: 1" in report
    assert CATEGORY_VALID_ROUTE_PREVIEW in report
