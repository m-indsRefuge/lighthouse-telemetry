# Lighthouse V1 Memory Layer Architecture

This document defines how Lighthouse V1 uses journals, datasets, feedback, and future semantic retrieval.

The core rule is simple:

```text
Journals are source-of-truth event records.
Datasets are regenerated learning/evaluation artifacts.
Semantic memory is a future retrieval helper.
Deterministic safety remains the authority boundary.
```

## Purpose

The V1 memory layer exists to make Lighthouse auditable, inspectable, and improvable without giving the model authority over the system.

It records what Lighthouse observed, interpreted, proposed, rejected, selected, exported, or executed. These records are intended to support later evaluation, repair loops, dataset creation, and eventually semantic retrieval.

The memory layer must not become an action authority. It must not bypass the route registry, tool registry, confirmation gate, autorun gate, or Operator approval.

## Authority model

Lighthouse follows this authority order:

```text
Operator
Deterministic engine and validators
Route registry
Tool registry
Confirmation gate
Autorun gate
Memory/journals/datasets
Model proposals
```

Memory can inform future reasoning and retrieval. It cannot approve a route, execute a tool, mutate the operating system, or convert an unsafe request into a safe one.

The model may propose or explain, but deterministic validators decide whether the proposal is valid. The model cannot grant itself permission.

## Memory layer components

The V1 memory layer has four main parts:

```text
append-only journals
feedback records
dataset exports
future semantic indexes
```

Each part has a different role.

## Append-only journals

Journals are the closest thing V1 has to source-of-truth operational memory.

A journal record should answer:

```text
What happened?
What input caused it?
What deterministic component handled it?
What was proposed?
What was accepted or rejected?
What safety gate was evaluated?
Was anything executed?
What was the outcome?
```

Journals are append-only by design. A new event adds a new line. Existing lines should not be rewritten during normal operation.

### Current journal families

```text
memory/operator_interactions.jsonl
memory/llm_route_previews.jsonl
memory/conversation_turns.jsonl
memory/action_journal.jsonl
memory/confirmation_previews.jsonl
```

The exact filenames may evolve, but the role distinction should stay stable.

### Operator interaction journal

The Operator interaction journal records deterministic `talk` and `talkrun` paths.

It captures:

```text
operator input
interpreted intent
recommended command
route handoff
autorun gate result when applicable
execution attempt flag
execution result flag
feedback target id
```

This journal supports evaluation of the deterministic route layer.

### LLM route preview journal

The LLM route preview journal records model route proposal attempts through LLM Contract V0.

It captures:

```text
original input
model status
model used or disabled
contract validation result
proposed intent
rejected authority fields
route handoff if valid
preview-only safety flags
errors and warnings
```

This journal supports evaluation of the model boundary. It is especially useful because invalid model outputs are not discarded. They become negative examples for contract validation.

### Conversational turn journal

The conversational turn journal records one complete preview-only conversational engine turn.

It joins:

```text
operator input
deterministic interpretation
LLM route boundary result
selected route source
selected route handoff
autorun gate result
turn safety flags
turn id
```

This journal is the richest V1 operational trace so far because it captures a whole decision path in one record.

A conversational turn may show that a safe read-only route could be auto-run, but the V0 turn command still executes nothing. The gate is evaluated, not acted on.

### Action journal

The action journal records engine-level plans, safe read-only executions, and related audit events.

It is closer to operational audit than model-learning data. It should remain compact, explicit, and deterministic.

### Confirmation preview journal

The confirmation preview journal records cases where Lighthouse prepared a confirmation-gated action preview.

It should capture what would require Operator approval without performing the action.

## Dataset exports

Datasets are derived artifacts, not source-of-truth memory.

A dataset export reads a source journal and writes a clean JSONL file for review, evaluation, or later training experiments.

The important distinction:

```text
journal file = growing append-only source log
dataset file = regenerated export snapshot
```

For example:

```text
memory/conversation_turns.jsonl
```

is append-only.

```text
memory/datasets/conversational_turn_dataset.jsonl
```

is regenerated each time `dataset turns` runs.

This means repeated dataset exports should not duplicate examples. The export should replace the previous snapshot with the current view of the source journal.

### Current dataset exports

```text
dataset operator
dataset llm preview
dataset turns
```

These commands export records under:

```text
memory/datasets/
```

Dataset exports do not execute routes, call the model, mutate the operating system, or change the source journal.

## Feedback records

Feedback records are operator-provided labels or notes that help classify stored examples.

Examples:

```text
useful
not_useful
wrong_intent
wrong_route
unsafe
confusing
corrected
```

