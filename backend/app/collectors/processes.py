"""
Process telemetry collector for Lighthouse.

Collects a read-only snapshot of running processes and returns
the top processes by memory usage.
"""

from typing import Any

import psutil


def bytes_to_mb(value: int) -> float:
    return round(value / (1024 ** 2), 2)


def get_top_processes(limit: int = 10) -> dict[str, Any]:
    """
    Collect top running processes by memory usage.
    """

    try:
        processes: list[dict[str, Any]] = []

        for process in psutil.process_iter(
            ["pid", "name", "memory_info", "memory_percent", "cpu_percent"]
        ):
            try:
                info = process.info
                memory_info = info.get("memory_info")

                processes.append(
                    {
                        "pid": info.get("pid"),
                        "name": info.get("name"),
                        "memory_mb": bytes_to_mb(memory_info.rss) if memory_info else 0,
                        "memory_percent": round(info.get("memory_percent", 0), 2),
                        "cpu_percent": info.get("cpu_percent", 0),
                    }
                )

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        top_processes = sorted(
            processes,
            key=lambda item: item["memory_mb"],
            reverse=True,
        )[:limit]

        return {
            "status": "ok",
            "count": len(top_processes),
            "processes": top_processes,
        }

    except Exception as error:
        return {
            "status": "error",
            "message": f"Failed to collect process telemetry: {error}",
        }