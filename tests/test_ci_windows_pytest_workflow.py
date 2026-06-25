"""
Tests for the minimal Windows Pytest GitHub Actions workflow.
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "windows-pytest.yml"


def read_workflow() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_windows_pytest_workflow_exists() -> None:
    assert WORKFLOW_PATH.exists()


def test_windows_pytest_workflow_uses_windows_runner() -> None:
    workflow = read_workflow()

    assert "runs-on: windows-latest" in workflow


def test_windows_pytest_workflow_uses_python_312() -> None:
    workflow = read_workflow()

    assert "actions/setup-python@v5" in workflow
    assert 'python-version: "3.12"' in workflow


def test_windows_pytest_workflow_installs_requirements() -> None:
    workflow = read_workflow()

    assert "python -m pip install --upgrade pip" in workflow
    assert "python -m pip install -r requirements.txt" in workflow


def test_windows_pytest_workflow_runs_pytest_suite() -> None:
    workflow = read_workflow()

    assert "python -m pytest tests -ra" in workflow


def test_windows_pytest_workflow_keeps_ollama_disabled() -> None:
    workflow = read_workflow()

    assert 'LIGHTHOUSE_USE_OLLAMA: "0"' in workflow


def test_windows_pytest_workflow_has_manual_and_pr_triggers() -> None:
    workflow = read_workflow()

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" in workflow
    assert "push:" in workflow
