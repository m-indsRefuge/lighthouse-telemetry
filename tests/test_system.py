"""
Tests for the Lighthouse system collector.
"""

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.collectors.system import get_system_info


def test_get_system_info_returns_dictionary() -> None:
    """
    The system collector should return a dictionary.
    """
    result: dict[str, Any] = get_system_info()

    assert isinstance(result, dict)
    assert result


def test_get_system_info_includes_status() -> None:
    """
    The system collector should include a status field.
    """
    result = get_system_info()

    assert "status" in result


def test_get_system_info_does_not_return_error_status() -> None:
    """
    The system collector should not fail during normal collection.
    """
    result = get_system_info()

    assert result.get("status") != "error"
