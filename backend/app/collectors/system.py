"""
System telemetry collector for Lighthouse.

Collects basic operating system and machine information.
This collector is read-only and uses Python's standard library.
"""

from typing import Any
import platform
import sys


def get_system_info() -> dict[str, Any]:
    """
    Collect basic system information.

    Returns:
        Dictionary containing OS, machine, and Python runtime details.
    """

    try:
        return {
            "status": "ok",
            "os": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": sys.version.split()[0],
        }

    except Exception as error:
        return {
            "status": "error",
            "message": f"Failed to collect system telemetry: {error}",
        }