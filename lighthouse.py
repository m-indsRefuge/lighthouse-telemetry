"""
Root launcher for Lighthouse.

This allows the Operator to start Lighthouse from the repository root with:

    python lighthouse.py

The actual CLI remains in backend/app/cli.py.
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_PATH = PROJECT_ROOT / "backend"


def ensure_backend_on_path() -> None:
    """
    Ensure the backend package directory is importable from repo root.
    """
    backend_path = str(BACKEND_PATH)

    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)


def main() -> None:
    """
    Start the Lighthouse CLI.
    """
    ensure_backend_on_path()

    from app.cli import command_loop

    command_loop()


if __name__ == "__main__":
    main()
