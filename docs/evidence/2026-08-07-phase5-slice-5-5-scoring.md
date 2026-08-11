# Phase 5 Slice 5.5 Screens And Candidate Scoring

**Date:** 2026-08-07

**Branch:** `phase5-prediff`

**Purpose:** add deterministic quality, value, and momentum screens plus explainable candidate scoring and ordering without starting Slice 5.6 freshness adjudication

## Result

Slice 5.5 implements all three required screen families and the frozen profile-fit, diversification, redundancy, source-support, highlight, and tie-break policy. All metrics come from stored local rows at or before the scoring boundary. Missing values remain explicit, raw ranking cannot override blocked or downgraded state, and no provider, recommendation, trade, API, or UI path is added.

## Changed Files

- `src/dashboard/rules_and_data/candidates/screen_adapters.py`
- `src/dashboard/rules_and_data/candidates/scoring.py`
- `src/dashboard/rules_and_data/candidates/models.py`
- `src/dashboard/rules_and_data/candidates/portfolio_sources.py`
- `src/dashboard/rules_and_data/candidates/universe.py`
- `src/dashboard/rules_and_data/candidates/__init__.py`
- `tests/rules_and_data/candidates/test_candidate_screens.py`
- `tests/rules_and_data/candidates/test_candidate_scoring.py`
- `tests/rules_and_data/candidates/test_candidate_universe.py`
- `docs/candidate_contracts.md`
- `docs/adr/adr_ph13_candidate_engine_boundary.md`
- `docs/evidence/2026-08-07-phase5-slice-5-5-scoring.md`

No database migration is required.

## Contract Decisions

- Screen policy: `candidate-screens.v1`.
- Scoring policy: `candidate-scoring.v1`.
- Score-input evidence: `candidate-score-inputs.v1`.
- Economic-overlap evidence: `candidate-economic-overlap.v1`.
- Fit weights are 16% growth, 20% value, 20% quality, 12% income, 12% speculative-risk, and 20% source support.
- Numeric fit requires all five observed profile-alignment dimensions; multiple sources cannot fill a missing factor.
- Diversification uses a fixed 5% hypothetical allocation and equal sector/geography HHI effects.
- Redundancy uses economic-exposure overlap. Scores at or above 50 downgrade an otherwise complete review.
- The stable tie-break is eligibility, fit descending, diversification descending, redundancy ascending, evidence-domain coverage descending, then asset ID.

The 5% allocation is a comparison device, not trade sizing. Phase 4 remains descriptive and does not grant suitability permission.

## Test Coverage

Focused tests cover:

- exact quality, value, and momentum screen qualification;
- missing source versus no qualifying asset;
- merged screen evidence and reason codes;
- concentrated-growth, dividend/income, broad-ETF, speculative-small-cap, balanced, and insufficient-data profiles;
- repeated and permuted byte-equivalent scoring;
- exact ties resolved by canonical asset ID;
- raw ranking unable to bypass profile conflict, critical missing evidence, or material redundancy;
- missing highlights surfaced without zero substitution;
- normalization and diversification boundary values.

All candidate contract, persistence, source, screen, and scoring tests pass: `64 passed`.

## Data Limitations

- `asset_analytics_snapshot` is optional storage. Its absence is a missing value-screen source, not a runtime error.
- Current factor ingestion can leave growth, value, or quality null. Candidate fit remains unavailable until another documented stored source supplies those dimensions.
- ETF look-through rows are mutable current-state data without an effective date. Redundancy evidence therefore retains unknown freshness for Slice 5.6.
- Classification and portfolio exposure must meet the existing known-coverage policy before diversification becomes numeric.

## Explicit Exclusions

This slice does not set evidence-age thresholds, adjudicate stale-versus-current conflicts, add liquidity or sentiment-only guardrails, persist or orchestrate a complete run, expose an API, render UI, assign a recommendation action, size a trade, call a provider, or call an LLM.

## Verification

```text
candidate tests: 64 passed
full Ruff: passed
architecture boundary command: passed
repository tests: 527 passed, 1 existing Starlette/httpx deprecation warning
web lint: passed with 0 errors and 4 existing Fast Refresh warnings
web tests: 88 passed across 22 files
web production build: passed
full data-health workflow: ok=true; findings=[]; 66/66 readiness targets;
  zero pending jobs by cycles 3 and 4; 92 subscriptions; healthy provider;
  12/12 external price checks matched exactly
web data-health scan: ok=true; 53/53 routes returned 200; no console errors;
  no failed requests; 44 warning markers reflect explicit unavailable, missing,
  or provider-state text rather than a failed request or unresolved readiness job
API health: 200; status=ok; database=connected
Vite app: 200
GitHub Actions: recorded after push
```

## Gate Result

The Slice 5.5 scoring-policy gate passes in focused fixtures. Stop after full verification and remote CI; do not begin Slice 5.6 in this task.

## Next Model Recommendation

Use **GPT-5.6 SOL Extra High with maximum reasoning** for Slice 5.6. Evidence-type freshness boundaries, stale/current conflicts, liquidity and speculative-risk conditions, sentiment-only prevention, and structured guardrail ordering are safety-critical and interact with every score state.
