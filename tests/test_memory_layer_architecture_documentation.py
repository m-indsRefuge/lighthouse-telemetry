"""
Documentation regression tests for Lighthouse memory layer architecture.
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEMORY_DOC = PROJECT_ROOT / "docs" / "memory_layer_architecture.md"
README = PROJECT_ROOT / "README.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_memory_layer_doc_defines_journals_and_datasets() -> None:
    content = read(MEMORY_DOC)

    assert "Journals are source-of-truth event records." in content
    assert "Datasets are regenerated learning/evaluation artifacts." in content
    assert "journal file = growing append-only source log" in content
    assert "dataset file = regenerated export snapshot" in content


def test_memory_layer_doc_preserves_authority_boundaries() -> None:
    content = read(MEMORY_DOC)

    assert "Semantic memory is not part of the V1 authority layer." in content
    assert "Memory cannot override the route registry." in content
    assert "Memory cannot override the tool registry." in content
    assert "Memory cannot override the autorun gate." in content
    assert "Memory cannot override Operator confirmation." in content


def test_readme_links_memory_layer_architecture_doc() -> None:
    content = read(README)

    assert "docs/memory_layer_architecture.md" in content
