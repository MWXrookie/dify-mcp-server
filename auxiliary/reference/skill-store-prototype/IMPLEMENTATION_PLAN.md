# Skill Store Prototype Implementation Plan

> **For agentic workers:** Execute this plan task-by-task. Steps use checkbox
> syntax for tracking. This is an isolated prototype; never copy changes into
> production code during this test.

**Goal:** implement and independently review a minimal SQLite skill store and
deterministic `search_simulation_skill` contract.

**Architecture:** a standard-library-only Python module owns quality gating,
canonical parameter fingerprints, SQLite persistence, similarity scoring, and
usage feedback. Pytest exercises the public contract with real temporary
databases.

**Tech Stack:** Python 3.12, SQLite, pytest 9.1.1.

**Spec:** `work/plugin-tests/superpowers/DESIGN.md`

## Global Constraints

- Create or modify files only under `work/plugin-tests/superpowers/`.
- Never modify production code, executor code, security limits, or root files.
- Do not run Git commands; this project is treated as a fixed source snapshot.
- Do not add third-party runtime dependencies.
- Do not use a vector database.
- Do not insert a skill unless the complete quality gate passes.
- Treat exit code zero as insufficient evidence by itself.

---

### Task 1: Contract Tests

**Files:**
- Create: `work/plugin-tests/superpowers/test_skill_store.py`

**Interfaces:**
- Consumes: `SkillCandidate`, `SkillStore`, `QualityDecision`
- Produces:
  - `SkillCandidate(task_type, parameters, summary, code, evidence)`
  - `ValidationEvidence`
  - `SkillStore(db_path)`
  - `SkillStore.record(candidate) -> QualityDecision`
  - `SkillStore.search(task_type, parameters, limit=3) -> list[dict]`
  - `SkillStore.record_usage(retrieval_token, evidence) -> dict`

- [ ] **Step 1: Write the failing tests**

```python
def test_rejects_non_normal_verdict(tmp_path):
    store = SkillStore(tmp_path / "skills.db")
    decision = store.record(
        good_candidate(result={"verdict": "zero_field", ...})
    )
    assert decision.accepted is False
    assert decision.reason == "verdict_not_normal"
    assert store.count() == 0
```

Add the six behavior tests defined in `DESIGN.md`.

- [ ] **Step 2: Run the tests and capture RED**

Run:

```powershell
py -m pytest work/plugin-tests/superpowers/test_skill_store.py -q
```

Expected: collection fails because `skill_store` does not exist.

- [ ] **Step 3: Implement the minimal module**

Create `skill_store.py` with standard-library-only code sufficient to make the
contract tests pass.

- [ ] **Step 4: Run the tests and capture GREEN**

Run:

```powershell
py -m pytest work/plugin-tests/superpowers/test_skill_store.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Run the complete prototype suite**

Run:

```powershell
py -m pytest work/plugin-tests/superpowers -q
```

Expected: all prototype tests pass with no warnings.

### Task 2: Independent Review

**Files:**
- Create: `work/plugin-tests/superpowers/review_prompt.md`
- Create: `work/plugin-tests/superpowers/review.md`

**Interfaces:**
- Consumes: `DESIGN.md`, `IMPLEMENTATION_PLAN.md`, `skill_store.py`,
  `test_skill_store.py`
- Produces: severity-ranked independent review with a merge verdict

- [ ] **Step 1: Write the reviewer prompt**

Use the Superpowers code-review structure and explicitly instruct the reviewer
to remain read-only.

- [ ] **Step 2: Dispatch a fresh Codex reviewer**

Run:

```powershell
codex exec --skip-git-repo-check --sandbox read-only --ask-for-approval never `
  --cd work/plugin-tests/superpowers --output-last-message review.md `
  "$(Get-Content -Raw review_prompt.md)"
```

- [ ] **Step 3: Inspect the review**

Record strengths, issues, and verdict. Fix every Critical or Important issue
with a failing regression test first, then rerun the full suite.

### Task 3: Verification and Evaluation

**Files:**
- Create: `work/plugin-tests/superpowers/verification.md`
- Create: `work/plugin-tests/superpowers/evaluation.md`

**Interfaces:**
- Consumes: RED/GREEN output, final suite output, independent review
- Produces: reproducible evidence and a recommendation on whether Superpowers
  materially changed the process

- [ ] **Step 1: Record exact commands and observed results**

No completion claim is allowed without fresh command output.

- [ ] **Step 2: Re-run the production-snapshot boundary check**

Run:

```powershell
Get-ChildItem -Recurse -File work/plugin-tests/superpowers |
  Select-Object FullName, Length
```

Expected: every created artifact is inside the approved directory.

- [ ] **Step 3: Compare workflow outcomes**

Document whether explicit design, TDD, isolation, and review changed the result
compared with a normal direct implementation. Record limitations and plugin
availability failure.

### Task 4: Review Rework

**Trigger:** independent review returned `With fixes` with one Critical and
seven Important findings.

**Files:**
- Modify: `DESIGN.md`
- Modify: `test_skill_store.py`
- Modify: `skill_store.py`

**Interfaces:**
- Produces:
  - `ValidationEvidence`
  - `evidence_from_analysis_result(result, analysis_run_id, verifier_version)`
  - immutable `simulation_skill_versions`
  - mutable `simulation_skill_heads`
  - single-use `simulation_retrieval_tokens`
  - `SkillStore.version_count()`
  - `SkillStore.history(task_type, parameters) -> list[dict]`
  - `search_simulation_skill(store, task_type, parameters, limit=3)`

- [ ] **Step 1: Add failing regression tests for every Critical/Important issue**

Tests must cover evidence retention, typed provenance, exact-first ranking,
concurrent recording, schema-level invariants, invalid input rejection,
injected database paths, failed feedback, and adapter behavior.

- [ ] **Step 2: Run the tests and capture the review-fix RED**

Run:

```powershell
py -m pytest work/plugin-tests/superpowers/test_skill_store.py -q
```

Expected: failures point to the reviewed contract gaps, not test syntax.

- [ ] **Step 3: Implement the immutable-version design**

Use atomic SQLite upserts, immutable evidence versions, a latest-version head,
schema `CHECK` constraints, bounded canonical parameters, and exact-first
ranking.

- [ ] **Step 4: Run the tests and capture the review-fix GREEN**

Run:

```powershell
py -m pytest work/plugin-tests/superpowers -q
```

Expected: all tests pass without warnings.

- [ ] **Step 5: Dispatch a second independent review**

Create `review_after_fixes.md`. If new Critical or Important findings appear,
repeat the regression-test cycle before final verification.
