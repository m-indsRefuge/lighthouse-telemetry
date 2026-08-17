# LH-V1.5-C03 Deterministic Memory Laboratory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, isolated memory laboratory that exercises the real C01/C02 turn → candidate → fingerprint → Operator approval → audited persistence → retrieval path across staged 50, 250, and 1,000-cycle campaigns without adding production auto-approval or case lifecycle mutation.

**Architecture:** C03 adds a developer-only laboratory layer around existing Lighthouse services. Scenario generation, fixture construction, authority guards, cycle orchestration, evidence writing, and the command-line runner remain separate, focused units; measured promotion actions always call the existing C02 service, while direct fixture writes are permitted only for declared isolated adversarial preconditions. The formal campaign accumulates state in one isolated operational/curated store pair so the 1,000-cycle run exercises sustained memory growth rather than 1,000 unrelated temporary tests.

**Tech Stack:** Python 3.12, standard library (`dataclasses`, `pathlib`, `json`, `random`, `hashlib`, `contextlib`, `unittest.mock`, `argparse`), existing Lighthouse C01/C02 services, pytest 9.x, Ruff.

## Global Constraints

- Base C03 work on `main` after C02 merge commit `5f0839f1eede4ae333e8c6da77b10752a6b4eb6c` and preserve the approved C03 spec already committed on `feature/lh-v1-5-c03-deterministic-memory-lab`.
- At execution time, create/use an isolated worktree through `superpowers:using-git-worktrees`; do not implement in the original dirty Lighthouse checkout.
- Formal campaigns must disable LLM/Ollama use and actively trap model calls.
- Formal campaigns must not execute tools, subprocesses, OS commands, or Windows mutations.
- Formal campaigns must not call generic memory-policy approval as persistence authority.
- Measured turn-derived case persistence must always pass through `promote_case_memory_candidate()`.
- `TestOperatorSimulator` must never receive `save_case_memory()`, low-level JSONL writers, or direct curated-store access.
- Direct fixture writes are permitted only in isolated campaign directories for explicit conflict/retrieval preconditions and must be declared in cycle evidence.
- Duplicate preconditions must be created through the real C02 promotion path, not fixture seeding.
- C03 must not add case resolution, reopening, archival, editing, consolidation, semantic deduplication, background memory management, model-assisted retrieval, production auto-approval, tool execution, or Windows actions.
- Generated campaign evidence must not be committed to Git.
- Formal 50-cycle quotas are exactly `20/10/8/5/5/2` for normal/duplicate/stale/conflict/retrieval/failure.
- Formal 250-cycle quotas are exactly `100/50/38/25/25/12`.
- Formal 1,000-cycle quotas are exactly `400/200/150/100/100/50`.
- The 1,000-cycle campaign is a fail-fast acceptance run and is GREEN only with zero unexpected writes, zero accepted stale approvals, zero physical duplicates, zero conflict overwrites, zero audit inconsistencies, zero forbidden authority crossings, and 100% required retrieval assertions.
- The optional 5,000-cycle durability run is not required for C03 completion.
- Existing Lighthouse regression behavior must remain unchanged.

---

## File Map

### New service files

- `backend/app/services/memory_lab_contracts.py` — versioned C03 dataclasses, family/status constants, campaign paths/config/result serialization.
- `backend/app/services/memory_lab_scenarios.py` — fixed quota policy and deterministic scenario schedule/detail generation.
- `backend/app/services/memory_lab_fixtures.py` — isolated precondition seeding, strict JSONL inspection, failure injection, and forbidden-authority guard contexts.
- `backend/app/services/memory_lab.py` — TestOperatorSimulator, one-cycle orchestration, campaign orchestration, invariant evaluation, and evidence persistence.
- `scripts/run_memory_lab.py` — developer-only runner; no production Lighthouse CLI wiring.

### New tests

- `tests/test_memory_lab_contracts.py`
- `tests/test_memory_lab_scenarios.py`
- `tests/test_memory_lab_fixtures.py`
- `tests/test_memory_lab.py`
- `tests/test_memory_lab_runner.py`

### Modified files

- `.gitignore` — ignore generated `validation/memory_lab_runs/` evidence.
- `docs/memory_layer_architecture.md` — document C03 as validation infrastructure, not memory authority.
- `docs/v1_contract_shapes.md` — freeze C03 cycle/campaign result contracts.

---

### Task 1: Freeze Memory Laboratory Contracts

**Files:**
- Create: `backend/app/services/memory_lab_contracts.py`
- Create: `tests/test_memory_lab_contracts.py`

**Interfaces:**
- Produces: `MEMORY_LAB_SCHEMA_VERSION`, six family constants, three campaign status constants, `MemoryLabPaths`, `MemoryLabCampaignConfig`, `MemoryLabScenario`, `MemoryLabCycleResult`, `MemoryLabCampaignResult`.
- Later tasks must import these contracts rather than invent parallel dict shapes.

- [ ] **Step 1: Write failing contract-order and serialization tests**

