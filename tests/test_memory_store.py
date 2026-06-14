"""
Tests for Lighthouse memory store.

The memory store is the low-level controlled file layer for Lighthouse memory.
It should only read and write known files inside data/memory.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.memory_store import (
    BASELINES_FILENAME,
    CASES_FILENAME,
    KNOWLEDGE_INDEX_FILENAME,
    MEMORY_SCHEMA_VERSION,
    MEMORY_STORE_STATUS_ERROR,
    MEMORY_STORE_STATUS_OK,
    OPERATOR_PREFERENCES_FILENAME,
    append_case_memory,
    append_jsonl_memory,
    ensure_memory_directory,
    get_memory_file_path,
    read_baselines,
    read_case_memories,
    read_json_memory,
    read_jsonl_memory,
    read_knowledge_index,
    read_operator_preferences,
    validate_memory_filename,
    write_baselines,
    write_json_memory,
    write_knowledge_index,
    write_operator_preferences,
)


def test_ensure_memory_directory_creates_directory(tmp_path) -> None:
    """
    The memory directory should be created when missing.
    """
    memory_dir = tmp_path / "data" / "memory"

    assert not memory_dir.exists()

    result = ensure_memory_directory(memory_dir)

    assert result == memory_dir
    assert memory_dir.exists()
    assert memory_dir.is_dir()


def test_validate_memory_filename_accepts_known_files() -> None:
    """
    Known controlled memory filenames should be accepted.
    """
    assert validate_memory_filename(BASELINES_FILENAME) == BASELINES_FILENAME
    assert validate_memory_filename(OPERATOR_PREFERENCES_FILENAME) == (
        OPERATOR_PREFERENCES_FILENAME
    )
    assert validate_memory_filename(CASES_FILENAME) == CASES_FILENAME
    assert validate_memory_filename(KNOWLEDGE_INDEX_FILENAME) == (
        KNOWLEDGE_INDEX_FILENAME
    )


def test_validate_memory_filename_rejects_unknown_or_unsafe_files() -> None:
    """
    Unknown filenames or path traversal attempts should be rejected.
    """
    unsafe_filenames = [
        "../outside.json",
        "nested/file.json",
        r"nested\file.json",
        "unknown.json",
    ]

    for filename in unsafe_filenames:
        try:
            validate_memory_filename(filename)
            raised = False
        except ValueError:
            raised = True

        assert raised is True


def test_get_memory_file_path_stays_inside_memory_directory(tmp_path) -> None:
    """
    Controlled filenames should resolve directly inside the memory directory.
    """
    memory_dir = tmp_path / "memory"

    path = get_memory_file_path(BASELINES_FILENAME, memory_dir)

    assert path == memory_dir / BASELINES_FILENAME
    assert path.parent.resolve() == memory_dir.resolve()


def test_read_missing_json_returns_default(tmp_path) -> None:
    """
    Missing JSON memory files should return the provided default.
    """
    memory_dir = tmp_path / "memory"

    result = read_json_memory(
        BASELINES_FILENAME,
        default={"baseline": "empty"},
        memory_dir=memory_dir,
    )

    assert result.status == MEMORY_STORE_STATUS_OK
    assert result.data == {"baseline": "empty"}


def test_write_and_read_baselines(tmp_path) -> None:
    """
    Baseline memory should round-trip through JSON.
    """
    memory_dir = tmp_path / "memory"
    baselines = {
        "memory": {
            "normal_idle_percent_min": 30,
            "normal_idle_percent_max": 40,
        }
    }

    write_result = write_baselines(baselines, memory_dir=memory_dir)
    read_result = read_baselines(memory_dir=memory_dir)

    assert write_result.status == MEMORY_STORE_STATUS_OK
    assert read_result.status == MEMORY_STORE_STATUS_OK
    assert read_result.data == baselines


def test_write_and_read_operator_preferences(tmp_path) -> None:
    """
    Operator preferences should round-trip through JSON.
    """
    memory_dir = tmp_path / "memory"
    preferences = {
        "explanation_style": "plain_english",
        "require_confirmation_for_actions": True,
    }

    write_result = write_operator_preferences(preferences, memory_dir=memory_dir)
    read_result = read_operator_preferences(memory_dir=memory_dir)

    assert write_result.status == MEMORY_STORE_STATUS_OK
    assert read_result.status == MEMORY_STORE_STATUS_OK
    assert read_result.data == preferences


def test_read_knowledge_index_returns_default_when_missing(tmp_path) -> None:
    """
    Missing knowledge index should return a stable default shape.
    """
    memory_dir = tmp_path / "memory"

    result = read_knowledge_index(memory_dir=memory_dir)

    assert result.status == MEMORY_STORE_STATUS_OK
    assert result.data == {
        "schema_version": MEMORY_SCHEMA_VERSION,
        "entries": [],
    }


def test_write_and_read_knowledge_index(tmp_path) -> None:
    """
    Knowledge index should round-trip through JSON.
    """
    memory_dir = tmp_path / "memory"
    knowledge_index = {
        "schema_version": 1,
        "entries": [
            {
                "id": "windows_event_41",
                "title": "Kernel-Power Event ID 41",
            }
        ],
    }

    write_result = write_knowledge_index(knowledge_index, memory_dir=memory_dir)
    read_result = read_knowledge_index(memory_dir=memory_dir)

    assert write_result.status == MEMORY_STORE_STATUS_OK
    assert read_result.status == MEMORY_STORE_STATUS_OK
    assert read_result.data == knowledge_index


def test_write_json_memory_rejects_non_serializable_data(tmp_path) -> None:
    """
    Non-JSON-serializable data should return an error result.
    """
    memory_dir = tmp_path / "memory"
    data = {
        "bad_value": {1, 2, 3},
    }

    result = write_json_memory(
        BASELINES_FILENAME,
        data,
        memory_dir=memory_dir,
    )

    assert result.status == MEMORY_STORE_STATUS_ERROR
    assert result.error is not None


def test_read_json_memory_rejects_non_object_root(tmp_path) -> None:
    """
    JSON memory files must use an object as the root.
    """
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True)
    path = memory_dir / BASELINES_FILENAME
    path.write_text("[]", encoding="utf-8")

    result = read_json_memory(
        BASELINES_FILENAME,
        default={"fallback": True},
        memory_dir=memory_dir,
    )

    assert result.status == MEMORY_STORE_STATUS_ERROR
    assert result.data == {"fallback": True}


def test_append_and_read_case_memories_newest_first(tmp_path) -> None:
    """
    Case memories should append as JSONL and read newest-first by default.
    """
    memory_dir = tmp_path / "memory"

    first_result = append_case_memory(
        {
            "case_id": "case_1",
            "summary": "First case",
        },
        memory_dir=memory_dir,
    )
    second_result = append_case_memory(
        {
            "case_id": "case_2",
            "summary": "Second case",
        },
        memory_dir=memory_dir,
    )

    read_result = read_case_memories(memory_dir=memory_dir)

    assert first_result.status == MEMORY_STORE_STATUS_OK
    assert second_result.status == MEMORY_STORE_STATUS_OK
    assert read_result.status == MEMORY_STORE_STATUS_OK

    entries = read_result.data["entries"]

    assert read_result.data["entry_count"] == 2
    assert entries[0]["case_id"] == "case_2"
    assert entries[1]["case_id"] == "case_1"
    assert entries[0]["schema_version"] == MEMORY_SCHEMA_VERSION
    assert "created_at" in entries[0]


def test_read_jsonl_memory_respects_limit(tmp_path) -> None:
    """
    JSONL reads should support a limit.
    """
    memory_dir = tmp_path / "memory"

    append_case_memory({"case_id": "case_1"}, memory_dir=memory_dir)
    append_case_memory({"case_id": "case_2"}, memory_dir=memory_dir)
    append_case_memory({"case_id": "case_3"}, memory_dir=memory_dir)

    result = read_case_memories(limit=2, memory_dir=memory_dir)

    entries = result.data["entries"]

    assert result.status == MEMORY_STORE_STATUS_OK
    assert result.data["entry_count"] == 2
    assert entries[0]["case_id"] == "case_3"
    assert entries[1]["case_id"] == "case_2"


def test_read_jsonl_memory_can_read_oldest_first(tmp_path) -> None:
    """
    JSONL reads should support oldest-first ordering.
    """
    memory_dir = tmp_path / "memory"

    append_case_memory({"case_id": "case_1"}, memory_dir=memory_dir)
    append_case_memory({"case_id": "case_2"}, memory_dir=memory_dir)

    result = read_case_memories(
        newest_first=False,
        memory_dir=memory_dir,
    )

    entries = result.data["entries"]

    assert entries[0]["case_id"] == "case_1"
    assert entries[1]["case_id"] == "case_2"


def test_read_jsonl_memory_skips_invalid_lines(tmp_path) -> None:
    """
    Invalid JSONL lines should be skipped and counted.
    """
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True)
    path = memory_dir / CASES_FILENAME

    path.write_text(
        "\n".join(
            [
                json.dumps({"case_id": "case_1"}),
                "this is not json",
                json.dumps(["not", "an", "object"]),
                json.dumps({"case_id": "case_2"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = read_jsonl_memory(
        CASES_FILENAME,
        newest_first=False,
        memory_dir=memory_dir,
    )

    entries = result.data["entries"]

    assert result.status == MEMORY_STORE_STATUS_OK
    assert result.data["entry_count"] == 2
    assert result.data["invalid_line_count"] == 2
    assert entries[0]["case_id"] == "case_1"
    assert entries[1]["case_id"] == "case_2"


def test_append_jsonl_memory_rejects_unknown_file(tmp_path) -> None:
    """
    Generic JSONL appends should reject unsupported memory files.
    """
    memory_dir = tmp_path / "memory"

    result = append_jsonl_memory(
        "unknown.jsonl",
        {"case_id": "case_1"},
        memory_dir=memory_dir,
    )

    assert result.status == MEMORY_STORE_STATUS_ERROR
    assert result.error is not None