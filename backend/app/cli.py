"""
Interactive command line interface for Lighthouse.

This turns Lighthouse from a one-shot telemetry report into a small
read-only assistant that can respond to user commands.
"""

from typing import Any

from app.collectors.event_logs import get_recent_system_events
from app.collectors.windows.cim import collect_windows_cim_evidence
from app.services.windows_diagnostic_findings import build_windows_diagnostic_findings
from app.services.windows_evidence_aggregator import collect_windows_evidence
from app.services.windows_evidence_report import format_windows_evidence_report
from app.main import collect_telemetry
from app.reporting.console_report import print_console_report
from app.services.action_journal import (
    format_journal_report,
    read_journal_entries,
)
from app.services.assistant import classify_user_intent
from app.services.confirmation_gate import (
    build_confirmation_request,
    format_confirmation_request,
)
from app.services.confirmation_journal import record_target_confirmation_preview
from app.services.explanation_composer import compose_engine_explanation
from app.services.insights import build_system_insight, format_insight_report
from app.services.operator_interaction_journal import (
    format_feedback_labels_report,
    format_operator_feedback_result,
    format_operator_interactions_report,
    record_operator_feedback,
    record_operator_interaction,
)
from app.services.operator_dataset_export import (
    export_operator_route_dataset,
    format_operator_dataset_export_report,
)
from app.services.llm_preview_dataset_export import (
    export_llm_preview_dataset,
    format_llm_preview_dataset_export_report,
)
from app.services.conversation_turn_dataset_export import (
    export_conversational_turn_dataset,
    format_conversational_turn_dataset_export_report,
    format_conversational_turn_dataset_review_report,
)
from app.services.operator_routes import (
    build_operator_routes_report,
    validate_route_handoff_for_autorun,
)
from app.services.operator_conversation import (
    format_operator_response,
    interpret_operator_input,
)
from app.services.lighthouse_engine import (
    LighthouseEngineResult,
    run_lighthouse_engine,
)
from app.services.llm import ask_lighthouse, get_ollama_status, run_ollama_model_test
from app.services.llm_route_engine import build_llm_route_call
from app.services.llm_preview_journal import (
    format_llm_route_previews_report,
    record_llm_route_preview,
)
from app.services.llm_conversation_preview import (
    build_llm_conversation_preview,
    format_llm_conversation_preview_report,
)
from app.services.conversational_engine_turn import (
    build_conversational_engine_turn,
    format_conversational_engine_turn_report,
    format_conversational_engine_turns_report,
    read_conversational_engine_turns,
)
from app.services.llm_preview_feedback import (
    format_llm_preview_feedback_result,
    format_preview_feedback_labels_report,
    record_llm_preview_feedback,
)
from app.services.conversation_turn_feedback import (
    format_turn_feedback_labels_report,
    format_turn_feedback_report,
    format_turn_feedback_result,
    record_turn_feedback,
)
from app.services.case_memory_candidate import (
    format_case_memory_candidate_preview_report,
    preview_case_memory_candidate,
)
from app.services.snapshot_store import get_latest_snapshot, list_snapshots, save_snapshot
from app.services.target_resolver import (
    TARGET_STATUS_CANDIDATE_FOUND,
    format_target_resolution,
    resolve_target_for_tool,
)
from app.services.tool_executor import ToolExecutionResult
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
    print("runplan <text> Run a request through Lighthouse Engine v1")
    print("talk <text>    Interpret natural input and suggest a safe route")
    print("talkrun <text> Interpret natural input and auto-run safe read-only routes")
    print("routes      Show Operator route registry and policy health")
    print("interactions Show recent Operator interaction traces")
    print("feedback labels Show valid Operator feedback labels")
    print("feedback <trace_id> <label> [note] Save feedback for an interaction")
    print("dataset operator Export Operator route dataset")
    print("dataset llm preview Export LLM preview route dataset")
    print("dataset turns Export conversational turn dataset")
    print("dataset turns review Review exported conversational turn dataset rows")
    print("dataset turns review included Review included dataset rows")
    print("dataset turns review excluded Review excluded dataset rows")
    print("dataset turns review feedback Review feedback-labeled dataset rows")
    print("journal     Show recent Lighthouse action journal entries")
    print("ask         Ask Lighthouse a plain-English question")
    print("model       Show local Ollama model status")
    print("model test  Send a tiny safe test prompt to the local Ollama model")
    print("llm preview <text> Preview a model route proposal through LLM Contract V0")
    print("llm talk <text> Compare deterministic talk with LLM route preview")
    print("turn <text> Build a full conversational engine turn preview")
    print("turns       Show recent conversational engine turn records")
    print("turn feedback labels Show valid conversational turn feedback labels")
    print("turn feedbacks Show recent conversational turn feedback records")
    print("turn feedback <turn_id> <label> [note] Save feedback for a turn")
    print("turn feedback latest <label> [note] Save feedback for the latest turn")
    print("case preview <turn_id> Preview a deterministic case candidate without writing memory")
    print("llm previews Show recent LLM route preview journal entries")
    print("llm preview feedback labels Show valid LLM preview feedback labels")
    print("llm preview feedback <preview_id> <label> [note] Save feedback for an LLM preview")
    print("events      Show recent crash-relevant Windows events")
    print("windows     Show aggregated Windows-native evidence and findings")
    print("cim         Show Windows-native CIM evidence only")
    print("cim         Show Windows-native CIM hardware and OS evidence")
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
    print("- llm preview my laptop feels slow")
    print("- llm talk why is chrome eating memory")
    print("- turn why is my laptop slow")
    print("- turn feedback labels")
    print("- turn feedbacks")
    print("- turn feedback turn-example useful routed correctly")
    print("- turn feedback latest useful routed correctly")
    print("- case preview turn-example")
    print("- llm previews")
    print("- llm preview feedback labels")
    print("- llm preview feedback llmprev-example useful routed correctly")
    print("- plan please optimize RAM usage")
    print("- plan delete files to make space")
    print("- plan close Chrome because it is using memory")
    print("- runplan please optimize RAM usage")
    print("- runplan delete files to make space")
    print("- runplan close Chrome because it is using memory")
    print("- talk my laptop feels slow")
    print("- talk why is chrome eating memory")
    print("- talk close chrome")
    print("- talkrun my laptop feels slow")
    print("- talkrun why is chrome eating memory")
    print("- talkrun close chrome")
    print("- routes")
    print("- interactions")
    print("- feedback labels")
    print("- feedback optrace-example useful routed correctly")
    print("- dataset operator")
    print("- dataset llm preview")
    print("- windows")
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


