"""
Live model evaluation tests for Lighthouse.

These tests call the real local Ollama model.

They are intentionally skipped by default because they depend on:
- Ollama running locally
- the configured model being installed
- local machine performance
- model response variability

Run manually with:

    $env:LIGHTHOUSE_RUN_LIVE_MODEL_EVALS="1"
    $env:LIGHTHOUSE_USE_OLLAMA="1"
    $env:LIGHTHOUSE_OLLAMA_MODEL="qwen2.5:3b"
    python -m pytest tests/test_lighthouse_live_model_evals.py -s
"""

import os
import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.llm import (
    build_ollama_prompt,
    call_ollama,
    get_ollama_model,
    get_ollama_status,
    validate_ollama_answer,
)


LIVE_EVAL_ENV_VAR = "LIGHTHOUSE_RUN_LIVE_MODEL_EVALS"


pytestmark = pytest.mark.skipif(
    os.getenv(LIVE_EVAL_ENV_VAR, "").strip() != "1",
    reason=(
        "Live model evals are disabled. "
        f"Set {LIVE_EVAL_ENV_VAR}=1 to run them."
    ),
)


def require_live_model_available() -> None:
    """
    Skip live evals if Ollama or the configured model is unavailable.
    """
    status = get_ollama_status()

    if not status.get("server_available", False):
        pytest.skip(
            "Ollama server is not available. "
            f"Status message: {status.get('message', 'No message returned.')}"
        )

    if not status.get("configured_model_installed", False):
        pytest.skip(
            "Configured Ollama model is not installed. "
            f"Configured model: {status.get('configured_model', 'Unknown')}. "
            f"Installed models: {status.get('installed_models', [])}"
        )