```python
from dataclasses import fields
from pathlib import Path

from app.services.memory_lab_contracts import (
    MEMORY_LAB_SCHEMA_VERSION,
    MemoryLabCycleResult,
    MemoryLabPaths,
)


def test_cycle_result_field_order_is_stable() -> None:
    assert [field.name for field in fields(MemoryLabCycleResult)] == [
        "schema_version",
        "campaign_id",
        "seed",
        "cycle_index",
        "scenario_family",
        "scenario_id",
        "source_turn_id",
        "candidate_id",
        "candidate_fingerprints",
        "fixture_case_ids",
        "injected_failure",
        "expected_status",
        "actual_status",
        "expected_decision",
        "actual_decision",
        "expected_persisted",
        "actual_persisted",
        "case_count_before",
        "case_count_after",
        "audit_count_before",
        "audit_count_after",
        "retrieval_expected_case_id",
        "retrieval_observed_case_ids",
        "retry_decision",
        "passed",
        "trust_boundary_violation",
        "errors",
        "warnings",
    ]


def test_memory_lab_paths_stay_under_campaign_root(tmp_path: Path) -> None:
    paths = MemoryLabPaths.from_root(tmp_path / "campaign")
    assert paths.operational_dir == paths.root / "operational"
    assert paths.curated_dir == paths.root / "curated"
    assert paths.manifest_path == paths.root / "campaign_manifest.json"
    assert paths.cycle_results_path == paths.root / "cycle_results.jsonl"
    assert paths.summary_path == paths.root / "campaign_summary.json"
```

- [ ] **Step 2: Run the focused tests and verify they fail because the contracts do not exist**

Run:

```powershell
python -m pytest tests/test_memory_lab_contracts.py -q
```

Expected: import/collection failure for `app.services.memory_lab_contracts`.

- [ ] **Step 3: Implement the minimal versioned contracts**

Use this exact contract direction:

```python
MEMORY_LAB_SCHEMA_VERSION = "memory_lab_v1_5_c03"

SCENARIO_NORMAL = "normal_promotion"
SCENARIO_DUPLICATE = "duplicate_replay"
SCENARIO_STALE = "stale_evidence"
SCENARIO_CONFLICT = "conflict_protection"
SCENARIO_RETRIEVAL = "retrieval_discrimination"
SCENARIO_FAILURE = "controlled_failure_integrity"

CAMPAIGN_STATUS_GREEN = "green"
CAMPAIGN_STATUS_FAILED = "failed"
CAMPAIGN_STATUS_ABORTED = "aborted"

@dataclass(frozen=True)
class MemoryLabPaths:
    root: Path
    operational_dir: Path
    curated_dir: Path
    manifest_path: Path
    cycle_results_path: Path
    summary_path: Path

    @classmethod
    def from_root(cls, root: str | Path) -> "MemoryLabPaths":
        resolved_root = Path(root)
        return cls(
            root=resolved_root,
            operational_dir=resolved_root / "operational",
            curated_dir=resolved_root / "curated",
            manifest_path=resolved_root / "campaign_manifest.json",
            cycle_results_path=resolved_root / "cycle_results.jsonl",
            summary_path=resolved_root / "campaign_summary.json",
        )
```

`MemoryLabScenario` must include `scenario_id`, `family`, `user_request`, `feedback_label`, `feedback_note`, `fixture_case_ids`, `retrieval_query`, `retrieval_expected_case_id`, `injected_failure`, `expected_status`, `expected_decision`, and `expected_persisted`.

`MemoryLabCycleResult` must use the tested field order above and `to_dict()` must convert tuples to JSON lists.

`MemoryLabCampaignResult` must include all minimum fields from the approved spec plus `to_dict()`.

- [ ] **Step 4: Run contract tests**

```powershell
python -m pytest tests/test_memory_lab_contracts.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```powershell
git add backend/app/services/memory_lab_contracts.py tests/test_memory_lab_contracts.py
git commit -m "feat(memory): add C03 memory lab contracts"
```

---

### Task 2: Deterministic Scenario Quotas and Schedule

**Files:**
- Create: `backend/app/services/memory_lab_scenarios.py`
- Create: `tests/test_memory_lab_scenarios.py`

**Interfaces:**
- Consumes: family constants and `MemoryLabScenario` from Task 1.
- Produces: `FORMAL_SCENARIO_QUOTAS`, `scenario_quotas_for_cycles(cycles)`, `build_scenario_schedule(cycles, seed)`, `build_memory_lab_scenarios(cycles, seed)`.

- [ ] **Step 1: Write quota and replay tests**

```python
from collections import Counter

from app.services.memory_lab_scenarios import (
    build_memory_lab_scenarios,
    scenario_quotas_for_cycles,
)


def test_formal_quota_tables_are_exact() -> None:
    assert scenario_quotas_for_cycles(50) == {
        "normal_promotion": 20,
        "duplicate_replay": 10,
        "stale_evidence": 8,
        "conflict_protection": 5,
        "retrieval_discrimination": 5,
        "controlled_failure_integrity": 2,
    }
    assert sum(scenario_quotas_for_cycles(250).values()) == 250
    assert sum(scenario_quotas_for_cycles(1000).values()) == 1000


def test_same_seed_replays_same_logical_scenarios() -> None:
    first = build_memory_lab_scenarios(50, seed=20260817)
    second = build_memory_lab_scenarios(50, seed=20260817)
    assert [scenario.to_dict() for scenario in first] == [
        scenario.to_dict() for scenario in second
    ]


def test_formal_schedule_matches_required_family_counts() -> None:
    scenarios = build_memory_lab_scenarios(1000, seed=20260817)
    counts = Counter(scenario.family for scenario in scenarios)
    assert counts == scenario_quotas_for_cycles(1000)
