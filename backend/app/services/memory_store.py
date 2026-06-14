"""
Memory store for Lighthouse.

This module provides low-level read/write access for Lighthouse memory files.

It does not make reasoning decisions.
It does not execute tools.
It does not change the operating system outside the Lighthouse memory data folder.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


MEMORY_STORE_STATUS_OK = "ok"
MEMORY_STORE_STATUS_ERROR = "error"

MEMORY_SCHEMA_VERSION = 1

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MEMORY_DIR = PROJECT_ROOT / "data" / "memory"

BASELINES_FILENAME = "baselines.json"
OPERATOR_PREFERENCES_FILENAME = "operator_preferences.json"
CASES_FILENAME = "cases.jsonl"
KNOWLEDGE_INDEX_FILENAME = "knowledge_index.json"

ALLOWED_MEMORY_FILES = {
    BASELINES_FILENAME,
    OPERATOR_PREFERENCES_FILENAME,
    CASES_FILENAME,
    KNOWLEDGE_INDEX_FILENAME,
}


@dataclass(frozen=True)
class MemoryStoreResult:
    """
    Result returned by memory-store operations.
    """

    status: str
    message: str
    path: str
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable result shape.
        """
        return {
            "status": self.status,
            "message": self.message,
            "path": self.path,
            "data": self.data,
            "error": self.error,
        }


def utc_timestamp() -> str:
    """
    Return a UTC timestamp in a compact ISO-8601 format.
    """
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_memory_directory(memory_dir: Path | str | None = None) -> Path:
    """
    Return the active Lighthouse memory directory.
    """
    if memory_dir is None:
        return MEMORY_DIR

    return Path(memory_dir)


def ensure_memory_directory(memory_dir: Path | str | None = None) -> Path:
    """
    Ensure the Lighthouse memory directory exists.
    """
    directory = get_memory_directory(memory_dir)
    directory.mkdir(parents=True, exist_ok=True)

    return directory


def validate_memory_filename(filename: str) -> str:
    """
    Validate that a memory filename is one of the controlled memory files.
    """
    normalized_filename = filename.strip().replace("\\", "/")

    if "/" in normalized_filename:
        raise ValueError("Memory filenames may not contain path separators.")

    if normalized_filename not in ALLOWED_MEMORY_FILES:
        raise ValueError(f"Unsupported memory file: {filename}")

    return normalized_filename


def get_memory_file_path(
    filename: str,
    memory_dir: Path | str | None = None,
) -> Path:
    """
    Return a safe path for a controlled Lighthouse memory file.

    This function only allows known filenames and ensures the final path remains
    directly inside the Lighthouse memory directory.
    """
    normalized_filename = validate_memory_filename(filename)
    directory = ensure_memory_directory(memory_dir)

    candidate_path = directory / normalized_filename
    resolved_directory = directory.resolve()
    resolved_candidate_parent = candidate_path.resolve(strict=False).parent

    if resolved_candidate_parent != resolved_directory:
        raise ValueError("Resolved memory path escaped the memory directory.")

    return candidate_path


def build_ok_result(
    *,
    message: str,
    path: Path,
    data: Any = None,
) -> MemoryStoreResult:
    """
    Build an ok memory-store result.
    """
    return MemoryStoreResult(
        status=MEMORY_STORE_STATUS_OK,
        message=message,
        path=str(path),
        data=data,
        error=None,
    )


def build_error_result(
    *,
    message: str,
    path: Path | str = "",
    error: Exception | str | None = None,
    data: Any = None,
) -> MemoryStoreResult:
    """
    Build an error memory-store result.
    """
    error_text = None

    if error is not None:
        error_text = str(error)

    return MemoryStoreResult(
        status=MEMORY_STORE_STATUS_ERROR,
        message=message,
        path=str(path),
        data=data,
        error=error_text,
    )


def read_json_memory(
    filename: str,
    *,
    default: dict[str, Any] | None = None,
    memory_dir: Path | str | None = None,
) -> MemoryStoreResult:
    """
    Read a controlled JSON memory file.

    Missing or empty files return the provided default.
    """
    fallback = default if default is not None else {}

    try:
        path = get_memory_file_path(filename, memory_dir)

        if not path.exists():
            return build_ok_result(
                message="Memory file does not exist. Returned default data.",
                path=path,
                data=fallback,
            )

        raw_content = path.read_text(encoding="utf-8").strip()

        if not raw_content:
            return build_ok_result(
                message="Memory file is empty. Returned default data.",
                path=path,
                data=fallback,
            )

        data = json.loads(raw_content)

        if not isinstance(data, dict):
            return build_error_result(
                message="Memory JSON root must be an object.",
                path=path,
                data=fallback,
            )

        return build_ok_result(
            message="Memory JSON read successfully.",
            path=path,
            data=data,
        )

    except Exception as error:
        return build_error_result(
            message="Unable to read memory JSON.",
            path="",
            error=error,
            data=fallback,
        )


def write_json_memory(
    filename: str,
    data: dict[str, Any],
    *,
    memory_dir: Path | str | None = None,
) -> MemoryStoreResult:
    """
    Write a controlled JSON memory file.
    """
    try:
        path = get_memory_file_path(filename, memory_dir)
        serialized = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
        path.write_text(serialized + "\n", encoding="utf-8")

        return build_ok_result(
            message="Memory JSON written successfully.",
            path=path,
            data=data,
        )

    except Exception as error:
        return build_error_result(
            message="Unable to write memory JSON.",
            path="",
            error=error,
            data=data,
        )


