# LH-V1.5-C02 — Controlled Case Promotion Design

Date: 2026-08-15
Status: Approved design
Base: `690bf5299964f27c7c00dc33aaa3ffcd2fb1fc8c`
Branch: `feature/lh-v1-5-c02-controlled-case-promotion`

## Purpose

LH-V1.5-C02 introduces the first controlled persistence path from Lighthouse operational conversational evidence into curated CaseMemory.

C02 promotes only one exact, deterministically reconstructed C01 candidate after explicit Operator approval of that candidate's fingerprint.

The core authority rule is:

> Only explicit Operator approval of the exact candidate contents may authorize turn-derived case persistence.

Model output, journal provenance, telemetry, engine provenance, and generic memory-policy source trust never substitute for Operator approval.

## Original Lighthouse trust model preserved

C02 preserves the existing Lighthouse authority hierarchy:

1. Operator intent and approval.
2. Deterministic reconstruction and validation.
3. Explicit persistence gate.
4. Curated memory append.
5. Append-only promotion audit evidence.

Model output remains proposal-only evidence. Memory never becomes execution authority. C02 does not add tool execution or OS mutation.

## Scope

C02 adds exactly one new capability:

> Store one deterministically valid, exact-fingerprint C01 case candidate into curated case memory after explicit Operator approval.

C02 does not add automatic promotion, model-approved promotion, journal-approved promotion, semantic memory, case editing, lifecycle mutation, resolution, archival, deletion, bulk promotion, background promotion, tool execution, Navigator behavior, or OS-changing actions.

## Existing storage boundary

Operational evidence remains under:

`memory/`

Curated deterministic case memory remains under:

`data/memory/cases.jsonl`

C02 adds an operational promotion audit journal:

`memory/case_promotions.jsonl`

No memory-directory migration occurs.

## Candidate lineage and fingerprint

C01 already provides a stable `candidate_id` derived from the source turn. C02 introduces a separate fingerprint because lineage identity is not sufficient to prove that the exact candidate reviewed by the Operator is still current.

The two identities have different meanings:

- `candidate_id`: stable lineage identity for the source-turn candidate.
- `candidate_fingerprint`: exact identity of the promotion-relevant candidate state.

If Operator feedback or other promotion-relevant evidence changes, the `candidate_id` remains stable but the fingerprint must change.

### Fingerprint version

C02 defines:

`CASE_MEMORY_CANDIDATE_FINGERPRINT_VERSION = "case_candidate_fingerprint_v1"`

### Fingerprint payload

The canonical fingerprint payload contains exactly:

- fingerprint version
- candidate schema version
- candidate id
- source turn id
- candidate provenance
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

The payload is serialized as deterministic canonical JSON using UTF-8, sorted keys, and stable separators, then hashed using SHA-256. The externally displayed fingerprint is the full 64-character lowercase hexadecimal digest.

### Fingerprint exclusions

The fingerprint deliberately excludes:

- candidate validation result
- C01 preview promotion envelope
- C01 preview safety envelope
- formatted CLI/report text
- approval-time result fields
- audit timestamps and event ids

Those values are derived, presentation-specific, or operation-specific rather than part of the evidence-plus-memory state being approved.

The design rule is:

> Fingerprint = promotion-relevant evidence + proposed curated memory.

## Preview behavior

The existing command remains:

`case preview <turn_id>`

C02 extends the preview report to display:

- Candidate ID
- Candidate fingerprint
- the exact approval command for that candidate

Example:

`case approve <turn_id> <candidate_fingerprint>`

Preview remains strictly read-only. It performs no persistence, model call, tool execution, or OS mutation.

## Approval CLI

The only C02 write-authorizing command is:

`case approve <turn_id> <fingerprint>`

There is no `approve latest`, no fingerprint-omitting shorthand, no interactive yes/no bypass, and no caller-supplied candidate JSON path.

Approval must name both:

1. the exact source turn; and
2. the exact candidate fingerprint.

## Approval-time regeneration

The approval command never trusts a serialized candidate supplied by the caller.

At approval time Lighthouse must:

1. accept only `turn_id` and `fingerprint` from the Operator command;
2. call the existing C01 candidate preview builder internally;
3. reconstruct the current candidate from authoritative operational journals;
4. validate provenance;
5. validate the proposed CaseMemory using `validate_case_memory()`;
6. recompute the current fingerprint;
7. require exact equality with the supplied fingerprint before any persistence gate is entered.

If the supplied fingerprint does not match the regenerated candidate, promotion is refused and Lighthouse instructs the Operator to preview the candidate again. Lighthouse must not offer to approve the changed candidate in the same command.