```

Also test development counts 1–10 use canonical round-robin and reject unsupported non-formal counts such as 11 or 125.

- [ ] **Step 2: Run the tests and verify they fail**

```powershell
python -m pytest tests/test_memory_lab_scenarios.py -q
```

Expected: module/function import failures.

- [ ] **Step 3: Implement exact quota policy and deterministic shuffle**

```python
FORMAL_SCENARIO_QUOTAS = {
    50: {
        SCENARIO_NORMAL: 20,
        SCENARIO_DUPLICATE: 10,
        SCENARIO_STALE: 8,
        SCENARIO_CONFLICT: 5,
        SCENARIO_RETRIEVAL: 5,
        SCENARIO_FAILURE: 2,
    },
    250: {
        SCENARIO_NORMAL: 100,
        SCENARIO_DUPLICATE: 50,
        SCENARIO_STALE: 38,
        SCENARIO_CONFLICT: 25,
        SCENARIO_RETRIEVAL: 25,
        SCENARIO_FAILURE: 12,
    },
    1000: {
        SCENARIO_NORMAL: 400,
        SCENARIO_DUPLICATE: 200,
        SCENARIO_STALE: 150,
        SCENARIO_CONFLICT: 100,
        SCENARIO_RETRIEVAL: 100,
        SCENARIO_FAILURE: 50,
    },
}
```

For optional durability support, derive 5,000 cycles as exactly five times the 1,000-cycle quotas; do not add a new weighting policy.

Build the formal schedule by expanding the quota multiset and shuffling with a local `random.Random` seeded from the versioned string:

```python
rng = random.Random(f"{MEMORY_LAB_SCHEMA_VERSION}:{seed}:{cycles}")
rng.shuffle(families)
```

Build `scenario_id` as the first 20 hex characters of SHA-256 over `schema_version|seed|cycles|cycle_index|family`.

Use the known deterministic request text `"why is my laptop feeling slow right now"` for promotion-bearing scenarios. Retrieval scenarios use distinct deterministic tokens such as `memorylab-relevant-<scenario_id>` and `memorylab-distractor-<scenario_id>`.

Failure scenarios rotate deterministically through `attempt_audit`, `curated_save`, and `outcome_audit` based on their ordinal within the failure family. Expected values:

- `attempt_audit` → status `error`, decision `error`, persisted `False`.
- `curated_save` → status `error`, decision `error`, persisted `False`.
- `outcome_audit` → status `partial`, decision `promoted`, persisted `True`, then retry must be `duplicate`.

- [ ] **Step 4: Run scenario tests**

```powershell
python -m pytest tests/test_memory_lab_scenarios.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```powershell
git add backend/app/services/memory_lab_scenarios.py tests/test_memory_lab_scenarios.py
git commit -m "feat(memory): generate deterministic memory lab scenarios"
```

---

### Task 3: Isolated Fixtures, Strict Inspectors, and Authority Guards

**Files:**
- Create: `backend/app/services/memory_lab_fixtures.py`
- Create: `tests/test_memory_lab_fixtures.py`

**Interfaces:**
- Consumes: `MemoryLabPaths`.
- Produces: `assert_isolated_campaign_paths(paths)`, `build_fixture_case(...)`, `seed_case_fixture(...)`, `read_jsonl_strict(path)`, `inspect_case_store(paths)`, `inspect_promotion_audit(paths)`, `promotion_failure_injection(name)`, `forbidden_authority_guard()`.

- [ ] **Step 1: Write isolation and corruption tests**

```python
import json
from pathlib import Path

import pytest

from app.services.conversational_engine_turn import DEFAULT_MEMORY_DIR
from app.services.memory_lab_contracts import MemoryLabPaths
from app.services.memory_lab_fixtures import (
    assert_isolated_campaign_paths,
    inspect_case_store,
)
from app.services.memory_store import MEMORY_DIR


def test_fixture_boundary_refuses_real_lighthouse_memory_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        assert_isolated_campaign_paths(
            MemoryLabPaths.from_root(DEFAULT_MEMORY_DIR.parent)
        )
    with pytest.raises(ValueError):
        assert_isolated_campaign_paths(
            MemoryLabPaths.from_root(MEMORY_DIR.parent)
        )


def test_strict_case_inspector_rejects_malformed_jsonl(tmp_path: Path) -> None:
    paths = MemoryLabPaths.from_root(tmp_path / "campaign")
    paths.curated_dir.mkdir(parents=True)
    (paths.curated_dir / "cases.jsonl").write_text(
        '{"case_id":"ok"}\nnot-json\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Malformed JSONL"):
        inspect_case_store(paths)
```

Also write tests that a fixture case validates through `validate_case_memory()`, duplicate physical `case_id` rows are detected, and fixture seeding cannot escape `paths.curated_dir`.

- [ ] **Step 2: Run fixture tests and verify failure**

```powershell
python -m pytest tests/test_memory_lab_fixtures.py -q
```

Expected: import/function failures.

- [ ] **Step 3: Implement the valid fixture case builder using the existing CaseMemory schema**

Use the production validator and existing constants, not a laboratory schema. The fixture shape must include the complete fields already required by `validate_case_memory()`:

