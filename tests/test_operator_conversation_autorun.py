"""
Tests for talkrun autorun safety policy.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.operator_conversation import (
    interpret_operator_input,
    is_safe_to_autorun,
)


def test_slowness_route_is_safe_to_autorun() -> None:
    result = interpret_operator_input("my laptop feels slow")

    allowed, reason = is_safe_to_autorun(result)

    assert allowed is True
    assert "Safe read-only diagnostic route" in reason


def test_chrome_memory_route_is_safe_to_autorun() -> None:
    result = interpret_operator_input("why is chrome eating memory")

    allowed, reason = is_safe_to_autorun(result)

    assert allowed is True
    assert "Safe read-only diagnostic route" in reason


def test_close_chrome_route_is_not_safe_to_autorun() -> None:
    result = interpret_operator_input("close chrome")

    allowed, reason = is_safe_to_autorun(result)

    assert allowed is False
    assert "Only read-only diagnostic routes" in reason


def test_delete_files_route_is_not_safe_to_autorun() -> None:
    result = interpret_operator_input("delete files to make space")

    allowed, reason = is_safe_to_autorun(result)

    assert allowed is False
    assert "Only read-only diagnostic routes" in reason


def test_unknown_route_is_not_safe_to_autorun() -> None:
    result = interpret_operator_input("banana window purple")

    allowed, reason = is_safe_to_autorun(result)

    assert allowed is False
    assert "not ok" in reason
