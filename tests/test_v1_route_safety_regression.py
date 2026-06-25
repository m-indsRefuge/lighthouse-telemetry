"""
Route and LLM authority safety regression tests for V1 consolidation.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.llm_contract import validate_llm_route_proposal
from app.services.llm_route_engine import build_llm_route_call
from app.services.operator_routes import validate_operator_route_registry


VALID_MODEL_PROPOSAL = """
{
  "schema_version": "llm_contract_v0",
  "proposed_intent": "performance_diagnostic",
  "interpreted_request": "why is my laptop slow",
  "confidence": 0.8,
  "reasoning_summary": "The user asks about slowness.",
  "safety_notes": ["Read-only diagnostic route only."]
}
"""


def test_operator_route_registry_validation_still_passes() -> None:
    result = validate_operator_route_registry()

    assert result["status"] == "ok"
    assert result["errors"] == []


def test_llm_contract_rejects_authority_fields() -> None:
    proposal = {
        "schema_version": "llm_contract_v0",
        "proposed_intent": "performance_diagnostic",
        "interpreted_request": "why is my laptop slow",
        "confidence": 0.8,
        "reasoning_summary": "The user asks about slowness.",
        "safety_notes": ["Read-only diagnostic route only."],
        "recommended_command": "runplan why is my laptop slow",
        "autorun_allowed": True,
    }

    result = validate_llm_route_proposal(proposal)

    assert result.valid is False
    assert result.status == "invalid"
    joined_errors = " ".join(result.errors).lower()
    assert "recommended_command" in joined_errors
    assert "autorun_allowed" in joined_errors


def test_llm_route_call_never_executes_valid_model_route() -> None:
    calls: list[str] = []

    def model_callable(prompt: str) -> str:
        calls.append(prompt)
        return VALID_MODEL_PROPOSAL

    result = build_llm_route_call(
        "why is my laptop slow",
        model_callable=model_callable,
    )

    assert result.status == "ok"
    assert result.used_model is True
    assert len(calls) == 1
    assert result.validation is not None
    assert result.validation.valid is True
    assert result.validation.route_handoff is not None
    assert result.validation.route_handoff["recommended_command"] == (
        "runplan why is my laptop slow"
    )
    assert "executed" not in result.to_dict()
