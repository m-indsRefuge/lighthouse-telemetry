"""
Tests for Lighthouse memory summarizer.

The memory summarizer turns retrieved memory into compact context that can later
be passed to the engine/model reasoning layer.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.memory_summarizer import (
    MEMORY_SUMMARY_STATUS_EMPTY,
    MEMORY_SUMMARY_STATUS_OK,
    compact_text,
    flatten_dict,
    format_key_value_section,
    get_entry_identifier,
    get_entry_summary,
    summarize_memory_context,
    summarize_memory_for_request,
)
from app.services.memory_retriever import (
    MemoryRetrievalQuery,
    retrieve_memory_for_request,
)
from app.services.memory_store import (
    append_case_memory,
    write_baselines,
    write_knowledge_index,
    write_operator_preferences,
)


def seed_memory(memory_dir: Path) -> None:
    """
    Seed test memory data.
    """
    write_baselines(
        {
            "memory": {
                "normal_idle_percent_min": 30,
                "normal_idle_percent_max": 40,
            },
            "cpu": {
                "normal_idle_percent_max": 10,
            },
        },
        memory_dir=memory_dir,
    )

    write_operator_preferences(
        {
            "communication": {
                "style": "plain_english",
            },
            "safety": {
                "diagnostics_before_action": True,
            },
        },
        memory_dir=memory_dir,
    )

    append_case_memory(
        {
            "case_id": "case_chrome_memory",
            "summary": "Chrome caused high memory pressure and laptop slowdown.",
            "evidence": {
                "process": "chrome.exe",
                "memory_mb": 4200,
            },
            "resolution": "Operator closed unused Chrome tabs.",
            "tags": ["chrome", "memory", "slowdown"],
        },
        memory_dir=memory_dir,
    )

    write_knowledge_index(
        {
            "schema_version": 1,
            "entries": [
                {
                    "id": "windows_memory_pressure",
                    "title": "Windows memory pressure troubleshooting",
                    "summary": "High memory usage can make Windows feel slow.",
                    "tags": ["windows", "memory", "slowdown"],
                }
            ],
        },
        memory_dir=memory_dir,
    )


def test_compact_text_handles_none_bool_and_long_values() -> None:
    """
    Compact text should normalize common values safely.
    """
    assert compact_text(None) == "none"
    assert compact_text(True) == "yes"
    assert compact_text(False) == "no"
    assert compact_text("hello\nworld") == "hello world"

    long_text = "x" * 200
    compacted = compact_text(long_text, max_length=20)

    assert len(compacted) == 20
    assert compacted.endswith("...")


def test_flatten_dict_returns_dotted_keys() -> None:
    """
    Nested dictionaries should flatten into dotted key/value pairs.
    """
    flattened = flatten_dict(
        {
            "memory": {
                "normal": {
                    "min": 30,
                    "max": 40,
                }
            },
            "cpu": 10,
        }
    )

    assert ("memory.normal.min", 30) in flattened
    assert ("memory.normal.max", 40) in flattened
    assert ("cpu", 10) in flattened


def test_format_key_value_section_handles_empty_data() -> None:
    """
    Empty sections should be explicit.
    """
    lines = format_key_value_section(
        title="System baselines",
        data={},
        max_items=5,
    )

    assert lines == [
        "System baselines:",
        "- none",
    ]


def test_get_entry_identifier_prefers_known_ids() -> None:
    """
    Entry identifiers should prefer case_id, memory_id, then id.
    """
    assert get_entry_identifier({"case_id": "case_1", "id": "entry_1"}) == "case_1"
    assert get_entry_identifier({"memory_id": "mem_1", "id": "entry_1"}) == "mem_1"
    assert get_entry_identifier({"id": "entry_1"}) == "entry_1"
    assert get_entry_identifier({}) == "unknown"


def test_get_entry_summary_prefers_summary_then_title() -> None:
    """
    Entry summary should prefer summary over title.
    """
    assert get_entry_summary(
        {
            "summary": "Summary text",
            "title": "Title text",
        }
    ) == "Summary text"

    assert get_entry_summary(
        {
            "title": "Title text",
        }
    ) == "Title text"

    assert get_entry_summary({}) == "No summary available."


def test_summarize_memory_context_builds_context_text(tmp_path) -> None:
    """
    Retrieved memory should become a compact context block.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    retrieval_result = retrieve_memory_for_request(
        "why is chrome using memory",
        memory_dir=memory_dir,
    )

    summary = summarize_memory_context(retrieval_result)

    assert summary.status == MEMORY_SUMMARY_STATUS_OK
    assert summary.user_request == "why is chrome using memory"
    assert "chrome" in summary.keywords
    assert "memory" in summary.keywords
    assert summary.baseline_count > 0
    assert summary.preference_count > 0
    assert summary.case_count == 1
    assert summary.knowledge_count == 1

    assert "LIGHTHOUSE MEMORY CONTEXT" in summary.context_text
    assert "System baselines:" in summary.context_text
    assert "Operator preferences:" in summary.context_text
    assert "Relevant case memories:" in summary.context_text
    assert "case_chrome_memory" in summary.context_text
    assert "Relevant knowledge entries:" in summary.context_text
    assert "windows_memory_pressure" in summary.context_text


def test_summarize_memory_for_request_retrieves_and_summarizes(tmp_path) -> None:
    """
    Convenience wrapper should retrieve then summarize memory.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    summary = summarize_memory_for_request(
        "chrome memory slowdown",
        memory_dir=memory_dir,
    )

    assert summary.status == MEMORY_SUMMARY_STATUS_OK
    assert summary.case_count == 1
    assert summary.knowledge_count == 1
    assert "Chrome caused high memory pressure" in summary.context_text


def test_summarize_empty_memory_context_returns_empty_status(tmp_path) -> None:
    """
    Empty memory should produce a stable empty summary.
    """
    memory_dir = tmp_path / "memory"

    retrieval_result = retrieve_memory_for_request(
        "unknown topic",
        memory_dir=memory_dir,
    )

    summary = summarize_memory_context(retrieval_result)

    assert summary.status == MEMORY_SUMMARY_STATUS_EMPTY
    assert summary.baseline_count == 0
    assert summary.preference_count == 0
    assert summary.case_count == 0
    assert summary.knowledge_count == 0
    assert "System baselines:" in summary.context_text
    assert "- none" in summary.context_text


def test_summary_result_to_dict_has_stable_shape(tmp_path) -> None:
    """
    Summary results should expose a serializable stable shape.
    """
    memory_dir = tmp_path / "memory"
    seed_memory(memory_dir)

    summary = summarize_memory_for_request(
        "chrome memory",
        memory_dir=memory_dir,
    )
    payload = summary.to_dict()

    assert payload["status"] == MEMORY_SUMMARY_STATUS_OK
    assert payload["user_request"] == "chrome memory"
    assert "chrome" in payload["keywords"]
    assert "memory" in payload["keywords"]
    assert isinstance(payload["context_text"], str)
    assert payload["baseline_count"] > 0
    assert payload["preference_count"] > 0
    assert payload["case_count"] == 1
    assert payload["knowledge_count"] == 1
    assert isinstance(payload["source_status"], dict)
    assert payload["warnings"] == []