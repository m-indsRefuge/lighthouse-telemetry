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


def test_dataset_turns_review_command_prints_dataset_review(monkeypatch, capsys) -> None:
    calls = {}

    def fake_review_report(limit=10):
        calls["limit"] = limit
        return "LIGHTHOUSE CONVERSATIONAL TURN DATASET REVIEW\nShown: 10"

    monkeypatch.setattr(
        cli,
        "format_conversational_turn_dataset_review_report",
        fake_review_report,
    )

    result = cli.run_canonical_command("dataset turns review")
    output = capsys.readouterr().out

    assert result == "handled"
    assert calls["limit"] == 10
    assert "LIGHTHOUSE CONVERSATIONAL TURN DATASET REVIEW" in output


def test_dataset_turns_review_limit_command_prints_dataset_review(
    monkeypatch,
    capsys,
) -> None:
    calls = {}

    def fake_review_report(limit=10):
        calls["limit"] = limit
        return "LIGHTHOUSE CONVERSATIONAL TURN DATASET REVIEW\nShown: 2"

    monkeypatch.setattr(
        cli,
        "format_conversational_turn_dataset_review_report",
        fake_review_report,
    )

    result = cli.run_canonical_command("dataset turns review 2")
    output = capsys.readouterr().out

    assert result == "handled"
    assert calls["limit"] == 2
    assert "Shown: 2" in output


def test_dataset_turns_rows_alias_prints_dataset_review(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "format_conversational_turn_dataset_review_report",
        lambda limit=10: "LIGHTHOUSE CONVERSATIONAL TURN DATASET REVIEW",
    )

    result = cli.run_canonical_command("dataset turns rows")
    output = capsys.readouterr().out

    assert result == "handled"
    assert "LIGHTHOUSE CONVERSATIONAL TURN DATASET REVIEW" in output


def test_dataset_turns_review_included_filter_command(monkeypatch, capsys) -> None:
    calls = {}

    def fake_review_report(limit=10, filter_mode="all", category=None):
        calls["limit"] = limit
        calls["filter_mode"] = filter_mode
        calls["category"] = category
        return "LIGHTHOUSE CONVERSATIONAL TURN DATASET REVIEW\nFilter: included"

    monkeypatch.setattr(
        cli,
        "format_conversational_turn_dataset_review_report",
        fake_review_report,
    )

    result = cli.run_canonical_command("dataset turns review included")
    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == {
        "limit": 10,
        "filter_mode": "included",
        "category": None,
    }
    assert "Filter: included" in output


def test_dataset_turns_review_excluded_filter_command(monkeypatch, capsys) -> None:
    calls = {}

    def fake_review_report(limit=10, filter_mode="all", category=None):
        calls["filter_mode"] = filter_mode
        return "LIGHTHOUSE CONVERSATIONAL TURN DATASET REVIEW\nFilter: excluded"

    monkeypatch.setattr(
        cli,
        "format_conversational_turn_dataset_review_report",
        fake_review_report,
    )

    result = cli.run_canonical_command("dataset turns review excluded")
    output = capsys.readouterr().out

    assert result == "handled"
    assert calls["filter_mode"] == "excluded"
    assert "Filter: excluded" in output


def test_dataset_turns_review_feedback_filter_command(monkeypatch, capsys) -> None:
    calls = {}

    def fake_review_report(limit=10, filter_mode="all", category=None):
        calls["filter_mode"] = filter_mode
        return "LIGHTHOUSE CONVERSATIONAL TURN DATASET REVIEW\nFilter: feedback"

    monkeypatch.setattr(
        cli,
        "format_conversational_turn_dataset_review_report",
        fake_review_report,
    )

    result = cli.run_canonical_command("dataset turns review feedback")
    output = capsys.readouterr().out

    assert result == "handled"
    assert calls["filter_mode"] == "feedback"
    assert "Filter: feedback" in output


def test_dataset_turns_review_corrections_filter_command(monkeypatch, capsys) -> None:
    calls = {}

    def fake_review_report(limit=10, filter_mode="all", category=None):
        calls["filter_mode"] = filter_mode
        return "LIGHTHOUSE CONVERSATIONAL TURN DATASET REVIEW\nFilter: corrections"

    monkeypatch.setattr(
        cli,
        "format_conversational_turn_dataset_review_report",
        fake_review_report,
    )

    result = cli.run_canonical_command("dataset turns review corrections")
    output = capsys.readouterr().out

    assert result == "handled"
    assert calls["filter_mode"] == "corrections"
    assert "Filter: corrections" in output


def test_dataset_turns_review_needed_filter_command(monkeypatch, capsys) -> None:
    calls = {}

    def fake_review_report(limit=10, filter_mode="all", category=None):
        calls["filter_mode"] = filter_mode
        return "LIGHTHOUSE CONVERSATIONAL TURN DATASET REVIEW\nFilter: review_needed"

    monkeypatch.setattr(
        cli,
        "format_conversational_turn_dataset_review_report",
        fake_review_report,
    )

    result = cli.run_canonical_command("dataset turns review review-needed")
    output = capsys.readouterr().out

    assert result == "handled"
    assert calls["filter_mode"] == "review_needed"
    assert "Filter: review_needed" in output


def test_dataset_turns_review_category_filter_command(monkeypatch, capsys) -> None:
    calls = {}

    def fake_review_report(limit=10, filter_mode="all", category=None):
        calls["filter_mode"] = filter_mode
        calls["category"] = category
        return (
            "LIGHTHOUSE CONVERSATIONAL TURN DATASET REVIEW\n"
            "Filter: category\n"
            "Category: needs_clarification_turn"
        )

    monkeypatch.setattr(
        cli,
        "format_conversational_turn_dataset_review_report",
        fake_review_report,
    )

    result = cli.run_canonical_command(
        "dataset turns review category needs_clarification_turn"
    )
    output = capsys.readouterr().out

    assert result == "handled"
    assert calls == {
        "filter_mode": "category",
        "category": "needs_clarification_turn",
    }
    assert "Filter: category" in output
    assert "Category: needs_clarification_turn" in output


def test_dataset_turns_review_category_usage_for_missing_category(capsys) -> None:
    result = cli.run_canonical_command("dataset turns review category")
    output = capsys.readouterr().out

    assert result == "handled"
    assert "Usage: dataset turns review category <category>" in output