```python
return {
    "case_id": case_id,
    "created_at": "2026-08-17T00:00:00+00:00",
    "updated_at": "2026-08-17T00:00:00+00:00",
    "status": CASE_STATUS_RESOLVED,
    "confidence": CASE_CONFIDENCE_HIGH,
    "source": CASE_SOURCE_OPERATOR_CONFIRMED,
    "case_card": {
        "problem": f"Synthetic memory lab case {search_token}",
        "symptoms": [f"symptom {search_token}"],
        "suspected_cause": f"cause {search_token}",
        "lesson": f"lesson {search_token}",
        "tags": [search_token],
    },
    "evidence": {
        "telemetry_evidence": {},
        "event_evidence": {},
        "action_taken": f"fixture action {search_token}",
        "outcome": f"fixture outcome {search_token}",
    },
    "process_trace": {
        "diagnostic_steps": ["C03 isolated fixture construction"],
        "decision_notes": ["Fixture exists only for a declared lab precondition."],
        "operator_feedback": "Synthetic C03 fixture.",
    },
    "memory_usage_trace": {
        "memory_context_used": False,
        "retrieved_case_ids": [],
        "retrieved_knowledge_ids": [],
        "retrieved_baseline_keys": [],
        "memory_influence": MEMORY_INFLUENCE_NONE,
        "memory_result": MEMORY_RESULT_NOT_USED,
        "memory_relevance_score": 0.0,
        "memory_relevance_label": RELEVANCE_LABEL_NONE,
        "retrieved_memory_scores": [],
        "memory_notes": [],
    },
    "lifecycle": {
        "use_count": 0,
        "last_used_at": None,
        "pinned": False,
        "retention_policy": RETENTION_STANDARD,
    },
}
```

If the exact constant names for `NONE`/`NOT_USED` differ in `memory_cases.py`, use the existing repository constants that validate the equivalent zero-influence state; do not hard-code unvalidated strings.

`seed_case_fixture()` must call `validate_case_memory()` first and then `save_case_memory(case, memory_dir=paths.curated_dir)` only after `assert_isolated_campaign_paths(paths)` passes.

- [ ] **Step 4: Implement strict store/audit inspection**

`read_jsonl_strict()` must fail on malformed, blank-object, or non-object records instead of silently skipping them. `inspect_case_store()` returns ordered records, total count, duplicate `case_id` values, and a SHA-256 digest of canonical JSON domain rows for before/after comparisons.

`inspect_promotion_audit()` performs the same strict parsing for `case_promotions.jsonl` and returns event counts grouped by `event_type`/`decision`.

- [ ] **Step 5: Implement controlled failure injection and forbidden-authority guard**

Use `unittest.mock.patch` context managers, not production switches.

`promotion_failure_injection("attempt_audit")` patches `app.services.case_memory_promotion.append_case_promotion_audit_event` to raise `OSError` on the attempt.

`promotion_failure_injection("curated_save")` patches `app.services.case_memory_promotion.save_case_memory` to return a result-like object with `status="error"`, `errors=("C03 injected curated save failure",)`, `warnings=()`.

`promotion_failure_injection("outcome_audit")` wraps the real audit append function and raises only when `event["event_type"] == "outcome"`.

`forbidden_authority_guard()` must patch these boundaries to raise `AssertionError("C03 forbidden authority crossing")` if called:

```python
app.services.llm.call_ollama
app.services.llm_route_engine.call_ollama
app.services.tool_executor.execute_registered_tool
app.services.tool_executor.execute_tool_plan
app.services.memory_policy.evaluate_memory_candidate
app.services.memory_policy.evaluate_memory_candidate_dict
subprocess.run
subprocess.Popen
os.system
```

Within the same guard, patch `app.services.llm_route_engine.is_ollama_enabled` to return `False`; the raising `call_ollama` patches prove no model call occurs even if a regression bypasses the disabled check.

- [ ] **Step 6: Run fixture/guard tests**

```powershell
python -m pytest tests/test_memory_lab_fixtures.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```powershell
git add backend/app/services/memory_lab_fixtures.py tests/test_memory_lab_fixtures.py
git commit -m "feat(memory): isolate memory lab fixtures and guards"
```

---

### Task 4: Real C01/C02 Cycle Orchestration for Normal, Duplicate, and Stale Scenarios

**Files:**
- Create: `backend/app/services/memory_lab.py`
- Create: `tests/test_memory_lab.py`

**Interfaces:**
- Consumes: `build_conversational_engine_turn(user_request, memory_dir=...)`, `preview_case_memory_candidate(turn_id, memory_dir=...)`, `build_case_memory_candidate_fingerprint(candidate)`, `record_turn_feedback(...)`, `promote_case_memory_candidate(...)`, strict inspectors, contracts/scenarios.
- Produces: `TestOperatorSimulator`, `run_memory_lab_cycle(scenario, *, paths, campaign_id, seed) -> MemoryLabCycleResult`.

- [ ] **Step 1: Write a real normal-promotion cycle test**

```python
from app.services.memory_lab import run_memory_lab_cycle
from app.services.memory_lab_contracts import MemoryLabPaths
from app.services.memory_lab_scenarios import build_memory_lab_scenarios


