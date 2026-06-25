"""
CLI tests for conversational turn dataset export.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import cli


def test_dataset_turns_command_exports_conversational_turn_dataset(
    monkeypatch,
    capsys,
) -> None:
    calls = {}

    def fake_export():
        calls["called"] = True
        return {
            "status": "ok",
            "message": "Conversational turn dataset exported.",
            "data": {
                "output_path": "memory/datasets/conversational_turn_dataset.jsonl",
                "total_examples": 2,
                "included_examples": 2,
                "review_needed_examples": 0,
                "unlabeled_examples": 0,
                "category_counts": {"deterministic_fallback_turn": 2},
            },
            "errors": [],
            "warnings": [],
        }

    def fake_format(result):
        return "LIGHTHOUSE CONVERSATIONAL TURN DATASET EXPORT"

    monkeypatch.setattr(cli, "export_conversational_turn_dataset", fake_export)
    monkeypatch.setattr(
        cli,
        "format_conversational_turn_dataset_export_report",
        fake_format,
    )

    result = cli.run_canonical_command("dataset turns")
    output = capsys.readouterr().out

    assert result == "handled"
    assert calls["called"] is True
    assert "LIGHTHOUSE CONVERSATIONAL TURN DATASET EXPORT" in output


def test_conversation_turn_dataset_alias_exports_dataset(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "export_conversational_turn_dataset",
        lambda: {
            "status": "ok",
            "message": "Conversational turn dataset exported.",
            "data": {},
            "errors": [],
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        cli,
        "format_conversational_turn_dataset_export_report",
        lambda result: "LIGHTHOUSE CONVERSATIONAL TURN DATASET EXPORT",
    )

    result = cli.run_canonical_command("conversation turn dataset")
    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE CONVERSATIONAL TURN DATASET EXPORT" in output
