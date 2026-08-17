# LH-V1.5-C02 Controlled Case Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fingerprint-bound, explicit-Operator-authorized, auditable, idempotent path that promotes one valid C01 case candidate into curated CaseMemory without granting persistence authority to models, journals, telemetry, or generic memory-policy trust.

**Architecture:** Extend the existing C01 candidate boundary with deterministic fingerprinting, then add a dedicated `case_memory_promotion.py` service above C01 reconstruction and the existing case-memory manager/store. Promotion regenerates the candidate from authoritative journals, revalidates and re-fingerprints it, performs a complete-store duplicate/conflict gate, records an append-only ATTEMPT audit event, persists the exact proposed case only when authorized, and records an OUTCOME event with truthful partial-failure semantics.

**Tech Stack:** Python 3.12, dataclasses, pathlib, hashlib, json, uuid, pytest, Ruff, existing Lighthouse memory services and CLI.

## Global Constraints

- Implement only on `feature/lh-v1-5-c02-controlled-case-promotion`.
- Accepted C01 regression floor: `650 passed, 5 skipped, 0 failed`.
- Only write-authorizing CLI command: `case approve <turn_id> <fingerprint>`.
- Fingerprint input: exactly 64 hexadecimal characters, case-insensitive; normalize to lowercase internally.
- Fingerprint payload: fingerprint version, candidate schema version, candidate id, source turn id, provenance, proposed case — and nothing else.
- Explicit fingerprint-bound Operator approval is mandatory; `memory_policy.py` direct-source trust cannot authorize C02 promotion.
- C02 may write only `memory/case_promotions.jsonl` and `data/memory/cases.jsonl`.
- No model invocation, tool execution, OS mutation, semantic deduplication, lifecycle mutation, bulk/background promotion, `approve latest`, interactive confirmation shortcut, or caller-supplied candidate persistence.
- C02 assumes the current single-Operator local CLI model; no distributed locking or database work.
- If implementation requires changing authority, storage boundaries, or campaign scope, stop and return to design review.

---

## File Map

- Modify `backend/app/services/case_memory_candidate.py` — candidate fingerprint and preview output.
- Create `backend/app/services/case_memory_promotion.py` — promotion result, audit journal, exact-approval gate, duplicate/conflict classification, persistence orchestration.
- Modify `backend/app/services/memory_manager.py` — exhaustive duplicate preflight.
- Modify `backend/app/cli.py` — thin `case approve` route.
- Modify `tests/test_case_memory_candidate.py`.
- Create `tests/test_case_memory_promotion.py`.
- Modify `tests/test_memory_manager.py`.
- Modify `tests/test_cli_case_memory_candidate.py`.
- Modify `docs/commands.md`, `docs/memory_layer_architecture.md`, `docs/v1_contract_shapes.md`, and `tests/test_v1_contract_shapes.py`.

---

### Task 1: Deterministic Candidate Fingerprint

**Files:**
- Modify: `backend/app/services/case_memory_candidate.py`
- Test: `tests/test_case_memory_candidate.py`

**Produces:**

```python
CASE_MEMORY_CANDIDATE_FINGERPRINT_VERSION = "case_candidate_fingerprint_v1"

def build_case_memory_candidate_fingerprint(candidate: CaseMemoryCandidate) -> str: ...

def normalize_case_memory_candidate_fingerprint(value: str) -> str | None: ...
```

- [ ] **Step 1: Add failing fingerprint tests**

```python
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
    assert build_case_memory_candidate_fingerprint(after.candidate) != fingerprint_a


def test_fingerprint_normalization_requires_exact_sha256_hex() -> None:
    assert normalize_case_memory_candidate_fingerprint("A" * 64) == "a" * 64
    assert normalize_case_memory_candidate_fingerprint("a" * 63) is None
    assert normalize_case_memory_candidate_fingerprint("g" * 64) is None
```

Also test that changing only `validation`, `promotion`, or `safety` does not change the fingerprint, while changing provenance or proposed case does.

- [ ] **Step 2: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_case_memory_candidate.py -k "fingerprint" -q
```

- [ ] **Step 3: Implement canonical fingerprinting**

```python
import json
import re

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
    return cleaned.lower() if FINGERPRINT_PATTERN.fullmatch(cleaned) else None
```

Extend the preview report with `Candidate fingerprint:` and the exact `case approve` command; do not add writes.

- [ ] **Step 4: Run GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_case_memory_candidate.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/case_memory_candidate.py tests/test_case_memory_candidate.py
git commit -m "feat(memory): fingerprint case candidates"
```

---

### Task 2: Exhaustive Duplicate Preflight

**Files:**
- Modify: `backend/app/services/memory_manager.py`
- Test: `tests/test_memory_manager.py`

- [ ] **Step 1: Add a failing regression**

Add `test_save_case_memory_duplicate_preflight_scans_complete_store` to `tests/test_memory_manager.py`. Save one case, then at least 55 distinct valid filler cases, then attempt to save the original `case_id` again and require `status == "duplicate"`.

