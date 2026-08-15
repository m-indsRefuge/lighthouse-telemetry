# LH-V1.5-C02 Controlled Case Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fingerprint-bound, explicit-Operator-authorized, auditable, idempotent path that promotes one valid C01 case candidate into curated CaseMemory without granting persistence authority to models, journals, telemetry, or generic memory-policy trust.

**Architecture:** Extend the existing C01 candidate boundary with deterministic fingerprinting, then add a dedicated `case_memory_promotion.py` service above C01 reconstruction and the existing case-memory manager/store. Promotion regenerates the candidate from authoritative journals, validates and re-fingerprints it, performs a complete-store duplicate/conflict gate, records an append-only ATTEMPT audit event, persists the exact proposed case only when authorized, then records an OUTCOME event with truthful partial-failure semantics.

**Tech Stack:** Python 3.12, dataclasses, pathlib, hashlib, json, uuid, pytest, Ruff, existing Lighthouse memory services and CLI.

## Global Constraints

- Base implementation on `690bf5299964f27c7c00dc33aaa3ffcd2fb1fc8c` plus the approved C02 design commits on `feature/lh-v1-5-c02-controlled-case-promotion`.
- Existing accepted regression floor: `650 passed, 5 skipped, 0 failed`.
- The only write-authorizing CLI command is `case approve <turn_id> <fingerprint>`.
- Fingerprints are exactly 64 hexadecimal characters on input, case-insensitive, and normalized to lowercase internally.
- Fingerprint payload contains exactly fingerprint version, candidate schema version, candidate id, source turn id, provenance, and proposed case.
- Explicit fingerprint-bound Operator approval is mandatory; generic `memory_policy.py` trust never authorizes C02 promotion.
- C02 may write only `memory/case_promotions.jsonl` and `data/memory/cases.jsonl`.
- No model invocation, tool execution, OS mutation, semantic deduplication, lifecycle mutation, bulk/background promotion, `approve latest`, or caller-supplied candidate persistence.
- C02 assumes the current single-Operator local CLI model; no distributed locking or transactional database work.
- Any implementation discovery that changes authority, storage boundaries, or scope stops the task and returns to design review.

---

## File Structure

- Modify `backend/app/services/case_memory_candidate.py` — deterministic candidate fingerprinting and preview display only.
- Create `backend/app/services/case_memory_promotion.py` — promotion result contract, audit journal, exact-approval gate, duplicate/conflict logic, persistence orchestration.
- Modify `backend/app/services/memory_manager.py` — make duplicate preflight inspect the complete case store.
- Modify `backend/app/cli.py` — thin `case approve` routing and report printing.
- Modify `docs/commands.md` — document preview fingerprint and exact approval command.
- Modify `docs/memory_layer_architecture.md` — document C02 promotion/audit boundary.
- Modify `docs/v1_contract_shapes.md` — freeze fingerprint and `CaseMemoryPromotionResult` shapes.
- Modify `tests/test_case_memory_candidate.py` — fingerprint and preview regression coverage.
- Create `tests/test_case_memory_promotion.py` — authority, audit, duplicate/conflict, partial-failure, side-effect-isolation tests.
- Modify `tests/test_cli_case_memory_candidate.py` — `case approve` CLI parsing/routing tests.
- Modify `tests/test_memory_manager.py` if present; otherwise add the full-store duplicate regression to the closest existing memory-manager test module.
- Modify `tests/test_v1_contract_shapes.py` — contract documentation assertions.

---

### Task 1: Deterministic C01 Candidate Fingerprint

**Files:**
- Modify: `backend/app/services/case_memory_candidate.py`
- Modify: `tests/test_case_memory_candidate.py`

**Interfaces:**
- Consumes: existing `CaseMemoryCandidate` and `CaseMemoryCandidatePreviewResult`.
- Produces: `CASE_MEMORY_CANDIDATE_FINGERPRINT_VERSION`, `build_case_memory_candidate_fingerprint(candidate: CaseMemoryCandidate) -> str`, `normalize_case_memory_candidate_fingerprint(value: str) -> str | None`.

- [ ] **Step 1: Write failing fingerprint tests**

