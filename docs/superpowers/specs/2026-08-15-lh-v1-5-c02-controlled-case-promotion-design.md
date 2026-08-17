# LH-V1.5-C02 — Controlled Case Promotion Design

Date: 2026-08-15  
Status: Approved design, self-reviewed  
Base: `690bf5299964f27c7c00dc33aaa3ffcd2fb1fc8c`  
Branch: `feature/lh-v1-5-c02-controlled-case-promotion`

## Purpose

LH-V1.5-C02 introduces the first controlled persistence path from Lighthouse operational conversational evidence into curated CaseMemory.

C02 promotes only one exact, deterministically reconstructed C01 candidate after explicit Operator approval of that candidate's fingerprint.

The core authority rule is:

> Only explicit Operator approval of the exact candidate contents may authorize turn-derived case persistence.

Model output, journal provenance, telemetry, engine provenance, and generic memory-policy source trust never substitute for Operator approval.

## Trust model preserved

C02 preserves the Lighthouse authority hierarchy:

1. Operator intent and explicit approval.
2. Deterministic reconstruction and validation.
3. Exact-fingerprint persistence gate.
4. Curated case append.
5. Append-only promotion audit evidence.

Model output remains proposal-only evidence. Memory never becomes execution authority. C02 adds no tool execution and no OS mutation.

## Scope

C02 adds exactly one new capability:

> Store one deterministically valid, exact-fingerprint C01 case candidate into curated case memory after explicit Operator approval.

Operational evidence remains under `memory/`. Curated case memory remains under `data/memory/cases.jsonl`. C02 adds `memory/case_promotions.jsonl` for operational promotion audit evidence. No memory-directory migration occurs.

## Hard exclusions

C02 does not add:

- automatic promotion
- model-approved promotion
- journal-approved promotion
- semantic deduplication
- case editing
- resolution, archival, deletion, or other lifecycle mutation
- memory consolidation or ranking changes
- semantic memory
- Navigator behavior
- OS actions or tool execution
- background or bulk promotion
- `approve latest`
- fingerprint-omitting approval
- interactive yes/no approval shortcuts
- caller-supplied candidate JSON persistence

## Candidate lineage and fingerprint

C01 already supplies a stable `candidate_id` derived from the source turn. C02 adds a separate `candidate_fingerprint` because lineage identity does not prove that the exact candidate reviewed by the Operator is still current.

- `candidate_id` = stable lineage identity for the source-turn candidate.
- `candidate_fingerprint` = exact identity of the promotion-relevant candidate state.

If Operator feedback or any other promotion-relevant evidence changes, `candidate_id` remains stable while `candidate_fingerprint` must change.

### Fingerprint version and payload

C02 defines:

`CASE_MEMORY_CANDIDATE_FINGERPRINT_VERSION = "case_candidate_fingerprint_v1"`

The canonical fingerprint payload contains exactly:

- fingerprint version
- candidate schema version
- candidate id
- source turn id
- provenance
- proposed case

Conceptually:

```json
{
  "fingerprint_version": "case_candidate_fingerprint_v1",
  "candidate_schema_version": "case_memory_candidate_v1_5",
  "candidate_id": "...",
  "source_turn_id": "...",
  "provenance": {},
  "proposed_case": {}
}
```

The payload is serialized as deterministic canonical JSON using UTF-8, sorted keys, and stable separators, then hashed using SHA-256. The displayed fingerprint is the full 64-character lowercase hexadecimal digest.

### Fingerprint exclusions

The fingerprint excludes:

- candidate validation result
- C01 preview promotion envelope
- C01 preview safety envelope
- formatted report text
- approval-time result fields
- audit timestamps and event ids

These are derived, presentation-specific, or operation-specific rather than part of the evidence-plus-memory state being approved.

Design rule:

> Fingerprint = promotion-relevant evidence + proposed curated memory.

### Accepted CLI fingerprint format

`case approve` accepts exactly 64 hexadecimal characters. Input may use upper- or lowercase hexadecimal; Lighthouse normalizes the supplied value to lowercase before comparison. Any other length or character set is malformed and must be refused before the persistence gate.