- [ ] **Step 2: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_memory_manager.py -k "complete_store" -q
```

- [ ] **Step 3: Make only the duplicate read exhaustive**

```python
existing_cases_result = read_case_memories(limit=None, memory_dir=memory_dir)
```

Do not change list/search defaults.

- [ ] **Step 4: Run GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_memory_manager.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/memory_manager.py tests/test_memory_manager.py
git commit -m "fix(memory): scan all cases before save"
```

---

### Task 3: Promotion Contracts, Audit Journal, and Equivalence

**Files:**
- Create: `backend/app/services/case_memory_promotion.py`
- Create: `tests/test_case_memory_promotion.py`

**Produces:**

```python
CASE_PROMOTION_AUDIT_SCHEMA_VERSION = 1
CASE_PROMOTION_POLICY_VERSION = "case_promotion_v1_5"
CASE_PROMOTION_AUDIT_FILENAME = "case_promotions.jsonl"
CASE_PROMOTION_APPROVAL_METHOD = "explicit_candidate_fingerprint"

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

- [ ] **Step 1: Add failing primitive tests**

Test:

```python
def test_case_records_equivalent_ignores_only_store_schema_version() -> None:
    proposed = {"case_id": "case-1", "created_at": "t", "status": "unresolved"}
    stored = dict(proposed, schema_version=1)
    assert case_records_equivalent(stored, proposed) is True
    assert case_records_equivalent(dict(stored, status="resolved"), proposed) is False


def test_promotion_id_is_stable_for_exact_candidate() -> None:
    assert build_case_promotion_id("candidate-1", "a" * 64) == build_case_promotion_id(
        "candidate-1", "a" * 64
    )
```

Also test that audit records append to `memory/case_promotions.jsonl`, preserve previous entries, use unique `event_id`s, and carry the required schema/policy/approval fields.

- [ ] **Step 2: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_case_memory_promotion.py -q
```

- [ ] **Step 3: Implement minimal primitives**

Implement:

```python
def build_case_promotion_id(candidate_id: str, fingerprint: str) -> str: ...
def case_promotion_journal_path(memory_dir: str | Path | None = None) -> Path: ...
def build_case_promotion_audit_event(...) -> dict[str, Any]: ...
def append_case_promotion_audit_event(event: dict[str, Any], *, memory_dir=None) -> None: ...
def read_case_promotion_audit_events(*, memory_dir=None) -> list[dict[str, Any]]: ...
def case_records_equivalent(existing_case: dict[str, Any], proposed_case: dict[str, Any]) -> bool: ...
```

For equivalence, ignore only store-injected top-level `schema_version`; compare every other meaningful domain field exactly, including `created_at` and `updated_at`.

- [ ] **Step 4: Run GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_case_memory_promotion.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/case_memory_promotion.py tests/test_case_memory_promotion.py
git commit -m "feat(memory): add case promotion audit contracts"
```

---

### Task 4: Exact-Fingerprint Promotion Orchestrator

**Files:**
- Modify: `backend/app/services/case_memory_promotion.py`
- Modify: `tests/test_case_memory_promotion.py`

**Produces:**

```python
def promote_case_memory_candidate(
    turn_id: str,
    fingerprint: str,
    *,
    operational_memory_dir: str | Path | None = None,
    curated_memory_dir: str | Path | None = None,
) -> CaseMemoryPromotionResult: ...
```

- [ ] **Step 1: Add authority/refusal tests**

Require no persistence for missing/malformed fingerprint, stale fingerprint, invalid C01 preview, invalid provenance, or invalid proposed case. Patch model invocation, tool executor, Windows action layers, and generic memory-policy evaluation to raise if promotion calls them.

- [ ] **Step 2: Add success/idempotency/conflict tests**

Require:

```text
first exact approval  -> status=ok, decision=promoted, persisted=true, case_write_performed=true
same approval again   -> status=duplicate, decision=duplicate, persisted=true, case_write_performed=false
same case_id/different meaningful content -> status=conflict, no extra case append
```

- [ ] **Step 3: Add audit-order/failure-matrix tests**

Assert ATTEMPT audit occurs before any curated save. Cover:

```text
ATTEMPT audit failure -> error, persisted=false, no save call
save failure          -> error outcome attempted, persisted=false
save + outcome success -> ok/promoted, persisted=true, audit_complete=true
save success + outcome audit failure -> partial/promoted, persisted=true, audit_complete=false
retry after partial -> duplicate, no second curated append
```

- [ ] **Step 4: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_case_memory_promotion.py -q
```

- [ ] **Step 5: Implement the gate in this order**

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

Then read the complete curated store with `read_case_memories(limit=None, ...)`, classify new/equivalent/conflict, append ATTEMPT audit, persist exactly `candidate.proposed_case` only for a new case, append OUTCOME audit, and return truthful status fields. Do not call `evaluate_memory_candidate()`.

