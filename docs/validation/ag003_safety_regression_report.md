# AG-003: Lighthouse Safety Regression Review — LLM Preview / Route Boundary

**Review date**: 2026-06-26  
**Review mode**: Validation-only  
**Reviewer**: Antigravity  
**Scope**: CLI command boundary, deterministic Operator routing, LLM contract/preview, tool safety, engine boundary

---

## 1. Executive Summary

**The reviewed boundary appears safe.**

All nine safety invariants in the core question hold across the reviewed files. No path exists in the reviewed code through which model output can execute a tool, mutate OS state, write authoritative memory, bypass confirmation, bypass the route registry, bypass the tool registry, or imply authority without passing through the approved deterministic gate.

Two low-severity issues and several test-coverage gaps are identified below. Neither issue permits a safety violation in current code; both are hardening recommendations.

---

## 2. Verified Safe Paths

### CLI and command boundary

| Path | File | Why it is safe |
|------|------|----------------|
| `talk <text>` | `backend/app/cli.py` | Calls `interpret_operator_input` deterministically. Prints result. Explicitly prints "No command was executed by talk." Never calls `run_lighthouse_engine`. |
| `talkrun <text>` | `backend/app/cli.py` | Calls `interpret_operator_input` then `validate_route_handoff_for_autorun`. Auto-runs only when the gate returns `allowed=True`. The gate requires `safety_class=read_only_diagnostic`, `command_family=runplan`, `autorun_allowed=True`, `manual_review_required=False`, plus a non-empty `engine_request`. Refused paths print "No command was executed by talkrun." |
| `llm preview <text>` | `backend/app/cli.py` | Preview-only. Calls `build_llm_route_call` and `record_llm_route_preview`. Prints "No command was executed by llm preview." Never calls `run_lighthouse_engine` or any executor. |
| `llm talk <text>` | `backend/app/cli.py` | Calls `build_llm_conversation_preview`, which is preview-only. Report explicitly states "No command was executed by llm talk." and "Model output was not handed to talk or talkrun." |
| `turn <text>` | `backend/app/cli.py` | Calls `build_conversational_engine_turn`, which builds deterministic and LLM sides, evaluates the autorun gate, records the turn, and executes nothing. |
| `runplan <text>` | `backend/app/cli.py` | Calls `run_lighthouse_engine`, then `execute_tools_for_request`. Engine and executor only run safe read-only tools. Confirmation-gated, blocked, unimplemented, and OS-changing tools are refused, not executed. |
| `plan <text>` | `backend/app/cli.py` | Calls `plan_tools_for_request` only. Prints plan. Never executes. |

### Deterministic Operator routing boundary

| Component | File | Why it is safe |
|-----------|------|----------------|
| Intent classification | `backend/app/services/operator_conversation.py` | Pure keyword matching. No model call. Destructive > OS-action > process/memory > repair > slowness > health > direct-command > unknown. Unknown falls through to `needs_clarification`. |
| Route registry | `backend/app/services/operator_routes.py` | Static frozen dictionary. Only three intents have `autorun_allowed=True`, and all three are `read_only_diagnostic`. OS-action, destructive, repair, direct-command, and unknown all have `autorun_allowed=False`. |
| Autorun gate | `backend/app/services/operator_routes.py` | Seven sequential boolean checks. Requires `route_ready=True`, `route_known=True`, `autorun_allowed=True`, `manual_review_required=False`, `safety_class=read_only_diagnostic`, `command_family=runplan`, and non-empty `engine_request`. Any failure returns `allowed=False`. |
| Registry self-validation | `backend/app/services/operator_routes.py` | Validates every route for internal consistency. Catches autorun/non-read-only conflicts, unknown-route invariants, and direct-command invariants. |
| Handoff builder | `backend/app/services/operator_routes.py` | Derives `engine_request` from `interpreted_request`, not by parsing display strings. Unknown intents return `route_ready=False`, `autorun_allowed=False`. |

### LLM contract and preview boundary

