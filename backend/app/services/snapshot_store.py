"""
Snapshot storage service for Lighthouse.

Saves read-only telemetry and event-log evidence to local JSON files.
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