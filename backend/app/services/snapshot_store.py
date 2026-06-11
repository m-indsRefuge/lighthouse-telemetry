"""
Snapshot storage service for Lighthouse.

Saves and reads read-only telemetry and event-log evidence from local JSON files.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.collectors.event_logs import get_recent_system_events
from app.main import collect_telemetry


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT_DIR = PROJECT_ROOT / "data" / "snapshots"


def build_snapshot() -> dict[str, Any]:
    """
    Build a complete Lighthouse snapshot.

    Includes current telemetry and recent Windows event-log evidence.
    """
    generated_at = datetime.now()

    return {
        "metadata": {
            "generated_at": generated_at.strftime("%Y-%m-%d %H:%M:%S"),
            "snapshot_type": "lighthouse_system_snapshot",
            "read_only": True,
        },
        "telemetry": collect_telemetry(),
        "event_report": get_recent_system_events(limit=100),
    }


def save_snapshot() -> dict[str, Any]:
    """
    Save a Lighthouse snapshot to the local data/snapshots folder.
    """
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now()
    timestamp = generated_at.strftime("%Y%m%d_%H%M%S")
    filename = f"lighthouse_snapshot_{timestamp}.json"
    file_path = SNAPSHOT_DIR / filename

    snapshot = build_snapshot()

    with file_path.open("w", encoding="utf-8") as file:
        json.dump(snapshot, file, indent=2)

    return {
        "status": "ok",
        "generated_at": generated_at.strftime("%Y-%m-%d %H:%M:%S"),
        "path": str(file_path),
        "filename": filename,
    }


def list_snapshots(limit: int = 10) -> dict[str, Any]:
    """
    List saved Lighthouse snapshots, newest first.
    """
    if not SNAPSHOT_DIR.exists():
        return {
            "status": "ok",
            "snapshot_count": 0,
            "snapshots": [],
        }

    files = sorted(
        SNAPSHOT_DIR.glob("lighthouse_snapshot_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    snapshots: list[dict[str, Any]] = []

    for file_path in files[:limit]:
        snapshots.append(
            {
                "filename": file_path.name,
                "path": str(file_path),
                "modified_at": datetime.fromtimestamp(
                    file_path.stat().st_mtime
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "size_kb": round(file_path.stat().st_size / 1024, 2),
            }
        )

    return {
        "status": "ok",
        "snapshot_count": len(files),
        "snapshots": snapshots,
    }


def load_snapshot(file_path: Path) -> dict[str, Any]:
    """
    Load a saved Lighthouse snapshot JSON file.
    """
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_latest_snapshot() -> dict[str, Any]:
    """
    Load the most recent saved Lighthouse snapshot.
    """
    if not SNAPSHOT_DIR.exists():
        return {
            "status": "error",
            "message": "No snapshot directory found. Run 'save' first.",
        }

    files = sorted(
        SNAPSHOT_DIR.glob("lighthouse_snapshot_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not files:
        return {
            "status": "error",
            "message": "No saved snapshots found. Run 'save' first.",
        }

    latest_file = files[0]

    try:
        snapshot = load_snapshot(latest_file)
    except Exception as error:
        return {
            "status": "error",
            "message": f"Failed to load latest snapshot: {error}",
            "path": str(latest_file),
        }

    return {
        "status": "ok",
        "filename": latest_file.name,
        "path": str(latest_file),
        "snapshot": snapshot,
    }