Feedback should not directly modify old source records. It should be stored as a separate event or linked record, then joined during dataset export.

This preserves auditability:

```text
original trace stays intact
feedback is attached as a later human judgment
dataset export combines both
```

## Why journal entries may look similar at first

Early V1 entries often look repetitive because the system is still mostly preview-only.

For example, many conversational turns currently follow this pattern:

```text
deterministic interpretation succeeds
LLM route boundary is disabled
deterministic route is selected
autorun gate says safe read-only route could run
execution remains disabled
turn is journaled
```

That repetition is expected and useful. It proves the safety path is stable.

As the engine grows, entries will diverge more:

```text
different model proposals
valid versus invalid contract outputs
different deterministic fallbacks
different autorun gate outcomes
different execution summaries
different feedback labels
different retrieved memories
different tool results
```

The journal schema is intentionally prepared for that richer future state.

## Future semantic memory

Semantic memory is not part of the V1 authority layer.

Future semantic memory may index selected journal records, dataset rows, case memories, knowledge entries, and summaries so Lighthouse can retrieve relevant prior context.

Semantic memory may help answer:

```text
Have we seen a similar issue before?
What route worked last time?
Which model proposal failed validation in a similar situation?
Which operator feedback labels were attached to similar turns?
What memory case or baseline is relevant?
```

Semantic memory must not answer:

```text
May this tool execute?
May this process be closed?
May this file be deleted?
May this model output bypass validation?
```

Those questions remain deterministic safety questions.

## Source of truth hierarchy

When information conflicts, use this hierarchy:

```text
1. Current live telemetry and tool results
2. Deterministic validators and engine outputs
3. Append-only journal records
4. Human feedback labels and notes
5. Dataset exports
6. Semantic retrieval summaries
7. Model-generated explanations
```

Dataset exports are useful, but they are derived. If there is a mismatch between a dataset row and its source journal entry, the journal wins.

Semantic summaries are useful, but they are lossy. If a semantic summary conflicts with structured memory or telemetry, the structured record wins.

## Design invariants

The V1 memory layer must preserve these invariants:

```text
Invalid memory is not silently accepted.
Model-suggested memory cannot bypass validation.
Search and review commands are read-only.
Dataset exports do not mutate source journals.
Dataset exports do not execute tools.
Semantic retrieval cannot authorize actions.
Memory cannot override the route registry.
Memory cannot override the tool registry.
Memory cannot override the autorun gate.
Memory cannot override Operator confirmation.
```

## Operational flow

The current V1 flow looks like this:

```text
Operator input
→ deterministic interpretation
→ optional model route proposal
→ LLM Contract V0 validation
→ selected route handoff
→ autorun gate evaluation
→ preview or safe read-only execution
→ journal record
→ optional feedback
→ dataset export
→ future semantic indexing
```

The key point is that the final arrow into semantic indexing is downstream. It does not loop back into authority.

## What self-improvement means in V1

In V1, self-improvement does not mean the model rewrites itself or changes its own rules.

It means Lighthouse accumulates structured evidence that lets the Operator and future deterministic tools improve the system.

Examples:

```text
identify repeated wrong intents
identify prompts that produce invalid LLM contracts
identify common safe diagnostic requests
identify route families that need better explanations
identify missing tests
identify memory cases worth adding
identify confusing Operator-facing wording
```

The system improves because its traces become analyzable.

## What must wait until later

The following should remain outside V1 unless explicitly reopened:

```text
semantic vector indexing
model-managed memory writes
autonomous memory repair
self-editing rules
MCP-based external model orchestration
public REST APIs
Lighthouse Navigator / OS navigation layer
autonomous OS-changing action
```

These are future capabilities and should be built only after the deterministic memory, journal, dataset, and safety boundaries are stable.

## Practical command map

Review recent operational records:

```text
interactions
llm previews
turns
journal
```

Export datasets:

```text
dataset operator
dataset llm preview
dataset turns
```

Add feedback:

```text
feedback <trace_id> <label> [note]
llm preview feedback <preview_id> <label> [note]
```

The expected workflow is:

```text
run preview or diagnostic path
review journal/turn records
add feedback when useful
export dataset snapshot
inspect dataset
use findings to improve tests, routes, docs, and validators
```

## Summary

The Lighthouse V1 memory layer is not a memory blob. It is a layered evidence system.

```text
Journals preserve events.
Feedback adds human judgment.
Datasets create reviewable learning artifacts.
Semantic memory will later improve retrieval.
Deterministic gates remain authority.
```

That is the design boundary that makes the memory layer useful without making it unsafe.
