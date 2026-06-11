"""
Tests for the Lighthouse safe ask layer.
"""

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.llm import (
    ask_lighthouse,
    format_lighthouse_answer,
    run_ollama_model_test,
)


def build_fake_telemetry() -> dict[str, Any]:
    """
    Build fake telemetry for testing the ask layer.
    """
    return {
        "cpu": {
            "status": "ok",
            "usage_percent": 10.0,
            "physical_cores": 8,
            "logical_cores": 16,
        },
        "memory": {
            "status": "ok",
            "usage_percent": 40.0,
            "total_gb": 16,
            "used_gb": 6.4,
            "available_gb": 9.6,
        },
        "disk": {
            "status": "ok",
            "usage_percent": 20.0,
            "total_gb": 512,
            "used_gb": 102,
            "free_gb": 410,
        },
        "processes": {
            "status": "ok",
            "processes": [
                {
                    "pid": 1234,
                    "name": "TestProcess.exe",
                    "memory_mb": 512.25,
                    "cpu_percent": 1.2,
                }
            ],
        },
    }


def build_fake_event_report() -> dict[str, Any]:
    """
    Build fake event-log evidence for testing the ask layer.
    """
    return {
        "status": "ok",
        "severity_summary": {
            "critical": 0,
            "warning": 0,
            "context": 5,
        },
        "possible_causes": [],
        "events": [],
    }


def test_ask_lighthouse_rejects_empty_question() -> None:
    result = ask_lighthouse("")

    assert result["status"] == "error"
    assert "No question provided" in result["message"]


def test_format_lighthouse_answer_contains_question() -> None:
    insight = {
        "overall_status": "GOOD",
        "summary": "Lighthouse did not find an obvious system fault.",
        "conclusion": "The system looks healthy right now.",
        "findings": ["CPU usage is healthy."],
        "recommendations": ["No immediate action needed."],
    }

    answer = format_lighthouse_answer(
        user_question="Is anything wrong with my laptop?",
        insight=insight,
    )

    assert "LIGHTHOUSE ASSISTANT" in answer
    assert "Question: Is anything wrong with my laptop?" in answer
    assert "Overall status: GOOD" in answer
    assert "AI mode:" in answer
    assert "Local Ollama model was not used." in answer


def test_ask_lighthouse_returns_safe_stub_answer(monkeypatch) -> None:
    """
    The ask layer should use the deterministic fallback when Ollama is disabled.
    """
    monkeypatch.setattr(
        "app.services.llm.collect_telemetry",
        build_fake_telemetry,
    )
    monkeypatch.setattr(
        "app.services.llm.get_recent_system_events",
        lambda limit=100: build_fake_event_report(),
    )
    monkeypatch.setattr(
        "app.services.llm.is_ollama_enabled",
        lambda: False,
    )

    result = ask_lighthouse("Is anything wrong with my laptop?")

    assert result["status"] == "ok"
    assert result["provider"] == "lighthouse_insight_engine"
    assert result["model"] == "deterministic_fallback"
    assert result["uses_external_ai"] is False
    assert result["used_fallback"] is True
    assert result["question"] == "Is anything wrong with my laptop?"
    assert "LIGHTHOUSE ASSISTANT" in result["answer"]
    assert "Overall status: GOOD" in result["answer"]


def test_ask_lighthouse_includes_insight_metrics(monkeypatch) -> None:
    """
    The ask layer should include structured insight metrics in fallback mode.
    """
    monkeypatch.setattr(
        "app.services.llm.collect_telemetry",
        build_fake_telemetry,
    )
    monkeypatch.setattr(
        "app.services.llm.get_recent_system_events",
        lambda limit=100: build_fake_event_report(),
    )
    monkeypatch.setattr(
        "app.services.llm.is_ollama_enabled",
        lambda: False,
    )

    result = ask_lighthouse("How is my system?")

    insight = result["insight"]

    assert insight["status"] == "ok"
    assert insight["overall_status"] == "GOOD"
    assert insight["metrics"]["cpu_status"] == "OK"
    assert insight["metrics"]["memory_status"] == "OK"
    assert insight["metrics"]["disk_status"] == "OK"


def test_run_ollama_model_test_returns_disabled_when_ollama_is_off(monkeypatch) -> None:
    """
    The model test should not call Ollama when Ollama is disabled.
    """
    monkeypatch.setattr(
        "app.services.llm.is_ollama_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        "app.services.llm.get_ollama_model",
        lambda: "qwen2.5:3b",
    )

    result = run_ollama_model_test()

    assert result["status"] == "disabled"
    assert result["model"] == "qwen2.5:3b"
    assert "LIGHTHOUSE_USE_OLLAMA=1" in result["message"]


def test_run_ollama_model_test_returns_ok_when_model_responds(monkeypatch) -> None:
    """
    The model test should return ok when Ollama is enabled and responds.
    """
    monkeypatch.setattr(
        "app.services.llm.is_ollama_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.llm.get_ollama_model",
        lambda: "qwen2.5:3b",
    )
    monkeypatch.setattr(
        "app.services.llm.get_ollama_status",
        lambda: {
            "status": "ok",
            "server_available": True,
            "configured_model": "qwen2.5:3b",
            "configured_model_installed": True,
            "installed_models": ["qwen2.5:3b"],
        },
    )
    monkeypatch.setattr(
        "app.services.llm.call_ollama",
        lambda prompt: {
            "status": "ok",
            "model": "qwen2.5:3b",
            "answer": "Lighthouse model test successful.",
        },
    )

    result = run_ollama_model_test()

    assert result["status"] == "ok"
    assert result["model"] == "qwen2.5:3b"
    assert "Lighthouse model test successful" in result["response"]


def test_run_ollama_model_test_reports_missing_model(monkeypatch) -> None:
    """
    The model test should report when Ollama is reachable but the model is missing.
    """
    monkeypatch.setattr(
        "app.services.llm.is_ollama_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.llm.get_ollama_model",
        lambda: "qwen2.5:3b",
    )
    monkeypatch.setattr(
        "app.services.llm.get_ollama_status",
        lambda: {
            "status": "ok",
            "server_available": True,
            "configured_model": "qwen2.5:3b",
            "configured_model_installed": False,
            "installed_models": [],
        },
    )

    result = run_ollama_model_test()

    assert result["status"] == "error"
    assert result["model"] == "qwen2.5:3b"
    assert "configured model is not installed" in result["message"]