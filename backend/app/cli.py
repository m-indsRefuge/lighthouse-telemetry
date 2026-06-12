"""
Interactive command line interface for Lighthouse.

This turns Lighthouse from a one-shot telemetry report into a small
read-only assistant that can respond to user commands.
"""

from typing import Any

from app.collectors.event_logs import get_recent_system_events
from app.main import collect_telemetry
from app.reporting.console_report import print_console_report
from app.services.action_journal import (
    format_journal_report,
    read_journal_entries,
    record_plan_execution,
)
from app.services.assistant import classify_user_intent
from app.services.confirmation_gate import (
    build_confirmation_request,
    format_confirmation_request,
)
from app.services.insights import build_system_insight, format_insight_report
from app.services.llm import ask_lighthouse, get_ollama_status, run_ollama_model_test
from app.services.snapshot_store import get_latest_snapshot, list_snapshots, save_snapshot
from app.services.tool_executor import (
    ToolExecutionResult,
    ToolPlanExecutionResult,
    execute_tools_for_request,
)
from app.services.tool_planner import ToolPlan, plan_tools_for_request


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


def yes_no(value: bool) -> str:
    """
    Convert a boolean into a human-readable yes/no value.
    """
    return "yes" if value else "no"


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
    print("slow        Alias for diagnose")
    print("insight     Show a plain-English Lighthouse assessment")
    print("explain     Alias for insight")
    print("plan <text> Show a safe Lighthouse tool plan")
    print("runplan <text> Plan and execute safe read-only tools")
    print("journal     Show recent Lighthouse action journal entries")
    print("ask         Ask Lighthouse a plain-English question")
    print("model       Show local Ollama model status")
    print("model test  Send a tiny safe test prompt to the local Ollama model")
    print("events      Show recent crash-relevant Windows events")
    print("crash       Alias for events")
    print("save        Save a timestamped local JSON snapshot")
    print("history     List saved local snapshots")
    print("last        Show the most recent saved snapshot summary")
    print("help        Show this command list")
    print("quit        Exit Lighthouse")
    print("-" * 52)
    print("\nYou can also ask in plain English, for example:")
    print("- is my laptop healthy")
    print("- why is my laptop slow")
    print("- did my laptop crash recently")
    print("- save this report")
    print("- show my saved snapshots")
    print("- show me the last report")
    print("- ask is anything wrong with my laptop?")
    print("- ask why does my laptop feel slow?")
    print("- plan please optimize RAM usage")
    print("- plan delete files to make space")
    print("- plan close Chrome because it is using memory")
    print("- runplan please optimize RAM usage")
    print("- runplan delete files to make space")
    print("- runplan close Chrome because it is using memory")
    print("- journal")


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


def print_save_report() -> None:
    """
    Save a Lighthouse snapshot and print the result.
    """
    result = save_snapshot()

    print("\nSAVE SNAPSHOT")
    print("=" * 52)

    if result.get("status") != "ok":
        print("Status: error")
        print(result.get("message", "Unable to save snapshot."))
        print("=" * 52)
        return

    print("Status: ok")
    print(f"Generated at: {result.get('generated_at', 'Unknown')}")
    print(f"File: {result.get('filename', 'Unknown')}")
    print(f"Path: {result.get('path', 'Unknown')}")
    print("=" * 52)


def print_history_report() -> None:
    """
    Print saved Lighthouse snapshots.
    """
    result = list_snapshots(limit=10)

    print("\nSNAPSHOT HISTORY")
    print("=" * 52)

    if result.get("status") != "ok":
        print("Status: error")
        print(result.get("message", "Unable to list snapshots."))
        print("=" * 52)
        return

    snapshots = result.get("snapshots", [])

    print(f"Total snapshots: {result.get('snapshot_count', 0)}")

    if not snapshots:
        print("No saved snapshots found. Run 'save' first.")
        print("=" * 52)
        return

    print("\nMost recent snapshots:")
    print("-" * 52)

    for index, snapshot in enumerate(snapshots, start=1):
        print(f"{index}. {snapshot.get('filename', 'Unknown')}")
        print(f"   Modified: {snapshot.get('modified_at', 'Unknown')}")
        print(f"   Size: {snapshot.get('size_kb', 'Unknown')} KB")
        print(f"   Path: {snapshot.get('path', 'Unknown')}")

    print("=" * 52)


