"""
Interactive command line interface for Lighthouse.

This turns Lighthouse from a one-shot telemetry report into a small
read-only assistant that can respond to user commands.
"""

from typing import Any

from app.main import collect_telemetry
from app.reporting.console_report import print_console_report


def classify_percent(value: Any, warning_at: float, critical_at: float) -> str:
    """
    Convert a percentage value into a simple health status.
    """
    try:
        percent = float(value)
    except (TypeError, ValueError):
        return "UNKNOWN"

    if percent >= critical_at:
        return "CRITICAL"

    if percent >= warning_at:
        return "WARNING"

    return "OK"


def print_help() -> None:
    """
    Print available Lighthouse commands.
    """
    print("\nLIGHTHOUSE COMMANDS")
    print("-" * 52)
    print("snapshot   Run a full system telemetry report")
    print("health     Show a simple health summary")
    print("help       Show this command list")
    print("quit       Exit Lighthouse")
    print("-" * 52)


def print_health_report(telemetry: dict[str, Any]) -> None:
    """
    Print a simplified health view based on telemetry thresholds.
    """
    cpu = telemetry.get("cpu", {})
    memory = telemetry.get("memory", {})
    disk = telemetry.get("disk", {})
    processes = telemetry.get("processes", {})

    cpu_status = classify_percent(cpu.get("usage_percent"), 75, 90)
    memory_status = classify_percent(memory.get("usage_percent"), 80, 90)
    disk_status = classify_percent(disk.get("usage_percent"), 80, 90)

    statuses = [cpu_status, memory_status, disk_status]

    if "CRITICAL" in statuses:
        overall = "CRITICAL"
    elif "WARNING" in statuses:
        overall = "WARNING"
    elif "UNKNOWN" in statuses:
        overall = "UNKNOWN"
    else:
        overall = "GOOD"

    print("\n" + "=" * 52)
    print("LIGHTHOUSE HEALTH SUMMARY")
    print("=" * 52)

    print(f"Overall health: {overall}")
    print()
    print(f"CPU usage:    {cpu.get('usage_percent', 'Unknown')}%  | {cpu_status}")
    print(f"Memory usage: {memory.get('usage_percent', 'Unknown')}% | {memory_status}")
    print(f"Disk usage:   {disk.get('usage_percent', 'Unknown')}%  | {disk_status}")

    top_processes = processes.get("processes", [])

    if top_processes:
        top = top_processes[0]
        print()
        print("Top memory process:")
        print(
            f"{top.get('name', 'Unknown')} "
            f"({top.get('memory_mb', 'Unknown')} MB)"
        )

    print()
    print("Recommendations:")

    recommendations: list[str] = []

    if cpu_status in {"WARNING", "CRITICAL"}:
        recommendations.append("- Check high CPU processes.")

    if memory_status in {"WARNING", "CRITICAL"}:
        recommendations.append("- Close unused applications or browser tabs.")

    if disk_status in {"WARNING", "CRITICAL"}:
        recommendations.append("- Free up disk space on the system drive.")

    if not recommendations:
        recommendations.append("- No immediate action needed.")

    for recommendation in recommendations:
        print(recommendation)

    print("=" * 52)


def command_loop() -> None:
    """
    Start the Lighthouse interactive shell.
    """
    print("\nLighthouse CLI")
    print("Read-only system telemetry assistant.")
    print("Type 'help' to see available commands.")
    print("Type 'quit' to exit.")

    while True:
        command = input("\nlighthouse> ").strip().lower()

        if not command:
            continue

        if command in {"quit", "exit", "q"}:
            print("Exiting Lighthouse.")
            break

        if command in {"help", "h", "?"}:
            print_help()
            continue

        if command in {"snapshot", "report"}:
            telemetry = collect_telemetry()
            print_console_report(telemetry)
            continue

        if command == "health":
            telemetry = collect_telemetry()
            print_health_report(telemetry)
            continue

        print(f"Unknown command: {command}")
        print("Type 'help' to see available commands.")


if __name__ == "__main__":
    command_loop()