# Isolated Skill Store Prototype Design

**Status:** approved by the explicit test brief on 2026-09-23

**Classification:** architectural prototype, isolated from production

**Goal:** prove a minimal storage and retrieval contract for a future
`skill_store.py` and MCP tool `search_simulation_skill` without changing the
executor or learning from unvalidated simulation results.

## Scope

This prototype is deliberately smaller than the production feature. It stores
known-good simulation patterns in SQLite, retrieves candidates by task type and
parameter similarity, and records whether retrieved skills later helped. It
does not generate code, call an LLM, modify Dify, register production MCP
tools, or use a vector database.

## Quality Gate

A result is admitted to the prototype skill library only when all conditions
hold:

1. `verdict` is exactly `normal`.
2. `metrics.finite` is exactly `true`.
3. `metrics.has_signal` is exactly `true`.
4. `max_pressure_pa` is finite, greater than zero, and no more than
   `1_000_000_000.0` Pa.
5. `rms_pressure_pa` is finite, non-negative, and no greater than
   `max_pressure_pa`.
6. typed validation evidence comes from the analysis-result adapter, has a
   non-empty run identifier, uses an allowlisted verifier version, and carries
   a 64-character SHA-256 artifact hash that the store recomputes before
   insertion.
7. generated code is non-empty.

An exit code of zero is never sufficient. A rejected candidate returns
`accepted=false` and a deterministic reason code; it is not inserted.

## Storage Contract

SQLite table `simulation_skill_versions` stores immutable evidence:

| Column | Purpose |
| --- | --- |
| `id` | Integer primary key |
| `task_type` | Stable task category such as `plane_wave` |
| `parameter_fingerprint` | SHA-256 prefix of canonical JSON parameters |
| `parameters_json` | Canonically sorted JSON retained for similarity scoring |
| `summary` | Short human-readable description |
| `code` | Minimal known-good simulation code |
| `code_sha256` | Hash used to distinguish immutable code versions |
| `verdict` | Always `normal` for stored rows |
| `finite`, `has_signal` | Validated field flags retained as schema invariants |
| `max_pressure_pa` | Validated peak pressure |
| `rms_pressure_pa` | Validated RMS pressure |
| `evidence_reference` | Analysis run or VAL-1 case identifier |
| `evidence_sha256` | Hash of the typed validation evidence |
| `hit_count` | Number of retrieval events |
| `success_count` | Number of retrieved skills that later succeeded |
| `created_at` | UTC ISO timestamp |

SQLite table `simulation_skill_heads` points each
`(task_type, parameter_fingerprint)` to the latest immutable version. Recording
a changed code or evidence payload inserts a new version and advances the head;
it never overwrites the previous evidence. Usage counters belong to a version,
not to the parameter key.

SQLite table `simulation_retrieval_tokens` binds feedback to one emitted search
result. Each token is single-use and stores only its SHA-256 hash.

## Retrieval Contract

`search_simulation_skill(task_type, parameters, limit=3)`:

1. Only searches rows with the exact `task_type`.
2. Returns an exact fingerprint match first.
3. Otherwise scores same-task rows using shared parameter coverage and normalized
   numeric similarity. The minimum score is `0.5`.
4. Orders equal-score rows by success rate, then hit count, then recency.
5. Returns query metadata plus matched parameters, evidence, usage statistics,
   numeric score, and a single-use feedback token. It does not return hidden
   vector distances.
6. Rejects `limit` values that are not integers in the inclusive range `1..50`.

The scoring formula is intentionally simple and explainable:

- exact canonical parameters: score `1.0`
- shared-key coverage: `common_keys / union_keys`
- mean similarity over common keys:
  - equal non-numeric values: `1.0`
  - different non-numeric values: `0.0`
  - numeric values: `1 / (1 + abs(a-b) / (abs(a) + abs(b) + epsilon))`
- final score: `0.6 * mean_similarity + 0.4 * coverage`

## Feedback Contract

`search` increments `hit_count` and issues one single-use retrieval token per
returned skill. `record_usage(retrieval_token, validation_evidence)` accepts the
token once, derives success from the validated evidence, and increments
`success_count` only for a fully valid `normal` result. Failed or abnormal uses
lower the success rate but do not delete the original evidence. Reusing or
fabricating a token does not affect ranking.

## Isolation Boundary

All prototype files live under `work/plugin-tests/superpowers/`. The prototype
does not import production modules, does not write to the production database,
and does not register an MCP tool. The eventual production change must be
reviewed separately after this test.

## Acceptance Criteria

- Every behavior has a test that failed before implementation.
- The tests use real SQLite files through pytest temporary directories.
- Non-normal or physically invalid candidates cannot be inserted.
- Exact and approximate same-task retrieval work.
- Cross-task leakage is impossible.
- Usage feedback changes ranking without allowing bad candidates in.
- A fresh reviewer identifies no unresolved critical or important issue.
