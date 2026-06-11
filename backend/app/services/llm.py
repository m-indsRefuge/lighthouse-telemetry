"""
Local LLM service for Lighthouse.

This module powers the Lighthouse "ask" command.

It is designed with a safe fallback:

1. Build a structured Lighthouse insight from read-only telemetry and events.
2. If Ollama is explicitly enabled, try to ask a local Ollama model.
3. If Ollama is disabled or unavailable, return the deterministic Lighthouse answer.

No system changes are made by this module.
"""

import json
import os
import urllib.error
import urllib.request
from typing import Any

from app.collectors.event_logs import get_recent_system_events
from app.main import collect_telemetry
from app.services.insights import build_system_insight


DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_OLLAMA_MODEL = "llama3.2:3b"
OLLAMA_TIMEOUT_SECONDS = 30


def is_ollama_enabled() -> bool:
    """
    Return True if Lighthouse should attempt to use Ollama.

    Ollama is disabled by default.
    Enable it by setting:

        LIGHTHOUSE_USE_OLLAMA=1
    """
    value = os.getenv("LIGHTHOUSE_USE_OLLAMA", "").strip().lower()

    return value in {"1", "true", "yes", "on"}


def get_ollama_model() -> str:
    """
    Return the configured Ollama model name.
    """
    return os.getenv("LIGHTHOUSE_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip()


def build_lighthouse_context(user_question: str) -> dict[str, Any]:
    """
    Build the context needed to answer a Lighthouse question.

    This collects read-only telemetry and event-log evidence, then builds
    a structured insight from those facts.
    """
    telemetry = collect_telemetry()
    event_report = get_recent_system_events(limit=100)

    insight = build_system_insight(
        telemetry=telemetry,
        event_report=event_report,
    )

    return {
        "status": "ok",
        "question": user_question,
        "telemetry": telemetry,
        "event_report": event_report,
        "insight": insight,
    }


def build_ollama_prompt(user_question: str, insight: dict[str, Any]) -> str:
    """
    Build a compact prompt for the local Ollama model.

    The model is only allowed to explain the supplied Lighthouse facts.
    It should not invent causes or suggest unsafe system changes.
    """
    metrics = insight.get("metrics", {})
    findings = insight.get("findings", [])
    recommendations = insight.get("recommendations", [])

    prompt = f"""
You are Lighthouse, a local read-only Windows telemetry assistant.

User question:
{user_question}

Known Lighthouse assessment:
- Overall status: {insight.get("overall_status", "UNKNOWN")}
- Summary: {insight.get("summary", "No summary available.")}
- Conclusion: {insight.get("conclusion", "No conclusion available.")}

Metrics:
- CPU status: {metrics.get("cpu_status", "UNKNOWN")}
- Memory status: {metrics.get("memory_status", "UNKNOWN")}
- Disk status: {metrics.get("disk_status", "UNKNOWN")}
- Critical events: {metrics.get("critical_events", 0)}
- Warning events: {metrics.get("warning_events", 0)}
- Context events: {metrics.get("context_events", 0)}

Findings:
{chr(10).join(f"- {finding}" for finding in findings)}

Recommendations:
{chr(10).join(f"- {recommendation}" for recommendation in recommendations)}

Rules:
- Use only the facts above.
- Do not claim certainty beyond the evidence.
- Do not recommend deleting files, killing processes, editing the registry, or changing system settings.
- Keep the answer short, practical, and calm.
- If the system looks healthy, say that clearly.
""".strip()

    return prompt


def call_ollama(prompt: str) -> dict[str, Any]:
    """
    Call the local Ollama generate API.

    Returns a normalized result dictionary.
    """
    model = get_ollama_model()

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }

    request = urllib.request.Request(
        DEFAULT_OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=OLLAMA_TIMEOUT_SECONDS,
        ) as response:
            raw_body = response.read().decode("utf-8")
            body = json.loads(raw_body)

        answer = body.get("response", "").strip()

        if not answer:
            return {
                "status": "error",
                "message": "Ollama returned an empty response.",
                "model": model,
            }

        return {
            "status": "ok",
            "model": model,
            "answer": answer,
        }

    except urllib.error.URLError as error:
        return {
            "status": "error",
            "message": f"Ollama is unavailable: {error}",
            "model": model,
        }
    except TimeoutError:
        return {
            "status": "error",
            "message": "Ollama request timed out.",
            "model": model,
        }
    except json.JSONDecodeError as error:
        return {
            "status": "error",
            "message": f"Ollama returned invalid JSON: {error}",
            "model": model,
        }
    except Exception as error:
        return {
            "status": "error",
            "message": f"Ollama call failed: {error}",
            "model": model,
        }


