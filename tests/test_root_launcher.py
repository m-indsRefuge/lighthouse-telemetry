"""
Tests for the root Lighthouse launcher.
"""

from pathlib import Path
import importlib.util
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_PATH = PROJECT_ROOT / "lighthouse.py"
BACKEND_PATH = PROJECT_ROOT / "backend"


def load_launcher_module():
    """
    Load lighthouse.py under an isolated module name.

    This proves importing the launcher does not start the interactive CLI.
    """
    spec = importlib.util.spec_from_file_location(
        "lighthouse_launcher_under_test",
        LAUNCHER_PATH,
    )

    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def test_launcher_file_exists() -> None:
    """
    The repo root should expose a Lighthouse launcher.
    """
    assert LAUNCHER_PATH.exists()


def test_launcher_import_does_not_start_cli() -> None:
    """
    Importing the launcher should not call command_loop.
    """
    module = load_launcher_module()

    assert hasattr(module, "main")
    assert hasattr(module, "ensure_backend_on_path")


def test_ensure_backend_on_path_adds_backend_path(monkeypatch) -> None:
    """
    The launcher should make backend importable from repo root.
    """
    module = load_launcher_module()

    fake_path = [
        path
        for path in sys.path
        if path != str(BACKEND_PATH)
    ]

    monkeypatch.setattr(sys, "path", fake_path)

    module.ensure_backend_on_path()

    assert sys.path[0] == str(BACKEND_PATH)


def test_launcher_can_import_cli_after_path_setup() -> None:
    """
    After path setup, app.cli.command_loop should be importable.
    """
    module = load_launcher_module()

    module.ensure_backend_on_path()

    from app.cli import command_loop

    assert callable(command_loop)
