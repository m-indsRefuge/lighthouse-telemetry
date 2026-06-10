"""
Console reporting for Lighthouse.

Turns raw telemetry dictionaries into a human-readable terminal report.
"""

from typing import Any


def format_status(value: dict[str, Any]) -> str:
    return value.get("status", "unknown")


def print_console_report(telemetry: dict[str, Any]) -> None:
    """
    Print a clean Lighthouse telemetry report to the terminal.
    """

    system = telemetry.get("system", {})
    cpu = telemetry.get("cpu", {})
    memory = telemetry.get("memory", {})
    disk = telemetry.get("disk", {})
    processes = telemetry.get("processes", {})

    print("=" * 52)
    print("LIGHTHOUSE SYSTEM REPORT")
    print("=" * 52)

    print("\nSYSTEM")
    print(f"Status: {format_status(system)}")
    print(f"OS: {system.get('os', 'Unknown')} {system.get('os_release', '')}")
    print(f"Machine: {system.get('machine', 'Unknown')}")
    print(f"Processor: {system.get('processor', 'Unknown')}")
    print(f"Python: {system.get('python_version', 'Unknown')}")

    print("\nCPU")
    print(f"Status: {format_status(cpu)}")
    print(f"Physical cores: {cpu.get('physical_cores', 'Unknown')}")
    print(f"Logical cores: {cpu.get('logical_cores', 'Unknown')}")
    print(f"Usage: {cpu.get('usage_percent', 'Unknown')}%")

    print("\nMEMORY")
    print(f"Status: {format_status(memory)}")
    print(f"Total: {memory.get('total_gb', 'Unknown')} GB")
    print(f"Used: {memory.get('used_gb', 'Unknown')} GB")
    print(f"Available: {memory.get('available_gb', 'Unknown')} GB")
    print(f"Usage: {memory.get('usage_percent', 'Unknown')}%")

    print("\nDISK")
    print(f"Status: {format_status(disk)}")
    print(f"Path: {disk.get('path', 'Unknown')}")
    print(f"Total: {disk.get('total_gb', 'Unknown')} GB")
    print(f"Used: {disk.get('used_gb', 'Unknown')} GB")
    print(f"Free: {disk.get('free_gb', 'Unknown')} GB")
    print(f"Usage: {disk.get('usage_percent', 'Unknown')}%")

    print("\nTOP PROCESSES BY MEMORY")
    print(f"Status: {format_status(processes)}")

    for process in processes.get("processes", []):
        print(
            f"{process.get('pid', 'Unknown'):>6} | "
            f"{process.get('name', 'Unknown'):<30} | "
            f"Memory: {process.get('memory_mb', 'Unknown')} MB | "
            f"CPU: {process.get('cpu_percent', 'Unknown')}%"
        )

    print("\nStatus: Read-only telemetry complete.")
    print("=" * 52)