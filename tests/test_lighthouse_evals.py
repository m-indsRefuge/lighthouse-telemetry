"""
Evaluation cases for Lighthouse assistant behavior.

These tests act as a lightweight quality gate before Lighthouse moves toward
action planning and OS tools.

The goal is to confirm that common laptop states produce stable, safe,
evidence-grounded behavior.
"""

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.llm import ask_lighthouse


def build_eval_telemetry(
    cpu_usage: float = 10.0,
    memory_usage: float = 40.0,
    disk_usage: float = 20.0,
    top_process_name: str = "TestProcess.exe",
    top_process_memory_mb: float = 512.25,
) -> dict[str, Any]:
    """
    Build fake telemetry for Lighthouse evaluation cases.
    """
    return {
        "cpu": {
            "status": "ok",
            "usage_percent": cpu_usage,
            "physical_cores": 8,
            "logical_cores": 16,
        },
        "memory": {
            "status": "ok",
            "usage_percent": memory_usage,
            "total_gb": 16,
            "used_gb": round(16 * (memory_usage / 100), 2),
            "available_gb": round(16 * (1 - memory_usage / 100), 2),
        },
        "disk": {
            "status": "ok",
            "usage_percent": disk_usage,
            "total_gb": 512,
            "used_gb": round(512 * (disk_usage / 100), 2),
            "free_gb": round(512 * (1 - disk_usage / 100), 2),
        },
        "processes": {
            "status": "ok",
            "processes": [
                {
                    "pid": 1234,
                    "name": top_process_name,
                    "memory_mb": top_process_memory_mb,
                    "cpu_percent": 1.2,
                }
            ],
        },
    }


