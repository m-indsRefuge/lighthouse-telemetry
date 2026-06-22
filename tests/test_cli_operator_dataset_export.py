"""
Tests for Operator dataset export CLI wiring.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import cli


def test_run_canonical_command_handles_dataset_operator(monkeypatch, capsys) -> None:
    calls = []

    def fake_export_operator_route_dataset():
        calls.append("called")
        return {
            "status": "ok",
            "message": "Operator route dataset exported.",
            "data": {
                "output_path": "memory/datasets/operator_route_dataset.jsonl",
                "total_examples": 3,
                "included_examples": 2,
                "review_needed_examples": 1,
                "unlabeled_examples": 0,
                "category_counts": {
                    "positive_route_example": 2,
                    "correction_needed": 1,
                },
            },
            "errors": [],
            "warnings": [],
        }

    monkeypatch.setattr(
        cli,
        "export_operator_route_dataset",
        fake_export_operator_route_dataset,
    )

    result = cli.run_canonical_command("dataset operator")

    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == ["called"]
    assert "LIGHTHOUSE OPERATOR DATASET EXPORT" in output
    assert "Status: ok" in output
    assert "Examples exported: 3" in output
    assert "Included examples: 2" in output
    assert "Review-needed examples: 1" in output
    assert "Output: memory/datasets/operator_route_dataset.jsonl" in output


def test_run_canonical_command_handles_dataset_operator_alias(monkeypatch, capsys) -> None:
    def fake_export_operator_route_dataset():
        return {
            "status": "ok",
            "message": "Operator route dataset exported.",
            "data": {
                "output_path": "memory/datasets/operator_route_dataset.jsonl",
                "total_examples": 1,
                "included_examples": 1,
                "review_needed_examples": 0,
                "unlabeled_examples": 0,
                "category_counts": {
                    "safe_refusal_example": 1,
                },
            },
            "errors": [],
            "warnings": [],
        }

    monkeypatch.setattr(
        cli,
        "export_operator_route_dataset",
        fake_export_operator_route_dataset,
    )

    result = cli.run_canonical_command("export operator dataset")

    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE OPERATOR DATASET EXPORT" in output
    assert "safe_refusal_example: 1" in output


def test_run_canonical_command_handles_dataset_usage(capsys) -> None:
    result = cli.run_canonical_command("dataset")

    output = capsys.readouterr().out

    assert result == "handled"
    assert "Usage: dataset operator" in output


def test_help_mentions_dataset_operator(capsys) -> None:
    cli.print_help()

    output = capsys.readouterr().out

    assert "dataset operator" in output
    assert "Export Operator route dataset" in output