| Component | File | Why it is safe |
|-----------|------|----------------|
| Forbidden fields | `backend/app/services/llm_contract.py` | Forbidden field names include `command`, `shell_command`, `powershell`, `tool`, `approved`, `autorun`, `autorun_allowed`, `manual_review_required`, `permission_granted`, `mutate_os`, and related authority/action fields. Presence of any forbidden field fails validation. |
| Allowed fields | `backend/app/services/llm_contract.py` | Strict allowlist of six fields: `schema_version`, `proposed_intent`, `interpreted_request`, `confidence`, `reasoning_summary`, `safety_notes`. Unknown fields fail validation. |
| Direct-command ban | `backend/app/services/llm_contract.py` | LLM may not propose `direct_command` intent or produce `direct_cli` command family handoffs. Both are validation errors. |
| Route handoff built by registry | `backend/app/services/llm_contract.py` | Handoff is always built via `build_route_handoff` from the deterministic route registry, never from model output. |
| JSON parsing safety | `backend/app/services/llm_contract.py` | `json.loads` is wrapped in try/except. Non-dict decoded values are rejected. Empty payloads are rejected. |
| Route engine never executes | `backend/app/services/llm_route_engine.py` | `build_llm_route_call` returns `LLMRouteCallResult` with validation status only. It never executes the handoff. |
| Conversation preview never executes | `backend/app/services/llm_conversation_preview.py` | `build_llm_conversation_preview` returns `executed=False` hardcoded. The formatted report states "No command was executed by llm talk." |
| Preview journal is append-only, not authority | `backend/app/services/llm_preview_journal.py` | Journal records include safety fields such as `preview_only=True`, `executed=False`, `model_authority=False`, and `os_mutation=False`. Records are written to JSONL and are not read back as routing input. |

### Tool safety boundary

| Component | File | Why it is safe |
|-----------|------|----------------|
| Tool registry | `backend/app/services/tool_registry.py` | Static frozen tuple. Every tool with elevated risk has `allow_automatic_use=False`. Blocked tools are unimplemented. `run_raw_command` is explicitly blocked. |
| Automatic use gating | `backend/app/services/tool_registry.py` | Requires implemented, read-only, risk level 0, no confirmation requirement, no target requirement, and `allow_automatic_use=True`. Unknown tools return `False`. |
| Tool executor safety check | `backend/app/services/tool_executor.py` | Sequential checks refuse unknown, blocked, not implemented, not read-only, non-risk-0, confirmation-required, target-required, and not-automatic tools. |
| Executor dispatch | `backend/app/services/tool_executor.py` | Hardcoded dictionary of read-only executors. No `subprocess`, `os.system`, or shell invocation. Each reads telemetry/events only. |
| Plan-level refusal | `backend/app/services/tool_executor.py` | Plans with status `blocked`, `needs_confirmation`, or `needs_clarification` refuse all tools without executing any. |
| Confirmation gate | `backend/app/services/confirmation_gate.py` | Unknown tools are refused. Blocked tools are refused. Non-confirmation tools are not confirmable. Target-required tools without a target are refused. Phrase must match exactly. |
| Registry self-validation | `backend/app/services/tool_registry.py` | Validates risk/read-only consistency, blocked-tool constraints, and automatic-use constraints. |

### Engine boundary

| Component | File | Why it is safe |
|-----------|------|----------------|
| Engine execution | `backend/app/services/lighthouse_engine.py` | Routes through `execute_tools_for_request`, which enforces read-only-only execution. Memory context is read-only retrieval. LLM route contract evidence is not used as execution authority. |
| Memory context | `backend/app/services/lighthouse_engine.py` | Memory context is read-only. It may retrieve and summarize Lighthouse memory, but it does not write memory, execute actions, or call the model. |
| LLM route contract in engine | `backend/app/services/lighthouse_engine.py` | LLM route proposals are validated and returned as evidence only. They are not passed to `execute_tools_for_request`. |

---

## 3. Verified Issues

### Issue 3.1: `talkrun` auto-execution path uses `gate_result.engine_request`, not the handoff `engine_request` field directly

