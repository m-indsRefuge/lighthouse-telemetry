"""
V1 contract shape freeze tests.

These tests intentionally lock the serializable shapes that now behave as
internal contracts between the deterministic engine, route registry, tool
execution layer, memory context, and LLM preview boundary.

If one of these assertions fails, treat it as a contract-change review,
not as a casual refactor failure.
"""

import sys
from dataclasses import fields
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"

if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.case_memory_candidate import (
    CASE_MEMORY_CANDIDATE_SCHEMA_VERSION,
    CaseMemoryCandidate,
    CaseMemoryCandidateValidation,
)
from app.services.case_memory_promotion import CaseMemoryPromotionResult
from app.services.engine_memory_context import EngineMemoryContext
from app.services.lighthouse_engine import LighthouseEngineResult
from app.services.llm_contract import LLMContractValidationResult
from app.services.llm_conversation_preview import LLMConversationPreviewResult
from app.services.llm_route_engine import LLMRouteCallResult
from app.services.operator_routes import OperatorRouteHandoff
from app.services.tool_executor import ToolExecutionResult, ToolPlanExecutionResult
from app.services.tool_planner import PlannedTool, ToolPlan


def assert_keys_exact(actual: dict, expected: list[str]) -> None:
    assert list(actual.keys()) == expected


def sample_planned_tool() -> PlannedTool:
    return PlannedTool(
        name="system_snapshot",
        reason="Read-only diagnostic evidence.",
        category="read_only_diagnostic",
        risk_level=0,
        read_only=True,
        implemented=True,
        requires_confirmation=False,
        requires_target=False,
        allow_automatic_use=True,
        logs_action=False,
    )


def sample_tool_execution_result() -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name="system_snapshot",
        status="executed",
        message="System snapshot collected.",
        data={"ok": True},
        safety_summary={
            "name": "system_snapshot",
            "risk_level": 0,
            "read_only": True,
            "implemented": True,
            "requires_confirmation": False,
            "requires_target": False,
            "allow_automatic_use": True,
        },
    )


def sample_llm_contract_validation() -> LLMContractValidationResult:
    return LLMContractValidationResult(
        status="ok",
        valid=True,
        message="LLM route proposal passed contract validation.",
        normalized_proposal={
            "schema_version": "llm_contract_v0",
            "proposed_intent": "performance_diagnostic",
            "interpreted_request": "why is my laptop slow",
            "confidence": 0.8,
            "reasoning_summary": "The user asks about slowness.",
            "safety_notes": ["Read-only route only."],
        },
        route_handoff={
            "route_ready": True,
            "route_known": True,
            "intent": "performance_diagnostic",
            "safety_class": "read_only_diagnostic",
            "command_family": "runplan",
            "recommended_command": "runplan why is my laptop slow",
            "engine_request": "why is my laptop slow",
            "autorun_allowed": True,
            "manual_review_required": False,
            "refusal_reason": "",
            "errors": [],
        },
        errors=(),
        warnings=(),
    )


def sample_llm_route_call() -> LLMRouteCallResult:
    return LLMRouteCallResult(
        status="ok",
        message="LLM route proposal passed contract validation.",
        model_used="injected_model",
        prompt="prompt",
        raw_model_output='{"schema_version": "llm_contract_v0"}',
        validation=sample_llm_contract_validation(),
        used_model=True,
        errors=(),
        warnings=(),
    )


def sample_engine_memory_context() -> EngineMemoryContext:
    return EngineMemoryContext(
        status="disabled",
        message="Engine memory context is disabled.",
        enabled=False,
        user_request="why is my laptop slow",
        context_text="",
        summary=None,
        warnings=(),
        errors=(),
    )


def sample_case_memory_candidate() -> CaseMemoryCandidate:
    return CaseMemoryCandidate(
        schema_version=CASE_MEMORY_CANDIDATE_SCHEMA_VERSION,
        candidate_id="case_candidate_example",
        source_turn_id="turn-example",
        source_turn_created_at="2026-08-13T08:00:00+00:00",
        provenance={
            "turn_journal": {"turn_id": "turn-example"},
            "operator_feedback": {"present": False, "record": None},
            "route": {"selected_source": "deterministic"},
            "autorun_gate": {"allowed": True},
            "turn_safety_envelope": {"preview_only": True},
            "dataset_classification": {"category": "safe_preview_turn"},
            "model_proposal": {
                "present": False,
                "role": "proposal_only",
                "authority": False,
                "record": None,
            },
        },
        proposed_case={"status": "unresolved"},
        validation=CaseMemoryCandidateValidation(
            provenance_valid=True,
            case_valid=True,
        ),
        promotion={
            "preview_only": True,
            "persisted": False,
            "operator_approval_required": True,
        },
        safety={
            "model_authority": False,
            "tool_execution": False,
            "os_mutation": False,
            "memory_write": False,
        },
    )