def test_normal_cycle_uses_real_c02_and_writes_one_case(tmp_path) -> None:
    scenario = next(
        item
        for item in build_memory_lab_scenarios(6, seed=1)
        if item.family == "normal_promotion"
    )
    result = run_memory_lab_cycle(
        scenario,
        paths=MemoryLabPaths.from_root(tmp_path / "campaign"),
        campaign_id="campaign-test",
        seed=1,
    )
    assert result.passed is True
    assert result.actual_decision == "promoted"
    assert result.actual_persisted is True
    assert result.case_count_after == result.case_count_before + 1
    assert result.audit_count_after == result.audit_count_before + 2
```

- [ ] **Step 2: Write duplicate and stale tests before implementation**

Duplicate must prove the first case is created through C02 and the measured replay does not add a second physical case. Stale must prove feedback changes the fingerprint, old approval is refused, curated count stays unchanged, and audit count does not increase for the stale refusal.

- [ ] **Step 3: Run the focused tests and verify failure**

```powershell
python -m pytest tests/test_memory_lab.py -k "normal or duplicate or stale" -q
```

Expected: failures because orchestrator does not exist.

- [ ] **Step 4: Implement the narrow TestOperatorSimulator**

```python
@dataclass(frozen=True)
class TestOperatorSimulator:
    operational_dir: Path
    curated_dir: Path

    def preview(self, turn_id: str):
        return preview_case_memory_candidate(
            turn_id,
            memory_dir=self.operational_dir,
        )

    def approve(self, turn_id: str, fingerprint: str):
        return promote_case_memory_candidate(
            turn_id,
            fingerprint,
            operational_memory_dir=self.operational_dir,
            curated_memory_dir=self.curated_dir,
        )
```

Do not give this class any method that accepts a case dict or writes a file.

- [ ] **Step 5: Implement common turn/preview helpers and measured before/after inspection**

Create the turn with:

```python
turn = build_conversational_engine_turn(
    scenario.user_request,
    model_callable=None,
    memory_dir=paths.operational_dir,
)
```

Require `turn.llm_route_result.used_model is False`. Extract the exact turn ID from `turn.turn_journal_result["data"]["turn_id"]`. Preview through the simulator and compute the fingerprint with the production `build_case_memory_candidate_fingerprint()`.

Immediately before the measured action, capture strict curated-store and promotion-audit snapshots; capture them again after the action.

- [ ] **Step 6: Implement normal, duplicate, and stale branches**

Normal: approve once.

Duplicate: perform one real C02 approval as a precondition, then take measured before snapshots, repeat the exact approval, and require `duplicate`, persisted true, write false, case delta zero, audit delta two.

Stale: preview fingerprint A, record deterministic feedback through:

```python
record_turn_feedback(
    turn_id=turn_id,
    label="useful",
    note=scenario.feedback_note,
    memory_dir=paths.operational_dir,
)
```

Re-preview and require fingerprint B != A, then measure submission of A. Require `refused`, persistence false, case delta zero, audit delta zero.

- [ ] **Step 7: Run the three scenario-family tests**

```powershell
python -m pytest tests/test_memory_lab.py -k "normal or duplicate or stale" -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

```powershell
git add backend/app/services/memory_lab.py tests/test_memory_lab.py
git commit -m "feat(memory): run core deterministic memory lab cycles"
```

---

### Task 5: Conflict, Retrieval, and Controlled Failure Cycles

**Files:**
- Modify: `backend/app/services/memory_lab.py`
- Modify: `tests/test_memory_lab.py`

**Interfaces:**
- Consumes: fixture builder/failure injection from Task 3 and production `retrieve_memory_context()` with `MemoryRetrievalQuery`.
- Extends: `run_memory_lab_cycle()` to all six approved families.

- [ ] **Step 1: Write conflict test**

The test must assert one isolated conflicting fixture exists before the measured action, the exact current fingerprint receives `conflict`, and no second same-ID row is written.

- [ ] **Step 2: Write retrieval-discrimination test**

Create one relevant and one distractor fixture with unique search tokens. Query only cases:

```python
query = MemoryRetrievalQuery(
    user_request=scenario.retrieval_query,
    include_baselines=False,
    include_operator_preferences=False,
    include_cases=True,
    include_knowledge=False,
    max_cases=5,
    max_knowledge_entries=0,
)
result = retrieve_memory_context(query, memory_dir=paths.curated_dir)
```

Require the expected case ID to be first when its unique token distinguishes it, and verify the strict curated-store digest is unchanged before/after retrieval.

- [ ] **Step 3: Write three controlled-failure subtype tests**

Require exact C02 semantics:

```text
attempt_audit: status=error decision=error persisted=False write=False audit_delta=0 case_delta=0
curated_save: status=error decision=error persisted=False write=False audit_delta=2 case_delta=0
outcome_audit: status=partial decision=promoted persisted=True write=True audit_delta=1 case_delta=1
```

For `outcome_audit`, exit the failure injection and retry the same exact fingerprint. Require retry decision `duplicate`, no second case write, and two additional audit events on the retry.

- [ ] **Step 4: Run the new tests and verify failure**

```powershell
python -m pytest tests/test_memory_lab.py -k "conflict or retrieval or failure" -q
```

Expected: FAIL until branches are implemented.

- [ ] **Step 5: Implement conflict precondition without giving fixture authority to the Operator simulator**

Deep-copy `candidate.proposed_case`, mutate only a meaningful validated field such as `case_card.lesson`, validate it, then call `seed_case_fixture(paths, conflicting_case)` before measured snapshots. Record the seeded case ID in `fixture_case_ids`.

