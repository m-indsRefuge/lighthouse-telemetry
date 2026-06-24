"""
Tests for Lighthouse Engine LLM Contract boundary.
"""

from pathlib import Path
import json
import sys
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.lighthouse_engine import run_lighthouse_engine


def fake_execution_result(user_request: str) -> SimpleNamespace:
    return SimpleNamespace(
        user_request=user_request,
        status="ok",
        plan_status="completed",
        intent="diagnose",
        message="Fake execution complete.",
        executed_tools=(),
        refused_tools=(),
        blocked_tools=(),
        safe_alternatives=(),
        to_dict=lambda: {
            "user_request": user_request,
            "status": "ok",
            "plan_status": "completed",
            "intent": "diagnose",
            "message": "Fake execution complete.",
        },
    )


def test_engine_does_not_call_llm_contract_by_default(monkeypatch) -> None:
    calls: list[str] = []

    def fake_model(prompt: str) -> str:
        calls.append(prompt)
        raise AssertionError("Model should not be called by default.")

    monkeypatch.setattr(
        "app.services.lighthouse_engine.execute_tools_for_request",
        lambda request: fake_execution_result(request),
    )
    monkeypatch.setattr(
        "app.services.lighthouse_engine.record_plan_execution",
        lambda execution_result: None,
    )

    result = run_lighthouse_engine(
        "my laptop is slow",
        include_memory_context=False,
        llm_route_model=fake_model,
    )

    data = result.to_dict()

    assert calls == []
    assert data["status"] == "ok"
    assert data["llm_route_contract"] is None


def test_engine_can_call_llm_contract_boundary_when_enabled(monkeypatch) -> None:
    def fake_model(prompt: str) -> str:
        assert "my laptop is slow" in prompt
        return json.dumps(
            {
                "schema_version": "llm_contract_v0",
                "proposed_intent": "performance_diagnostic",
                "interpreted_request": "why is my laptop slow",
                "confidence": 0.88,
                "reasoning_summary": "The user described slowness.",
                "safety_notes": ["Read-only diagnostic route."],
            }
        )

    monkeypatch.setattr(
        "app.services.lighthouse_engine.execute_tools_for_request",
        lambda request: fake_execution_result(request),
    )
    monkeypatch.setattr(
        "app.services.lighthouse_engine.record_plan_execution",
        lambda execution_result: None,
    )

    result = run_lighthouse_engine(
        "my laptop is slow",
        include_memory_context=False,
        include_llm_route_contract=True,
        llm_route_model=fake_model,
    )

    data = result.to_dict()

    assert data["status"] == "ok"
    assert data["llm_route_contract"]["status"] == "ok"
    assert data["llm_route_contract"]["validation"]["valid"] is True
    assert (
        data["llm_route_contract"]["validation"]["route_handoff"]["engine_request"]
        == "why is my laptop slow"
    )


def test_engine_llm_contract_failure_does_not_stop_deterministic_engine(monkeypatch) -> None:
    def fake_model(prompt: str) -> str:
        return json.dumps(
            {
                "schema_version": "llm_contract_v0",
                "proposed_intent": "performance_diagnostic",
                "interpreted_request": "why is my laptop slow",
                "confidence": 0.88,
                "tool_name": "unsafe_tool",
                "approved": True,
            }
        )

    monkeypatch.setattr(
        "app.services.lighthouse_engine.execute_tools_for_request",
        lambda request: fake_execution_result(request),
    )
    monkeypatch.setattr(
        "app.services.lighthouse_engine.record_plan_execution",
        lambda execution_result: None,
    )

    result = run_lighthouse_engine(
        "my laptop is slow",
        include_memory_context=False,
        include_llm_route_contract=True,
        llm_route_model=fake_model,
    )

    data = result.to_dict()

    assert data["status"] == "ok"
    assert data["execution_status"] == "ok"
    assert data["llm_route_contract"]["status"] == "invalid"
    assert data["llm_route_contract"]["validation"]["valid"] is False
