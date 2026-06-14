"""
Engine memory context for Lighthouse.

This module builds read-only memory context for the Lighthouse Engine.

It does not mutate memory.
It does not execute tools.
It does not make final safety decisions.
It does not call the model.

Its job is to provide a stable bridge between:
- memory retrieval
- memory summarization
- Lighthouse Engine orchestration
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.memory_summarizer import (
    MEMORY_SUMMARY_STATUS_EMPTY,
    MEMORY_SUMMARY_STATUS_OK,
    MEMORY_SUMMARY_STATUS_PARTIAL,
    MemorySummaryResult,
    summarize_memory_for_request,
)


ENGINE_MEMORY_STATUS_OK = "ok"
ENGINE_MEMORY_STATUS_EMPTY = "empty"
ENGINE_MEMORY_STATUS_PARTIAL = "partial"
ENGINE_MEMORY_STATUS_DISABLED = "disabled"
ENGINE_MEMORY_STATUS_ERROR = "error"


@dataclass(frozen=True)
class EngineMemoryContext:
    """
    Memory context prepared for Lighthouse Engine use.
    """

    status: str
    message: str
    enabled: bool
    user_request: str
    context_text: str
    summary: MemorySummaryResult | None
    warnings: tuple[str, ...]
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable engine memory context shape.
        """
        return {
            "status": self.status,
            "message": self.message,
            "enabled": self.enabled,
            "user_request": self.user_request,
            "context_text": self.context_text,
            "summary": self.summary.to_dict() if self.summary else None,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def map_memory_summary_status(summary_status: str) -> str:
    """
    Map memory summarizer status to engine memory context status.
    """
    if summary_status == MEMORY_SUMMARY_STATUS_OK:
        return ENGINE_MEMORY_STATUS_OK

    if summary_status == MEMORY_SUMMARY_STATUS_EMPTY:
        return ENGINE_MEMORY_STATUS_EMPTY

    if summary_status == MEMORY_SUMMARY_STATUS_PARTIAL:
        return ENGINE_MEMORY_STATUS_PARTIAL

    return ENGINE_MEMORY_STATUS_ERROR


def build_disabled_memory_context(user_request: str) -> EngineMemoryContext:
    """
    Build a disabled memory context result.
    """
    return EngineMemoryContext(
        status=ENGINE_MEMORY_STATUS_DISABLED,
        message="Engine memory context is disabled.",
        enabled=False,
        user_request=user_request,
        context_text="",
        summary=None,
        warnings=(),
        errors=(),
    )


def build_error_memory_context(
    *,
    user_request: str,
    error: Exception | str,
) -> EngineMemoryContext:
    """
    Build an error memory context result.
    """
    return EngineMemoryContext(
        status=ENGINE_MEMORY_STATUS_ERROR,
        message="Unable to build engine memory context.",
        enabled=True,
        user_request=user_request,
        context_text="",
        summary=None,
        warnings=(),
        errors=(str(error),),
    )


def build_engine_memory_context(
    user_request: str,
    *,
    enabled: bool = True,
    memory_dir: Path | str | None = None,
    max_cases: int = 5,
    max_knowledge_entries: int = 5,
) -> EngineMemoryContext:
    """
    Build read-only memory context for the Lighthouse Engine.

    This may read existing Lighthouse memory files and summarize them, but it
    does not write memory, execute tools, modify the OS, or call the model.
    """
    cleaned_request = user_request.strip()

    if not enabled:
        return build_disabled_memory_context(cleaned_request)

    try:
        summary = summarize_memory_for_request(
            cleaned_request,
            memory_dir=memory_dir,
            max_cases=max_cases,
            max_knowledge_entries=max_knowledge_entries,
        )

        status = map_memory_summary_status(summary.status)

        return EngineMemoryContext(
            status=status,
            message=summary.message,
            enabled=True,
            user_request=cleaned_request,
            context_text=summary.context_text,
            summary=summary,
            warnings=summary.warnings,
            errors=(),
        )

    except Exception as error:
        return build_error_memory_context(
            user_request=cleaned_request,
            error=error,
        )


def has_useful_memory_context(memory_context: EngineMemoryContext) -> bool:
    """
    Return True when memory context contains useful content for engine/model use.
    """
    return memory_context.status in {
        ENGINE_MEMORY_STATUS_OK,
        ENGINE_MEMORY_STATUS_PARTIAL,
    } and bool(memory_context.context_text.strip())


def build_memory_context_prompt_block(
    memory_context: EngineMemoryContext,
) -> str:
    """
    Build a prompt-safe memory context block.

    This does not call the model. It only creates a future-ready text block.
    """
    if not memory_context.enabled:
        return "Lighthouse memory context is disabled."

    if not has_useful_memory_context(memory_context):
        return "No relevant Lighthouse memory context was found."

    return memory_context.context_text