## Explicit Operator authority

C02 does not use generic `memory_policy.py` direct-source approval as case-promotion authority.

The existing generic memory policy may continue to serve its existing purposes, but its direct trust of sources such as `journal`, `engine`, or `telemetry` cannot authorize a turn-derived C02 case promotion.

For this path, explicit fingerprint-bound Operator approval is mandatory.

## Case epistemic source remains unchanged

C01 currently proposes conservative cases with values such as:

- `source = system_generated`
- `status = unresolved`
- `confidence = low`

C02 approval means "store this exact evidence-derived case," not "certify this diagnosis as true or resolved."

Therefore C02 must not silently transform source, status, confidence, causal claims, action, outcome, or other case content during approval.

Promotion authority is recorded separately in the audit journal.

## Promotion audit journal

C02 introduces:

`memory/case_promotions.jsonl`

with:

- `CASE_PROMOTION_AUDIT_SCHEMA_VERSION = 1`
- `CASE_PROMOTION_POLICY_VERSION = "case_promotion_v1_5"`

Each audit event contains at minimum:

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
- reason

The approval method is:

`explicit_candidate_fingerprint`

### Promotion identity

`promotion_id` is deterministic for one exact approved candidate and is derived from:

- promotion policy version
- candidate id
- candidate fingerprint

Each physical audit append has its own unique `event_id`.

This allows repeated attempts for the same promotion to remain correlated without treating them as the same event.

## Two-phase audit around curated persistence

C02 uses append-only evidence rather than pretending that two separate filesystem writes are atomic.

The persistence sequence is:

1. regenerate and validate candidate;
2. verify exact fingerprint match;
3. perform full-store duplicate/integrity check;
4. append promotion ATTEMPT audit event;
5. only if the ATTEMPT append succeeds, append the curated case where required;
6. append promotion OUTCOME audit event;
7. return a result that truthfully reports both persistence and audit completeness.

The ATTEMPT event is the evidence that an exact candidate was explicitly authorized before curated mutation occurred.

## Duplicate and integrity semantics

C02 must inspect the complete curated case store, not a bounded recent subset.

The duplicate/integrity check therefore uses the equivalent of:

`read_case_memories(limit=None)`

The existing `save_case_memory()` duplicate preflight must also be hardened to inspect all case memories rather than the normal bounded default view.

Three cases exist:

### No existing matching case id

The candidate is eligible for a new append after the ATTEMPT audit event succeeds.

### Same case id and equivalent meaningful case content

The operation is idempotent:

- decision: duplicate
- no second curated case append
- promotion OUTCOME records duplicate

### Same case id and different meaningful case content

This is an integrity conflict:

- decision: conflict
- no overwrite
- no second conflicting case under the same id
- promotion OUTCOME records conflict

## Deterministic case equivalence

The low-level JSONL store may inject storage metadata such as `schema_version` and `created_at` when absent.

C02 therefore requires a narrow deterministic `case_records_equivalent(existing_case, proposed_case)` comparison that ignores only storage-layer metadata injected by the store and compares all meaningful CaseMemory domain fields.

The comparison is exact deterministic equality after normalization. It is not fuzzy or semantic matching and does not call a model.

Meaningful fields must include, as applicable:

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

If any meaningful domain field differs, the records conflict.

## Promotion result contract

C02 introduces a stable `CaseMemoryPromotionResult` contract containing:

- status
- decision
- message
- source turn id
- candidate id
- candidate fingerprint
- promotion id
- case id
- persisted
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

Status describes overall operation completion. Decision describes the curated-memory outcome.

This distinction is required for partial success. For example:

- status: `partial`
- decision: `promoted`
- persisted: `true`
- audit_complete: `false`

This means the curated memory mutation succeeded while the final audit append did not.

## Failure semantics

### ATTEMPT audit failure

If the pre-write ATTEMPT audit event cannot be appended:

- no curated case write may occur
- status: error
- persisted: false
- audit_complete: false

### Curated case append failure

If the curated case append fails after a successful ATTEMPT event:

- C02 attempts to append an OUTCOME event with decision `error`
- status: error
- decision: error
- persisted: false

### Curated append succeeds and final audit succeeds

- status: ok
- decision: promoted
- persisted: true
- audit_complete: true

### Curated append succeeds but final audit fails

- status: partial
- decision: promoted
- persisted: true
- audit_complete: false

The Operator-facing result must clearly state that the case was already persisted and must not imply that no mutation occurred.

No rollback or deletion is attempted.

## Safe retry after partial success