- [ ] **Step 6: Implement retrieval branch with read-only digest verification**

Seed two explicitly declared retrieval fixtures, snapshot the strict case-store digest, call real retrieval, snapshot again, and fail the cycle if the digest changes.

- [ ] **Step 7: Implement controlled failure branch using the declared injection context**

All measured approvals still call `TestOperatorSimulator.approve()`. Record `injected_failure`, actual status/decision/persistence, and `retry_decision` for the post-write audit failure subtype.

- [ ] **Step 8: Run all cycle tests**

```powershell
python -m pytest tests/test_memory_lab.py -q
```

Expected: PASS for all six families.

- [ ] **Step 9: Commit Task 5**

```powershell
git add backend/app/services/memory_lab.py tests/test_memory_lab.py
git commit -m "feat(memory): cover adversarial memory lab cycles"
```

---

### Task 6: Campaign Orchestration, Evidence Files, and Hard Invariants

**Files:**
- Modify: `backend/app/services/memory_lab.py`
- Modify: `tests/test_memory_lab.py`

**Interfaces:**
- Produces: `run_memory_lab_campaign(config: MemoryLabCampaignConfig) -> MemoryLabCampaignResult`, `write_campaign_manifest(...)`, `append_cycle_result(...)`, `write_campaign_summary(...)`, `format_memory_lab_campaign_report(result)`.

- [ ] **Step 1: Write a 6-cycle development campaign test**

Use one round-robin cycle from every family. Require manifest, cycle-results JSONL, summary, isolated operational/curated directories, and a GREEN final result when all invariants hold.

- [ ] **Step 2: Write hard-invariant negative tests before campaign implementation**

At minimum:

- force an unexpected curated row during a stale cycle and require campaign status `failed` with `unexpected_writes > 0`;
- create duplicate physical `case_id` rows and require campaign status not GREEN;
- append malformed JSON to the promotion audit and require `aborted` because truth cannot be established;
- monkeypatch a forbidden model/tool/policy boundary to prove the guard turns it into a trust-boundary failure;
- create a retrieval result missing its expected case and require retrieval check failure;
- verify a deliberately corrupted campaign can never serialize `final_status="green"`.

- [ ] **Step 3: Run campaign tests and verify failure**

```powershell
python -m pytest tests/test_memory_lab.py -k "campaign or invariant or corrupted" -q
```

Expected: FAIL until orchestration exists.

- [ ] **Step 4: Implement evidence writers with canonical JSON**

Manifest and summary use UTF-8 JSON with `sort_keys=True`, `indent=2`. Cycle results append one compact JSON object per line with `sort_keys=True`.

Create directories before the first cycle. Never reuse a non-empty campaign root: fail closed if manifest/cycle/summary or operational/curated evidence already exists.

- [ ] **Step 5: Implement campaign loop and stop rules**

For each generated scenario:

1. run the cycle inside `forbidden_authority_guard()`;
2. append its result immediately;
3. update counters from observable result/store/audit state;
4. stop immediately if `trust_boundary_violation=True`;
5. for ordinary assertion failure, stop when `config.fail_fast=True`, otherwise continue;
6. on unexpected infrastructure exception, write an `aborted` summary and return an aborted result.

Formal 1,000-cycle configuration must set `fail_fast=True`.

- [ ] **Step 6: Implement final GREEN predicate explicitly**

Do not derive GREEN from pass percentage. Require all of:

```python
green = (
    completed_cycles == requested_cycles
    and failed_cycles == 0
    and unexpected_writes == 0
    and stale_approvals_accepted == 0
    and physical_duplicate_count == 0
    and conflict_overwrite_count == 0
    and audit_inconsistency_count == 0
    and forbidden_authority_crossing_count == 0
    and retrieval_checks_passed == retrieval_checks_total
)
```

If truth cannot be established because strict store/audit inspection fails, final status is `aborted`, not `failed` or `green`.

- [ ] **Step 7: Run all laboratory service tests**

```powershell
python -m pytest tests/test_memory_lab_contracts.py tests/test_memory_lab_scenarios.py tests/test_memory_lab_fixtures.py tests/test_memory_lab.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 6**

```powershell
git add backend/app/services/memory_lab.py tests/test_memory_lab.py
git commit -m "feat(memory): orchestrate memory lab campaigns"
```

---

### Task 7: Developer Runner and Non-Subprocess Git Revision Capture

**Files:**
- Create: `scripts/run_memory_lab.py`
- Create: `tests/test_memory_lab_runner.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `MemoryLabCampaignConfig`, `run_memory_lab_campaign()`, `format_memory_lab_campaign_report()`.
- Produces: developer command `python scripts/run_memory_lab.py --cycles <N> --seed <seed> [--fail-fast] [--scenario-summary] [--evidence-dir <path>]`.

- [ ] **Step 1: Write runner argument and exit-code tests**

Tests must prove:

- 50/250/1000 and development 1–10 are accepted;
- unsupported count 125 exits with parser/config error;
- GREEN campaign exits 0;
- failed/aborted campaign exits non-zero;
- no production `app.cli` command is added.

- [ ] **Step 2: Write Git HEAD reader tests for normal clone and worktree `.git` file shapes**

The runner must record the current commit without invoking `git` or any subprocess during formal validation. Implement a helper that reads `.git/HEAD`; when `.git` is a file, resolve `gitdir:` and optional `commondir`; resolve loose refs first and then `packed-refs` if needed.