## Preview behavior

The existing command remains:

`case preview <turn_id>`

C02 extends the preview report to display:

- Candidate ID
- Candidate fingerprint
- exact approval command

Example:

`case approve <turn_id> <candidate_fingerprint>`

Preview remains strictly read-only: no persistence, model call, tool execution, or OS mutation.

## Approval CLI

The only C02 write-authorizing command is:

`case approve <turn_id> <fingerprint>`

Approval must name both the source turn and exact candidate fingerprint.

There is no `approve latest`, no fingerprint omission, no interactive bypass, and no path for caller-supplied candidate data.

## Approval-time regeneration and validation

The approval command never trusts a serialized candidate supplied by the caller.

At approval time Lighthouse must:

1. accept only `turn_id` and `fingerprint` from the Operator command;
2. validate and normalize the fingerprint input;
3. call the existing C01 candidate preview builder internally;
4. reconstruct the current candidate from authoritative operational journals;
5. require valid provenance;
6. require valid proposed CaseMemory using `validate_case_memory()`;
7. recompute the current fingerprint;
8. require exact equality with the supplied normalized fingerprint before any persistence gate is entered.

If the fingerprint does not match, promotion is refused. Lighthouse instructs the Operator to preview again and must not offer to approve the changed candidate within the same command.

A matching fingerprint proves only that the Operator approved the exact reconstructed candidate. It does not replace deterministic validity checks.

## Explicit Operator authority

C02 does not use generic `memory_policy.py` direct-source approval as case-promotion authority.

The existing generic memory policy may continue serving its existing purposes, but direct trust of sources such as `journal`, `engine`, or `telemetry` cannot authorize a turn-derived C02 case promotion.

For this path, explicit fingerprint-bound Operator approval is mandatory.

## Case epistemic source remains unchanged

C01 proposes conservative cases such as:

- `source = system_generated`
- `status = unresolved`
- `confidence = low`

C02 approval means "store this exact evidence-derived case," not "certify the diagnosis as true or resolved."

C02 therefore must not silently transform source, status, confidence, causal claims, action, outcome, or any other CaseMemory content during approval.

Promotion authority is recorded separately in the audit journal.

## Promotion audit journal

C02 introduces:

`memory/case_promotions.jsonl`

with:

- `CASE_PROMOTION_AUDIT_SCHEMA_VERSION = 1`
- `CASE_PROMOTION_POLICY_VERSION = "case_promotion_v1_5"`

Each event contains at minimum:

- schema version
- policy version
- event id
- promotion id
- created at
- event type
- source turn id
- candidate id
- candidate fingerprint
- case id
- operator approved
- approval method
- decision
- persisted
- case write performed
- reason

`approval_method` is `explicit_candidate_fingerprint`.

### Promotion and event identities

`promotion_id` is deterministic for one exact approved candidate and is derived from:

- promotion policy version
- candidate id
- candidate fingerprint

Each physical audit append receives a unique `event_id`.

Repeated attempts for the same exact candidate therefore correlate to one promotion lineage while remaining distinct events.

### Audit event types and decisions

`event_type` is either `attempt` or `outcome`.

An `attempt` event uses `decision = attempting`.

An `outcome` event uses one of:

- `promoted`
- `duplicate`
- `conflict`
- `error`

Fingerprint mismatches and structurally invalid candidates are refused before the persistence gate and do not require an ATTEMPT event in C02.

## Two-phase audit around curated persistence

C02 uses append-only evidence instead of pretending that two filesystem writes are atomic.

The persistence sequence is:

1. regenerate and validate candidate;
2. verify exact fingerprint match;
3. perform full-store duplicate/integrity check;
4. append promotion ATTEMPT audit event;
5. only if ATTEMPT succeeds, append the curated case where required;
6. append promotion OUTCOME audit event;
7. return a result that truthfully reports both curated state and audit completeness.

The ATTEMPT event is the evidence that an exact candidate was explicitly authorized before curated mutation occurred.

## Full-store duplicate and integrity semantics

C02 must inspect the complete curated case store, not a bounded recent subset. The duplicate/integrity check therefore uses the equivalent of:

