"""
V1 conversational engine turn for Lighthouse.

This module builds one complete preview-only conversational turn:

- deterministic Operator interpretation
- model route proposal through LLM Contract V0
- deterministic route handoff selection
- autorun gate evaluation
- append-only turn journal record

It does not execute tools.
It does not mutate the operating system.
It does not give model output authority.
It does not hand model output directly to talk or talkrun.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.llm_route_engine import (
    LLMRouteCallResult,
    ModelRouteCallable,
    build_llm_route_call,
)
from app.services.operator_conversation import (
    OperatorConversationResult,
    interpret_operator_input,
)
from app.services.operator_routes import validate_route_handoff_for_autorun


CONVERSATIONAL_TURN_SCHEMA_VERSION = "conversation_turn_v0"
CONVERSATIONAL_TURN_STATUS_OK = "ok"
CONVERSATIONAL_TURN_STATUS_NEEDS_CLARIFICATION = "needs_clarification"

DEFAULT_MEMORY_DIR = Path(__file__).resolve().parents[3] / "memory"
CONVERSATIONAL_TURN_JOURNAL_FILENAME = "conversation_turns.jsonl"


@dataclass(frozen=True)
class ConversationalEngineTurnResult:
    """
    Stable preview-only result for one conversational engine turn.
    """

    status: str
    message: str
    user_request: str
    mode: str
    deterministic_result: OperatorConversationResult | None
    llm_route_result: LLMRouteCallResult | None
    selected_route_source: str
    selected_route_handoff: dict[str, Any]
    autorun_gate: Any | None
    turn_journal_result: dict[str, Any] | None
    executed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable conversational turn result.
        """
        return {
            "status": self.status,
            "message": self.message,
            "user_request": self.user_request,
            "mode": self.mode,
            "deterministic_result": (
                self.deterministic_result.to_dict()
                if self.deterministic_result is not None
                else None
            ),
            "llm_route_result": (
                self.llm_route_result.to_dict()
                if self.llm_route_result is not None
                else None
            ),
            "selected_route_source": self.selected_route_source,
            "selected_route_handoff": self.selected_route_handoff,
            "autorun_gate": gate_to_payload(self.autorun_gate),
            "turn_journal_result": self.turn_journal_result,
            "executed": self.executed,
        }


def utc_now_iso() -> str:
    """
    Return an ISO-like UTC timestamp.
    """
    return datetime.now(timezone.utc).isoformat()


def build_turn_id() -> str:
    """
    Build a compact unique id for one conversational turn.
    """
    return f"turn-{uuid4().hex}"


def resolve_memory_dir(memory_dir: str | Path | None = None) -> Path:
    """
    Resolve the memory directory used for conversational turn journals.
    """
    if memory_dir is None:
        return DEFAULT_MEMORY_DIR

    return Path(memory_dir)