Add tests that build one real C01 candidate, fingerprint it twice, mutate promotion-relevant copies, and prove only meaningful changes alter the digest:

```python
from copy import deepcopy

from app.services.case_memory_candidate import (
    build_case_memory_candidate_fingerprint,
    normalize_case_memory_candidate_fingerprint,
)


def test_candidate_fingerprint_is_stable_for_same_candidate(tmp_path: Path) -> None:
    source_turn = record_turn(tmp_path, use_model=True)
    result = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)
    assert result.candidate is not None

    first = build_case_memory_candidate_fingerprint(result.candidate)
    second = build_case_memory_candidate_fingerprint(result.candidate)

    assert first == second
    assert len(first) == 64
    assert first == first.lower()


def test_candidate_fingerprint_changes_when_operator_feedback_changes(tmp_path: Path) -> None:
    source_turn = record_turn(tmp_path)
    before = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)
    assert before.candidate is not None
    fingerprint_a = build_case_memory_candidate_fingerprint(before.candidate)

    recorded = record_turn_feedback(
        turn_id=source_turn["turn_id"],
        label="corrected",
        note="Operator correction",
        memory_dir=tmp_path,
    )
    assert recorded["status"] == "ok"

    after = preview_case_memory_candidate(source_turn["turn_id"], memory_dir=tmp_path)
    assert after.candidate is not None
    fingerprint_b = build_case_memory_candidate_fingerprint(after.candidate)

    assert fingerprint_b != fingerprint_a


def test_fingerprint_normalization_requires_exact_sha256_hex() -> None:
    assert normalize_case_memory_candidate_fingerprint("A" * 64) == "a" * 64
    assert normalize_case_memory_candidate_fingerprint("a" * 63) is None
    assert normalize_case_memory_candidate_fingerprint("g" * 64) is None
```

Also add a direct unit test that constructs a copied `CaseMemoryCandidate` with changed `validation`, `promotion`, and `safety` while keeping lineage/provenance/proposed_case unchanged; the fingerprint must remain equal.

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_case_memory_candidate.py -k "fingerprint" -q
```

Expected: failures because the fingerprint helpers do not yet exist.

- [ ] **Step 3: Implement canonical fingerprint helpers**

Add:

```python
import json
import re

