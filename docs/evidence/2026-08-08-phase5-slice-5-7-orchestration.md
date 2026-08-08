# Phase 5 Slice 5.7 Orchestration And Internal Service

**Date:** 2026-08-08

**Branch:** `phase5-prediff`

**Purpose:** compose the frozen Phase 5 source, scoring, guardrail, run-identity, and persistence contracts behind one provider-free internal service

## Result

Slice 5.7 adds `candidate-orchestration.v1` and advances the candidate methodology to `candidate-engine.deterministic.v3`. `CandidateRunService.execute()` accepts one normalized `CandidateRunRequest`, executes all twelve stored-source families, scores and guards the resolved pool, derives the final input snapshot and run identity, persists transactionally, and returns the immutable stored `CandidateRun`.

The service adds no public endpoint, transport model, provider client, recommendation action, suitability decision, trade path, or UI.

## Changed Files

- `src/dashboard/ai_brain/candidates/orchestration.py`
- `src/dashboard/ai_brain/candidates/models.py`
- `src/dashboard/ai_brain/candidates/persistence.py`
- `src/dashboard/ai_brain/candidates/__init__.py`
- `tests/ai_brain/candidates/test_candidate_orchestration.py`
- `docs/candidate_contracts.md`
- `docs/adr/adr_ph13_candidate_engine_boundary.md`
- `docs/evidence/2026-08-08-phase5-slice-5-7-orchestration.md`

## Contract Decisions

- The frozen request owns portfolio scope, UTC whole-second `as_of`, the completed Phase 4 profile, and normalized adapter parameters.
- The input snapshot includes every contract/policy version, full profile material, pool watermarks and exclusions, source limitations, evidence hashes, score-input states, missing metrics, freshness, and guardrail states consumed by the run.
- Temporary run/review IDs are excluded while scoring; final IDs are rebound after the input hash is known.
- Creation time, request ID, runtime, and output hash remain volatile and do not affect run identity.
- Exact replay returns the originally persisted run rather than a new object with changed audit fields.
- Changed evidence creates a distinct immutable historical run.
- Source reads and immutable run persistence share one DuckDB transaction.
- Profile, identity, watermark, and source version incompatibility fails before scoring or persistence with `CandidateInputCompatibilityError` and a structured dependency record.
- A run is blocked when it has no reviews or all reviews are blocked, partial when a usable run has incomplete source coverage, and completed when a usable run has full source coverage.
- Candidate eligibility and run status remain separate. Counts and missing dependencies are exposed directly by `CandidateRun`.

## Test Coverage

The real stored-source integration fixture covers:

- all twelve required source families in one orchestration run;
- eligible, downgraded, and blocked candidate states;
- source coverage, run state, counts, missing dependencies, methodology, and output integrity;
- exact idempotent replay and immutable persistence;
- changed source evidence producing a new run identity;
- incompatible source schema failing before scoring or persistence;
- network/provider isolation;
- a measured 300-statement query ceiling and five-second runtime ceiling for a three-candidate all-source fixture.

Focused candidate package: 111 tests passed.

## Data And Performance Limits

- The representative all-source fixture currently executes 266 DuckDB statements. The 300-statement test ceiling records the existing integration cost and prevents silent regression; it is not a production throughput claim.
- Runtime is measured around source resolution, scoring, and run construction. The focused fixture must remain below five seconds on the test environment.
- Mutable watchlist, catalog, peer-group definitions, classifications, broker positions, and undated ETF look-through rows retain the partial or unknown history semantics fixed in earlier slices.
- Missing or unsupported source families remain visible. The service does not hydrate them.

## Explicit Exclusions

This slice does not add recommendation logic, a public or private HTTP endpoint, an API response model, a UI, an LLM/provider call, a suitability decision, position sizing, or trade behavior.

## Verification

```text
candidate package tests: 111 passed
candidate and full Ruff: passed
architecture boundary command: passed
repository tests: 574 passed, 1 existing Starlette/httpx deprecation warning
web lint: passed with 0 errors and 4 existing Fast Refresh warnings
web tests: 88 passed across 22 files
web production build: passed
full data-health workflow: ok=true; findings=[]; 66/66 readiness targets;
  zero pending jobs in all four cycles; 92 subscriptions; healthy provider;
  12/12 external price checks matched exactly
web data-health scan: ok=true; 53/53 routes returned 200; no console errors;
  no failed requests; warning markers reflect explicit unavailable, missing,
  credential, or provider-state text rather than failed requests or stuck loading
live review: overview, signals, portfolio analytics, benchmarks, and operations
  rendered without console errors; operations settled to 74/74 projection-ready,
  25/25 ranking-complete, and zero pending jobs
API health: 200; status=ok; database=connected
Vite app: 200
GitHub Actions: pending push
```

## Gate Result

The Slice 5.7 gate passes locally. One deterministic internal service reproduces and persists a complete candidate run from stored point-in-time inputs; exact replay is idempotent, evidence changes produce history, incompatible versions fail closed, and no provider or recommendation path is reachable. Stop after exact-SHA CI; do not begin Slice 5.8 or recommendation logic in this task.

## Next Model Recommendation

Use **GPT-5.6 SOL High** for Slice 5.8. Closure crosses the full candidate suite, adjacent ranking/signal/analytics/benchmark/watchlist regressions, data-health workflows, live application review, requirement traceability, unsupported-source disclosure, and CI evidence. The contracts and behavior are now frozen and the remaining work is broad verification rather than ambiguous implementation, so high reasoning is sufficient.
