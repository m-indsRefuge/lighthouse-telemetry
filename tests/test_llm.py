import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.llm import build_ollama_prompt

def test_build_ollama_prompt_rejects_generic_computer_advice() -> None:
    """
    The Ollama prompt should discourage unsupported generic advice
    without listing blocked phrases that the model may echo.
    """
    insight = {
        "overall_status": "GOOD",
        "summary": "No obvious fault found.",
        "conclusion": "The system looks healthy based on this snapshot.",
        "metrics": {},
        "findings": [],
        "recommendations": ["No immediate action needed."],
    }

    prompt = build_ollama_prompt(
        user_question="Is my laptop okay?",
        insight=insight,
    )

    assert "Do not behave like a general computer-help chatbot." in prompt
    assert "Do not add generic maintenance advice" in prompt
    assert "Do not recommend generic actions" in prompt
    assert "Do not introduce categories of problems" in prompt
    assert "Do not end with broad support offers" in prompt
    assert "Lighthouse cannot rule out issues outside this telemetry snapshot." in prompt

    poisoned_prompt_phrases = [
        "updating software",
        "restarting",
        "scanning for viruses",
        "contacting a professional",
        "for further assistance",
        "let me know",
        "hidden faults",
        "deeper diagnostics",
        "definitely fine",
        "delete files",
        "edit registry",
        "disable services",
        "change drivers",
    ]

    normalized_prompt = prompt.lower()

    for phrase in poisoned_prompt_phrases:
        assert phrase not in normalized_prompt