def build_eval_event_report(
    critical: int = 0,
    warning: int = 0,
    context: int = 5,
    status: str = "ok",
    message: str = "",
    possible_causes: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build fake event-log evidence for Lighthouse evaluation cases.
    """
    if status != "ok":
        return {
            "status": status,
            "message": message or "Event log unavailable.",
            "severity_summary": {
                "critical": 0,
                "warning": 0,
                "context": 0,
            },
            "possible_causes": [],
            "events": [],
        }

    return {
        "status": "ok",
        "severity_summary": {
            "critical": critical,
            "warning": warning,
            "context": context,
        },
        "possible_causes": possible_causes or [],
        "events": [],
    }


def build_valid_ollama_answer() -> str:
    """
    Build a valid structured Ollama answer for evaluation tests.
    """
    return """
Direct answer: Based on this snapshot, no obvious system fault is visible right now.

Evidence:
- CPU status is OK.
- Memory status is OK.
- Disk status is OK.
- No critical crash pattern was found.

Limit of this snapshot:
Lighthouse cannot rule out issues outside this telemetry snapshot.

Next step: No immediate action needed from this snapshot.
""".strip()


def run_eval_case(
    monkeypatch,
    telemetry: dict[str, Any],
    event_report: dict[str, Any],
    question: str = "Is anything wrong with my laptop?",
    ollama_enabled: bool = False,
    ollama_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run ask_lighthouse with controlled telemetry, event evidence, and Ollama behavior.
    """
    monkeypatch.setattr(
        "app.services.llm.collect_telemetry",
        lambda: telemetry,
    )
    monkeypatch.setattr(
        "app.services.llm.get_recent_system_events",
        lambda limit=100: event_report,
    )
    monkeypatch.setattr(
        "app.services.llm.is_ollama_enabled",
        lambda: ollama_enabled,
    )

    if ollama_result is not None:
        monkeypatch.setattr(
            "app.services.llm.call_ollama",
            lambda prompt: ollama_result,
        )

    return ask_lighthouse(question)


def test_eval_healthy_laptop_returns_good_fallback(monkeypatch) -> None:
    """
    A healthy laptop snapshot should produce a GOOD fallback assessment.
    """
    result = run_eval_case(
        monkeypatch=monkeypatch,
        telemetry=build_eval_telemetry(
            cpu_usage=10.0,
            memory_usage=40.0,
            disk_usage=20.0,
        ),
        event_report=build_eval_event_report(
            critical=0,
            warning=0,
            context=5,
        ),
    )

    insight = result["insight"]

    assert result["status"] == "ok"
    assert result["provider"] == "lighthouse_insight_engine"
    assert result["used_fallback"] is True
    assert insight["overall_status"] == "GOOD"
    assert insight["metrics"]["cpu_status"] == "OK"
    assert insight["metrics"]["memory_status"] == "OK"
    assert insight["metrics"]["disk_status"] == "OK"
    assert "No immediate action needed" in result["answer"]


def test_eval_high_memory_pressure_is_flagged(monkeypatch) -> None:
    """
    High memory usage should be reflected in the insight metrics.
    """
    result = run_eval_case(
        monkeypatch=monkeypatch,
        telemetry=build_eval_telemetry(
            cpu_usage=12.0,
            memory_usage=87.0,
            disk_usage=22.0,
            top_process_name="MemoryHeavyApp.exe",
            top_process_memory_mb=4096.0,
        ),
        event_report=build_eval_event_report(),
    )

    insight = result["insight"]

    assert result["status"] == "ok"
    assert insight["metrics"]["memory_status"] in {"WARNING", "CRITICAL"}
    assert insight["overall_status"] in {"WARNING", "CRITICAL"}
    assert "memory" in result["answer"].lower()


def test_eval_high_cpu_pressure_is_flagged(monkeypatch) -> None:
    """
    High CPU usage should be reflected in the insight metrics.
    """
    result = run_eval_case(
        monkeypatch=monkeypatch,
        telemetry=build_eval_telemetry(
            cpu_usage=88.0,
            memory_usage=42.0,
            disk_usage=20.0,
        ),
        event_report=build_eval_event_report(),
    )

    insight = result["insight"]

    assert result["status"] == "ok"
    assert insight["metrics"]["cpu_status"] in {"WARNING", "CRITICAL"}
    assert insight["overall_status"] in {"WARNING", "CRITICAL"}
    assert "cpu" in result["answer"].lower()


def test_eval_high_disk_usage_is_flagged(monkeypatch) -> None:
    """
    High disk usage should be reflected in the insight metrics.
    """
    result = run_eval_case(
        monkeypatch=monkeypatch,
        telemetry=build_eval_telemetry(
            cpu_usage=9.0,
            memory_usage=41.0,
            disk_usage=91.0,
        ),
        event_report=build_eval_event_report(),
    )

    insight = result["insight"]

    assert result["status"] == "ok"
    assert insight["metrics"]["disk_status"] in {"WARNING", "CRITICAL"}
    assert insight["overall_status"] in {"WARNING", "CRITICAL"}
    assert "disk" in result["answer"].lower()


def test_eval_critical_event_evidence_is_reflected(monkeypatch) -> None:
    """
    Critical event evidence should be reflected in the insight metrics.
    """
    result = run_eval_case(
        monkeypatch=monkeypatch,
        telemetry=build_eval_telemetry(),
        event_report=build_eval_event_report(
            critical=1,
            warning=0,
            context=0,
            possible_causes=[
                "A critical crash-related system event was found.",
            ],
        ),
    )

    insight = result["insight"]

    assert result["status"] == "ok"
    assert insight["metrics"]["critical_events"] == 1
    assert insight["overall_status"] in {"WARNING", "CRITICAL"}
    assert "critical" in result["answer"].lower()


def test_eval_event_log_unavailable_does_not_crash_answer(monkeypatch) -> None:
    """
    If event-log evidence is unavailable, Lighthouse should still answer safely.
    """
    result = run_eval_case(
        monkeypatch=monkeypatch,
        telemetry=build_eval_telemetry(),
        event_report=build_eval_event_report(
            status="error",
            message="Unable to read Windows event logs.",
        ),
    )

    assert result["status"] == "ok"
    assert result["provider"] == "lighthouse_insight_engine"
    assert result["used_fallback"] is True
    assert result["answer"]
    assert "LIGHTHOUSE ASSISTANT" in result["answer"]


def test_eval_ollama_timeout_falls_back_safely(monkeypatch) -> None:
    """
    If Ollama times out, Lighthouse should fall back and explain why.
    """
    result = run_eval_case(
        monkeypatch=monkeypatch,
        telemetry=build_eval_telemetry(),
        event_report=build_eval_event_report(),
        ollama_enabled=True,
        ollama_result={
            "status": "error",
            "message": "Ollama request timed out.",
            "model": "qwen2.5:3b",
        },
    )

    assert result["status"] == "ok"
    assert result["provider"] == "lighthouse_insight_engine"
    assert result["used_fallback"] is True
    assert result["ollama_attempted"] is True
    assert result["fallback_reason"] == "Ollama request timed out."
    assert "Local Ollama model was attempted but not used." in result["answer"]


def test_eval_valid_ollama_answer_is_accepted(monkeypatch) -> None:
    """
    If Ollama returns a valid Lighthouse answer, Lighthouse should use it.
    """
    result = run_eval_case(
        monkeypatch=monkeypatch,
        telemetry=build_eval_telemetry(),
        event_report=build_eval_event_report(),
        ollama_enabled=True,
        ollama_result={
            "status": "ok",
            "model": "qwen2.5:3b",
            "answer": build_valid_ollama_answer(),
        },
    )

    assert result["status"] == "ok"
    assert result["provider"] == "ollama"
    assert result["model"] == "qwen2.5:3b"
    assert result["used_fallback"] is False
    assert result["validation"]["valid"] is True
    assert "Local Ollama model used: qwen2.5:3b" in result["answer"]


def test_eval_invalid_ollama_answer_is_rejected(monkeypatch) -> None:
    """
    If Ollama returns an answer that violates policy, Lighthouse should reject it.
    """
    invalid_answer = """
Direct answer: Your laptop is definitely fine.

Evidence:
- CPU status is OK.
- Memory status is OK.
- Disk status is OK.

Limit of this snapshot:
Lighthouse cannot rule out issues outside this telemetry snapshot.

Next step: Let me know if you need further assistance.
""".strip()

    result = run_eval_case(
        monkeypatch=monkeypatch,
        telemetry=build_eval_telemetry(),
        event_report=build_eval_event_report(),
        ollama_enabled=True,
        ollama_result={
            "status": "ok",
            "model": "qwen2.5:3b",
            "answer": invalid_answer,
        },
    )

    assert result["status"] == "ok"
    assert result["provider"] == "lighthouse_insight_engine"
    assert result["used_fallback"] is True
    assert result["ollama_attempted"] is True
    assert result["validation"]["valid"] is False
    assert "definitely fine" in result["validation"]["blocked_phrases"]
    assert "let me know" in result["validation"]["blocked_phrases"]
    assert "Local Ollama model was attempted but not used." in result["answer"]