def print_last_snapshot_report() -> None:
    """
    Print a summary of the most recent saved Lighthouse snapshot.
    """
    result = get_latest_snapshot()

    print("\nLATEST SNAPSHOT")
    print("=" * 52)

    if result.get("status") != "ok":
        print("Status: error")
        print(result.get("message", "Unable to load latest snapshot."))
        print("=" * 52)
        return

    snapshot = result.get("snapshot", {})
    metadata = snapshot.get("metadata", {})
    telemetry = snapshot.get("telemetry", {})
    event_report = snapshot.get("event_report", {})

    cpu = telemetry.get("cpu", {})
    memory = telemetry.get("memory", {})
    disk = telemetry.get("disk", {})
    processes = telemetry.get("processes", {})

    severity_summary = event_report.get("severity_summary", {})

    print("Status: ok")
    print(f"File: {result.get('filename', 'Unknown')}")
    print(f"Generated at: {metadata.get('generated_at', 'Unknown')}")
    print()
    print("Telemetry summary:")
    print(f"- CPU usage:    {cpu.get('usage_percent', 'Unknown')}%")
    print(f"- Memory usage: {memory.get('usage_percent', 'Unknown')}%")
    print(f"- Disk usage:   {disk.get('usage_percent', 'Unknown')}%")

    process_list = processes.get("processes", [])

    if process_list:
        top = process_list[0]
        print(
            "- Highest memory process: "
            f"{top.get('name', 'Unknown')} "
            f"using {top.get('memory_mb', 'Unknown')} MB"
        )

    print()
    print("Event summary:")
    print(f"- Critical events: {severity_summary.get('critical', 0)}")
    print(f"- Warning events:  {severity_summary.get('warning', 0)}")
    print(f"- Context events:  {severity_summary.get('context', 0)}")

    print("=" * 52)


def print_insight_report() -> None:
    """
    Print a plain-English Lighthouse assessment.
    """
    telemetry = collect_telemetry()
    event_report = get_recent_system_events(limit=100)

    insight = build_system_insight(
        telemetry=telemetry,
        event_report=event_report,
    )

    print(format_insight_report(insight))


def print_ask_report(question: str) -> None:
    """
    Ask Lighthouse a plain-English question.
    """
    result = ask_lighthouse(question)

    if result.get("status") != "ok":
        print("\nLIGHTHOUSE ASSISTANT")
        print("=" * 52)
        print("Status: error")
        print(result.get("message", "Unable to answer question."))
        print("=" * 52)
        return

    print(result.get("answer", "No answer returned."))


def print_model_report() -> None:
    """
    Print local Ollama model status.
    """
    result = get_ollama_status()

    print("\nLIGHTHOUSE MODEL STATUS")
    print("=" * 52)
    print(f"Status: {result.get('status', 'unknown')}")
    print(f"Ollama enabled: {result.get('ollama_enabled', False)}")
    print(f"Ollama server available: {result.get('server_available', False)}")
    print(f"Configured model: {result.get('configured_model', 'Unknown')}")
    print(
        "Configured model installed: "
        f"{result.get('configured_model_installed', False)}"
    )

    message = result.get("message")

    if message:
        print()
        print(f"Message: {message}")

    installed_models = result.get("installed_models", [])

    print()
    print("Installed models:")

    if installed_models:
        for model in installed_models:
            print(f"- {model}")
    else:
        print("- No installed models detected.")

    print()
    print("AI mode guidance:")

    if not result.get("ollama_enabled", False):
        print("- Lighthouse is currently using the safe deterministic fallback.")
        print("- Set LIGHTHOUSE_USE_OLLAMA=1 to enable local Ollama attempts.")
    elif not result.get("server_available", False):
        print("- Ollama is enabled, but the local Ollama server is not reachable.")
    elif not result.get("configured_model_installed", False):
        print("- Ollama is reachable, but the configured model is not installed.")
    else:
        print("- Ollama is enabled and the configured model appears to be installed.")

    print("=" * 52)


