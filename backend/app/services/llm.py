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
import socket
import urllib.error
import urllib.request
from typing import Any

from app.collectors.event_logs import get_recent_system_events
from app.main import collect_telemetry
from app.services.insights import build_system_insight


DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
DEFAULT_OLLAMA_MODEL = "qwen2.5:3b"
OLLAMA_TIMEOUT_SECONDS = 30
OLLAMA_STATUS_TIMEOUT_SECONDS = 5


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
    model = os.getenv("LIGHTHOUSE_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip()

    if not model:
        return DEFAULT_OLLAMA_MODEL

    return model


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
    Build a strict prompt for the local Ollama model.

    The model is only allowed to explain the supplied Lighthouse facts.
    It should not invent causes, offer generic computer advice, or suggest
    unsafe system changes.
    """
    metrics = insight.get("metrics", {})
    findings = insight.get("findings", [])
    recommendations = insight.get("recommendations", [])

    findings_text = (
        "\n".join(f"- {finding}" for finding in findings)
        if findings
        else "- No specific findings were provided."
    )

    recommendations_text = (
        "\n".join(f"- {recommendation}" for recommendation in recommendations)
        if recommendations
        else "- No specific recommendation was provided."
    )

    prompt = f"""
You are Lighthouse, a local read-only Windows telemetry assistant.

Your role:
- Explain only what Lighthouse can see from the supplied telemetry and event evidence.
- Stay calm, practical, and evidence-based.
- Do not behave like a general computer-help chatbot.
- Do not add generic maintenance advice unless it is directly supported by the evidence.
- Do not imply that Lighthouse can repair, change, or control the computer.
- Do not offer broad follow-up support or end with open-ended assistant phrases.

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
{findings_text}

Recommendations:
{recommendations_text}

Lighthouse Answer Policy:
- Base the answer only on the evidence above.
- Say "based on this snapshot" when giving a conclusion.
- If the evidence looks healthy, say that no obvious fault is visible right now.
- If evidence is limited, say what Lighthouse cannot determine.
- Do not claim that the laptop is definitely fine.
- Do not invent causes that are not present in the evidence.
- Do not recommend deleting files, killing processes, editing the registry, disabling services, changing drivers, or changing Windows settings.
- Do not recommend generic actions like updating software, restarting, cleaning the disk, scanning for viruses, closing apps, or contacting a professional unless the evidence directly supports that recommendation.
- Do not say "please contact a professional", "let me know", "for further assistance", or similar broad support phrases.
- If the overall status is GOOD and the recommendation says no immediate action is needed, the next step should be: "No immediate action needed from this snapshot."
- Keep the response short.

Required answer structure:
1. Direct answer
2. Evidence
3. Limit of this snapshot
4. Next step
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
    except (TimeoutError, socket.timeout):
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


def get_ollama_status() -> dict[str, Any]:
    """
    Check Lighthouse's Ollama configuration and local Ollama availability.

    This does not generate text.
    It only checks whether the local Ollama server can be reached and whether
    the configured model appears in the installed model list.
    """
    configured_model = get_ollama_model()
    enabled = is_ollama_enabled()

    request = urllib.request.Request(
        DEFAULT_OLLAMA_TAGS_URL,
        method="GET",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=OLLAMA_STATUS_TIMEOUT_SECONDS,
        ) as response:
            raw_body = response.read().decode("utf-8")
            body = json.loads(raw_body)

        models = body.get("models", [])
        installed_models: list[str] = []

        for model in models:
            name = model.get("name") or model.get("model")

            if name:
                installed_models.append(name)

        configured_model_installed = configured_model in installed_models

        return {
            "status": "ok",
            "ollama_enabled": enabled,
            "server_available": True,
            "configured_model": configured_model,
            "configured_model_installed": configured_model_installed,
            "installed_models": installed_models,
            "generate_url": DEFAULT_OLLAMA_URL,
            "tags_url": DEFAULT_OLLAMA_TAGS_URL,
        }

    except urllib.error.URLError as error:
        return {
            "status": "unavailable",
            "ollama_enabled": enabled,
            "server_available": False,
            "configured_model": configured_model,
            "configured_model_installed": False,
            "installed_models": [],
            "message": f"Ollama is unavailable: {error}",
            "generate_url": DEFAULT_OLLAMA_URL,
            "tags_url": DEFAULT_OLLAMA_TAGS_URL,
        }
    except (TimeoutError, socket.timeout):
        return {
            "status": "unavailable",
            "ollama_enabled": enabled,
            "server_available": False,
            "configured_model": configured_model,
            "configured_model_installed": False,
            "installed_models": [],
            "message": "Ollama status check timed out.",
            "generate_url": DEFAULT_OLLAMA_URL,
            "tags_url": DEFAULT_OLLAMA_TAGS_URL,
        }
    except json.JSONDecodeError as error:
        return {
            "status": "error",
            "ollama_enabled": enabled,
            "server_available": True,
            "configured_model": configured_model,
            "configured_model_installed": False,
            "installed_models": [],
            "message": f"Ollama returned invalid JSON: {error}",
            "generate_url": DEFAULT_OLLAMA_URL,
            "tags_url": DEFAULT_OLLAMA_TAGS_URL,
        }
    except Exception as error:
        return {
            "status": "error",
            "ollama_enabled": enabled,
            "server_available": False,
            "configured_model": configured_model,
            "configured_model_installed": False,
            "installed_models": [],
            "message": f"Ollama status check failed: {error}",
            "generate_url": DEFAULT_OLLAMA_URL,
            "tags_url": DEFAULT_OLLAMA_TAGS_URL,
        }


def run_ollama_model_test() -> dict[str, Any]:
    """
    Send a tiny safe test prompt to the configured Ollama model.

    This confirms whether the local model can actually generate a response.
    """
    configured_model = get_ollama_model()

    if not is_ollama_enabled():
        return {
            "status": "disabled",
            "model": configured_model,
            "message": "Ollama is not enabled. Set LIGHTHOUSE_USE_OLLAMA=1 first.",
        }

    status_result = get_ollama_status()

    if not status_result.get("server_available", False):
        return {
            "status": "error",
            "model": configured_model,
            "message": status_result.get(
                "message",
                "Ollama server is not available.",
            ),
        }

    if not status_result.get("configured_model_installed", False):
        return {
            "status": "error",
            "model": configured_model,
            "message": (
                "Ollama is reachable, but the configured model is not installed."
            ),
        }

    prompt = (
        "You are Lighthouse, a local telemetry assistant. "
        "Reply with exactly this sentence: Lighthouse model test successful."
    )

    result = call_ollama(prompt)

    if result.get("status") != "ok":
        return {
            "status": "error",
            "model": configured_model,
            "message": result.get("message", "Ollama model test failed."),
        }

    return {
        "status": "ok",
        "model": result.get("model", configured_model),
        "response": result.get("answer", ""),
    }


def format_lighthouse_answer(
    user_question: str,
    insight: dict[str, Any],
    ollama_attempted: bool = False,
    fallback_reason: str | None = None,
) -> str:
    """
    Format a deterministic Lighthouse assistant-style answer.

    This is used when Ollama is disabled, unavailable, or fails.
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

    if ollama_attempted:
        lines.append("- Local Ollama model was attempted but not used.")

        if fallback_reason:
            lines.append(f"- Fallback reason: {fallback_reason}")
        else:
            lines.append("- Fallback reason: Unknown Ollama error.")
    else:
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
                    "ollama_attempted": True,
                    "fallback_reason": None,
                    "question": cleaned_question,
                    "answer": answer,
                    "insight": insight,
                }

            fallback_reason = ollama_result.get(
                "message",
                "Ollama returned an error.",
            )
            answer = format_lighthouse_answer(
                user_question=cleaned_question,
                insight=insight,
                ollama_attempted=True,
                fallback_reason=fallback_reason,
            )

            return {
                "status": "ok",
                "provider": "lighthouse_insight_engine",
                "model": "deterministic_fallback",
                "uses_external_ai": False,
                "used_fallback": True,
                "ollama_attempted": True,
                "fallback_reason": fallback_reason,
                "ollama_model": ollama_result.get("model", get_ollama_model()),
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
            "ollama_attempted": False,
            "fallback_reason": None,
            "question": cleaned_question,
            "answer": answer,
            "insight": insight,
        }

    except Exception as error:
        return {
            "status": "error",
            "message": f"Failed to answer Lighthouse question: {error}",
        }