def format_lighthouse_answer(
    user_question: str,
    insight: dict[str, Any],
) -> str:
    """
    Format a deterministic Lighthouse assistant-style answer.

    This is used when Ollama is disabled or unavailable.
    """
    overall_status = insight.get("overall_status", "UNKNOWN")
    summary = insight.get("summary", "No summary available.")
    conclusion = insight.get("conclusion", "No conclusion available.")
    findings = insight.get("findings", [])
    recommendations = insight.get("recommendations", [])

    lines: list[str] = []

    lines.append("")
    lines.append("LIGHTHOUSE ASSISTANT")
    lines.append("=" * 52)
    lines.append(f"Question: {user_question}")
    lines.append("")
    lines.append(f"Overall status: {overall_status}")
    lines.append("")
    lines.append("Answer:")
    lines.append(f"- {summary}")
    lines.append(f"- {conclusion}")

    if findings:
        lines.append("")
        lines.append("Evidence:")

        for finding in findings:
            lines.append(f"- {finding}")

    if recommendations:
        lines.append("")
        lines.append("Suggested next step:")

        for recommendation in recommendations:
            lines.append(f"- {recommendation}")

    lines.append("")
    lines.append("AI mode:")
    lines.append("- Local Ollama model was not used.")
    lines.append("- This answer was generated by the Lighthouse insight engine.")
    lines.append("=" * 52)

    return "\n".join(lines)


def format_ollama_answer(
    user_question: str,
    ollama_answer: str,
    model: str,
    insight: dict[str, Any],
) -> str:
    """
    Format an Ollama-generated Lighthouse answer.
    """
    lines: list[str] = []

    lines.append("")
    lines.append("LIGHTHOUSE ASSISTANT")
    lines.append("=" * 52)
    lines.append(f"Question: {user_question}")
    lines.append("")
    lines.append(f"Overall status: {insight.get('overall_status', 'UNKNOWN')}")
    lines.append("")
    lines.append("Answer:")
    lines.append(ollama_answer)
    lines.append("")
    lines.append("AI mode:")
    lines.append(f"- Local Ollama model used: {model}")
    lines.append("- The answer was grounded in Lighthouse telemetry and event evidence.")
    lines.append("=" * 52)

    return "\n".join(lines)


def ask_lighthouse(user_question: str) -> dict[str, Any]:
    """
    Answer a user question using Lighthouse's safe assistant layer.

    Uses Ollama only when LIGHTHOUSE_USE_OLLAMA=1.
    Otherwise, uses the deterministic insight engine answer.
    """
    cleaned_question = user_question.strip()

    if not cleaned_question:
        return {
            "status": "error",
            "message": "No question provided.",
        }

    try:
        context = build_lighthouse_context(cleaned_question)
        insight = context.get("insight", {})

        if is_ollama_enabled():
            prompt = build_ollama_prompt(
                user_question=cleaned_question,
                insight=insight,
            )
            ollama_result = call_ollama(prompt)

            if ollama_result.get("status") == "ok":
                answer = format_ollama_answer(
                    user_question=cleaned_question,
                    ollama_answer=ollama_result.get("answer", ""),
                    model=ollama_result.get("model", get_ollama_model()),
                    insight=insight,
                )

                return {
                    "status": "ok",
                    "provider": "ollama",
                    "model": ollama_result.get("model", get_ollama_model()),
                    "uses_external_ai": False,
                    "used_fallback": False,
                    "question": cleaned_question,
                    "answer": answer,
                    "insight": insight,
                }

        answer = format_lighthouse_answer(
            user_question=cleaned_question,
            insight=insight,
        )

        return {
            "status": "ok",
            "provider": "lighthouse_insight_engine",
            "model": "deterministic_fallback",
            "uses_external_ai": False,
            "used_fallback": True,
            "question": cleaned_question,
            "answer": answer,
            "insight": insight,
        }

    except Exception as error:
        return {
            "status": "error",
            "message": f"Failed to answer Lighthouse question: {error}",
        }