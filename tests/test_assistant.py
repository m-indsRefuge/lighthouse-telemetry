"""
Tests for the Lighthouse assistant intent router.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.assistant import classify_user_intent, normalize_text


def test_normalize_text_removes_basic_punctuation() -> None:
    result = normalize_text("Why is my laptop slow?!")

    assert result == "why is my laptop slow"


def test_classifies_health_request() -> None:
    result = classify_user_intent("is my laptop healthy?")

    assert result.status == "ok"
    assert result.intent == "health"
    assert result.canonical_command == "health"
    assert result.confidence > 0


def test_classifies_diagnose_request() -> None:
    result = classify_user_intent("why is my laptop slow?")

    assert result.status == "ok"
    assert result.intent == "diagnose"
    assert result.canonical_command == "diagnose"
    assert result.confidence > 0


def test_classifies_crash_request() -> None:
    result = classify_user_intent("did my laptop crash recently?")

    assert result.status == "ok"
    assert result.intent == "events"
    assert result.canonical_command == "events"
    assert result.confidence > 0


def test_classifies_save_request() -> None:
    result = classify_user_intent("save this report")

    assert result.status == "ok"
    assert result.intent == "save"
    assert result.canonical_command == "save"
    assert result.confidence > 0


def test_classifies_history_request() -> None:
    result = classify_user_intent("show my saved snapshots")

    assert result.status == "ok"
    assert result.intent == "history"
    assert result.canonical_command == "history"
    assert result.confidence > 0


def test_classifies_last_snapshot_request() -> None:
    result = classify_user_intent("show me the last report")

    assert result.status == "ok"
    assert result.intent == "last"
    assert result.canonical_command == "last"
    assert result.confidence > 0


def test_classifies_quit_request() -> None:
    result = classify_user_intent("close lighthouse")

    assert result.status == "ok"
    assert result.intent == "quit"
    assert result.canonical_command == "quit"
    assert result.confidence > 0


def test_unknown_request_returns_unknown() -> None:
    result = classify_user_intent("make me a sandwich")

    assert result.status == "unknown"
    assert result.intent is None
    assert result.canonical_command is None
    assert result.confidence == 0.0