def print_windows_cim_evidence_report() -> None:
    """
    Collect and print Windows-native CIM-only evidence.
    """
    result = collect_windows_cim_evidence()
    print(format_windows_evidence_report(result))


def print_windows_evidence_report() -> None:
    """
    Collect and print aggregated Windows-native evidence and deterministic findings.
    """
    result = collect_windows_evidence()
    findings_result = build_windows_diagnostic_findings(
        result.get("evidence_items", [])
    )
    print(format_windows_evidence_report(result, findings_result=findings_result))


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


def print_llm_route_preview_report(
    user_request: str,
    model_callable: Any | None = None,
    memory_dir: Any | None = None,
) -> None:
    """
    Preview a model-proposed route through LLM Contract V0.

    This is preview-only:
    - it may call the model boundary
    - it validates model output
    - it does not execute the recommended command
    - it does not hand model output into talk or talkrun
    - it does not mutate the OS
    """
    cleaned_request = user_request.strip()

    print("\nLIGHTHOUSE LLM ROUTE PREVIEW")
    print("=" * 52)
    print("Mode: preview_only")
    print("Execution: disabled")
    print("Authority: deterministic route registry and autorun gate")
    print()

    if not cleaned_request:
        print("Status: needs_clarification")
        print("Message: Please provide a request after llm preview.")
        print()
        print("Examples:")
        print("- llm preview my laptop feels slow")
        print("- llm preview why is chrome eating memory")
        print("=" * 52)
        print("No command was executed by llm preview.")
        return

    result = build_llm_route_call(
        cleaned_request,
        model_callable=model_callable,
    )
    journal_result = record_llm_route_preview(
        user_request=cleaned_request,
        preview_result=result,
        memory_dir=memory_dir,
    )

    print(f"Request: {cleaned_request}")
    print(f"Status: {result.status}")
    print(f"Message: {result.message}")
    print(f"Model used: {result.model_used or 'none'}")
    print(f"Used model: {yes_no(result.used_model)}")

    validation = result.validation

    print()
    print("Contract validation:")
    print("-" * 52)

    if validation is None:
        print("Contract validation: not_available")
    else:
        print(f"Contract status: {validation.status}")
        print(f"Contract valid: {yes_no(validation.valid)}")
        print(f"Contract message: {validation.message}")

        proposal = validation.normalized_proposal or {}

        print()
        print("Normalized proposal:")
        print("-" * 52)
        print(f"Proposed intent: {proposal.get('proposed_intent', 'unknown')}")
        print(f"Interpreted request: {proposal.get('interpreted_request')}")
        print(f"Confidence: {proposal.get('confidence')}")

        handoff = validation.route_handoff or {}

        print()
        print("Deterministic route handoff:")
        print("-" * 52)

        if handoff:
            print(f"Route ready: {yes_no(bool(handoff.get('route_ready')))}")
            print(f"Route known: {yes_no(bool(handoff.get('route_known')))}")
            print(f"Intent: {handoff.get('intent')}")
            print(f"Safety class: {handoff.get('safety_class')}")
            print(f"Command family: {handoff.get('command_family')}")
            print(f"Recommended command: {handoff.get('recommended_command')}")
            print(f"Engine request: {handoff.get('engine_request')}")
            print(f"Autorun allowed: {yes_no(bool(handoff.get('autorun_allowed')))}")
            print(
                "Manual review required: "
                f"{yes_no(bool(handoff.get('manual_review_required')))}"
            )
        else:
            print("- none")

        if validation.errors:
            print()
            print("Contract errors:")
            print("-" * 52)

            for error in validation.errors:
                print(f"- {error}")

        if validation.warnings:
            print()
            print("Contract warnings:")
            print("-" * 52)

            for warning in validation.warnings:
                print(f"- {warning}")

    if result.errors and validation is None:
        print()
        print("Boundary errors:")
        print("-" * 52)

        for error in result.errors:
            print(f"- {error}")

    if result.warnings and validation is None:
        print()
        print("Boundary warnings:")
        print("-" * 52)

        for warning in result.warnings:
            print(f"- {warning}")

    print()
    print("Preview journal:")
    print("-" * 52)
    print(f"Status: {journal_result.get('status')}")
    print(f"Message: {journal_result.get('message')}")

    journal_data = journal_result.get("data", {})

    if isinstance(journal_data, dict):
        print(f"Preview ID: {journal_data.get('preview_id')}")
        print(f"Saved: {yes_no(bool(journal_data.get('saved')))}")

    journal_errors = journal_result.get("errors", [])

    if journal_errors:
        print("Journal errors:")
        for error in journal_errors:
            print(f"- {error}")

    print()
    print("Execution:")
    print("-" * 52)
    print("- No command was executed by llm preview.")
    print("- Model output was not handed to talk or talkrun.")
    print("- Model output cannot bypass the route registry or autorun gate.")
    print("=" * 52)