def test_planned_tool_contract_shape_is_frozen() -> None:
    result = sample_planned_tool().to_dict()

    assert_keys_exact(
        result,
        [
            "name",
            "reason",
            "category",
            "risk_level",
            "read_only",
            "implemented",
            "requires_confirmation",
            "requires_target",
            "allow_automatic_use",
            "logs_action",
        ],
    )


def test_tool_plan_contract_shape_is_frozen() -> None:
    planned_tool = sample_planned_tool()
    result = ToolPlan(
        status="ok",
        intent="performance_diagnostic",
        user_request="why is my laptop slow",
        message="Read-only diagnostics can run.",
        tools=(planned_tool,),
        blocked_tools=(),
        safe_alternatives=(),
    ).to_dict()

    assert_keys_exact(
        result,
        [
            "status",
            "intent",
            "user_request",
            "message",
            "requires_confirmation",
            "tools",
            "blocked_tools",
            "safe_alternatives",
        ],
    )

    assert result["tools"][0]["name"] == "system_snapshot"


def test_tool_execution_result_contract_shape_is_frozen() -> None:
    result = sample_tool_execution_result().to_dict()

    assert_keys_exact(
        result,
        [
            "tool_name",
            "status",
            "message",
            "data",
            "safety_summary",
        ],
    )


def test_tool_plan_execution_result_contract_shape_is_frozen() -> None:
    result = ToolPlanExecutionResult(
        status="ok",
        message="Execution completed.",
        plan_status="completed",
        intent="performance_diagnostic",
        user_request="why is my laptop slow",
        executed_tools=(sample_tool_execution_result(),),
        refused_tools=(),
        blocked_tools=(),
        safe_alternatives=(),
    ).to_dict()

    assert_keys_exact(
        result,
        [
            "status",
            "message",
            "plan_status",
            "intent",
            "user_request",
            "executed_tools",
            "refused_tools",
            "blocked_tools",
            "safe_alternatives",
        ],
    )

    assert result["executed_tools"][0]["tool_name"] == "system_snapshot"


def test_operator_route_handoff_contract_shape_is_frozen() -> None:
    result = OperatorRouteHandoff(
        route_ready=True,
        route_known=True,
        intent="performance_diagnostic",
        safety_class="read_only_diagnostic",
        command_family="runplan",
        recommended_command="runplan why is my laptop slow",
        engine_request="why is my laptop slow",
        autorun_allowed=True,
        manual_review_required=False,
        refusal_reason="",
        errors=(),
    ).to_dict()

    assert_keys_exact(
        result,
        [
            "route_ready",
            "route_known",
            "intent",
            "safety_class",
            "command_family",
            "recommended_command",
            "engine_request",
            "autorun_allowed",
            "manual_review_required",
            "refusal_reason",
            "errors",
        ],
    )


def test_engine_memory_context_contract_shape_is_frozen() -> None:
    result = sample_engine_memory_context().to_dict()

    assert_keys_exact(
        result,
        [
            "status",
            "message",
            "enabled",
            "user_request",
            "context_text",
            "summary",
            "warnings",
            "errors",
        ],
    )


def test_llm_contract_validation_result_shape_is_frozen() -> None:
    result = sample_llm_contract_validation().to_dict()

    assert_keys_exact(
        result,
        [
            "status",
            "valid",
            "message",
            "normalized_proposal",
            "route_handoff",
            "errors",
            "warnings",
        ],
    )

    assert result["normalized_proposal"]["schema_version"] == "llm_contract_v0"


def test_llm_route_call_result_shape_is_frozen() -> None:
    result = sample_llm_route_call().to_dict()

    assert_keys_exact(
        result,
        [
            "status",
            "message",
            "model_used",
            "prompt",
            "raw_model_output",
            "validation",
            "used_model",
            "errors",
            "warnings",
        ],
    )

    assert result["validation"]["valid"] is True