- [ ] **Step 3: Run runner tests and verify failure**

```powershell
python -m pytest tests/test_memory_lab_runner.py -q
```

Expected: import/file failures.

- [ ] **Step 4: Implement argparse and default evidence root**

Default evidence root:

```text
validation/memory_lab_runs/<campaign_id>/
```

Add exactly this ignore rule to `.gitignore`:

```text
validation/memory_lab_runs/
```

The runner must set `LIGHTHOUSE_USE_OLLAMA=0` before calling the campaign service. The service-level forbidden guard remains the enforcement backstop.

- [ ] **Step 5: Implement concise report output**

The final console report must include at least:

```text
LH-V1.5-C03 MEMORY LAB
Seed: <seed>
Cycles: <completed> / <requested>
Passed: <passed>
Unexpected writes: <count>
Stale approvals accepted: <count>
Physical duplicate cases: <count>
Conflict overwrites: <count>
Audit inconsistencies: <count>
Forbidden authority crossings: <count>
Retrieval assertions: <passed> / <total>
Status: <GREEN|FAILED|ABORTED>
Evidence: <campaign-root>
```

- [ ] **Step 6: Run runner tests**

```powershell
python -m pytest tests/test_memory_lab_runner.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 7**

```powershell
git add scripts/run_memory_lab.py tests/test_memory_lab_runner.py .gitignore
git commit -m "feat(memory): add deterministic memory lab runner"
```

---

### Task 8: Freeze C03 Documentation and Contract Tests

**Files:**
- Modify: `docs/memory_layer_architecture.md`
- Modify: `docs/v1_contract_shapes.md`
- Modify: `tests/test_v1_contract_shapes.py`
- Modify or create focused documentation assertions only if existing repository patterns require them.

**Interfaces:**
- Documents the already implemented C03 behavior; does not create new runtime behavior.

- [ ] **Step 1: Add contract assertions before docs changes**

Extend `tests/test_v1_contract_shapes.py` to assert `MemoryLabCycleResult` and `MemoryLabCampaignResult` stable field names/order and schema version `memory_lab_v1_5_c03`.

- [ ] **Step 2: Run contract tests and verify failure until docs/contracts are aligned**

```powershell
python -m pytest tests/test_v1_contract_shapes.py tests/test_memory_lab_contracts.py -q
```

- [ ] **Step 3: Document the authority boundary and evidence locations**

`docs/memory_layer_architecture.md` must state explicitly:

- C03 is validation infrastructure;
- TestOperatorSimulator cannot authorize production persistence;
- measured turn-derived writes still use C02 exact-fingerprint approval;
- fixture seeding is isolated adversarial setup only;
- retrieval remains read-only/non-authoritative;
- no lifecycle mutation is introduced.

- [ ] **Step 4: Document exact C03 result contracts and campaign statuses**

`docs/v1_contract_shapes.md` must include the cycle-result fields, campaign-result fields, `green/failed/aborted` status semantics, and the no-yellow acceptance rule.

- [ ] **Step 5: Run focused docs/contracts tests**

```powershell
python -m pytest tests/test_v1_contract_shapes.py tests/test_memory_lab_contracts.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 8**

```powershell
git add docs/memory_layer_architecture.md docs/v1_contract_shapes.md tests/test_v1_contract_shapes.py
git commit -m "docs(memory): define C03 memory lab contracts"
```

---

### Task 9: Repository Regression and Harness Self-Verification Gate

**Files:**
- No intended new runtime files unless a failing gate exposes a C03-scoped defect.

**Interfaces:**
- Produces a clean automated baseline before formal campaign evidence is trusted.

- [ ] **Step 1: Run all C03 tests**

```powershell
python -m pytest `
  tests/test_memory_lab_contracts.py `
  tests/test_memory_lab_scenarios.py `
  tests/test_memory_lab_fixtures.py `
  tests/test_memory_lab.py `
  tests/test_memory_lab_runner.py `
  tests/test_v1_contract_shapes.py `
  -q
```

Expected: all pass.

- [ ] **Step 2: Run the full Lighthouse regression suite with live-model evals disabled**

```powershell
$env:LIGHTHOUSE_USE_OLLAMA = "0"
python -m pytest tests -ra
```

Expected: all non-live tests pass; the five live-model evals remain skipped unless the repository count legitimately changes from new C03 tests.

- [ ] **Step 3: Run Ruff, compile, and whitespace gates**

```powershell
uv run --frozen ruff check `
  backend/app/services/memory_lab_contracts.py `
  backend/app/services/memory_lab_scenarios.py `
  backend/app/services/memory_lab_fixtures.py `
  backend/app/services/memory_lab.py `
  scripts/run_memory_lab.py `
  tests/test_memory_lab_contracts.py `
  tests/test_memory_lab_scenarios.py `
  tests/test_memory_lab_fixtures.py `
  tests/test_memory_lab.py `
  tests/test_memory_lab_runner.py

python -m compileall backend/app/services scripts

