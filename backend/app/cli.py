"""
Interactive command line interface for Lighthouse.

This turns Lighthouse from a one-shot telemetry report into a small
read-only assistant that can respond to user commands.
"""

from typing import Any

from app.collectors.event_logs import get_recent_system_events
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
    print("snapshot    Run a full system telemetry report")
    print("health      Show a simple health summary")
    print("cpu         Show CPU status")
    print("memory      Show memory status")
    print("disk        Show disk status")
    print("processes   Show top memory processes")
    print("diagnose    Explain likely causes of slowness")
    print("events      Show recent crash-relevant Windows events")
    print("crash       Alias for events")
    print("help        Show this command list")
    print("quit        Exit Lighthouse")
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


def print_cpu_report(telemetry: dict[str, Any]) -> None:
    """
    Print CPU telemetry.
    """
    cpu = telemetry.get("cpu", {})

    print("\nCPU STATUS")
    print("-" * 52)
    print(f"Status: {cpu.get('status', 'unknown')}")
    print(f"Physical cores: {cpu.get('physical_cores', 'Unknown')}")
    print(f"Logical cores: {cpu.get('logical_cores', 'Unknown')}")
    print(f"Usage: {cpu.get('usage_percent', 'Unknown')}%")
    print("-" * 52)


def print_memory_report(telemetry: dict[str, Any]) -> None:
    """
    Print memory telemetry.
    """
    memory = telemetry.get("memory", {})

    print("\nMEMORY STATUS")
    print("-" * 52)
    print(f"Status: {memory.get('status', 'unknown')}")
    print(f"Total: {memory.get('total_gb', 'Unknown')} GB")
    print(f"Used: {memory.get('used_gb', 'Unknown')} GB")
    print(f"Available: {memory.get('available_gb', 'Unknown')} GB")
    print(f"Usage: {memory.get('usage_percent', 'Unknown')}%")
    print("-" * 52)


def print_disk_report(telemetry: dict[str, Any]) -> None:
    """
    Print disk telemetry.
    """
    disk = telemetry.get("disk", {})

    print("\nDISK STATUS")
    print("-" * 52)
    print(f"Status: {disk.get('status', 'unknown')}")
    print(f"Path: {disk.get('path', 'Unknown')}")
    print(f"Total: {disk.get('total_gb', 'Unknown')} GB")
    print(f"Used: {disk.get('used_gb', 'Unknown')} GB")
    print(f"Free: {disk.get('free_gb', 'Unknown')} GB")
    print(f"Usage: {disk.get('usage_percent', 'Unknown')}%")
    print("-" * 52)


def print_process_report(telemetry: dict[str, Any]) -> None:
    """
    Print top memory-consuming processes.
    """
    processes = telemetry.get("processes", {})
    process_list = processes.get("processes", [])

    print("\nTOP PROCESSES BY MEMORY")
    print("-" * 52)
    print(f"Status: {processes.get('status', 'unknown')}")

    if not process_list:
        print("No process data available.")
        print("-" * 52)
        return

    for process in process_list:
        print(
            f"{process.get('pid', 'Unknown'):>6} | "
            f"{process.get('name', 'Unknown'):<30} | "
            f"Memory: {process.get('memory_mb', 'Unknown')} MB | "
            f"CPU: {process.get('cpu_percent', 'Unknown')}%"
        )

    print("-" * 52)


