"""
Tests for Lighthouse CLI LLM preview dataset export wiring.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import cli


def test_print_llm_preview_dataset_export_report(monkeypatch, capsys) -> None:
    def fake_export() -> dict:
        return {
            "status": "ok",
            "message": "LLM preview dataset exported.",
            "data": {
                "output_path": "memory/datasets/llm_preview_route_dataset.jsonl",
                "total_examples": 1,
                "included_examples": 1,
                "review_needed_examples": 0,
                "unlabeled_examples": 0,
                "category_counts": {"valid_route_preview": 1},
            },
            "errors": [],
            "warnings": [],
        }

    monkeypatch.setattr(cli, "export_llm_preview_dataset", fake_export)

    cli.print_llm_preview_dataset_export_report()

    output = capsys.readouterr().out

    assert "LIGHTHOUSE LLM PREVIEW DATASET EXPORT" in output
    assert "Status: ok" in output
    assert "Examples exported: 1" in output
    assert "valid_route_preview: 1" in output


def test_run_canonical_command_handles_dataset_llm_preview(monkeypatch, capsys) -> None:
    calls: list[str] = []

    def fake_report() -> None:
        calls.append("called")
        print("LLM PREVIEW DATASET EXPORT CALLED")

    monkeypatch.setattr(cli, "print_llm_preview_dataset_export_report", fake_report)

    result = cli.run_canonical_command("dataset llm preview")

    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == ["called"]
    assert "LLM PREVIEW DATASET EXPORT CALLED" in output


def test_run_canonical_command_handles_llm_preview_dataset_alias(monkeypatch, capsys) -> None:
    calls: list[str] = []

    def fake_report() -> None:
        calls.append("called")
        print("LLM PREVIEW DATASET EXPORT CALLED")

    monkeypatch.setattr(cli, "print_llm_preview_dataset_export_report", fake_report)

    result = cli.run_canonical_command("llm preview dataset")

    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == ["called"]
    assert "LLM PREVIEW DATASET EXPORT CALLED" in output