`read_case_memories(limit=None)`

The existing `save_case_memory()` duplicate preflight must also be hardened to inspect all case memories rather than the normal bounded default view.

Three cases exist.

### No existing matching case id

The candidate is eligible for a new append after ATTEMPT audit succeeds.

### Same case id and equivalent meaningful case content

This is idempotent duplicate state:

- no second curated case append
- outcome decision: `duplicate`
- the approved proposed case is already persisted

### Same case id and different meaningful case content

This is an integrity conflict:

- no overwrite
- no second conflicting case under the same id
- outcome decision: `conflict`
- the approved proposed case is not considered persisted

## Deterministic case equivalence

The low-level JSONL store may inject storage metadata such as `schema_version` when absent.

C02 requires a narrow deterministic `case_records_equivalent(existing_case, proposed_case)` comparison that ignores only storage-layer metadata injected by the store and compares all meaningful CaseMemory domain content.

Meaningful domain fields include, as applicable:

- case id
- created at
- updated at
- status
- confidence
- source
- case card
- evidence
- process trace
- memory usage trace
- lifecycle

The comparison is exact deterministic equality after normalization. It is not fuzzy or semantic matching and never calls a model.

If any meaningful domain field differs, the records conflict.

## Promotion result contract

C02 introduces a stable `CaseMemoryPromotionResult` containing:

- status
- decision
- message
- source turn id
- candidate id
- candidate fingerprint
- promotion id
- case id
- persisted
- case write performed
- audit complete
- errors
- warnings

### Status values

- `ok`
- `refused`
- `duplicate`
- `conflict`
- `partial`
- `error`

### Decision values

- `promoted`
- `refused`
- `duplicate`
- `conflict`
- `error`

### Field semantics

`persisted` means the exact approved proposed case exists in curated memory after the operation.

`case_write_performed` means this specific invocation appended a new curated case record.

`audit_complete` means the required audit evidence for this invocation completed successfully.

This makes duplicate and partial states unambiguous:

Successful new promotion:

- status: `ok`
- decision: `promoted`
- persisted: `true`
- case_write_performed: `true`
- audit_complete: `true`

Idempotent duplicate:

- status: `duplicate`
- decision: `duplicate`
- persisted: `true`
- case_write_performed: `false`
- audit_complete: `true`

Post-write audit failure:

- status: `partial`
- decision: `promoted`
- persisted: `true`
- case_write_performed: `true`
- audit_complete: `false`

Integrity conflict:

- status: `conflict`
- decision: `conflict`
- persisted: `false`
- case_write_performed: `false`

## Failure semantics

### ATTEMPT audit failure

If the pre-write ATTEMPT event cannot be appended:

- no curated case write may occur
- status: `error`
- decision: `error`
- persisted: `false`
- case_write_performed: `false`
- audit_complete: `false`

### Curated case append failure

If the case append fails after successful ATTEMPT:

- C02 attempts an OUTCOME event with decision `error`
- status: `error`
- decision: `error`
- persisted: `false`
- case_write_performed: `false`
- `audit_complete` reflects whether the error OUTCOME append succeeded

### Curated append succeeds and final audit succeeds

- status: `ok`
- decision: `promoted`
- persisted: `true`
- case_write_performed: `true`
- audit_complete: `true`

### Curated append succeeds but final audit fails

- status: `partial`
- decision: `promoted`
- persisted: `true`
- case_write_performed: `true`
- audit_complete: `false`

The Operator-facing result must clearly state that the case was already persisted and must never imply that no mutation occurred.

No rollback or deletion is attempted.

## Safe retry after partial success

If a case append succeeds but final audit fails, repeating the same exact approval is safe.

The regenerated candidate and same fingerprint lead the full-store integrity gate to find the already-persisted equivalent case. C02 returns duplicate, reports `persisted=true` and `case_write_performed=false`, and does not append the case again. A new ATTEMPT/OUTCOME sequence can complete the evidence trail.

Idempotency is the recovery mechanism; C02 does not introduce rollback.

## Concurrency boundary

C02 is designed for Lighthouse's current single-Operator local CLI execution model.