def test_llm_conversation_preview_result_shape_is_frozen() -> None:
    result = LLMConversationPreviewResult(
        status="ok",
        message="Preview completed.",
        user_request="why is my laptop slow",
        deterministic_result=None,
        llm_route_result=sample_llm_route_call(),
        autorun_gate=None,
        preview_journal_result={
            "status": "ok",
            "message": "recorded",
            "data": {"preview_id": "llmprev-example"},
            "errors": [],
            "warnings": [],
        },
        executed=False,
    ).to_dict()

    assert_keys_exact(
        result,
        [
            "status",
            "message",
            "user_request",
            "deterministic_result",
            "llm_route_result",
            "autorun_gate",
            "preview_journal_result",
            "executed",
        ],
    )

    assert result["executed"] is False


def test_case_memory_candidate_contract_shape_is_frozen() -> None:
    result = sample_case_memory_candidate().to_dict()

    assert_keys_exact(
        result,
        [
            "schema_version",
            "candidate_id",
            "source_turn_id",
            "source_turn_created_at",
            "provenance",
            "proposed_case",
            "validation",
            "promotion",
            "safety",
        ],
    )
    assert_keys_exact(
        result["validation"],
        ["provenance_valid", "case_valid", "errors", "warnings"],
    )
    assert result["promotion"]["preview_only"] is True
    assert result["promotion"]["persisted"] is False
    assert result["safety"]["memory_write"] is False


def test_lighthouse_engine_result_contract_shape_is_frozen() -> None:
    result = LighthouseEngineResult(
        status="ok",
        message="Engine completed.",
        user_request="why is my laptop slow",
        execution_status="not_run",
        plan_status="ok",
        intent="performance_diagnostic",
        execution_result=None,
        confirmation_previews=(),
        plan_journal_result=None,
        errors=(),
        memory_context=sample_engine_memory_context(),
        llm_route_contract=sample_llm_route_call(),
    ).to_dict()

    assert_keys_exact(
        result,
        [
            "status",
            "message",
            "user_request",
            "execution_status",
            "plan_status",
            "intent",
            "execution_result",
            "confirmation_previews",
            "plan_journal_result",
            "memory_context",
            "llm_route_contract",
            "errors",
        ],
    )

    assert result["memory_context"]["enabled"] is False
    assert result["llm_route_contract"]["validation"]["valid"] is True


def test_frozen_contract_shapes_are_json_serializable() -> None:
    import json

    objects = [
        sample_planned_tool().to_dict(),
        ToolPlan(
            status="ok",
            intent="performance_diagnostic",
            user_request="why is my laptop slow",
            message="Read-only diagnostics can run.",
            tools=(sample_planned_tool(),),
            blocked_tools=(),
            safe_alternatives=(),
        ).to_dict(),
        sample_tool_execution_result().to_dict(),
        sample_llm_contract_validation().to_dict(),
        sample_llm_route_call().to_dict(),
        sample_engine_memory_context().to_dict(),
        sample_case_memory_candidate().to_dict(),
    ]

    for payload in objects:
        json.dumps(payload)

def test_case_memory_promotion_result_contract_shape_is_frozen() -> None:
    assert [field.name for field in fields(CaseMemoryPromotionResult)] == [
        "status",
        "decision",
        "message",
        "source_turn_id",
        "candidate_id",
        "candidate_fingerprint",
        "promotion_id",
        "case_id",
        "persisted",
        "case_write_performed",
        "audit_complete",
        "errors",
        "warnings",
    ]


def test_case_memory_promotion_result_truth_semantics_are_frozen() -> None:
    duplicate = CaseMemoryPromotionResult(
        status="duplicate",
        decision="duplicate",
        message="Exact approved case already exists.",
        source_turn_id="turn-example",
        candidate_id="candidate-example",
        candidate_fingerprint="a" * 64,
        promotion_id="promotion-example",
        case_id="case-example",
        persisted=True,
        case_write_performed=False,
        audit_complete=True,
    )

    assert duplicate.persisted is True
    assert duplicate.case_write_performed is False
    assert duplicate.audit_complete is True

    partial = CaseMemoryPromotionResult(
        status="partial",
        decision="promoted",
        message=(
            "Exact approved case was persisted, but final audit "
            "did not complete."
        ),
        source_turn_id="turn-example",
        candidate_id="candidate-example",
        candidate_fingerprint="a" * 64,
        promotion_id="promotion-example",
        case_id="case-example",
        persisted=True,
        case_write_performed=True,
        audit_complete=False,
        errors=("final audit failed",),
    )

    assert partial.persisted is True
    assert partial.case_write_performed is True
    assert partial.audit_complete is False