def conversational_turn_journal_path(memory_dir: str | Path | None = None) -> Path:
    """
    Return the conversational turn JSONL path.
    """
    return resolve_memory_dir(memory_dir) / CONVERSATIONAL_TURN_JOURNAL_FILENAME


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """
    Append one JSON object to a JSONL file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, sort_keys=True, ensure_ascii=False))
        file.write("\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """
    Read a JSONL file. Malformed rows are skipped rather than breaking review.
    """
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped_line = line.strip()

            if not stripped_line:
                continue

            try:
                parsed = json.loads(stripped_line)
            except json.JSONDecodeError:
                continue

            if isinstance(parsed, dict):
                records.append(parsed)

    return records


def result_to_payload(result: Any) -> dict[str, Any]:
    """
    Convert a result-like object to a dictionary.
    """
    if result is None:
        return {}

    if hasattr(result, "to_dict"):
        payload = result.to_dict()

        if isinstance(payload, dict):
            return payload

    if isinstance(result, dict):
        return dict(result)

    return {}


def gate_to_payload(autorun_gate: Any) -> dict[str, Any] | None:
    """
    Convert an autorun gate result to a dictionary when present.
    """
    if autorun_gate is None:
        return None

    if hasattr(autorun_gate, "to_dict"):
        payload = autorun_gate.to_dict()

        if isinstance(payload, dict):
            return payload

    if isinstance(autorun_gate, dict):
        return dict(autorun_gate)

    return None


def select_route_handoff(
    deterministic_result: OperatorConversationResult,
    llm_route_result: LLMRouteCallResult,
) -> tuple[str, dict[str, Any]]:
    """
    Select the handoff to evaluate for the turn.

    A valid LLM contract handoff is preferred as the proposed route for this
    preview. If the LLM path is disabled or invalid, the deterministic route
    remains the fallback candidate.
    """
    if llm_route_result.validation is not None and llm_route_result.validation.valid:
        handoff = llm_route_result.validation.route_handoff or {}

        if handoff:
            return "llm_contract", dict(handoff)

    deterministic_handoff = deterministic_result.route_handoff or {}

    if deterministic_handoff:
        return "deterministic", dict(deterministic_handoff)

    return "none", {}


def build_conversational_turn_record(
    *,
    user_request: str,
    deterministic_result: OperatorConversationResult,
    llm_route_result: LLMRouteCallResult,
    selected_route_source: str,
    selected_route_handoff: dict[str, Any],
    autorun_gate: Any | None,
) -> dict[str, Any]:
    """
    Build one journal record for a conversational engine turn.
    """
    return {
        "turn_id": build_turn_id(),
        "created_at": utc_now_iso(),
        "schema_version": CONVERSATIONAL_TURN_SCHEMA_VERSION,
        "mode": "conversation_turn_preview",
        "original_input": user_request,
        "normalized_input": user_request.strip(),
        "status": CONVERSATIONAL_TURN_STATUS_OK,
        "deterministic_result": result_to_payload(deterministic_result),
        "llm_route_result": result_to_payload(llm_route_result),
        "selected_route_source": selected_route_source,
        "selected_route_handoff": selected_route_handoff,
        "autorun_gate": gate_to_payload(autorun_gate),
        "safety": {
            "preview_only": True,
            "executed": False,
            "tool_execution": False,
            "model_authority": False,
            "os_mutation": False,
            "talkrun_integration": False,
        },
    }


def record_conversational_engine_turn(
    *,
    user_request: str,
    deterministic_result: OperatorConversationResult,
    llm_route_result: LLMRouteCallResult,
    selected_route_source: str,
    selected_route_handoff: dict[str, Any],
    autorun_gate: Any | None,
    memory_dir: str | Path | None = None,
) -> dict[str, Any]:
    """
    Record one preview-only conversational engine turn.
    """
    try:
        record = build_conversational_turn_record(
            user_request=user_request,
            deterministic_result=deterministic_result,
            llm_route_result=llm_route_result,
            selected_route_source=selected_route_source,
            selected_route_handoff=selected_route_handoff,
            autorun_gate=autorun_gate,
        )
        append_jsonl(conversational_turn_journal_path(memory_dir), record)

        return {
            "status": "ok",
            "message": "Conversational engine turn recorded.",
            "data": {
                "turn_id": record["turn_id"],
                "saved": True,
                "record": record,
            },
            "errors": [],
            "warnings": [],
        }
    except OSError as error:
        return {
            "status": "error",
            "message": "Conversational engine turn could not be recorded.",
            "data": {"turn_id": None, "saved": False},
            "errors": [str(error)],
            "warnings": [],
        }


def build_conversational_engine_turn(
    user_request: str,
    *,
    model_callable: ModelRouteCallable | None = None,
    memory_dir: str | Path | None = None,
) -> ConversationalEngineTurnResult:
    """
    Build one preview-only conversational engine turn.

    The LLM route boundary may be attempted when enabled or injected for tests,
    but the model never executes, authorizes, or bypasses deterministic gates.
    """
    cleaned_request = user_request.strip()

    if not cleaned_request:
        return ConversationalEngineTurnResult(
            status=CONVERSATIONAL_TURN_STATUS_NEEDS_CLARIFICATION,
            message="Please provide a request for the conversational turn.",
            user_request="",
            mode="preview_only",
            deterministic_result=None,
            llm_route_result=None,
            selected_route_source="none",
            selected_route_handoff={},
            autorun_gate=None,
            turn_journal_result=None,
            executed=False,
        )

    deterministic_result = interpret_operator_input(cleaned_request)
    llm_route_result = build_llm_route_call(
        cleaned_request,
        model_callable=model_callable,
    )
    selected_route_source, selected_route_handoff = select_route_handoff(
        deterministic_result=deterministic_result,
        llm_route_result=llm_route_result,
    )
    autorun_gate = (
        validate_route_handoff_for_autorun(selected_route_handoff)
        if selected_route_handoff
        else None
    )
    journal_result = record_conversational_engine_turn(
        user_request=cleaned_request,
        deterministic_result=deterministic_result,
        llm_route_result=llm_route_result,
        selected_route_source=selected_route_source,
        selected_route_handoff=selected_route_handoff,
        autorun_gate=autorun_gate,
        memory_dir=memory_dir,
    )

    return ConversationalEngineTurnResult(
        status=CONVERSATIONAL_TURN_STATUS_OK,
        message="Conversational engine turn completed. No command was executed.",
        user_request=cleaned_request,
        mode="preview_only",
        deterministic_result=deterministic_result,
        llm_route_result=llm_route_result,
        selected_route_source=selected_route_source,
        selected_route_handoff=selected_route_handoff,
        autorun_gate=autorun_gate,
        turn_journal_result=journal_result,
        executed=False,
    )


def read_conversational_engine_turns(
    *,
    limit: int = 10,
    memory_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """
    Read recent conversational engine turn records, newest first.
    """
    if limit <= 0:
        return []

    records = read_jsonl(conversational_turn_journal_path(memory_dir))
    return list(reversed(records))[:limit]


def extract_turn_id(journal_result: dict[str, Any] | None) -> str | None:
    """
    Extract the turn id from a turn journal result.
    """
    if not isinstance(journal_result, dict):
        return None

    data = journal_result.get("data", {})

    if isinstance(data, dict):
        turn_id = data.get("turn_id")

        if isinstance(turn_id, str) and turn_id:
            return turn_id

    return None


def yes_no(value: bool) -> str:
    """
    Convert a boolean into a human-readable yes/no value.
    """
    return "yes" if value else "no"


def format_conversational_engine_turn_report(
    result: ConversationalEngineTurnResult,
) -> str:
    """
    Format one conversational engine turn for the CLI.
    """
    lines = [
        "LIGHTHOUSE CONVERSATIONAL ENGINE TURN",
        "=" * 52,
        "Mode: preview_only",
        "Execution: disabled",
        "Authority: deterministic route registry and autorun gate",
        "",
        f"Status: {result.status}",
        f"Message: {result.message}",
    ]

    if not result.user_request:
        lines.extend(
            [
                "",
                "Examples:",
                "- turn my laptop feels slow",
                "- turn why is chrome eating memory",
                "=" * 52,
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            f"Request: {result.user_request}",
            "",
            "DETERMINISTIC INTERPRETATION",
            "-" * 52,
        ]
    )

    if result.deterministic_result is None:
        lines.append("Status: not_available")
    else:
        lines.extend(
            [
                f"Status: {result.deterministic_result.status}",
                f"Intent: {result.deterministic_result.intent}",
                f"Interpreted request: {result.deterministic_result.interpreted_request}",
                f"Recommended command: {result.deterministic_result.recommended_command}",
            ]
        )

    lines.extend(
        [
            "",
            "MODEL ROUTE BOUNDARY",
            "-" * 52,
        ]
    )

    if result.llm_route_result is None:
        lines.append("Status: not_available")
    else:
        lines.extend(
            [
                f"Status: {result.llm_route_result.status}",
                f"Message: {result.llm_route_result.message}",
                f"Model used: {result.llm_route_result.model_used or 'none'}",
                f"Used model: {yes_no(result.llm_route_result.used_model)}",
            ]
        )

        validation = result.llm_route_result.validation

        if validation is None:
            lines.append("Contract validation: not_available")
        else:
            proposal = validation.normalized_proposal or {}
            lines.extend(
                [
                    f"Contract status: {validation.status}",
                    f"Contract valid: {yes_no(validation.valid)}",
                    f"Proposed intent: {proposal.get('proposed_intent', 'unknown')}",
                    f"Interpreted request: {proposal.get('interpreted_request')}",
                    f"Confidence: {proposal.get('confidence')}",
                ]
            )

    lines.extend(
        [
            "",
            "SELECTED ROUTE",
            "-" * 52,
            f"Source: {result.selected_route_source}",
        ]
    )

    if result.selected_route_handoff:
        lines.extend(
            [
                f"Intent: {result.selected_route_handoff.get('intent')}",
                f"Safety class: {result.selected_route_handoff.get('safety_class')}",
                f"Command family: {result.selected_route_handoff.get('command_family')}",
                f"Recommended command: {result.selected_route_handoff.get('recommended_command')}",
                f"Engine request: {result.selected_route_handoff.get('engine_request')}",
            ]
        )
    else:
        lines.append("Route handoff: none")

    lines.extend(
        [
            "",
            "AUTORUN GATE",
            "-" * 52,
        ]
    )

    if result.autorun_gate is None:
        lines.append("Status: not_available")
    else:
        lines.extend(
            [
                f"Status: {result.autorun_gate.status}",
                f"Allowed: {yes_no(result.autorun_gate.allowed)}",
                f"Reason: {result.autorun_gate.reason}",
            ]
        )

    turn_id = extract_turn_id(result.turn_journal_result)

    lines.extend(
        [
            "",
            "TURN JOURNAL",
            "-" * 52,
            f"Status: {result.turn_journal_result.get('status') if result.turn_journal_result else 'not_recorded'}",
            f"Turn ID: {turn_id or 'none'}",
            "",
            "EXECUTION",
            "-" * 52,
            "No command was executed by this conversational turn.",
            "Model output was not handed to talk or talkrun.",
            "Model output cannot bypass the route registry or autorun gate.",
            "=" * 52,
        ]
    )

    return "\n".join(lines)

def format_conversational_engine_turns_report(
    *,
    limit: int = 10,
    memory_dir: str | Path | None = None,
) -> str:
    """
    Build a plain-text report of recent conversational engine turn records.
    """
    turns = read_conversational_engine_turns(limit=limit, memory_dir=memory_dir)

    lines = [
        "LIGHTHOUSE CONVERSATIONAL ENGINE TURNS",
        "-" * 52,
        f"Shown: {len(turns)}",
    ]

    if not turns:
        lines.append("No conversational engine turns recorded yet.")
        return "\n".join(lines)

    for record in turns:
        deterministic = record.get("deterministic_result", {})
        llm_route = record.get("llm_route_result", {})
        selected_handoff = record.get("selected_route_handoff", {})
        autorun_gate = record.get("autorun_gate", {})
        safety = record.get("safety", {})

        if not isinstance(deterministic, dict):
            deterministic = {}
        if not isinstance(llm_route, dict):
            llm_route = {}
        if not isinstance(selected_handoff, dict):
            selected_handoff = {}
        if not isinstance(autorun_gate, dict):
            autorun_gate = {}
        if not isinstance(safety, dict):
            safety = {}

        lines.append("")
        lines.append(f"turn_id: {record.get('turn_id')}")
        lines.append(f"created_at: {record.get('created_at')}")
        lines.append(f"status: {record.get('status')}")
        lines.append(f"original_input: {record.get('original_input')}")
        lines.append(f"deterministic_intent: {deterministic.get('intent')}")
        lines.append(f"llm_route_status: {llm_route.get('status')}")
        lines.append(f"selected_route_source: {record.get('selected_route_source')}")
        lines.append(f"selected_intent: {selected_handoff.get('intent')}")
        lines.append(
            "recommended_command: "
            f"{selected_handoff.get('recommended_command')}"
        )
        lines.append(f"autorun_gate_status: {autorun_gate.get('status')}")
        lines.append(
            "autorun_gate_allowed: "
            f"{'yes' if autorun_gate.get('allowed') else 'no'}"
        )
        lines.append(f"executed: {'yes' if safety.get('executed') else 'no'}")
        lines.append(
            "preview_only: "
            f"{'yes' if safety.get('preview_only') else 'no'}"
        )

    return "\n".join(lines)
