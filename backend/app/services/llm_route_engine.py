"""
LLM route call boundary for Lighthouse.

This module is the narrow bridge between a model response and Lighthouse's
deterministic route contract.

The model may only return a contract-shaped proposal. The proposal is then
validated by LLM Contract V0. The resulting route handoff is built by the
deterministic route registry.

This module does not execute tools.
This module does not mutate the operating system.
This module does not write memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.services.llm import call_ollama, get_ollama_model, is_ollama_enabled
from app.services.llm_contract import (
    LLM_CONTRACT_SCHEMA_VERSION,
    LLMContractValidationResult,
    validate_llm_route_proposal,
)


LLM_ROUTE_STATUS_OK = "ok"
LLM_ROUTE_STATUS_DISABLED = "disabled"
LLM_ROUTE_STATUS_INVALID = "invalid"
LLM_ROUTE_STATUS_ERROR = "error"

LLM_ROUTE_PROMPT_MAX_USER_REQUEST_LENGTH = 500

ModelRouteCallable = Callable[[str], Any]


@dataclass(frozen=True)
class LLMRouteCallResult:
    """
    Stable result returned by the LLM route call boundary.
    """

    status: str
    message: str
    model_used: str | None
    prompt: str
    raw_model_output: Any
    validation: LLMContractValidationResult | None
    used_model: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable LLM route call result.
        """
        return {
            "status": self.status,
            "message": self.message,
            "model_used": self.model_used,
            "prompt": self.prompt,
            "raw_model_output": self.raw_model_output,
            "validation": self.validation.to_dict() if self.validation else None,
            "used_model": self.used_model,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def truncate_user_request(user_request: str) -> str:
    """
    Bound user request text before inserting it into a route prompt.
    """
    cleaned_request = user_request.strip()

    if len(cleaned_request) <= LLM_ROUTE_PROMPT_MAX_USER_REQUEST_LENGTH:
        return cleaned_request

    return cleaned_request[:LLM_ROUTE_PROMPT_MAX_USER_REQUEST_LENGTH].rstrip()


def build_llm_route_prompt(user_request: str) -> str:
    """
    Build the strict prompt used for model route proposals.
    """
    cleaned_request = truncate_user_request(user_request)

    return f"""
You are Lighthouse's route proposal model.

Return only one JSON object matching this exact schema:

{{
  "schema_version": "{LLM_CONTRACT_SCHEMA_VERSION}",
  "proposed_intent": "performance_diagnostic | process_memory_diagnostic | repair_request | os_action_request | destructive_action_request | general_health_check | unknown",
  "interpreted_request": "short plain-language request for the deterministic engine, or null",
  "confidence": 0.0,
  "reasoning_summary": "brief reason for the proposed intent",
  "safety_notes": ["brief safety note"]
}}

Rules:
- Do not include shell commands.
- Do not include tool names or tool arguments.
- Do not include approval, permission, autorun, or execution fields.
- Do not claim that anything has been executed.
- Do not propose direct CLI commands.
- If uncertain, use proposed_intent "unknown" and interpreted_request null.
- The deterministic Lighthouse route registry is the authority.

Operator request:
{cleaned_request}
""".strip()


def normalize_model_output(model_output: Any) -> Any:
    """
    Normalize common model output wrapper shapes into the proposed payload.
    """
    if isinstance(model_output, dict):
        if "response" in model_output:
            return model_output.get("response")

        if "answer" in model_output:
            return model_output.get("answer")

    return model_output


def call_default_ollama_route_model(prompt: str) -> dict[str, Any]:
    """
    Call the existing local Ollama boundary for a route proposal.

    Ollama remains opt-in through LIGHTHOUSE_USE_OLLAMA=1.
    """
    if not is_ollama_enabled():
        return {
            "status": LLM_ROUTE_STATUS_DISABLED,
            "message": "Ollama route proposal is disabled.",
            "model": get_ollama_model(),
        }

    return call_ollama(prompt)


def build_disabled_result(prompt: str, model_name: str | None = None) -> LLMRouteCallResult:
    """
    Build a disabled result without calling a model.
    """
    return LLMRouteCallResult(
        status=LLM_ROUTE_STATUS_DISABLED,
        message="LLM route proposal was not attempted.",
        model_used=model_name,
        prompt=prompt,
        raw_model_output=None,
        validation=None,
        used_model=False,
    )


def build_llm_route_call(
    user_request: str,
    *,
    model_callable: ModelRouteCallable | None = None,
) -> LLMRouteCallResult:
    """
    Ask a model for a route proposal and validate it through LLM Contract V0.

    This function never executes the handoff.
    """
    prompt = build_llm_route_prompt(user_request)

    if model_callable is None and not is_ollama_enabled():
        return build_disabled_result(
            prompt=prompt,
            model_name=get_ollama_model(),
        )

    try:
        raw_result = (
            model_callable(prompt)
            if model_callable is not None
            else call_default_ollama_route_model(prompt)
        )
    except Exception as error:
        return LLMRouteCallResult(
            status=LLM_ROUTE_STATUS_ERROR,
            message="LLM route proposal call failed.",
            model_used=get_ollama_model() if model_callable is None else "injected_model",
            prompt=prompt,
            raw_model_output=None,
            validation=None,
            used_model=True,
            errors=(str(error),),
        )

    if isinstance(raw_result, dict) and raw_result.get("status") == LLM_ROUTE_STATUS_DISABLED:
        return LLMRouteCallResult(
            status=LLM_ROUTE_STATUS_DISABLED,
            message=raw_result.get("message", "LLM route proposal is disabled."),
            model_used=raw_result.get("model", get_ollama_model()),
            prompt=prompt,
            raw_model_output=raw_result,
            validation=None,
            used_model=False,
        )

    if isinstance(raw_result, dict) and raw_result.get("status") == "error":
        message = raw_result.get("message", "LLM route proposal returned an error.")
        return LLMRouteCallResult(
            status=LLM_ROUTE_STATUS_ERROR,
            message=message,
            model_used=raw_result.get("model", get_ollama_model()),
            prompt=prompt,
            raw_model_output=raw_result,
            validation=None,
            used_model=True,
            errors=(message,),
        )

    model_output = normalize_model_output(raw_result)
    validation = validate_llm_route_proposal(model_output)

    if not validation.valid:
        return LLMRouteCallResult(
            status=LLM_ROUTE_STATUS_INVALID,
            message="LLM route proposal failed contract validation.",
            model_used=get_ollama_model() if model_callable is None else "injected_model",
            prompt=prompt,
            raw_model_output=raw_result,
            validation=validation,
            used_model=True,
            errors=validation.errors,
            warnings=validation.warnings,
        )

    return LLMRouteCallResult(
        status=LLM_ROUTE_STATUS_OK,
        message="LLM route proposal passed contract validation.",
        model_used=get_ollama_model() if model_callable is None else "injected_model",
        prompt=prompt,
        raw_model_output=raw_result,
        validation=validation,
        used_model=True,
        warnings=validation.warnings,
    )