def print_model_test_report() -> None:
    """
    Test the configured local Ollama model with a tiny safe prompt.
    """
    result = run_ollama_model_test()

    print("\nLIGHTHOUSE MODEL TEST")
    print("=" * 52)
    print(f"Status: {result.get('status', 'unknown')}")
    print(f"Configured model: {result.get('model', 'Unknown')}")

    if result.get("status") == "ok":
        print()
        print("Response:")
        print(result.get("response", "No response returned."))
    else:
        print()
        print("Message:")
        print(result.get("message", "Model test failed."))

    print("=" * 52)


def print_tool_list(title: str, tools: tuple[Any, ...]) -> None:
    """
    Print a list of planned tool records.
    """
    print()
    print(f"{title}:")
    print("-" * 52)

    if not tools:
        print("- none")
        return

    for tool in tools:
        print(f"- {tool.name}")
        print(f"  Reason: {tool.reason}")
        print(f"  Category: {tool.category}")
        print(f"  Risk level: {tool.risk_level}")
        print(f"  Read-only: {yes_no(tool.read_only)}")
        print(f"  Implemented: {yes_no(tool.implemented)}")
        print(f"  Automatic use allowed: {yes_no(tool.allow_automatic_use)}")
        print(f"  Requires confirmation: {yes_no(tool.requires_confirmation)}")
        print(f"  Requires target: {yes_no(tool.requires_target)}")
        print(f"  Logs action: {yes_no(tool.logs_action)}")


def print_tool_plan_report(user_request: str) -> None:
    """
    Print a Lighthouse tool plan for a user request.

    This does not execute tools.
    It only shows what the planner would select or block.
    """
    cleaned_request = user_request.strip()

    print("\nLIGHTHOUSE TOOL PLAN")
    print("=" * 52)

    if not cleaned_request:
        print("Status: needs_clarification")
        print("Message: Please provide a request after the plan command.")
        print()
        print("Examples:")
        print("- plan please optimize RAM usage")
        print("- plan delete files to make space")
        print("- plan close Chrome because it is using memory")
        print("=" * 52)
        return

    plan: ToolPlan = plan_tools_for_request(cleaned_request)

    print(f"Request: {plan.user_request}")
    print(f"Status: {plan.status}")
    print(f"Intent: {plan.intent}")
    print(f"Requires confirmation: {yes_no(plan.requires_confirmation)}")
    print()
    print(f"Message: {plan.message}")

    print_tool_list("Planned tools", plan.tools)
    print_tool_list("Blocked tools", plan.blocked_tools)
    print_tool_list("Safe alternatives", plan.safe_alternatives)

    print("=" * 52)


def print_execution_data_summary(tool_name: str, data: dict[str, Any] | None) -> None:
    """
    Print a compact summary of read-only tool execution data.

    This avoids dumping large raw telemetry dictionaries into the CLI.
    """
    if not data:
        print("  Data: none")
        return

    if tool_name == "inspect_cpu_usage":
        cpu = data.get("cpu", {})
        print(f"  CPU usage: {cpu.get('usage_percent', 'Unknown')}%")
        print(f"  CPU status: {cpu.get('status', 'unknown')}")
        return

    if tool_name == "inspect_memory_usage":
        memory = data.get("memory", {})
        print(f"  Memory usage: {memory.get('usage_percent', 'Unknown')}%")
        print(f"  Used: {memory.get('used_gb', 'Unknown')} GB")
        print(f"  Available: {memory.get('available_gb', 'Unknown')} GB")
        return

    if tool_name == "inspect_disk_usage":
        disk = data.get("disk", {})
        print(f"  Disk usage: {disk.get('usage_percent', 'Unknown')}%")
        print(f"  Used: {disk.get('used_gb', 'Unknown')} GB")
        print(f"  Free: {disk.get('free_gb', 'Unknown')} GB")
        return

    if tool_name == "list_top_processes":
        processes = data.get("processes", {})
        process_list = processes.get("processes", [])

        if not process_list:
            print("  No process data available.")
            return

        top = process_list[0]
        print("  Top memory process:")
        print(
            f"  - {top.get('name', 'Unknown')} "
            f"using {top.get('memory_mb', 'Unknown')} MB"
        )
        return

    if tool_name == "read_recent_events":
        event_report = data.get("event_report", {})
        severity_summary = event_report.get("severity_summary", {})

        print(f"  Event status: {event_report.get('status', 'unknown')}")
        print(f"  Critical events: {severity_summary.get('critical', 0)}")
        print(f"  Warning events: {severity_summary.get('warning', 0)}")
        print(f"  Context events: {severity_summary.get('context', 0)}")
        return

    if tool_name == "show_health_summary":
        insight = data.get("insight", {})
        print(f"  Overall status: {insight.get('overall_status', 'UNKNOWN')}")
        print(f"  Summary: {insight.get('summary', 'No summary available.')}")
        return

    if tool_name == "collect_snapshot":
        insight = data.get("insight", {})
        telemetry = data.get("telemetry", {})
        cpu = telemetry.get("cpu", {})
        memory = telemetry.get("memory", {})
        disk = telemetry.get("disk", {})

        print(f"  Overall status: {insight.get('overall_status', 'UNKNOWN')}")
        print(f"  CPU usage: {cpu.get('usage_percent', 'Unknown')}%")
        print(f"  Memory usage: {memory.get('usage_percent', 'Unknown')}%")
        print(f"  Disk usage: {disk.get('usage_percent', 'Unknown')}%")
        return

    print(f"  Data keys: {', '.join(sorted(data.keys()))}")