If a case append succeeds but final audit fails, repeating the same exact approval is safe.

The regenerated candidate and same fingerprint lead the full-store integrity gate to find the already-persisted equivalent case. C02 returns duplicate and does not append the case again. A new ATTEMPT/OUTCOME audit sequence can then complete the evidence trail.

This idempotency is the recovery mechanism; C02 does not introduce rollback.

## Audit scope for refused requests

Fingerprint mismatches and structurally invalid candidates are rejected before entering the persistence gate and do not require a promotion ATTEMPT event in C02.

Fingerprint-valid explicit approval attempts that reach the persistence gate are auditable, including promoted, duplicate, conflict, and write-error outcomes.

## Concurrency boundary

C02 is designed for Lighthouse's current single-Operator local CLI execution model.

C02 does not add:

- multi-process locking
- transactional databases
- distributed write coordination
- concurrent promotion arbitration

A narrow read-check-write interval therefore remains. This is accepted for V1.5. If Lighthouse later supports concurrent processes or agents capable of curated-memory writes, this boundary must be redesigned before those writers are authorized.

## Side-effect boundary

C02 may write only:

- `memory/case_promotions.jsonl`
- `data/memory/cases.jsonl`

It must not call or mutate:

- model invocation paths
- tool executors
- Windows action layers
- unrelated memory stores
- lifecycle mutation paths

## Hard exclusions

The following are explicitly outside C02:

- automatic promotion
- model-approved promotion
- journal-approved promotion
- semantic deduplication
- case editing
- case resolution
- case archival
- case deletion
- memory consolidation
- memory ranking changes
- semantic memory
- Navigator
- OS actions
- tool execution
- background promotion
- bulk promotion
- `approve latest`
- interactive confirmation shortcuts

## Automated acceptance criteria

### Fingerprint tests

- same candidate produces same fingerprint
- changed Operator feedback changes fingerprint
- changed provenance changes fingerprint
- changed proposed case changes fingerprint
- presentation-only/derived fields do not affect fingerprint

### Authority tests

- missing fingerprint cannot persist
- malformed fingerprint cannot persist
- mismatched fingerprint cannot persist
- invalid provenance cannot persist
- invalid case cannot persist
- generic memory-policy trust cannot substitute for explicit Operator approval
- no caller-supplied candidate payload can bypass regeneration

### Persistence tests

- valid exact approval writes exactly one case
- same exact approval repeated leaves exactly one case
- same case id plus equivalent content is duplicate
- same case id plus different content is conflict
- duplicate preflight scans the complete case store

### Audit tests

- ATTEMPT is written before any curated case append
- ATTEMPT write failure prevents curated persistence
- case write failure produces error outcome when possible
- successful case write produces promoted outcome
- final-audit failure produces partial with persisted=true
- retry after partial produces no duplicate curated case

### Side-effect isolation tests

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

Automated tests prove the deterministic machinery. The live smoke test validates the real Operator workflow.

### Successful promotion smoke test

1. generate a genuine conversational turn;
2. run `case preview <turn_id>`;
3. inspect the candidate and copy its fingerprint;
4. run `case approve <turn_id> <fingerprint>`;
5. verify the expected case exists once in curated memory;
6. repeat the same approval;
7. verify duplicate/no second case;
8. inspect both the promotion audit journal and curated case store.

### Stale approval smoke test

1. preview a genuine turn and capture fingerprint A;
2. append/change Operator feedback for that turn;
3. attempt approval with fingerprint A;
4. approval must be refused with no new curated write;
5. preview again;
6. fingerprint B must differ from fingerprint A.

The smoke test is the final reality check that Lighthouse's observed behavior matches the intended Operator-controlled memory model.

## Implementation boundaries

C02 implementation should prefer a dedicated promotion service above C01 candidate reconstruction and existing case-memory persistence primitives.

The implementation should reuse:

- C01 candidate reconstruction
- `validate_case_memory()`
- existing low-level case memory store
- existing case manager save path where appropriate

It must not duplicate routing or memory-policy authority.

The implementation may add narrowly scoped helpers for:

- candidate fingerprinting
- promotion audit journaling
- full-store equivalence checking
- promotion result formatting
- CLI parsing for `case approve`

Any implementation discovery that requires changing the authority model, storage boundary, or scope defined here must stop and return to design review rather than silently widening C02.

## Final campaign definition

LH-V1.5-C02 establishes a fingerprint-bound, explicit-Operator-authorized, auditable, idempotent promotion path from a valid C01 candidate into curated CaseMemory, without granting persistence authority to models, journals, telemetry, or generic memory-policy trust.
