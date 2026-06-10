"""
Disk telemetry collector for Lighthouse.

Collects disk usage information from the operating system
using psutil and returns a clean dictionary.
"""

from typing import Any

import psutil


def bytes_to_gb(value: int) -> float:
    """
    Convert bytes to gigabytes.
    """

    return round(value / (1024 ** 3), 2)


def get_disk_info(path: str = "C:\\") -> dict[str, Any]:
    """
    Collect disk usage telemetry for a given path.

    Args:
        path: The disk path to inspect. Defaults to C:\\ on Windows.

    Returns:
        Dictionary containing disk usage statistics.
    """

    try:
        disk = psutil.disk_usage(path)

        return {
            "status": "ok",
            "path": path,
            "total_gb": bytes_to_gb(disk.total),
            "used_gb": bytes_to_gb(disk.used),
            "free_gb": bytes_to_gb(disk.free),
            "usage_percent": disk.percent,
        }

    except Exception as error:
        return {
            "status": "error",
            "path": path,
            "message": f"Failed to collect disk telemetry: {error}",
        }