def print_tool_execution_results(
    title: str,
    results: tuple[ToolExecutionResult, ...],
) -> None:
    """
    Print tool execution results.
    """
    print()
    print(f"{title}:")
    print("-" * 52)

    if not results:
        print("- none")
        return

    for result in results:
        print(f"- {result.tool_name}")
        print(f"  Status: {result.status}")
        print(f"  Message: {result.message}")

        if result.status == "executed":
            print_execution_data_summary(result.tool_name, result.data)
        else:
            reason = result.safety_summary.get("reason")

            if reason:
                print(f"  Safety reason: {reason}")


def print_confirmation_previews(result: ToolPlanExecutionResult) -> None:
    """
    Print confirmation-gate previews for confirmation-required plans.

    This is only a preview. It does not accept confirmation input and does not
    execute OS-changing tools.
    """
    if result.plan_status != "needs_confirmation":
        return

    print()
    print("Confirmation gate preview:")
    print("-" * 52)
    print(
        "This is a preview only. Lighthouse will not execute "
        "confirmation-gated tools from runplan."
    )

    if not result.refused_tools:
        print("- No refused confirmation-gated tools were returned.")
        return

    for refused_tool in result.refused_tools:
        request = build_confirmation_request(refused_tool.tool_name)
        print(format_confirmation_request(request))


def print_runplan_report(user_request: str) -> None:
    """
    Plan a request and execute only safe read-only tools.

    This never executes blocked tools, confirmation-required tools,
    unimplemented tools, or OS-changing tools.
    """
    cleaned_request = user_request.strip()

    print("\nLIGHTHOUSE RUN PLAN")
    print("=" * 52)

    if not cleaned_request:
        print("Status: needs_clarification")
        print("Message: Please provide a request after the runplan command.")
        print()
        print("Examples:")
        print("- runplan please optimize RAM usage")
        print("- runplan delete files to make space")
        print("- runplan close Chrome because it is using memory")
        print("=" * 52)
        return

    result: ToolPlanExecutionResult = execute_tools_for_request(cleaned_request)
    journal_result = record_plan_execution(result)

    print(f"Request: {result.user_request}")
    print(f"Execution status: {result.status}")
    print(f"Plan status: {result.plan_status}")
    print(f"Intent: {result.intent}")
    print()
    print(f"Message: {result.message}")

    print_tool_execution_results("Executed tools", result.executed_tools)
    print_tool_execution_results("Refused tools", result.refused_tools)

    print()
    print("Blocked tools:")
    print("-" * 52)

    if result.blocked_tools:
        for tool_name in result.blocked_tools:
            print(f"- {tool_name}")
    else:
        print("- none")

    print()
    print("Safe alternatives:")
    print("-" * 52)

    if result.safe_alternatives:
        for tool_name in result.safe_alternatives:
            print(f"- {tool_name}")
    else:
        print("- none")

    print_confirmation_previews(result)

    print()
    print("Journal:")
    print("-" * 52)
    print(f"Status: {journal_result.status}")
    print(f"Message: {journal_result.message}")
    print(f"Path: {journal_result.path}")

    print("=" * 52)