def print_diagnosis(telemetry: dict[str, Any]) -> None:
    """
    Print a simple explanation of likely performance or crash-related issues.
    """
    cpu = telemetry.get("cpu", {})
    memory = telemetry.get("memory", {})
    disk = telemetry.get("disk", {})
    processes = telemetry.get("processes", {})

    cpu_status = classify_percent(cpu.get("usage_percent"), 75, 90)
    memory_status = classify_percent(memory.get("usage_percent"), 80, 90)
    disk_status = classify_percent(disk.get("usage_percent"), 80, 90)

    event_report = get_recent_system_events(limit=100)
    event_status = event_report.get("status", "unknown")
    severity_summary = event_report.get("severity_summary", {})

    critical_events = severity_summary.get("critical", 0)
    warning_events = severity_summary.get("warning", 0)
    context_events = severity_summary.get("context", 0)

    print("\nLIGHTHOUSE DIAGNOSIS")
    print("=" * 52)

    print("Live telemetry:")
    print(f"- CPU usage:    {cpu.get('usage_percent', 'Unknown')}%  | {cpu_status}")
    print(f"- Memory usage: {memory.get('usage_percent', 'Unknown')}% | {memory_status}")
    print(f"- Disk usage:   {disk.get('usage_percent', 'Unknown')}%  | {disk_status}")

    process_list = processes.get("processes", [])

    if process_list:
        top = process_list[0]
        print(
            "- Highest memory process: "
            f"{top.get('name', 'Unknown')} "
            f"using {top.get('memory_mb', 'Unknown')} MB"
        )

    print()
    print("Recent event evidence:")

    if event_status != "ok":
        print(f"- Event log check unavailable: {event_report.get('message', 'Unknown error')}")
    else:
        print(f"- Critical events: {critical_events}")
        print(f"- Warning events:  {warning_events}")
        print(f"- Context events:  {context_events}")

        possible_causes = event_report.get("possible_causes", [])

        for cause in possible_causes:
            print(f"- {cause}")

    print()
    print("Conclusion:")

    has_live_pressure = any(
        status in {"WARNING", "CRITICAL"}
        for status in {cpu_status, memory_status, disk_status}
    )

    if critical_events > 0:
        print("A critical crash-related event was found. Run 'events' for details.")
    elif warning_events > 0:
        print("Warning-level system events were found. Run 'events' for details.")
    elif has_live_pressure:
        print("Live system pressure was detected, but no critical crash pattern was found.")
    else:
        print("No obvious system fault detected right now.")

    print()
    print("Suggested next step:")

    if critical_events > 0 or warning_events > 0:
        print("- Run the 'events' command and review the event classifications.")
    elif cpu_status in {"WARNING", "CRITICAL"}:
        print("- Run the 'processes' command and look for high CPU usage.")
    elif memory_status in {"WARNING", "CRITICAL"}:
        print("- Close unused applications or browser tabs.")
    elif disk_status in {"WARNING", "CRITICAL"}:
        print("- Free up disk space on the system drive.")
    else:
        print("- No immediate action needed.")

    print("=" * 52)


def print_events_report(limit: int = 100) -> None:
    """
    Print recent crash-relevant Windows System events.
    """
    report = get_recent_system_events(limit=limit)

    print("\nRECENT SYSTEM EVENTS")
    print("=" * 52)

    status = report.get("status", "unknown")
    print(f"Status: {status}")

    if status != "ok":
        print(report.get("message", "Unable to read Windows event logs."))
        print("=" * 52)
        return

    print(f"Generated at: {report.get('generated_at', 'Unknown')}")
    print(f"Log: {report.get('log', 'Unknown')}")
    print(f"Events checked: {report.get('events_checked', 'Unknown')}")
    print(f"Relevant events found: {report.get('relevant_event_count', 'Unknown')}")

    severity_summary = report.get("severity_summary", {})

    print("\nSeverity summary:")
    print(f"- Critical: {severity_summary.get('critical', 0)}")
    print(f"- Warning:  {severity_summary.get('warning', 0)}")
    print(f"- Context:  {severity_summary.get('context', 0)}")

    print("\nPossible causes:")
    possible_causes = report.get("possible_causes", [])

    if possible_causes:
        for cause in possible_causes:
            print(f"- {cause}")
    else:
        print("- No possible causes returned.")

    events = report.get("events", [])

    if not events:
        print("\nNo relevant recent system events found.")
        print("=" * 52)
        return

    print("\nRecent relevant events:")
    print("-" * 52)

    for event in events:
        print(f"Time: {event.get('time', 'Unknown')}")
        print(f"Severity: {event.get('severity', 'Unknown')}")
        print(f"Type: {event.get('event_type_label', 'Unknown')}")
        print(f"Source: {event.get('source', 'Unknown')}")
        print(f"Event ID: {event.get('event_id', 'Unknown')}")
        print(f"Classification: {event.get('classification', 'Unknown')}")
        print("-" * 52)

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

        if command == "cpu":
            telemetry = collect_telemetry()
            print_cpu_report(telemetry)
            continue

        if command == "memory":
            telemetry = collect_telemetry()
            print_memory_report(telemetry)
            continue

        if command == "disk":
            telemetry = collect_telemetry()
            print_disk_report(telemetry)
            continue

        if command in {"processes", "process"}:
            telemetry = collect_telemetry()
            print_process_report(telemetry)
            continue

        if command in {"diagnose", "slow", "why is my laptop slow"}:
            telemetry = collect_telemetry()
            print_diagnosis(telemetry)
            continue

        if command in {"events", "event", "crash", "crashes"}:
            print_events_report()
            continue

        print(f"Unknown command: {command}")
        print("Type 'help' to see available commands.")


if __name__ == "__main__":
    command_loop()