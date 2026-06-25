# Lighthouse V1 Contract Shapes

This document records the serializable shapes that behave as internal V1
contracts between Lighthouse subsystems.

These are not user-facing UI contracts. They are implementation contracts used
by tests, CLI display, engine orchestration, journals, route handoffs, and
future documentation.

If one of these shapes changes, treat it as a V1 contract-change review.

## Frozen contract objects

```text
PlannedTool
ToolPlan
ToolExecutionResult
ToolPlanExecutionResult
OperatorRouteHandoff
EngineMemoryContext
LLMContractValidationResult
LLMRouteCallResult
LLMConversationPreviewResult
LighthouseEngineResult
```

## Safety principle

Shape stability protects the deterministic safety spine:

```text
model output
→ LLM contract validation
→ deterministic route handoff
→ autorun gate
→ engine/tool registry
```

Model output is never the source of execution authority.

## Contract-change rule

If a field is added, removed, renamed, or moved:

1. Update the owning service deliberately.
2. Update `tests/test_v1_contract_shapes.py`.
3. Update this document.
4. Confirm that journals, dataset export, CLI display, and route handoff logic
   still interpret the shape correctly.
5. Run the full test suite.
6. Run the local CLI smoke checklist.

## Current serialized keys

### PlannedTool

```text
name
reason
category
risk_level
read_only
implemented
requires_confirmation
requires_target
allow_automatic_use
logs_action
```

### ToolPlan

```text
status
intent
user_request
message
requires_confirmation
tools
blocked_tools
safe_alternatives
```

### ToolExecutionResult

```text
tool_name
status
message
data
safety_summary
```

### ToolPlanExecutionResult

```text
status
message
plan_status
intent
user_request
executed_tools
refused_tools
blocked_tools
safe_alternatives
```

### OperatorRouteHandoff

```text
route_ready
route_known
intent
safety_class
command_family
recommended_command
engine_request
autorun_allowed
manual_review_required
refusal_reason
errors
```

### EngineMemoryContext

```text
status
message
enabled
user_request
context_text
summary
warnings
errors
```

### LLMContractValidationResult

```text
status
valid
message
normalized_proposal
route_handoff
errors
warnings
```

### LLMRouteCallResult

```text
status
message
model_used
prompt
raw_model_output
validation
used_model
errors
warnings
```

### LLMConversationPreviewResult

```text
status
message
user_request
deterministic_result
llm_route_result
autorun_gate
preview_journal_result
executed
```

### LighthouseEngineResult

```text
status
message
user_request
execution_status
plan_status
intent
execution_result
confirmation_previews
plan_journal_result
memory_context
llm_route_contract
errors
```