**File**: `backend/app/cli.py`  
**Function**: `print_operator_conversation_run_report`  
**What happens**: After the autorun gate passes, `print_runplan_report(gate_result.engine_request or "")` is called. The `engine_request` originates from `OperatorAutorunGateResult.engine_request`, which is set from the handoff dictionary.  
**Why it matters**: This path is currently safe because `engine_request` in the handoff is always set from `interpreted_request`, a deterministic string. However, if a future code change were to populate `engine_request` from model output, the `talkrun` path would pass it directly to the engine. The `or ""` fallback means an empty/None `engine_request` would produce a `needs_clarification` path.  
**Safety impact**: Low. Currently safe. Future-risk only.  
**Smallest recommended fix**: Add an assertion or guard in `print_operator_conversation_run_report` that validates the `gate_result.engine_request` is a non-empty stripped string before passing it to `print_runplan_report`.  
**Test coverage**: `test_cli_operator_conversation.py` tests `talkrun` with safe and unsafe intents, but does not explicitly assert the `engine_request` value passed to the engine.

### Issue 3.2: LLM contract rejects `direct_command`, but processing may still build partial invalid-result handoff data

**File**: `backend/app/services/llm_contract.py`  
**Function**: `validate_llm_route_proposal`  
**What happens**: When a model proposes `direct_command`, the validator appends errors and returns invalid. Processing may still build partial route handoff data before rejection.  
**Why it matters**: The final result is correct: the proposal is rejected. However, a future consumer that reads `validation.route_handoff` from an invalid result without checking `validation.valid` could misuse partial handoff data.  
**Safety impact**: None in current code. The result is invalid, the handoff is never used for execution, and the `LLMRouteCallResult` status is invalid.  
**Smallest recommended fix**: Short-circuit and return immediately after detecting `proposed_intent = "direct_command"`, before building any route handoff.  
**Test coverage**: Existing tests cover rejection. No test inspects whether partial handoff in an invalid result is safely inert.

---

## 4. Suspected but Unverified Concerns

These are not proven issues from the reviewed files. They are noted for awareness.

1. `classify_user_intent` in `assistant.py` was not reviewed. The `interpret_direct_command` function in `operator_conversation.py` delegates to it. It appears to be deterministic keyword matching, but this should be verified separately if direct-command drift is suspected.

2. `build_conversational_engine_turn` in `conversational_engine_turn.py` was not reviewed. Based on the CLI docstring, it appears safe and preview/record-only, but this should be verified separately if the `turn` path changes.

3. `engine_memory_context.py` was not reviewed. Based on the engine docstring and usage, this should only retrieve and summarize memory context.

4. Model output normalization passes through unexpected non-dict types. These flow to contract validation and fail safely, but may produce less informative errors.

---

## 5. Missing or Weak Tests

### 5.1 Missing: `talkrun` passes correct `engine_request` value to engine

Recommended test: In `test_cli_operator_conversation.py`, add a test for `talkrun` with a safe read-only intent that captures or asserts the exact `engine_request` string passed to `print_runplan_report`. This proves the talkrun-to-engine handoff uses the deterministic request, not a display string.

### 5.2 Missing: `llm talk` CLI command does not call any executor

Recommended test: In `test_llm_conversation_preview.py` or a new `test_cli_llm_talk.py`, add a test that calls `print_llm_conversation_preview_report` with a mock model callable and asserts that `execute_tools_for_request` and `run_lighthouse_engine` are never called.

### 5.3 Missing: `turn` CLI command does not call any executor

Recommended test: Add a test that calls `print_conversational_engine_turn_report` and asserts no tool executor or engine executor is invoked.

### 5.4 Missing: LLM contract `route_handoff` from an invalid result is not usable for execution

Recommended test: In `test_llm_contract.py`, add a test that validates a proposal with forbidden fields, then asserts `result.valid is False` and `result.route_handoff.get("autorun_allowed") is not True`.

### 5.5 Missing: `talkrun` with empty/whitespace input does not execute

Recommended test: In `test_cli_operator_conversation.py`, add a test that calls `print_operator_conversation_run_report("")` and asserts no engine call occurs.

### 5.6 Missing: Route handoff built from model output always defers to registry

Recommended test: In `test_llm_route_engine.py`, add a test with an injected model that returns a valid proposal for `performance_diagnostic`. Assert that `result.validation.route_handoff["autorun_allowed"]` matches the registry value, not any model-supplied field.

### 5.7 Weak: `test_lighthouse_engine.py` does not test the `include_llm_route_contract=True` path

