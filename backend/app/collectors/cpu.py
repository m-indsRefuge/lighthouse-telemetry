"""
CPU telemetry collector for Lighthouse.

This module is read-only. It asks the operating system for CPU information
through psutil and returns a clean dictionary for the rest of the app.
"""

from typing import Any

import psutil


def get_cpu_info() -> dict[str, Any]:
    """
    Collect current CPU telemetry.

    Returns:
        A dictionary containing CPU core counts and current CPU usage.
    """

    try:
        physical_cores = psutil.cpu_count(logical=False)
        logical_cores = psutil.cpu_count(logical=True)

        usage_percent = psutil.cpu_percent(interval=1)

        return {
            "status": "ok",
            "physical_cores": physical_cores,
            "logical_cores": logical_cores,
            "usage_percent": usage_percent,
        }

    except Exception as error:
        return {
            "status": "error",
            "message": f"Failed to collect CPU telemetry: {error}",
        }