def print_llm_route_previews_report(
    *,
    limit: int = 10,
    memory_dir: Any | None = None,
) -> None:
    """
    Print recent preview-only LLM route proposal records.
    """
    print(format_llm_route_previews_report(limit=limit, memory_dir=memory_dir))

def print_llm_conversation_preview_report(
    user_request: str,
    model_callable: Any | None = None,
    memory_dir: Any | None = None,
) -> None:
    """
    Print a side-by-side deterministic and LLM route preview.

    This is preview-only. It does not execute any route.
    """
    result = build_llm_conversation_preview(
        user_request,
        model_callable=model_callable,
        memory_dir=memory_dir,
    )
    print(format_llm_conversation_preview_report(result))




def print_conversational_engine_turn_report(
    user_request: str,
    model_callable: Any | None = None,
    memory_dir: Any | None = None,
) -> None:
    """
    Print one preview-only conversational engine turn.

    This builds the deterministic and LLM route boundaries together, evaluates
    the autorun gate, records the turn, and executes nothing.
    """
    result = build_conversational_engine_turn(
        user_request,
        model_callable=model_callable,
        memory_dir=memory_dir,
    )
    print(format_conversational_engine_turn_report(result))


def print_llm_preview_feedback_labels_report() -> None:
    """
    Print allowed LLM preview feedback labels.
    """
    print(format_preview_feedback_labels_report())


def print_llm_preview_feedback_report(
    preview_id: str,
    label: str,
    note: str = "",
) -> None:
    """
    Record and print Operator feedback for an LLM preview id.
    """
    result = record_llm_preview_feedback(
        preview_id=preview_id,
        label=label,
        note=note,
    )
    print(format_llm_preview_feedback_result(result))


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


def print_confirmation_previews(result: Any) -> None:
    """
    Print confirmation previews.

    When called with a LighthouseEngineResult, this prints the engine-produced
    confirmation previews without rebuilding or re-journaling them.

    The fallback path keeps older CLI tests compatible with the earlier
    ToolPlanExecutionResult shape.
    """
    if isinstance(result, LighthouseEngineResult):
        print_engine_confirmation_previews(result)
        return

    print_legacy_confirmation_previews(result)


def print_engine_confirmation_previews(engine_result: LighthouseEngineResult) -> None:
    """
    Print confirmation previews that were already produced by Lighthouse Engine.
    """
    if engine_result.plan_status != "needs_confirmation":
        return

    print()
    print("Confirmation gate preview:")
    print("-" * 52)
    print(
        "This is a preview only. Lighthouse will not execute "
        "confirmation-gated tools from runplan."
    )

    if not engine_result.confirmation_previews:
        print("- No confirmation previews were returned by Lighthouse Engine.")
        return

    for preview in engine_result.confirmation_previews:
        print(format_target_resolution(preview.target_resolution))
        print(format_confirmation_request(preview.confirmation_request))

        print()
        print("Confirmation preview journal:")
        print("-" * 52)

        if preview.journal_result is None:
            print("Status: not_recorded")
            print("Message: No confirmation preview journal result was returned.")
            print("Path: unknown")
        else:
            print(f"Status: {preview.journal_result.status}")
            print(f"Message: {preview.journal_result.message}")
            print(f"Path: {preview.journal_result.path}")