def append_jsonl_memory(
    filename: str,
    entry: dict[str, Any],
    *,
    memory_dir: Path | str | None = None,
) -> MemoryStoreResult:
    """
    Append one JSONL entry to a controlled Lighthouse memory file.

    The entry is enriched with schema_version and created_at when those fields
    are not already present.
    """
    try:
        path = get_memory_file_path(filename, memory_dir)

        normalized_entry = dict(entry)
        normalized_entry.setdefault("schema_version", MEMORY_SCHEMA_VERSION)
        normalized_entry.setdefault("created_at", utc_timestamp())

        serialized = json.dumps(
            normalized_entry,
            ensure_ascii=False,
            sort_keys=True,
        )

        with path.open("a", encoding="utf-8") as file:
            file.write(serialized + "\n")

        return build_ok_result(
            message="Memory JSONL entry appended successfully.",
            path=path,
            data=normalized_entry,
        )

    except Exception as error:
        return build_error_result(
            message="Unable to append memory JSONL entry.",
            path="",
            error=error,
            data=entry,
        )


def read_jsonl_memory(
    filename: str,
    *,
    limit: int | None = 50,
    newest_first: bool = True,
    memory_dir: Path | str | None = None,
) -> MemoryStoreResult:
    """
    Read entries from a controlled JSONL memory file.

    Invalid JSON lines are skipped and counted.
    """
    try:
        path = get_memory_file_path(filename, memory_dir)

        if limit is not None and limit < 0:
            return build_error_result(
                message="Limit must be zero or greater.",
                path=path,
                data={
                    "entries": [],
                    "entry_count": 0,
                    "invalid_line_count": 0,
                },
            )

        if not path.exists():
            return build_ok_result(
                message="Memory JSONL file does not exist. Returned empty entries.",
                path=path,
                data={
                    "entries": [],
                    "entry_count": 0,
                    "invalid_line_count": 0,
                },
            )

        entries: list[dict[str, Any]] = []
        invalid_line_count = 0

        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()

            if not line:
                continue

            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                invalid_line_count += 1
                continue

            if not isinstance(parsed, dict):
                invalid_line_count += 1
                continue

            entries.append(parsed)

        if newest_first:
            entries = list(reversed(entries))

        if limit is not None:
            entries = entries[:limit]

        return build_ok_result(
            message="Memory JSONL read successfully.",
            path=path,
            data={
                "entries": entries,
                "entry_count": len(entries),
                "invalid_line_count": invalid_line_count,
            },
        )

    except Exception as error:
        return build_error_result(
            message="Unable to read memory JSONL.",
            path="",
            error=error,
            data={
                "entries": [],
                "entry_count": 0,
                "invalid_line_count": 0,
            },
        )


def read_baselines(
    *,
    memory_dir: Path | str | None = None,
) -> MemoryStoreResult:
    """
    Read system baseline memory.
    """
    return read_json_memory(
        BASELINES_FILENAME,
        default={},
        memory_dir=memory_dir,
    )


def write_baselines(
    baselines: dict[str, Any],
    *,
    memory_dir: Path | str | None = None,
) -> MemoryStoreResult:
    """
    Write system baseline memory.
    """
    return write_json_memory(
        BASELINES_FILENAME,
        baselines,
        memory_dir=memory_dir,
    )


def read_operator_preferences(
    *,
    memory_dir: Path | str | None = None,
) -> MemoryStoreResult:
    """
    Read Operator preference memory.
    """
    return read_json_memory(
        OPERATOR_PREFERENCES_FILENAME,
        default={},
        memory_dir=memory_dir,
    )


def write_operator_preferences(
    preferences: dict[str, Any],
    *,
    memory_dir: Path | str | None = None,
) -> MemoryStoreResult:
    """
    Write Operator preference memory.
    """
    return write_json_memory(
        OPERATOR_PREFERENCES_FILENAME,
        preferences,
        memory_dir=memory_dir,
    )


def read_knowledge_index(
    *,
    memory_dir: Path | str | None = None,
) -> MemoryStoreResult:
    """
    Read knowledge index memory.
    """
    return read_json_memory(
        KNOWLEDGE_INDEX_FILENAME,
        default={
            "schema_version": MEMORY_SCHEMA_VERSION,
            "entries": [],
        },
        memory_dir=memory_dir,
    )


def write_knowledge_index(
    knowledge_index: dict[str, Any],
    *,
    memory_dir: Path | str | None = None,
) -> MemoryStoreResult:
    """
    Write knowledge index memory.
    """
    return write_json_memory(
        KNOWLEDGE_INDEX_FILENAME,
        knowledge_index,
        memory_dir=memory_dir,
    )


def append_case_memory(
    case_entry: dict[str, Any],
    *,
    memory_dir: Path | str | None = None,
) -> MemoryStoreResult:
    """
    Append an incident/case memory entry.
    """
    return append_jsonl_memory(
        CASES_FILENAME,
        case_entry,
        memory_dir=memory_dir,
    )


def read_case_memories(
    *,
    limit: int | None = 50,
    newest_first: bool = True,
    memory_dir: Path | str | None = None,
) -> MemoryStoreResult:
    """
    Read incident/case memory entries.
    """
    return read_jsonl_memory(
        CASES_FILENAME,
        limit=limit,
        newest_first=newest_first,
        memory_dir=memory_dir,
    )