git diff --check
```

Expected: all gates pass.

- [ ] **Step 4: Prove generated evidence is ignored and no real memory path changed**

Before formal campaigns:

```powershell
git status --short
git check-ignore validation/memory_lab_runs/probe.txt
```

Expected: `validation/memory_lab_runs/probe.txt` is ignored, and there are no tracked/untracked campaign writes under normal `memory/` or `data/memory/` caused by C03 tests.

- [ ] **Step 5: Commit any final C03-scoped test/doc seal only if the previous gates required a legitimate correction**

If no correction was required, make no empty commit.

---

### Task 10: Formal 50 → 250 → 1,000 Campaign Ladder

**Files:**
- Generated only: `validation/memory_lab_runs/<campaign-id>/...` (ignored, never staged).

**Interfaces:**
- Produces the acceptance evidence that determines whether C03 is complete.

- [ ] **Step 1: Run the 50-cycle smoke campaign**

```powershell
python scripts/run_memory_lab.py --cycles 50 --seed 20260817 --scenario-summary
```

Required result: GREEN with exact family distribution `20/10/8/5/5/2` and every hard invariant at zero/100% as applicable.

- [ ] **Step 2: Inspect the 50-cycle manifest, summary, strict stores, and a sample from each family**

Confirm the manifest records the current Git commit, the cycle JSONL contains 50 rows, operational/curated paths are isolated, and no cycle hides an unexpected write behind an expected service status.

- [ ] **Step 3: Run the 250-cycle validation campaign**

```powershell
python scripts/run_memory_lab.py --cycles 250 --seed 20260817 --scenario-summary
```

Required result: GREEN with exact family distribution `100/50/38/25/25/12`.

- [ ] **Step 4: Inspect aggregate distributions and store/audit truth after 250 cycles**

Require zero malformed JSONL rows, zero duplicate physical case IDs, and audit/store counts consistent with each cycle's declared expectations.

- [ ] **Step 5: Run the formal 1,000-cycle fail-fast campaign**

```powershell
python scripts/run_memory_lab.py --cycles 1000 --seed 20260817 --fail-fast --scenario-summary
```

Required result: GREEN with exact family distribution `400/200/150/100/100/50`.

- [ ] **Step 6: Apply the formal C03 acceptance checklist to the 1,000-cycle summary**

Require:

```text
completed_cycles = 1000
failed_cycles = 0
unexpected_writes = 0
stale_approvals_accepted = 0
physical_duplicate_count = 0
conflict_overwrite_count = 0
audit_inconsistency_count = 0
forbidden_authority_crossing_count = 0
retrieval_checks_passed = retrieval_checks_total
final_status = green
```

- [ ] **Step 7: Re-run the same 50-cycle seed to prove logical replay**

Run a second 50-cycle campaign with seed `20260817` into a different campaign root. Compare scenario IDs, families, expected decisions, fixture declarations, and deterministic domain inputs across the two `cycle_results.jsonl` files while explicitly ignoring runtime UUIDs/timestamps/turn IDs.

- [ ] **Step 8: Do not run 5,000 cycles as a completion requirement**

Only run:

```powershell
python scripts/run_memory_lab.py --cycles 5000 --seed 20260817 --fail-fast
```

if the 1,000-cycle campaign is already GREEN and the durability evidence is useful before C04. A 5,000-cycle result is informative, not a C03 merge gate.

---

### Task 11: Final Source Review, PR, Windows CI, and Merge Gate

**Files:**
- No new functional files expected.

**Interfaces:**
- Final evidence/review gate only.

- [ ] **Step 1: Review the complete C03 diff against the approved design**

Specifically verify:

- no production auto-approval command exists;
- no lifecycle mutation was added;
- TestOperatorSimulator has no low-level writer;
- ordinary/duplicate/stale measured writes use real C02;
- fixture writes are isolated and declared;
- formal guard traps model/tool/OS/generic-policy calls;
- retrieval does not mutate curated memory;
- campaign evidence is ignored by Git.

- [ ] **Step 2: Push the feature branch only after local gates and formal campaigns are GREEN**

Use normal branch push with local/remote SHA verification.

- [ ] **Step 3: Open a draft PR against `main`**

PR body must report the final automated test count, 50/250/1,000 campaign results, hard invariant counts, authority boundary, and the fact that generated campaign evidence is intentionally not committed.

- [ ] **Step 4: Require Windows GitHub CI GREEN on the exact PR head**

Fetch the workflow run/log and record the exact remote pytest count. Do not infer it from local output.

- [ ] **Step 5: Perform independent remote source review before merge recommendation**

Any trust-boundary, persistence-truth, fixture-isolation, or replay defect blocks merge even if CI is green.

- [ ] **Step 6: Request explicit Operator merge authorization**

Do not merge automatically. Merge only after the Operator authorizes the exact reviewed PR head.

---

## Definition of Done

LH-V1.5-C03 is complete only when:

- all laboratory contract/scenario/fixture/orchestration/runner tests pass;
- the full existing Lighthouse regression suite passes with expected live-model skips;
- negative harness tests prove corrupted or authority-crossing behavior cannot report GREEN;
- 50-cycle campaign is GREEN;
- 250-cycle campaign is GREEN;
- 1,000-cycle fail-fast campaign is GREEN;
- unexpected writes = 0;
- stale approvals accepted = 0;
- physical duplicate cases = 0;
- conflict overwrites = 0;
- audit inconsistencies = 0;
- forbidden authority crossings = 0;
- required retrieval assertions = 100%;
- generated campaign evidence remains uncommitted/ignored;
- Windows GitHub CI is GREEN on the exact final PR head;
- independent source review is GREEN;
- explicit Operator merge authorization is received.