- [ ] **Step 6: Run GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_case_memory_promotion.py -q
```

- [ ] **Step 7: Commit**

```powershell
git add backend/app/services/case_memory_promotion.py tests/test_case_memory_promotion.py
git commit -m "feat(memory): add controlled case promotion"
```

---

### Task 5: Thin CLI Approval Route

**Files:**
- Modify: `backend/app/cli.py`
- Modify: `tests/test_cli_case_memory_candidate.py`

- [ ] **Step 1: Add failing CLI tests**

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
    assert cli.run_canonical_command(f"case approve turn-example {fingerprint}") == "handled"
    assert calls == [("turn-example", fingerprint)]
    assert "Status: ok" in capsys.readouterr().out
```

Also require usage-only behavior for missing turn, missing fingerprint, extra arguments, `approve latest`, and malformed fingerprint. No implicit latest turn and no interactive prompt.

- [ ] **Step 2: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cli_case_memory_candidate.py -q
```

- [ ] **Step 3: Implement only thin routing**

Add imports for the promotion service/formatter, help text for:

```text
case approve <turn_id> <fingerprint>
```

Parse exactly two arguments after `case approve `. CLI contains no persistence logic.

- [ ] **Step 4: Run GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cli_case_memory_candidate.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add backend/app/cli.py tests/test_cli_case_memory_candidate.py
git commit -m "feat(cli): add exact case approval command"
```

---

### Task 6: Contracts, Documentation, and Verification

**Files:**
- Modify: `docs/commands.md`
- Modify: `docs/memory_layer_architecture.md`
- Modify: `docs/v1_contract_shapes.md`
- Modify: `tests/test_v1_contract_shapes.py`

- [ ] **Step 1: Freeze implemented contracts in docs**

Document exact preview/approve commands, fingerprint payload/exclusions, Operator-only authority, audit journal/event fields, result fields/statuses/decisions, duplicate semantics (`persisted=true`, `case_write_performed=false`), partial semantics (`decision=promoted`, `persisted=true`, `audit_complete=false`), and no model/tool/OS authority expansion.

- [ ] **Step 2: Run contract tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_v1_contract_shapes.py -q
```

- [ ] **Step 3: Run focused regression**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/test_case_memory_candidate.py `
  tests/test_case_memory_promotion.py `
  tests/test_memory_manager.py `
  tests/test_cli_case_memory_candidate.py `
  tests/test_v1_contract_shapes.py `
  -q
```

- [ ] **Step 4: Run full regression**

```powershell
.\.venv\Scripts\python.exe -m pytest tests -ra
```

Required: zero failures and no regression below the accepted C01 baseline.

- [ ] **Step 5: Run static/whitespace gates**

```powershell
.\.venv\Scripts\python.exe -m compileall backend tests
.\.venv\Scripts\ruff.exe check `
  backend/app/services/case_memory_candidate.py `
  backend/app/services/case_memory_promotion.py `
  backend/app/services/memory_manager.py `
  backend/app/cli.py `
  tests/test_case_memory_candidate.py `
  tests/test_case_memory_promotion.py `
  tests/test_memory_manager.py `
  tests/test_cli_case_memory_candidate.py
git diff --check
```

- [ ] **Step 6: Commit docs/contracts**

```powershell
git add docs/commands.md docs/memory_layer_architecture.md docs/v1_contract_shapes.md tests/test_v1_contract_shapes.py
git commit -m "docs(memory): document controlled case promotion"
```

- [ ] **Step 7: Final scope gate**

```powershell
git status --short
git log --oneline --decorate -10
git diff origin/main...HEAD --stat
git diff origin/main...HEAD --check
```

Do not push or open a PR until Byte source review is complete.

---

## Live Smoke-Test Gate

Run only after all automated gates are green:

1. Generate a genuine conversational turn.
2. `case preview <turn_id>` and inspect/copy the fingerprint.
3. `case approve <turn_id> <fingerprint>`.
4. Verify exactly one matching record in `data/memory/cases.jsonl`.
5. Repeat the same approval and verify duplicate/no second case.
6. Inspect `memory/case_promotions.jsonl` ATTEMPT/OUTCOME events.
7. Preview another genuine turn and capture fingerprint A.
8. Add/change Operator feedback for that turn.
9. Attempt approval with fingerprint A; it must refuse without a curated write.
10. Preview again and confirm fingerprint B differs.
11. Compare CLI claims to both on-disk append-only stores before declaring C02 complete.

## Self-Review

- Spec coverage: Tasks 1-6 cover every approved fingerprint, authority, audit, integrity, failure, CLI, side-effect, regression, and smoke-test requirement.
- Placeholder scan: no TBD/TODO or unresolved file/path placeholders remain.
- Type consistency: fingerprint helper, `CaseMemoryPromotionResult`, promotion service signature, CLI command, statuses, and decisions are consistent throughout.
- Scope check: C02 remains a single bounded persistence subsystem; no lifecycle, semantic memory, Navigator, tool, or OS work is included.