def print_legacy_confirmation_previews(result: Any) -> None:
    """
    Print target-aware confirmation-gate previews for older direct callers.

    This path is kept only so existing tests or callers that pass a
    ToolPlanExecutionResult-like object still work. The live runplan command now
    uses Lighthouse Engine instead.
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
        target_resolution = resolve_target_for_tool(
            tool_name=refused_tool.tool_name,
            user_request=result.user_request,
        )

        print(format_target_resolution(target_resolution))

        target = None

        if (
            target_resolution.status == TARGET_STATUS_CANDIDATE_FOUND
            and target_resolution.target
        ):
            target = target_resolution.target

        confirmation_request = build_confirmation_request(
            tool_name=refused_tool.tool_name,
            target=target,
        )

        print(format_confirmation_request(confirmation_request))

        preview_journal_result = record_target_confirmation_preview(
            user_request=result.user_request,
            tool_name=refused_tool.tool_name,
            target_resolution=target_resolution,
            confirmation_request=confirmation_request,
        )

        print()
        print("Confirmation preview journal:")
        print("-" * 52)
        print(f"Status: {preview_journal_result.status}")
        print(f"Message: {preview_journal_result.message}")
        print(f"Path: {preview_journal_result.path}")


def print_engine_errors(engine_result: LighthouseEngineResult) -> None:
    """
    Print non-fatal engine warnings or errors.
    """
    if not engine_result.errors:
        return

    print()
    print("Engine warnings:")
    print("-" * 52)

    for error in engine_result.errors:
        print(f"- {error}")


def print_memory_context_summary(engine_result: LighthouseEngineResult) -> None:
    """
    Print a compact memory-context summary from Lighthouse Engine.

    This does not print the full memory context block by default.
    The full context is intended for engine/model use and future debug views.
    """
    memory_context = getattr(engine_result, "memory_context", None)

    print()
    print("Memory context:")
    print("-" * 52)

    if memory_context is None:
        print("Status: not_available")
        print("Message: No memory context was returned by Lighthouse Engine.")
        return

    print(f"Status: {memory_context.status}")
    print(f"Enabled: {yes_no(memory_context.enabled)}")
    print(f"Message: {memory_context.message}")

    summary = memory_context.summary

    if summary is None:
        print("Baselines: 0")
        print("Operator preferences: 0")
        print("Relevant cases: 0")
        print("Knowledge entries: 0")
    else:
        print(f"Baselines: {summary.baseline_count}")
        print(f"Operator preferences: {summary.preference_count}")
        print(f"Relevant cases: {summary.case_count}")
        print(f"Knowledge entries: {summary.knowledge_count}")

    if memory_context.warnings:
        print()
        print("Memory warnings:")

        for warning in memory_context.warnings:
            print(f"- {warning}")

    if memory_context.errors:
        print()
        print("Memory errors:")

        for error in memory_context.errors:
            print(f"- {error}")

    if memory_context.context_text.strip() and summary is not None:
        print()
        print("Full memory context: available to engine, hidden in normal CLI output.")


def print_engine_explanation(engine_result: LighthouseEngineResult) -> None:
    """
    Print the deterministic human-facing Lighthouse explanation.

    This does not call the model, execute tools, mutate the OS, or write memory.
    It only formats the already-produced engine result for the Operator.
    """
    explanation = compose_engine_explanation(engine_result)

    print()
    print(explanation.text)


def print_plan_journal_result(engine_result: LighthouseEngineResult) -> None:
    """
    Print the plan-level journal result returned by Lighthouse Engine.
    """
    print()
    print("Journal:")
    print("-" * 52)

    if engine_result.plan_journal_result is None:
        print("Status: not_recorded")
        print("Message: No plan journal result was returned.")
        print("Path: unknown")
        return

    print(f"Status: {engine_result.plan_journal_result.status}")
    print(f"Message: {engine_result.plan_journal_result.message}")
    print(f"Path: {engine_result.plan_journal_result.path}")


def print_runplan_report(user_request: str) -> None:
    """
    Run a request through Lighthouse Engine v1.

    The engine coordinates planning, safe read-only execution, target
    resolution, confirmation preview generation, memory-context summarization,
    and journaling.

    It still does not execute blocked tools, confirmation-required tools,
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

    engine_result = run_lighthouse_engine(cleaned_request)
    execution_result = engine_result.execution_result

    print(f"Request: {engine_result.user_request}")
    print(f"Engine status: {engine_result.status}")
    print(f"Execution status: {engine_result.execution_status}")
    print(f"Plan status: {engine_result.plan_status}")
    print(f"Intent: {engine_result.intent}")
    print()
    print(f"Message: {engine_result.message}")

    print_engine_explanation(engine_result)
    print_engine_errors(engine_result)
    print_memory_context_summary(engine_result)

    if execution_result is None:
        print_tool_execution_results("Executed tools", ())
        print_tool_execution_results("Refused tools", ())

        print()
        print("Blocked tools:")
        print("-" * 52)
        print("- none")

        print()
        print("Safe alternatives:")
        print("-" * 52)
        print("- none")

        print_plan_journal_result(engine_result)

        print("=" * 52)
        return

    print_tool_execution_results("Executed tools", execution_result.executed_tools)
    print_tool_execution_results("Refused tools", execution_result.refused_tools)

    print()
    print("Blocked tools:")
    print("-" * 52)

    if execution_result.blocked_tools:
        for tool_name in execution_result.blocked_tools:
            print(f"- {tool_name}")
    else:
        print("- none")

    print()
    print("Safe alternatives:")
    print("-" * 52)

    if execution_result.safe_alternatives:
        for tool_name in execution_result.safe_alternatives:
            print(f"- {tool_name}")
    else:
        print("- none")

    print_confirmation_previews(engine_result)
    print_plan_journal_result(engine_result)

    print("=" * 52)