CASE_MEMORY_CANDIDATE_FINGERPRINT_VERSION = "case_candidate_fingerprint_v1"
FINGERPRINT_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def build_case_memory_candidate_fingerprint(candidate: CaseMemoryCandidate) -> str:
    payload = {
        "fingerprint_version": CASE_MEMORY_CANDIDATE_FINGERPRINT_VERSION,
        "candidate_schema_version": candidate.schema_version,
        "candidate_id": candidate.candidate_id,
        "source_turn_id": candidate.source_turn_id,
        "provenance": deepcopy(candidate.provenance),
        "proposed_case": deepcopy(candidate.proposed_case),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_case_memory_candidate_fingerprint(value: str) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if FINGERPRINT_PATTERN.fullmatch(cleaned) is None:
        return None
    return cleaned.lower()
```

Extend `format_case_memory_candidate_preview_report()` so a valid candidate displays:

```text
Candidate fingerprint: <64-char fingerprint>
To approve this exact candidate:
case approve <turn_id> <fingerprint>
```

The preview must remain read-only.

- [ ] **Step 4: Run candidate tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_case_memory_candidate.py -q
```

Expected: all candidate tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add backend/app/services/case_memory_candidate.py tests/test_case_memory_candidate.py
git commit -m "feat(memory): fingerprint case candidates"
```

---

### Task 2: Full-Store Duplicate Integrity Hardening

**Files:**
- Modify: `backend/app/services/memory_manager.py`
- Test: existing memory-manager test module

**Interfaces:**
- Consumes: `read_case_memories(limit=None)`.
- Produces: existing `save_case_memory()` with exhaustive duplicate preflight; no public signature change.

- [ ] **Step 1: Write a regression that places a duplicate beyond the previous default window**

Use the real store with more than 50 valid cases, then attempt to save a case whose `case_id` matches an older record:

```python
def test_save_case_memory_duplicate_preflight_scans_complete_store(tmp_path: Path) -> None:
    original = build_case_memory(
        case_id="case-old-duplicate",
        problem="original",
        symptoms=["symptom"],
        suspected_cause="unknown",
        lesson="lesson",
        tags=["test"],
        telemetry_evidence={"availability": "not_observed"},
        event_evidence={"availability": "not_observed"},
        action_taken="none",
        outcome="unknown",
        diagnostic_steps=["step"],
        decision_notes=["note"],
    )
    assert save_case_memory(original, memory_dir=tmp_path).status == "ok"

    for index in range(55):
        filler = build_case_memory(
            case_id=f"case-filler-{index}",
            problem=f"filler {index}",
            symptoms=["symptom"],
            suspected_cause="unknown",
            lesson="lesson",
            tags=["test"],
            telemetry_evidence={"availability": "not_observed"},
            event_evidence={"availability": "not_observed"},
            action_taken="none",
            outcome="unknown",
            diagnostic_steps=["step"],
            decision_notes=["note"],
        )
        assert save_case_memory(filler, memory_dir=tmp_path).status == "ok"

    duplicate = dict(original)
    result = save_case_memory(duplicate, memory_dir=tmp_path)
    assert result.status == "duplicate"
```

- [ ] **Step 2: Run the regression and verify RED against the bounded read**

```powershell
.\.venv\Scripts\python.exe -m pytest <memory-manager-test-file> -k "complete_store" -q
```

Expected: failure if the existing bounded read hides the old duplicate.

- [ ] **Step 3: Harden the existing manager preflight**

Change only the duplicate read inside `save_case_memory()`:

```python
existing_cases_result = read_case_memories(limit=None, memory_dir=memory_dir)
```

Do not change list/search defaults.

- [ ] **Step 4: Run the memory-manager tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest <memory-manager-test-file> -q
```

- [ ] **Step 5: Commit Task 2**

```powershell
git add backend/app/services/memory_manager.py <memory-manager-test-file>
git commit -m "fix(memory): scan all cases before save"
```

---

### Task 3: Promotion Result, Audit Journal, and Domain Equivalence

**Files:**
- Create: `backend/app/services/case_memory_promotion.py`
- Create: `tests/test_case_memory_promotion.py`

**Interfaces:**
- Consumes: `CaseMemoryCandidate`, `validate_case_memory`, `read_case_memories`, `save_case_memory`, C01 fingerprint helpers.
- Produces: `CaseMemoryPromotionResult`, `case_promotion_journal_path()`, `append_case_promotion_audit_event()`, `case_records_equivalent()`, `build_case_promotion_id()`.

- [ ] **Step 1: Write failing contract/audit/equivalence tests**

Add tests for:

```python
def test_case_records_equivalent_ignores_only_store_metadata() -> None:
    proposed = {"case_id": "case-1", "created_at": "t", "status": "unresolved"}
    stored = dict(proposed, schema_version=1)
    assert case_records_equivalent(stored, proposed) is True

    changed = dict(stored, status="resolved")
    assert case_records_equivalent(changed, proposed) is False


def test_promotion_id_is_stable_for_exact_candidate() -> None:
    first = build_case_promotion_id("candidate-1", "a" * 64)
    second = build_case_promotion_id("candidate-1", "a" * 64)
    assert first == second


def test_audit_event_append_is_jsonl_and_append_only(tmp_path: Path) -> None:
    event = build_case_promotion_audit_event(
        promotion_id="promo-1",
        source_turn_id="turn-1",
        candidate_id="candidate-1",
        candidate_fingerprint="a" * 64,
        case_id="case-1",
        event_type="attempt",
        decision="attempting",
        persisted=False,
        reason="explicit exact-fingerprint approval entered persistence gate",
    )
    append_case_promotion_audit_event(event, memory_dir=tmp_path)
    records = read_case_promotion_audit_events(memory_dir=tmp_path)
    assert records == [event]
```

- [ ] **Step 2: Run promotion tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_case_memory_promotion.py -q
```

- [ ] **Step 3: Implement the minimal dedicated promotion primitives**

Use constants:

```python
CASE_PROMOTION_AUDIT_SCHEMA_VERSION = 1
CASE_PROMOTION_POLICY_VERSION = "case_promotion_v1_5"
CASE_PROMOTION_AUDIT_FILENAME = "case_promotions.jsonl"
CASE_PROMOTION_APPROVAL_METHOD = "explicit_candidate_fingerprint"
```

Define:

```python
@dataclass(frozen=True)
class CaseMemoryPromotionResult:
    status: str
    decision: str
    message: str
    source_turn_id: str
    candidate_id: str
    candidate_fingerprint: str
    promotion_id: str
    case_id: str
    persisted: bool
    case_write_performed: bool
    audit_complete: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
```

For equivalence, remove only `schema_version` from the stored copy when that key was injected by the low-level store, then compare the remaining domain dictionaries exactly. Do not ignore `created_at` because C01 supplies it as domain content.

Audit writes use `uuid4().hex` for `event_id`, UTC timestamps, sorted-key JSON, parent-directory creation, and append mode.

- [ ] **Step 4: Run promotion primitive tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_case_memory_promotion.py -q
```

- [ ] **Step 5: Commit Task 3**

```powershell
git add backend/app/services/case_memory_promotion.py tests/test_case_memory_promotion.py
git commit -m "feat(memory): add case promotion audit contracts"
```

---

### Task 4: Exact-Fingerprint Promotion Orchestrator

**Files:**
- Modify: `backend/app/services/case_memory_promotion.py`
- Modify: `tests/test_case_memory_promotion.py`

**Interfaces:**
- Consumes: `preview_case_memory_candidate(turn_id, memory_dir=...)`, `build_case_memory_candidate_fingerprint()`, `normalize_case_memory_candidate_fingerprint()`, `validate_case_memory()`, `read_case_memories(limit=None)`, `save_case_memory()`.
- Produces: `promote_case_memory_candidate(turn_id: str, fingerprint: str, *, operational_memory_dir: str | Path | None = None, curated_memory_dir: str | Path | None = None) -> CaseMemoryPromotionResult`.

- [ ] **Step 1: Write authority and refusal tests**

Cover exact 64-hex input, mismatch, invalid preview, invalid case, and absence of alternate authority:

```python
def test_promotion_refuses_stale_fingerprint_without_curated_write(tmp_path: Path) -> None:
    operational = tmp_path / "operational"
    curated = tmp_path / "curated"
    turn = record_turn(operational)
    preview = preview_case_memory_candidate(turn["turn_id"], memory_dir=operational)
    assert preview.candidate is not None
    stale = build_case_memory_candidate_fingerprint(preview.candidate)

    assert record_turn_feedback(
        turn_id=turn["turn_id"],
        label="corrected",
        note="changed after preview",
        memory_dir=operational,
    )["status"] == "ok"

    result = promote_case_memory_candidate(
        turn["turn_id"],
        stale,
        operational_memory_dir=operational,
        curated_memory_dir=curated,
    )

    assert result.status == "refused"
    assert result.persisted is False
    assert read_case_memories(limit=None, memory_dir=curated).data["entry_count"] == 0
```

Also patch model/tool/OS entrypoints to raise if called during promotion.

- [ ] **Step 2: Write success, duplicate, and conflict tests**

Test one valid exact approval writes one case, repeating it leaves one case and returns `status="duplicate"`, `persisted=True`, `case_write_performed=False`, and same ID with altered meaningful content returns conflict with no extra append.

- [ ] **Step 3: Write audit-order and failure-matrix tests**

Monkeypatch audit and save functions to record call order and inject failures:

```python
def test_attempt_audit_precedes_case_write(monkeypatch, ...):
    calls: list[str] = []
    monkeypatch.setattr(module, "append_case_promotion_audit_event", lambda *a, **k: calls.append("audit"))
    monkeypatch.setattr(module, "save_case_memory", lambda *a, **k: calls.append("case") or ok_save_result())
    ...
    assert calls[:2] == ["audit", "case"]
```

Required matrix:

- ATTEMPT audit failure => no save call, `status="error"`, `persisted=False`, `audit_complete=False`.
- save failure => OUTCOME error attempted, `status="error"`, `decision="error"`, `persisted=False`.
- save success + outcome success => `status="ok"`, `decision="promoted"`, `persisted=True`, `case_write_performed=True`, `audit_complete=True`.
- save success + outcome failure => `status="partial"`, `decision="promoted"`, `persisted=True`, `case_write_performed=True`, `audit_complete=False`.
- retry after partial => no second case append, duplicate result.

- [ ] **Step 4: Run the new orchestrator tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_case_memory_promotion.py -q
```

- [ ] **Step 5: Implement promotion in strict gate order**

Implement these checks in order:

```python
clean_turn_id = turn_id.strip() if isinstance(turn_id, str) else ""
normalized_fingerprint = normalize_case_memory_candidate_fingerprint(fingerprint)
if not clean_turn_id or normalized_fingerprint is None:
    return refused_result(...)

preview = preview_case_memory_candidate(clean_turn_id, memory_dir=operational_memory_dir)
if preview.status != "ok" or preview.candidate is None:
    return refused_result(...)

candidate = preview.candidate
if not candidate.validation.provenance_valid or not candidate.validation.case_valid:
    return refused_result(...)

current_fingerprint = build_case_memory_candidate_fingerprint(candidate)
if current_fingerprint != normalized_fingerprint:
    return refused_result(...)

case_validation = validate_case_memory(candidate.proposed_case)
if not case_validation.valid:
    return refused_result(...)
```

Then inspect `read_case_memories(limit=None, memory_dir=curated_memory_dir)`, classify no-match/equivalent/conflict, append ATTEMPT audit, and only then save the exact `candidate.proposed_case` for a new case.

Do not call `evaluate_memory_candidate()` from `memory_policy.py`.

- [ ] **Step 6: Run promotion tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_case_memory_promotion.py -q
```

- [ ] **Step 7: Commit Task 4**

```powershell
git add backend/app/services/case_memory_promotion.py tests/test_case_memory_promotion.py
git commit -m "feat(memory): add controlled case promotion"
```

---

### Task 5: Thin CLI Approval Route

**Files:**
- Modify: `backend/app/cli.py`
- Modify: `tests/test_cli_case_memory_candidate.py`

**Interfaces:**
- Consumes: `promote_case_memory_candidate()` and `format_case_memory_promotion_result()`.
- Produces: canonical CLI route `case approve <turn_id> <fingerprint>`.

- [ ] **Step 1: Write failing CLI tests**

Add:

```python
def test_case_approve_routes_exact_turn_and_fingerprint(monkeypatch, capsys) -> None:
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        cli,
        "promote_case_memory_candidate",
        lambda turn_id, fingerprint: calls.append((turn_id, fingerprint)) or object(),
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "format_case_memory_promotion_result",
        lambda result: "LIGHTHOUSE CASE PROMOTION\nStatus: ok",
        raising=False,
    )

    fingerprint = "a" * 64
    handled = cli.run_canonical_command(f"case approve turn-example {fingerprint}")
    output = capsys.readouterr().out

    assert handled == "handled"
    assert calls == [("turn-example", fingerprint)]
    assert "Status: ok" in output
```

Add missing-turn, missing-fingerprint, extra-argument, `approve latest`, and malformed-fingerprint tests. CLI must not substitute latest or prompt interactively.

- [ ] **Step 2: Run CLI tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cli_case_memory_candidate.py -q
```

- [ ] **Step 3: Add thin imports, formatter, help text, and parser**

Use exact usage:

```text
case approve <turn_id> <fingerprint>
```

Parse with whitespace splitting after `case approve `. Require exactly two arguments. Pass only those strings to the promotion service. No persistence logic belongs in `cli.py`.

- [ ] **Step 4: Run CLI tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cli_case_memory_candidate.py -q
```

- [ ] **Step 5: Commit Task 5**

```powershell
git add backend/app/cli.py tests/test_cli_case_memory_candidate.py
git commit -m "feat(cli): add exact case approval command"
```

---

### Task 6: Contract Documentation and Complete Verification

**Files:**
- Modify: `docs/commands.md`
- Modify: `docs/memory_layer_architecture.md`
- Modify: `docs/v1_contract_shapes.md`
- Modify: `tests/test_v1_contract_shapes.py`

**Interfaces:**
- Consumes: final code contracts from Tasks 1-5.
- Produces: durable C02 user/architecture/contract documentation.

- [ ] **Step 1: Update docs to match implemented behavior exactly**

Document:

```text
case preview <turn_id>
case approve <turn_id> <64-hex-fingerprint>
```

Freeze:

- fingerprint payload and exclusions;
- Operator-only authority;
- audit journal path and event fields;
- `CaseMemoryPromotionResult` fields and status/decision enums;
- duplicate result semantics: `persisted=true`, `case_write_performed=false`;
- partial semantics: `decision=promoted`, `persisted=true`, `audit_complete=false`;
- no model/tool/OS authority expansion.

- [ ] **Step 2: Update contract-shape tests and run them**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_v1_contract_shapes.py -q
```

- [ ] **Step 3: Run focused C02/C01/memory/CLI tests**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/test_case_memory_candidate.py `
  tests/test_case_memory_promotion.py `
  tests/test_cli_case_memory_candidate.py `
  tests/test_v1_contract_shapes.py `
  -q
```

Also include the existing memory-manager test module used in Task 2.

Expected: all focused tests pass.

- [ ] **Step 4: Run full Lighthouse regression**

```powershell
.\.venv\Scripts\python.exe -m pytest tests -ra
```

Required: at least the accepted C01 baseline with zero failures; the pass count should increase from 650 as C02 tests are added, while existing 5 skips may remain if unchanged.

- [ ] **Step 5: Run static and whitespace gates**

```powershell
.\.venv\Scripts\python.exe -m compileall backend tests
.\.venv\Scripts\ruff.exe check `
  backend/app/services/case_memory_candidate.py `
  backend/app/services/case_memory_promotion.py `
  backend/app/services/memory_manager.py `
  backend/app/cli.py `
  tests/test_case_memory_candidate.py `
  tests/test_case_memory_promotion.py `
  tests/test_cli_case_memory_candidate.py
git diff --check
```

All must pass.

- [ ] **Step 6: Commit documentation/contracts**

```powershell
git add docs/commands.md docs/memory_layer_architecture.md docs/v1_contract_shapes.md tests/test_v1_contract_shapes.py
git commit -m "docs(memory): document controlled case promotion"
```

- [ ] **Step 7: Run final scope gate before push**

```powershell
git status --short
git log --oneline --decorate -8
git diff origin/main...HEAD --stat
git diff origin/main...HEAD --check
```

Confirm only C02-authorized code/tests/docs plus the approved spec/plan are present.

- [ ] **Step 8: Push feature branch and open PR only after Byte review**

Do not merge directly. PR must run GitHub Windows Pytest CI and remain under Byte-Nolan final merge authority.

---

## Live Smoke-Test Gate After Automated Acceptance

Do not perform this before all automated gates are green.

1. Generate one genuine conversational turn in Lighthouse.
2. Run `case preview <turn_id>` and inspect the candidate/fingerprint.
3. Run `case approve <turn_id> <fingerprint>`.
4. Verify the case appears exactly once in `data/memory/cases.jsonl`.
5. Repeat the same approval and verify duplicate/no second case.
6. Inspect `memory/case_promotions.jsonl` for ATTEMPT/OUTCOME evidence.
7. Preview another genuine turn, capture fingerprint A, add/change Operator feedback, then attempt approval with fingerprint A.
8. Confirm stale approval is refused with no new curated write.
9. Preview again and confirm fingerprint B differs.
10. Compare CLI claims to the two on-disk append-only stores before declaring C02 complete.

## Plan Self-Review

- Spec coverage: all approved C02 authority, fingerprint, audit, duplicate/conflict, failure, side-effect, CLI, regression, and smoke-test requirements map to Tasks 1-6.
- Placeholder scan: no TODO/TBD implementation gaps remain. The only execution-time variable is the exact existing memory-manager test filename, which must be resolved from the repository before Task 2 without changing the test intent.
- Type consistency: fingerprint helper, promotion result fields, promotion service signature, CLI route, and status/decision names are consistent across tasks.
- Scope check: C02 remains one bounded persistence subsystem and does not include lifecycle, semantic memory, or OS/tool work.
