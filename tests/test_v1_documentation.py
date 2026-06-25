"""
Documentation regression tests for README, safety model, and command reference.
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
README = PROJECT_ROOT / "README.md"
SAFETY_MODEL = PROJECT_ROOT / "docs" / "safety_model.md"
COMMANDS = PROJECT_ROOT / "docs" / "commands.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_readme_documents_v1_safety_spine() -> None:
    content = read(README)

    assert "Observe -> Mediate -> Act" in content
    assert "The model is not authority." in content
    assert "The Operator remains in command." in content


def test_readme_documents_startup_and_tests() -> None:
    content = read(README)

    assert "python lighthouse.py" in content
    assert "python -m pytest tests" in content
    assert ".github/workflows/windows-pytest.yml" in content


def test_readme_links_supporting_docs() -> None:
    content = read(README)

    assert "docs/safety_model.md" in content
    assert "docs/commands.md" in content
    assert "docs/v1_contract_shapes.md" in content
    assert "docs/memory_layer_architecture.md" in content


def test_safety_model_documents_authority_boundaries() -> None:
    content = read(SAFETY_MODEL)

    assert "Model output is never execution authority." in content
    assert "Route Registry" in content
    assert "Tool Registry" in content
    assert "Autorun Gate" in content
    assert "Memory" in content


def test_safety_model_documents_llm_rejected_authority_fields() -> None:
    content = read(SAFETY_MODEL)

    for field in [
        "recommended_command",
        "shell_command",
        "autorun_allowed",
        "permission_granted",
        "delete_file",
        "registry_change",
    ]:
        assert field in content


def test_commands_document_key_operator_and_llm_paths() -> None:
    content = read(COMMANDS)

    for command in [
        "talk <text>",
        "talkrun <text>",
        "llm preview <text>",
        "llm talk <text>",
        "dataset operator",
        "dataset llm preview",
    ]:
        assert command in content


def test_commands_document_windows_evidence_paths() -> None:
    content = read(COMMANDS)

    assert "windows" in content
    assert "cim" in content
    assert "events" in content
