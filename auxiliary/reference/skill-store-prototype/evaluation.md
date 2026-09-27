# Superpowers Production-Effect Evaluation

## Verdict

Superpowers materially changed the development process. The strongest evidence
is that the first independent review found a Critical data-loss defect in an
implementation that was already green under 11 tests. That defect would likely
have survived an ordinary direct implementation.

The plugin is valuable for architectural or high-risk changes. It adds
significant ceremony for small local edits.

## Scope And Isolation

The test implemented a minimal `skill_store` and `search_simulation_skill`
contract prototype without touching production code, the executor, security
limits, project roots, or the production database. The final suite contains 34
passing tests in an isolated SQLite-backed prototype.

## Plugin Availability

Superpowers was installed and enabled, but its skills were not present in the
main agent's available-skill list for this already-running task. The fallback was:

1. read the cached official `using-superpowers`, `brainstorming`,
   `writing-plans`, `test-driven-development`, `requesting-code-review`, and
   `verification-before-completion` instructions;
2. follow the same design/plan/TDD/review/verification sequence manually;
3. dispatch independent Codex reviewer processes, which could read the cached
   review skill and produced separate review artifacts.

The plugin therefore changed the process through its methodology, but the main
task did not have direct invokable `superpowers:*` skills.

## What Each Stage Changed

### Design

The design phase classified this as an architectural prototype rather than a
small coding task. That forced explicit quality gates, storage boundaries,
feedback semantics, and acceptance criteria before implementation.

### Plan

The plan defined test-first steps and isolated file ownership. When the first
review found evidence overwrite, the plan was extended rather than patched
silently.

### TDD

Every behavior had captured RED evidence before implementation:

- initial RED: 11 errors because `skill_store` did not exist;
- review-fix RED: 23 failures against the revised contract;
- second follow-up RED: 11 failures against tokens, schema versioning,
  tamper detection, and invalid limits.

This prevented tests from being written to match an implementation after the
fact.

### Independent Review

Review 1 found the Critical defect: recording a changed implementation for the
same task and parameters overwrote evidence while inheriting usage statistics.
The revised design split immutable versions from the latest-version head.

Review 2 found that typed evidence was still forgeable, schema setup was not
versioned, direct SQL could bypass some invariants, and feedback was
caller-forgeable. The revision added hash verification, `PRAGMA user_version`,
stronger `CHECK` constraints, and single-use retrieval tokens.

Review 3 confirmed no new Critical issue but concluded the prototype still must
not enter production without signed validation receipts, explicit legacy
migration, stronger cross-table integrity, and replay prevention.

## Quantitative Result

| Metric | Result |
| --- | --- |
| Final automated tests | 34 passed |
| Independent review passes | 3 |
| Critical findings caught | 1 |
| Important production blockers identified | Multiple, documented in `verification.md` |
| Production code modified | 0 files |
| Production executor/security modified | No |
| Vector database introduced | No |

## Production Effect

Positive effects:

- forced a design before implementation;
- produced reproducible RED/GREEN evidence;
- caught a Critical audit-trail and data-attribution defect;
- converted vague security concerns into explicit schema, provenance, and
  feedback-contract tests;
- left a clear production boundary instead of presenting a prototype as
  production-ready.

Costs:

- three review cycles and multiple implementation revisions for a small
  prototype;
- reviewer subprocesses could not run pytest in their sandbox;
- the process can keep finding legitimate hardening work indefinitely unless a
  production boundary is declared.

## Recommendation

Keep Superpowers for changes that alter shared contracts, persistence,
security boundaries, or architecture. Use the full design/TDD/review loop for
the future production `skill_store.py`.

Do not keep it as mandatory ceremony for one-line fixes, text edits, or
throwaway investigations. For this test, the plugin is judged effective because
it changed both the artifact and the decision: the prototype is better than a
direct implementation would have been, and it is correctly identified as not
ready to merge.

Production implementation must not copy this prototype directly. It needs:

- signed validation receipts supplied by the trusted analysis/executor
  boundary;
- task, parameter, code, and retrieval binding;
- explicit schema migration and rollback;
- server-owned storage injection;
- durable token cleanup and replay prevention.