def print_operator_conversation_report(user_input: str) -> None:
    """
    Interpret natural Operator input and suggest a safe Lighthouse route.

    This does not execute the recommended command.
    This does not call the model.
    This does not mutate the operating system.
    """
    cleaned_input = user_input.strip()

    print("\nLIGHTHOUSE TALK")
    print("=" * 52)

    result = interpret_operator_input(cleaned_input)

    print(format_operator_response(result))

    journal_result = record_operator_interaction(
        mode="talk",
        result=result,
        autorun_gate=None,
        execution={
            "attempted": False,
            "executed": False,
            "refused": False,
            "engine_request": None,
        },
    )

    print_trace_id_from_journal_result(journal_result)

    print()
    print("Execution:")
    print("- No command was executed by talk.")

    if result.recommended_command:
        print("- Review the recommended command before running it.")
        print(f"- To continue, type: {result.recommended_command}")
    elif result.clarifying_question:
        print("- Answer the clarifying question and try talk again.")

    print("=" * 52)


def print_operator_conversation_run_report(user_input: str) -> None:
    """
    Interpret natural Operator input and auto-run only safe read-only routes.

    This does not call the model.
    This does not mutate the operating system.
    It only hands off to runplan when the conversation result is explicitly
    classified as a safe read-only diagnostic route.
    """
    cleaned_input = user_input.strip()

    print("\nLIGHTHOUSE TALKRUN")
    print("=" * 52)

    result = interpret_operator_input(cleaned_input)

    print(format_operator_response(result))
    print()
    print("Autorun decision:")
    print("-" * 52)

    handoff = result.route_handoff or {}
    gate_result = validate_route_handoff_for_autorun(handoff)
    recommended_command = handoff.get("recommended_command")

    if not gate_result.allowed:
        journal_result = record_operator_interaction(
            mode="talkrun",
            result=result,
            autorun_gate=gate_result,
            execution={
                "attempted": True,
                "executed": False,
                "refused": True,
                "engine_request": None,
            },
        )

        print_trace_id_from_journal_result(journal_result)

        print("Status: refused")
        print(f"Reason: {gate_result.reason}")
        print("No command was executed by talkrun.")

        if gate_result.errors:
            print("Gate errors:")
            for error in gate_result.errors:
                print(f"- {error}")

        if result.recommended_command:
            print()
            print("Manual review route:")
            print(f"- Use talk first, then review: {result.recommended_command}")

        print("=" * 52)
        return

    journal_result = record_operator_interaction(
        mode="talkrun",
        result=result,
        autorun_gate=gate_result,
        execution={
            "attempted": True,
            "executed": True,
            "refused": False,
            "engine_request": gate_result.engine_request,
        },
    )

    print_trace_id_from_journal_result(journal_result)

    print("Status: ok")
    print(f"Reason: {gate_result.reason}")
    print(f"Selected command: {recommended_command}")
    print("- Auto-running read-only route through Operator Autorun Gate.")
    print("=" * 52)

    print_runplan_report(gate_result.engine_request or "")


def print_journal_report(limit: int = 10) -> None:
    """
    Print recent Lighthouse action journal entries.
    """
    read_result = read_journal_entries(limit=limit)

    print(format_journal_report(read_result))



def print_operator_interactions_report(limit: int = 10) -> None:
    """
    Print recent Operator interaction traces.
    """
    print(format_operator_interactions_report(limit=limit))


def print_operator_feedback_labels_report() -> None:
    """
    Print allowed Operator feedback labels.
    """
    print(format_feedback_labels_report())


def print_operator_feedback_report(trace_id: str, label: str, note: str = "") -> None:
    """
    Record and print Operator feedback for a trace id.
    """
    result = record_operator_feedback(trace_id=trace_id, label=label, note=note)
    print(format_operator_feedback_result(result))


def print_turn_feedback_labels_report() -> None:
    """
    Print allowed conversational turn feedback labels.
    """
    print(format_turn_feedback_labels_report())


def print_turn_feedbacks_report(limit: int = 10) -> None:
    """
    Print recent conversational turn feedback records.
    """
    print(format_turn_feedback_report(limit=limit))


def print_turn_feedback_report(turn_id: str, label: str, note: str = "") -> None:
    """
    Record and print feedback for a conversational turn id.
    """
    result = record_turn_feedback(turn_id=turn_id, label=label, note=note)
    print(format_turn_feedback_result(result))


def print_case_preview_report(turn_id: str) -> None:
    """
    Print a read-only deterministic case-memory candidate preview.
    """
    result = preview_case_memory_candidate(turn_id)
    print(format_case_memory_candidate_preview_report(result))


def is_placeholder_turn_id(turn_id: str) -> bool:
    """
    Return true when the Operator entered an example placeholder, not a real id.
    """
    return turn_id.strip().lower() in {"<turn_id>", "turn_id"}


