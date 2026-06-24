"""
Tests for Lighthouse LLM route call boundary.
"""

from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.llm_route_engine import (
    LLM_ROUTE_STATUS_DISABLED,
    LLM_ROUTE_STATUS_INVALID,
    LLM_ROUTE_STATUS_OK,
    build_llm_route_call,
    build_llm_route_prompt,
)


def test_build_llm_route_prompt_contains_contract_boundary() -> None:
    prompt = build_llm_route_prompt("my laptop is slow")

    assert "Return only one JSON object" in prompt
    assert "llm_contract_v0" in prompt
    assert "Do not include shell commands." in prompt
    assert "Do not include tool names or tool arguments." in prompt
    assert "The deterministic Lighthouse route registry is the authority." in prompt


def test_build_llm_route_call_returns_disabled_without_model_when_ollama_disabled(monkeypatch) -> None:
    monkeypatch.delenv("LIGHTHOUSE_USE_OLLAMA", raising=False)

    result = build_llm_route_call("my laptop is slow")

    assert result.status == LLM_ROUTE_STATUS_DISABLED
    assert result.used_model is False
    assert result.validation is None


def test_build_llm_route_call_accepts_contract_shaped_json_from_injected_model() -> None:
    def fake_model(prompt: str) -> str:
        assert "my laptop is slow" in prompt
        return json.dumps(
            {
                "schema_version": "llm_contract_v0",
                "proposed_intent": "performance_diagnostic",
                "interpreted_request": "why is my laptop slow",
                "confidence": 0.83,
                "reasoning_summary": "The request describes slowness.",
                "safety_notes": ["Read-only diagnostic route."],
            }
        )

    result = build_llm_route_call(
        "my laptop is slow",
        model_callable=fake_model,
    )

    assert result.status == LLM_ROUTE_STATUS_OK
    assert result.used_model is True
    assert result.validation is not None
    assert result.validation.valid is True
    assert result.validation.route_handoff["engine_request"] == "why is my laptop slow"
    assert result.validation.route_handoff["autorun_allowed"] is True


def test_build_llm_route_call_rejects_forbidden_authority_fields_from_model() -> None:
    def fake_model(prompt: str) -> str:
        return json.dumps(
            {
                "schema_version": "llm_contract_v0",
                "proposed_intent": "performance_diagnostic",
                "interpreted_request": "why is my laptop slow",
                "confidence": 0.83,
                "tool_name": "run_windows_repair",
                "approved": True,
            }
        )

    result = build_llm_route_call(
        "my laptop is slow",
        model_callable=fake_model,
    )

    assert result.status == LLM_ROUTE_STATUS_INVALID
    assert result.validation is not None
    assert result.validation.valid is False
    assert any("forbidden authority field" in error for error in result.errors)


def test_build_llm_route_call_allows_destructive_classification_without_authority() -> None:
    def fake_model(prompt: str) -> str:
        return json.dumps(
            {
                "schema_version": "llm_contract_v0",
                "proposed_intent": "destructive_action_request",
                "interpreted_request": "delete files to make space",
                "confidence": 0.71,
                "reasoning_summary": "The user requested a data-changing action.",
                "safety_notes": ["Manual review required."],
            }
        )

    result = build_llm_route_call(
        "delete files to make space",
        model_callable=fake_model,
    )

    assert result.status == LLM_ROUTE_STATUS_OK
    assert result.validation is not None
    assert result.validation.route_handoff["autorun_allowed"] is False
    assert result.validation.route_handoff["manual_review_required"] is True
    assert result.validation.route_handoff["command_family"] == "runplan_preview_only"


def test_build_llm_route_call_normalizes_response_wrapper() -> None:
    def fake_model(prompt: str) -> dict:
        return {
            "response": json.dumps(
                {
                    "schema_version": "llm_contract_v0",
                    "proposed_intent": "general_health_check",
                    "interpreted_request": "is anything wrong with my computer",
                    "confidence": 0.7,
                }
            )
        }

    result = build_llm_route_call(
        "check my computer",
        model_callable=fake_model,
    )

    assert result.status == LLM_ROUTE_STATUS_OK
    assert result.validation is not None
    assert result.validation.route_handoff["engine_request"] == "is anything wrong with my computer"
