# Phase 5 Slice 5.1 Domain And Evidence Contracts

**Date:** 2026-08-05

**Branch:** `phase5-prediff`

**Purpose:** complete the pure candidate domain and evidence protocol after the Slice 5.0 prerequisite gate passed

## Result

Slice 5.1 is complete. The repository now has immutable, provider-neutral contracts for candidate runs, reviews, source matches, evidence, score states, highlights, warnings, missing metrics, and source watermarks. Canonical serialization and content-derived identities follow ADR PH13.

## Changed Files

- `src/dashboard/ai_brain/candidates/__init__.py`
- `src/dashboard/ai_brain/candidates/canonical.py`
- `src/dashboard/ai_brain/candidates/models.py`
- `tests/ai_brain/candidates/test_candidate_contracts.py`
- `docs/candidate_contracts.md`
- `docs/adr/adr_ph13_candidate_engine_boundary.md`
- `docs/evidence/2026-08-05-phase5-slice-5-1-domain-contracts.md`

No migration or existing schema changed.

## Implemented Contract

- Stable run, candidate, review, and evidence identities derived from material inputs.
- Separate version constants for run schema, review schema, evidence schema, candidate methodology, and reason-code definitions.
- UTC whole-second timestamps and evidence/run point-in-time bounds.
- Decimal values canonically quantized to eight places using round-half-even.
- Deterministic ordering for every set-like contract sequence.
- Required fit, diversification, and redundancy states without scoring behavior.
- Structured valuation, risk, and sentiment highlights.
- Structured missing metrics, warnings, source coverage, and final eligibility state.
- Evidence closure from nested source, score, highlight, and warning records to the review.
- Explicit volatile fields excluded from hashes.
- Run output-hash recomputation and integrity reporting for Slice 5.2 persistence enforcement.

## Contract Tests

The pure suite proves:

- malformed and materially mismatched IDs are rejected;
- unknown eligibility, evidence, source-family, and score states are rejected;
- duplicate reason codes are rejected;
- source matches and candidate reviews cannot be evidence-free;
- unavailable scores require a structured missing metric;
- canonical source, evidence, and reason permutations serialize and hash identically;
- materially changed evidence changes the output hash;
- decimal rounding and volatile hash exclusions are stable;
- cross-run reviews and future data timestamps are rejected.

## Explicit Exclusions

This slice adds no persistence, schema migration, API, ranking adapter, source query, economic-exposure resolver, candidate scoring, ranking, tie-break, freshness adjudication, provider call, recommendation action, or UI.

## Verification

```text
ruff candidate contracts and tests: passed
candidate contract tests: 18 passed
combined profile, candidate, and architecture tests: 33 passed
architecture boundary command: passed
```

The combined gate includes the Phase 4 profile tests and architecture boundary tests required by the Slice 5.0 dependency.

## Remaining Risks And Deferred Work

- Persistence must enforce `CandidateRun.output_hash_is_valid` on write and read.
- Source adapters must supply canonical repository asset IDs and stable source record identities; this slice cannot prove source correctness.
- Economic-exposure alias and underlying resolution remains deferred to Slice 5.3.
- Score, ranking, freshness, and eligibility policies remain deliberately undefined until their scheduled slices.

## Gate Result

The Slice 5.1 pure-contract gate passes. Stop after commit and review; do not begin Slice 5.2 in this task.

## Next Model Recommendation

Use **GPT-5.6 Sol with high reasoning** for Slice 5.2. The migration and repository layer must preserve decimal precision, deterministic ordering, idempotent run identity, immutable history, and hash integrity, but its scope is narrower than the economic-exposure resolution work in Slice 5.3.