Recommended test: Add a test calling `run_lighthouse_engine` with `include_llm_route_contract=True` and a mock model callable. Assert the `llm_route_contract` is attached as evidence but the `execution_result` is unchanged.

### 5.8 Weak: No test for `talkrun` with `os_action_request` or `destructive_action_request` intent

Recommended test: Explicitly test `talkrun` with `close chrome` and `delete files to make space` to prove the two highest-risk intent categories are refused through the full `talkrun` path.

---

## 6. Contract Drift

All checked contract/result shapes appear stable and serializable.

| Shape | File | Stable | Serializable | Notes |
|-------|------|--------|-------------|-------|
| `LighthouseEngineResult` | `backend/app/services/lighthouse_engine.py` | Yes | Yes | `to_dict()` present. |
| `ToolPlan` | `backend/app/services/tool_planner.py` | Yes | Yes | `to_dict()` present. |
| `ToolPlanExecutionResult` | `backend/app/services/tool_executor.py` | Yes | Yes | `to_dict()` present. |
| `OperatorRouteHandoff` | `backend/app/services/operator_routes.py` | Yes | Yes | `to_dict()` present. |
| `EngineMemoryContext` | Not in scope | Not verified | Not verified | Imported by engine; should be verified separately if drift is suspected. |
| `LLMContractValidationResult` | `backend/app/services/llm_contract.py` | Yes | Yes | `to_dict()` present. |
| `LLMRouteCallResult` | `backend/app/services/llm_route_engine.py` | Yes | Yes | `to_dict()` present. |
| `LLMConversationPreviewResult` | `backend/app/services/llm_conversation_preview.py` | Yes | Yes | `to_dict()` present. `executed` defaults to `False`. |

---

## 7. Safety Boundary Verdict

| Question | Answer | Evidence |
|----------|--------|----------|
| Can model output execute tools? | No | LLM route engine returns validation results only. Tool executor requires registry-backed automatic-use approval. No model output reaches `execute_registered_tool`. |
| Can model output authorize actions? | No | Forbidden fields include `approved`, `approval`, `autorun_allowed`, and `permission_granted`. Contract validation rejects these. Route handoff is always built by the deterministic registry. |
| Can model output bypass the route registry? | No | `build_route_handoff` is always called with the proposed intent looked up against `OPERATOR_ROUTE_REGISTRY`. Unknown intents return `route_ready=False`, `autorun_allowed=False`. |
| Can model output bypass the tool registry? | No | Tool executor checks `get_tool_by_name` for every tool. Unknown tools are refused. The executor dispatch table is hardcoded. |
| Can model output bypass the autorun gate? | No | `validate_route_handoff_for_autorun` performs sequential boolean checks. Model output never populates handoff fields; they come from the registry. |
| Can preview mode mutate OS state? | No | `llm preview`, `llm talk`, and `turn` never call `run_lighthouse_engine`, `execute_tools_for_request`, or any tool executor. They return result objects with `executed=False`. |
| Can preview mode write authoritative memory? | No | Preview journal writes are append-only JSONL with `safety.model_authority=False`. Journal entries are never read back as routing decisions. Memory context in the engine is read-only retrieval. |
| Can unsafe routes autorun? | No | Only `performance_diagnostic`, `process_memory_diagnostic`, and `general_health_check` have `autorun_allowed=True`, and all three are `read_only_diagnostic`. The autorun gate additionally requires read-only safety and `command_family=runplan`. |
| Can unknown/direct-command routes autorun? | No | `INTENT_UNKNOWN` has `autorun_allowed=False`, `manual_review_required=True`, `command_family=none`. `INTENT_DIRECT_COMMAND` has `autorun_allowed=False`. Both are refused by the autorun gate. |

---

## 8. Minimal Next Action

Add the three highest-priority missing tests:

1. Test that `talkrun` passes the correct `engine_request` to the engine.
2. Test that an invalid LLM contract result's `route_handoff` does not contain `autorun_allowed=True`.
3. Test `talkrun` explicitly with `os_action_request` and `destructive_action_request`.

These are small, targeted additions to existing test files. No new modules, no refactors, no architectural changes.
