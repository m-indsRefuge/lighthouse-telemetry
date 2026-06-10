"""
Memory telemetry collector for Lighthouse.

Collects RAM statistics from the operating system
using psutil and returns a clean dictionary.
"""

from typing import Any

import psutil


def bytes_to_gb(value: int) -> float:
    """
    Convert bytes to gigabytes.
    """

    return round(value / (1024 ** 3), 2)


def get_memory_info() -> dict[str, Any]:
    """
    Collect memory telemetry.

    Returns:
        Dictionary containing RAM statistics.
    """

    try:
        memory = psutil.virtual_memory()

        return {
            "status": "ok",
            "total_gb": bytes_to_gb(memory.total),
            "available_gb": bytes_to_gb(memory.available),
            "used_gb": bytes_to_gb(memory.used),
            "usage_percent": memory.percent,
        }

    except Exception as error:
        return {
            "status": "error",
            "message": f"Failed to collect memory telemetry: {error}",
        }