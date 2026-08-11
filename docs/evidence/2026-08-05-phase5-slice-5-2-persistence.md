# Phase 5 Slice 5.2 Candidate Persistence

**Date:** 2026-08-05

**Branch:** `phase5-prediff`

**Purpose:** add the minimum immutable persistence required to audit and reproduce deterministic candidate runs

## Result

Slice 5.2 is complete. Candidate runs and their review audit graph now persist transactionally in DuckDB, round-trip through the Slice 5.1 contracts, preserve canonical decimal precision and ordering, and fail closed on identity, hash, payload, or normalized-row conflicts.

## Changed Files

- `src/dashboard/db/migrations/candidate_runs.sql`
- `src/dashboard/db/db_conn.py`
- `src/dashboard/rules_and_data/candidates/persistence.py`
- `src/dashboard/rules_and_data/candidates/serialization.py`
- `src/dashboard/rules_and_data/candidates/__init__.py`
- `tests/rules_and_data/candidates/test_candidate_persistence.py`
- `tests/test_production_schema_contracts.py`
- `docs/candidate_contracts.md`
- `docs/adr/adr_ph13_candidate_engine_boundary.md`
- `docs/evidence/2026-08-05-phase5-slice-5-2-persistence.md`

## Schema Decisions

Eight tables persist candidate run metadata, source watermarks, reviews, reason codes, source matches, run-scoped evidence, missing metrics, and warnings.

The following fields are structured because later reads and filters require them:

- run identity, portfolio, timestamps, versions, profile identity, hashes, and status;
- source watermark domain, schema, timestamp, and coverage;
- candidate/review/asset identity, ticker, versions, top-level scores, timestamps, and eligibility;
- reason, source-match, evidence, missing-metric, and warning codes and states.

The complete versioned `CandidateReview` is stored as canonical JSON. This preserves score components, highlights, and nested evidence associations exactly while those shapes remain intentionally extensible in later scoring and guardrail slices. Typed rows are integrity-checked against the payload on every read.

Evidence is keyed by run and evidence ID because freshness is relative to the candidate run's `as_of`. Historical runs therefore retain their original freshness state.

## Persistence Behavior

- Schema initialization is repeatable and registered in production `init_db`.
- Writes use one transaction for the complete run graph.
- The repository rejects a run before writing when its output hash is invalid.
- Repeating the same run and material output returns an idempotent no-op.
- Volatile retry metadata does not mutate the first stored run.
- Reusing a run identity with different material output fails closed.
- A changed input snapshot creates a distinct run without modifying history.
- Reads reconstruct canonical domain models and verify review payloads, structured rows, evidence, and run hashes.
- Decimal values are explicitly round-half-even quantized before DuckDB insertion rather than relying on database conversion behavior.

## Explicit Exclusions

This slice adds no source query, ranking/watchlist/benchmark adapter, held-exposure exclusion, alias or underlying resolver, nomination logic, score methodology, final ranking, freshness adjudication, API, provider call, recommendation action, or UI.

No existing table semantics changed, and no Phase 6 recommendation, decision, prompt, provider, or model-call table was added.

## Verification

```text
focused candidate persistence and production schema tests: 9 passed
ruff focused persistence files: passed
combined profile, candidate, production schema, migration, news schema, and architecture tests: 55 passed
architecture boundary command: passed
```

The combined gate includes all candidate contracts and persistence tests, Phase 4 profile tests, production schema and existing migration regressions, news schema initialization, and architecture boundaries.

## Remaining Risks And Deferred Work

- Slice 5.3 must define canonical repository asset and economic-exposure resolution before source rows can be produced safely.
- Candidate review canonical JSON intentionally carries component/highlight details until later slices establish stable query requirements; any future normalization must preserve historical payload readability.
- This repository is not yet called by orchestration. Slice 5.7 owns that integration.
- No data backfill is required because no candidate runs existed before this migration.

## Gate Result

The Slice 5.2 persistence and reproducibility gate passes. Stop after commit and review; do not begin Slice 5.3 in this task.

## Next Model Recommendation

Use **GPT-5.6 Sol with xhigh reasoning** for Slice 5.3. Outside-holding exclusion must reconcile direct assets, aliases, CDR underlyings, ETF overlap, and unresolved identities across ranking, watchlist, all-universe, and benchmark sources; a false distinct identity would invalidate every later candidate result.