def resolve_latest_conversational_turn_id() -> str | None:
    """
    Return the most recent conversational turn id, if one exists.
    """
    turns = read_conversational_engine_turns(limit=1)

    if not turns:
        return None

    turn_id = turns[0].get("turn_id")

    if isinstance(turn_id, str) and turn_id:
        return turn_id

    return None


def print_turn_feedback_latest_report(label: str, note: str = "") -> None:
    """
    Record and print feedback for the latest conversational turn.
    """
    turn_id = resolve_latest_conversational_turn_id()

    if turn_id is None:
        print("LIGHTHOUSE CONVERSATIONAL TURN FEEDBACK")
        print("-" * 52)
        print("Status: invalid")
        print("Message: No conversational engine turns recorded yet.")
        print("Saved: no")
        print("Run 'turn <request>' first, then try 'turn feedback latest <label> [note]'.")
        return

    print_turn_feedback_report(turn_id, label, note)


def print_trace_id_from_journal_result(journal_result: dict[str, Any]) -> None:
    """
    Print a trace id when a journal write succeeds.
    """
    data = journal_result.get("data", {})

    if isinstance(data, dict) and data.get("trace_id"):
        print(f"Trace ID: {data['trace_id']}")


def print_operator_dataset_export_report() -> None:
    """
    Export and print the Operator route dataset report.
    """
    result = export_operator_route_dataset()
    print(format_operator_dataset_export_report(result))



def print_llm_preview_dataset_export_report() -> None:
    """
    Export and print the LLM preview route dataset report.
    """
    result = export_llm_preview_dataset()
    print(format_llm_preview_dataset_export_report(result))


def print_conversational_turn_dataset_export_report() -> None:
    """
    Export and print the conversational turn dataset report.
    """
    result = export_conversational_turn_dataset()
    print(format_conversational_turn_dataset_export_report(result))


def print_conversational_turn_dataset_review_report(
    limit: int = 10,
    filter_mode: str = "all",
    category: str | None = None,
) -> None:
    """
    Print recent rows from the exported conversational turn dataset.
    """
    report_kwargs: dict[str, Any] = {"limit": limit}

    if filter_mode != "all":
        report_kwargs["filter_mode"] = filter_mode

    if category is not None:
        report_kwargs["category"] = category

    print(format_conversational_turn_dataset_review_report(**report_kwargs))


def print_conversational_engine_turns_report(
    *,
    limit: int = 10,
    memory_dir: Any | None = None,
) -> None:
    """
    Print recent preview-only conversational engine turn records.
    """
    print(
        format_conversational_engine_turns_report(
            limit=limit,
            memory_dir=memory_dir,
        )
    )