C02 does not add multi-process locking, transactional databases, distributed coordination, or concurrent promotion arbitration.

A narrow read-check-write interval remains. This is accepted for V1.5. If Lighthouse later permits concurrent processes or agents to write curated memory, this boundary must be redesigned before those writers are authorized.

## Side-effect boundary

C02 may write only:

- `memory/case_promotions.jsonl`
- `data/memory/cases.jsonl`

It must not invoke or mutate:

- model invocation paths
- tool executors
- Windows action layers
- unrelated memory writers
- lifecycle mutation paths

## Automated acceptance criteria

### Fingerprint

- same candidate produces same fingerprint
- changed Operator feedback changes fingerprint
- changed provenance changes fingerprint
- changed proposed case changes fingerprint
- presentation-only/derived fields do not affect fingerprint
- uppercase valid hexadecimal input normalizes safely
- malformed length or non-hex input is refused

### Authority

- missing fingerprint cannot persist
- malformed fingerprint cannot persist
- mismatched fingerprint cannot persist
- invalid provenance cannot persist
- invalid case cannot persist
- generic memory-policy trust cannot substitute for explicit Operator approval
- no caller-supplied candidate payload can bypass internal regeneration

### Persistence and integrity

- valid exact approval writes exactly one case
- same exact approval repeated leaves exactly one case
- duplicate result reports persisted=true and case_write_performed=false
- same case id plus equivalent content is duplicate
- same case id plus different content is conflict
- duplicate preflight scans the complete case store

### Audit and failure handling

- ATTEMPT is written before any curated append
- ATTEMPT failure prevents curated persistence
- case write failure produces error OUTCOME when possible
- successful case write produces promoted OUTCOME
- final-audit failure produces partial with persisted=true
- retry after partial produces no duplicate curated case
- audit event ids are unique while promotion id is stable for the same exact candidate

### Side-effect isolation

Promotion tests must fail immediately if C02 invokes:

- a model
- a tool executor
- Windows mutation/action code
- unrelated memory writers

## Regression acceptance

Accepted C01 baseline:

- 650 passed
- 5 skipped
- 0 failed

C02 may not regress this baseline.

Before merge, run:

- focused C02 tests
- relevant C01/memory/CLI/safety tests
- full Lighthouse pytest suite
- Ruff on changed Python files
- Python compile/AST validation
- `git diff --check`
- GitHub Windows Pytest CI

## Live smoke-test acceptance

Automated tests prove deterministic machinery. The live smoke test validates the actual Operator workflow.

### Successful promotion

1. generate a genuine conversational turn;
2. run `case preview <turn_id>`;
3. inspect the candidate and copy its fingerprint;
4. run `case approve <turn_id> <fingerprint>`;
5. verify the expected case exists once in curated memory;
6. repeat the same approval;
7. verify duplicate/no second case;
8. inspect both promotion audit and curated case stores.

### Stale approval

1. preview a genuine turn and capture fingerprint A;
2. append/change Operator feedback for that turn;
3. attempt approval with fingerprint A;
4. approval must be refused with no new curated write;
5. preview again;
6. fingerprint B must differ from fingerprint A.

The smoke test is the final reality check that observed Lighthouse behavior matches the intended Operator-controlled memory model.

## Implementation boundaries

C02 should use a dedicated promotion service above C01 candidate reconstruction and existing case-memory persistence primitives.

Reuse:

- C01 candidate reconstruction
- `validate_case_memory()`
- existing low-level case store
- existing case manager save path where appropriate

Narrow helpers may be added for:

- candidate fingerprinting
- promotion audit journaling
- full-store equivalence checking
- promotion result formatting
- CLI parsing for `case approve`

Do not duplicate routing authority or generic memory-policy authority.

Any implementation discovery that requires changing this authority model, storage boundary, or campaign scope must stop and return to design review rather than silently widening C02.

## Final campaign definition

LH-V1.5-C02 establishes a fingerprint-bound, explicit-Operator-authorized, auditable, idempotent promotion path from a valid C01 candidate into curated CaseMemory, without granting persistence authority to models, journals, telemetry, or generic memory-policy trust.