def print_journal_report(limit: int = 10) -> None:
    """
    Print recent Lighthouse action journal entries.
    """
    read_result = read_journal_entries(limit=limit)

    print(format_journal_report(read_result))


def run_canonical_command(command: str) -> str:
    """
    Run a known Lighthouse command.

    Returns:
        handled: command was handled and the loop should continue
        exit: command was handled and the loop should exit
        unknown: command was not recognized
    """
    cleaned_command = command.strip()
    normalized_command = cleaned_command.lower()

    if normalized_command in {"quit", "exit", "q"}:
        print("Exiting Lighthouse.")
        return "exit"

    if normalized_command in {"help", "h", "?"}:
        print_help()
        return "handled"

    if normalized_command == "plan":
        print_tool_plan_report("")
        return "handled"

    if normalized_command.startswith("plan "):
        plan_request = cleaned_command[5:].strip()
        print_tool_plan_report(plan_request)
        return "handled"

    if normalized_command == "runplan":
        print_runplan_report("")
        return "handled"

    if normalized_command.startswith("runplan "):
        runplan_request = cleaned_command[8:].strip()
        print_runplan_report(runplan_request)
        return "handled"

    if normalized_command in {"journal", "action journal", "audit", "audit log"}:
        print_journal_report()
        return "handled"

    if normalized_command in {"snapshot", "report"}:
        telemetry = collect_telemetry()
        print_console_report(telemetry)
        return "handled"

    if normalized_command == "health":
        telemetry = collect_telemetry()
        print_health_report(telemetry)
        return "handled"

    if normalized_command == "cpu":
        telemetry = collect_telemetry()
        print_cpu_report(telemetry)
        return "handled"

    if normalized_command == "memory":
        telemetry = collect_telemetry()
        print_memory_report(telemetry)
        return "handled"

    if normalized_command == "disk":
        telemetry = collect_telemetry()
        print_disk_report(telemetry)
        return "handled"

    if normalized_command in {"processes", "process"}:
        telemetry = collect_telemetry()
        print_process_report(telemetry)
        return "handled"

    if normalized_command in {"diagnose", "slow"}:
        telemetry = collect_telemetry()
        print_diagnosis(telemetry)
        return "handled"

    if normalized_command in {"insight", "explain", "assessment", "assistant"}:
        print_insight_report()
        return "handled"

    if normalized_command in {"model test", "models test", "llm test", "ollama test"}:
        print_model_test_report()
        return "handled"

    if normalized_command in {"model", "models", "llm", "ollama"}:
        print_model_report()
        return "handled"

    if normalized_command in {"events", "event", "crash", "crashes"}:
        print_events_report()
        return "handled"

    if normalized_command in {"save", "save snapshot", "save report"}:
        print_save_report()
        return "handled"

    if normalized_command in {"history", "snapshots"}:
        print_history_report()
        return "handled"

    if normalized_command in {"last", "latest", "last snapshot"}:
        print_last_snapshot_report()
        return "handled"

    return "unknown"


def command_loop() -> None:
    """
    Start the Lighthouse interactive shell.
    """
    print("\nLighthouse CLI")
    print("Read-only system telemetry assistant.")
    print("Type 'help' to see available commands.")
    print("Type 'quit' to exit.")

    while True:
        user_input = input("\nlighthouse> ").strip()
        command = user_input.lower()

        if not command:
            continue

        if command == "ask":
            question = input("Ask Lighthouse> ").strip()
            print_ask_report(question)
            continue

        if command.startswith("ask "):
            question = user_input[4:].strip()
            print_ask_report(question)
            continue

        result = run_canonical_command(user_input)

        if result == "exit":
            break

        if result == "handled":
            continue

        assistant_intent = classify_user_intent(user_input)

        if assistant_intent.status == "ok" and assistant_intent.canonical_command:
            print(
                "\nAssistant interpreted your request as: "
                f"{assistant_intent.canonical_command}"
            )
            print(f"Reason: {assistant_intent.reason}")

            result = run_canonical_command(assistant_intent.canonical_command)

            if result == "exit":
                break

            if result == "handled":
                continue

        print(f"Unknown command: {user_input}")
        print("Type 'help' to see available commands.")


if __name__ == "__main__":
    command_loop()