def print_operator_routes_report() -> None:
    """
    Print the Operator route registry and policy validation report.
    """
    print(build_operator_routes_report())


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

    if normalized_command == "talk":
        print_operator_conversation_report("")
        return "handled"

    if normalized_command.startswith("talk "):
        talk_request = cleaned_command[5:].strip()
        print_operator_conversation_report(talk_request)
        return "handled"

    if normalized_command == "llm talk":
        print_llm_conversation_preview_report("")
        return "handled"

    if normalized_command.startswith("llm talk "):
        llm_talk_request = cleaned_command[len("llm talk "):].strip()
        print_llm_conversation_preview_report(llm_talk_request)
        return "handled"

    if normalized_command in {"case", "case preview"}:
        print("Usage: case preview <turn_id>")
        return "handled"

    if normalized_command.startswith("case preview "):
        turn_id = cleaned_command[len("case preview "):].strip()

        if not turn_id:
            print("Usage: case preview <turn_id>")
            return "handled"

        print_case_preview_report(turn_id)
        return "handled"

    if normalized_command in {
        "turn feedbacks",
        "turn feedback journal",
        "turn feedback log",
        "conversation turn feedbacks",
        "conversation turn feedback journal",
        "conversational turn feedbacks",
        "conversational turn feedback journal",
    }:
        print_turn_feedbacks_report()
        return "handled"

    if normalized_command in {
        "turn feedback labels",
        "turn feedback-labels",
        "conversation turn feedback labels",
        "conversational turn feedback labels",
    }:
        print_turn_feedback_labels_report()
        return "handled"

    if normalized_command in {
        "turn feedback",
        "conversation turn feedback",
        "conversational turn feedback",
    }:
        print("Usage: turn feedback <turn_id> <label> [note]")
        print("Use 'turn feedback labels' to list valid labels.")
        return "handled"

    if normalized_command in {
        "turn feedback latest",
        "conversation turn feedback latest",
        "conversational turn feedback latest",
    }:
        print("Usage: turn feedback latest <label> [note]")
        print("Use 'turn feedback labels' to list valid labels.")
        return "handled"

    if normalized_command.startswith("turn feedback latest "):
        feedback_text = cleaned_command[len("turn feedback latest "):].strip()
        parts = feedback_text.split(maxsplit=1)

        if not parts:
            print("Usage: turn feedback latest <label> [note]")
            print("Use 'turn feedback labels' to list valid labels.")
            return "handled"

        label = parts[0]
        note = parts[1] if len(parts) > 1 else ""

        print_turn_feedback_latest_report(label, note)
        return "handled"

    if normalized_command.startswith("conversation turn feedback latest "):
        feedback_text = cleaned_command[len("conversation turn feedback latest "):].strip()
        parts = feedback_text.split(maxsplit=1)

        if not parts:
            print("Usage: turn feedback latest <label> [note]")
            print("Use 'turn feedback labels' to list valid labels.")
            return "handled"

        label = parts[0]
        note = parts[1] if len(parts) > 1 else ""

        print_turn_feedback_latest_report(label, note)
        return "handled"

    if normalized_command.startswith("conversational turn feedback latest "):
        feedback_text = cleaned_command[
            len("conversational turn feedback latest "):
        ].strip()
        parts = feedback_text.split(maxsplit=1)

        if not parts:
            print("Usage: turn feedback latest <label> [note]")
            print("Use 'turn feedback labels' to list valid labels.")
            return "handled"

        label = parts[0]
        note = parts[1] if len(parts) > 1 else ""

        print_turn_feedback_latest_report(label, note)
        return "handled"

    if normalized_command.startswith("turn feedback "):
        feedback_text = cleaned_command[len("turn feedback "):].strip()
        parts = feedback_text.split(maxsplit=2)

        if len(parts) < 2:
            print("Usage: turn feedback <turn_id> <label> [note]")
            print("Use 'turn feedback labels' to list valid labels.")
            return "handled"

        turn_id = parts[0]
        label = parts[1]
        note = parts[2] if len(parts) > 2 else ""

        if is_placeholder_turn_id(turn_id):
            print("Usage: turn feedback <turn_id> <label> [note]")
            print("Do not include angle brackets. Use a real turn id from 'turns'.")
            print("Or use: turn feedback latest <label> [note]")
            return "handled"

        print_turn_feedback_report(turn_id, label, note)
        return "handled"

    if normalized_command.startswith("conversation turn feedback "):
        feedback_text = cleaned_command[len("conversation turn feedback "):].strip()
        parts = feedback_text.split(maxsplit=2)

        if len(parts) < 2:
            print("Usage: conversation turn feedback <turn_id> <label> [note]")
            print("Use 'turn feedback labels' to list valid labels.")
            return "handled"

        turn_id = parts[0]
        label = parts[1]
        note = parts[2] if len(parts) > 2 else ""

        print_turn_feedback_report(turn_id, label, note)
        return "handled"

    if normalized_command.startswith("conversational turn feedback "):
        feedback_text = cleaned_command[len("conversational turn feedback "):].strip()
        parts = feedback_text.split(maxsplit=2)

        if len(parts) < 2:
            print("Usage: conversational turn feedback <turn_id> <label> [note]")
            print("Use 'turn feedback labels' to list valid labels.")
            return "handled"

        turn_id = parts[0]
        label = parts[1]
        note = parts[2] if len(parts) > 2 else ""

        print_turn_feedback_report(turn_id, label, note)
        return "handled"

    if normalized_command == "turn":
        print_conversational_engine_turn_report("")
        return "handled"

    if normalized_command.startswith("turn "):
        turn_request = cleaned_command[5:].strip()
        print_conversational_engine_turn_report(turn_request)
        return "handled"

    if normalized_command == "engine turn":
        print_conversational_engine_turn_report("")
        return "handled"

    if normalized_command.startswith("engine turn "):
        turn_request = cleaned_command[len("engine turn "):].strip()
        print_conversational_engine_turn_report(turn_request)
        return "handled"

    if normalized_command in {"llm previews", "llm preview journal", "llm route previews"}:
        print_llm_route_previews_report()
        return "handled"

    if normalized_command in {
        "turns",
        "conversation turns",
        "conversational turns",
        "engine turns",
        "turn journal",
    }:
        print_conversational_engine_turns_report()
        return "handled"

    if normalized_command in {
        "dataset llm preview",
        "llm preview dataset",
        "export llm preview dataset",
        "dataset export llm preview",
    }:
        print_llm_preview_dataset_export_report()
        return "handled"

    if normalized_command in {
        "dataset turns review",
        "dataset turn review",
        "dataset turns rows",
        "dataset turn rows",
        "conversation turn dataset review",
        "conversational turn dataset review",
    }:
        print_conversational_turn_dataset_review_report()
        return "handled"

    dataset_review_filter_commands = {
        "dataset turns review included": "included",
        "dataset turns rows included": "included",
        "dataset turns review excluded": "excluded",
        "dataset turns rows excluded": "excluded",
        "dataset turns review feedback": "feedback",
        "dataset turns rows feedback": "feedback",
        "dataset turns review corrections": "corrections",
        "dataset turns rows corrections": "corrections",
        "dataset turns review review-needed": "review_needed",
        "dataset turns review review_needed": "review_needed",
        "dataset turns rows review-needed": "review_needed",
        "dataset turns rows review_needed": "review_needed",
    }

    if normalized_command in dataset_review_filter_commands:
        print_conversational_turn_dataset_review_report(
            filter_mode=dataset_review_filter_commands[normalized_command],
        )
        return "handled"

    if normalized_command in {
        "dataset turns review category",
        "dataset turns rows category",
    }:
        print("Usage: dataset turns review category <category>")
        return "handled"

    if normalized_command.startswith("dataset turns review category "):
        category = cleaned_command[len("dataset turns review category "):].strip()
        print_conversational_turn_dataset_review_report(
            filter_mode="category",
            category=category,
        )
        return "handled"

    if normalized_command.startswith("dataset turns rows category "):
        category = cleaned_command[len("dataset turns rows category "):].strip()
        print_conversational_turn_dataset_review_report(
            filter_mode="category",
            category=category,
        )
        return "handled"

    if normalized_command.startswith("dataset turns review "):
        limit_text = cleaned_command[len("dataset turns review "):].strip()

        try:
            limit = int(limit_text)
        except ValueError:
            print("Usage: dataset turns review <limit>")
            return "handled"

        print_conversational_turn_dataset_review_report(limit=limit)
        return "handled"

    if normalized_command.startswith("dataset turns rows "):
        limit_text = cleaned_command[len("dataset turns rows "):].strip()

        try:
            limit = int(limit_text)
        except ValueError:
            print("Usage: dataset turns rows <limit>")
            return "handled"

        print_conversational_turn_dataset_review_report(limit=limit)
        return "handled"

    if normalized_command in {
        "dataset turns",
        "dataset turn",
        "dataset conversation turns",
        "dataset conversational turns",
        "conversation turn dataset",
        "conversational turn dataset",
        "export conversation turn dataset",
        "dataset export conversation turns",
    }:
        print_conversational_turn_dataset_export_report()
        return "handled"

    if normalized_command in {
        "llm preview feedback labels",
        "llm preview feedback-labels",
        "llm route preview feedback labels",
    }:
        print_llm_preview_feedback_labels_report()
        return "handled"

    if normalized_command in {"llm preview feedback", "llm route preview feedback"}:
        print("Usage: llm preview feedback <preview_id> <label> [note]")
        print("Use 'llm preview feedback labels' to list valid labels.")
        return "handled"

    if normalized_command.startswith("llm preview feedback "):
        feedback_text = cleaned_command[len("llm preview feedback "):].strip()
        parts = feedback_text.split(maxsplit=2)

        if len(parts) < 2:
            print("Usage: llm preview feedback <preview_id> <label> [note]")
            print("Use 'llm preview feedback labels' to list valid labels.")
            return "handled"

        preview_id = parts[0]
        label = parts[1]
        note = parts[2] if len(parts) > 2 else ""

        print_llm_preview_feedback_report(preview_id, label, note)
        return "handled"

    if normalized_command == "llm preview":
        print_llm_route_preview_report("")
        return "handled"

    if normalized_command.startswith("llm preview "):
        llm_preview_request = cleaned_command[len("llm preview "):].strip()
        print_llm_route_preview_report(llm_preview_request)
        return "handled"

    if normalized_command == "talkrun":
        print_operator_conversation_run_report("")
        return "handled"

    if normalized_command.startswith("talkrun "):
        talkrun_request = cleaned_command[8:].strip()
        print_operator_conversation_run_report(talkrun_request)
        return "handled"

    if normalized_command in {"routes", "route", "operator routes", "route policy"}:
        print_operator_routes_report()
        return "handled"

    if normalized_command in {
        "dataset operator",
        "operator dataset",
        "export operator dataset",
        "dataset export operator",
    }:
        print_operator_dataset_export_report()
        return "handled"

    if normalized_command in {"dataset", "datasets", "export dataset"}:
        print("Usage: dataset operator | dataset llm preview | dataset turns")
        return "handled"

    if normalized_command in {"interactions", "interaction", "operator interactions"}:
        print_operator_interactions_report()
        return "handled"

    if normalized_command in {"feedback labels", "feedback-labels", "operator feedback labels"}:
        print_operator_feedback_labels_report()
        return "handled"

    if normalized_command in {"feedback", "operator feedback"}:
        print("Usage: feedback <trace_id> <label> [note]")
        print("Use 'feedback labels' to list valid labels.")
        return "handled"

    if normalized_command.startswith("feedback "):
        feedback_text = cleaned_command[len("feedback "):].strip()
        parts = feedback_text.split(maxsplit=2)

        if len(parts) < 2:
            print("Usage: feedback <trace_id> <label> [note]")
            print("Use 'feedback labels' to list valid labels.")
            return "handled"

        trace_id = parts[0]
        label = parts[1]
        note = parts[2] if len(parts) > 2 else ""

        print_operator_feedback_report(trace_id, label, note)
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

    if normalized_command in {"windows", "windows evidence"}:
        print_windows_evidence_report()
        return "handled"

    if normalized_command in {"cim", "cim evidence"}:
        print_windows_cim_evidence_report()
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
    print("minds_Refuge")

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