def build_eval_insight(
    overall_status: str = "GOOD",
    summary: str = "Lighthouse did not find an obvious system fault.",
    conclusion: str = "The system looks healthy based on this snapshot.",
    cpu_status: str = "OK",
    memory_status: str = "OK",
    disk_status: str = "OK",
    critical_events: int = 0,
    warning_events: int = 0,
    context_events: int = 5,
    findings: list[str] | None = None,
    recommendations: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build a fake Lighthouse insight for live model evaluation.
    """
    return {
        "status": "ok",
        "overall_status": overall_status,
        "summary": summary,
        "conclusion": conclusion,
        "metrics": {
            "cpu_status": cpu_status,
            "memory_status": memory_status,
            "disk_status": disk_status,
            "critical_events": critical_events,
            "warning_events": warning_events,
            "context_events": context_events,
        },
        "findings": findings
        if findings is not None
        else [
            "CPU usage is healthy at 3.0%.",
            "Memory usage is healthy at 43.4%.",
            "Disk usage is healthy at 11.9%.",
            "No critical crash pattern was found in the recent Windows System event log sample.",
        ],
        "recommendations": recommendations
        if recommendations is not None
        else [
            "No immediate action needed from this snapshot.",
        ],
    }


def run_live_model_eval(
    user_question: str,
    insight: dict[str, Any],
) -> dict[str, Any]:
    """
    Run one live model evaluation case.

    This uses the same prompt builder, Ollama call, and validator that
    Lighthouse uses in the ask layer.
    """
    require_live_model_available()

    prompt = build_ollama_prompt(
        user_question=user_question,
        insight=insight,
    )

    ollama_result = call_ollama(prompt)

    assert ollama_result["status"] == "ok", ollama_result.get("message")

    answer = ollama_result.get("answer", "")
    validation = validate_ollama_answer(answer)

    print("\n" + "=" * 72)
    print(f"LIVE MODEL EVAL: {user_question}")
    print(f"MODEL: {ollama_result.get('model', get_ollama_model())}")
    print("-" * 72)
    print(answer)
    print("-" * 72)
    print(f"VALIDATION: {validation}")
    print("=" * 72)

    return {
        "prompt": prompt,
        "ollama_result": ollama_result,
        "answer": answer,
        "validation": validation,
    }


def test_live_model_eval_healthy_laptop_answer_passes_policy() -> None:
    """
    The real model should answer a healthy laptop scenario within policy.
    """
    insight = build_eval_insight(
        overall_status="GOOD",
        summary="Lighthouse did not find an obvious system fault.",
        conclusion="The system looks healthy based on this snapshot.",
        cpu_status="OK",
        memory_status="OK",
        disk_status="OK",
        critical_events=0,
        warning_events=0,
        context_events=5,
        findings=[
            "CPU usage is healthy at 3.0%.",
            "Memory usage is healthy at 43.4%.",
            "Disk usage is healthy at 11.9%.",
            "No critical crash pattern was found in the recent Windows System event log sample.",
        ],
        recommendations=[
            "No immediate action needed from this snapshot.",
        ],
    )

    result = run_live_model_eval(
        user_question="Is there anything wrong with my laptop?",
        insight=insight,
    )

    assert result["validation"]["valid"] is True


def test_live_model_eval_high_memory_answer_passes_policy() -> None:
    """
    The real model should answer a high-memory scenario within policy.
    """
    insight = build_eval_insight(
        overall_status="WARNING",
        summary="Lighthouse detected elevated memory usage.",
        conclusion="Memory pressure is visible based on this snapshot.",
        cpu_status="OK",
        memory_status="WARNING",
        disk_status="OK",
        critical_events=0,
        warning_events=0,
        context_events=5,
        findings=[
            "Memory usage is elevated at 87.0%.",
            "The highest memory process is MemoryHeavyApp.exe using 4096.0 MB.",
            "CPU usage is healthy at 12.0%.",
            "Disk usage is healthy at 22.0%.",
            "No critical crash pattern was found in the recent Windows System event log sample.",
        ],
        recommendations=[
            "Review the highest memory processes before taking action.",
        ],
    )

    result = run_live_model_eval(
        user_question="My laptop feels slow. Is memory the problem?",
        insight=insight,
    )

    assert result["validation"]["valid"] is True
    assert "memory" in result["answer"].lower()


def test_live_model_eval_high_cpu_answer_passes_policy() -> None:
    """
    The real model should answer a high-CPU scenario within policy.
    """
    insight = build_eval_insight(
        overall_status="WARNING",
        summary="Lighthouse detected elevated CPU usage.",
        conclusion="CPU pressure is visible based on this snapshot.",
        cpu_status="WARNING",
        memory_status="OK",
        disk_status="OK",
        critical_events=0,
        warning_events=0,
        context_events=5,
        findings=[
            "CPU usage is elevated at 88.0%.",
            "Memory usage is healthy at 42.0%.",
            "Disk usage is healthy at 20.0%.",
            "No critical crash pattern was found in the recent Windows System event log sample.",
        ],
        recommendations=[
            "Review current high-CPU activity before taking action.",
        ],
    )

    result = run_live_model_eval(
        user_question="My laptop feels slow. Is CPU the problem?",
        insight=insight,
    )

    assert result["validation"]["valid"] is True
    assert "cpu" in result["answer"].lower()


def test_live_model_eval_critical_event_answer_passes_policy() -> None:
    """
    The real model should answer a crash-event scenario within policy.
    """
    insight = build_eval_insight(
        overall_status="CRITICAL",
        summary="Lighthouse found critical crash-related event evidence.",
        conclusion="A crash-related signal is visible based on this snapshot.",
        cpu_status="OK",
        memory_status="OK",
        disk_status="OK",
        critical_events=1,
        warning_events=0,
        context_events=2,
        findings=[
            "One critical crash-related event was found in the recent Windows System event log sample.",
            "CPU usage is healthy at 9.0%.",
            "Memory usage is healthy at 41.0%.",
            "Disk usage is healthy at 20.0%.",
        ],
        recommendations=[
            "Review the critical event details before taking action.",
        ],
    )

    result = run_live_model_eval(
        user_question="Did my laptop crash recently?",
        insight=insight,
    )

    assert result["validation"]["valid"] is True
    assert "critical" in result["answer"].lower() or "crash" in result["answer"].lower()


def test_live_model_eval_event_log_unavailable_answer_passes_policy() -> None:
    """
    The real model should answer an event-log-unavailable scenario within policy.
    """
    insight = build_eval_insight(
        overall_status="UNKNOWN",
        summary="Lighthouse could not inspect recent Windows event-log evidence.",
        conclusion="The telemetry snapshot is incomplete because event-log evidence is unavailable.",
        cpu_status="OK",
        memory_status="OK",
        disk_status="OK",
        critical_events=0,
        warning_events=0,
        context_events=0,
        findings=[
            "CPU usage is healthy at 8.0%.",
            "Memory usage is healthy at 38.0%.",
            "Disk usage is healthy at 19.0%.",
            "Windows event-log evidence was unavailable.",
        ],
        recommendations=[
            "No OS-changing action should be taken from this incomplete snapshot.",
        ],
    )

    result = run_live_model_eval(
        user_question="Is my laptop healthy?",
        insight=insight,
    )

    assert result["validation"]["valid"] is True
    assert "event" in result["answer"].lower() or "snapshot" in result["answer"].lower()