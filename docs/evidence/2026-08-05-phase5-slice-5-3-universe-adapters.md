# Phase 5 Slice 5.3 Outside-Holding Universe

**Date:** 2026-08-05

**Branch:** `phase5-prediff`

**Purpose:** produce a deterministic, evidence-backed outside-holding pool from stored local sources without scoring or recommendation behavior

## Result

Slice 5.3 implements read-only adapters for persisted rankings, active watchlist assets, bounded asset/catalog search, and benchmark constituents or documented proxies. The pool resolves canonical economic exposure, merges duplicate source nominations, retains source reasons and evidence, excludes held exposure, and blocks unresolved identity instead of assuming it is outside the portfolio.

## Changed Files

- `src/dashboard/assets/__init__.py`
- `src/dashboard/assets/identity.py`
- `src/dashboard/ingestion/ticker_universe.py`
- `src/dashboard/rules_and_data/candidates/source_adapters.py`
- `src/dashboard/rules_and_data/candidates/universe.py`
- `src/dashboard/rules_and_data/candidates/__init__.py`
- `tests/rules_and_data/candidates/test_candidate_universe.py`
- `docs/candidate_contracts.md`
- `docs/adr/adr_ph13_candidate_engine_boundary.md`
- `docs/evidence/2026-08-05-phase5-slice-5-3-universe-adapters.md`

No database migration is required.

## Identity And Exclusion Policy

- Repository `asset_id` is canonical identity after documented alias or CDR-underlying resolution.
- Direct assets and resolvable CDR wrappers share one economic-exposure identity.
- ETF overlap is not treated as identity equivalence; later redundancy scoring owns weighted overlap.
- Held exposure is derived point in time from the transaction ledger or the repository's broker position map, matching existing portfolio semantics.
- Direct and equivalent held exposures are excluded before any later scoring.
- Unknown, ambiguous, or missing CDR-underlying identity is represented as one deduplicated blocked nomination with a critical evidence-backed warning.

## Source Behavior

- Ranking reads the latest persisted snapshot per asset at or before `as_of`; it does not invoke ranking refresh behavior.
- Watchlist reads active rows updated at or before `as_of`.
- All-universe search reads bounded matching rows from `asset` and `stock_catalog`, preferring repository assets when duplicated.
- Benchmark reads the latest deterministic composition source at or before `as_of`, preserving exact versus proxy reason codes.
- Every nomination contains a versioned reason code and stable evidence reference.
- Source, evidence, candidate, exclusion, warning, watermark, and final pool ordering is deterministic.

Watchlist, asset/catalog, and broker position-map tables are mutable current-state sources. Their results disclose partial historical coverage rather than claiming full snapshot reconstruction. Empty requested snapshots report missing coverage; omitted optional search or benchmark requests report unsupported coverage.

## Explicit Exclusions

This slice adds no fit, diversification, redundancy, valuation, quality, momentum, sentiment, freshness, or final candidate score. It adds no recommendation action, trade behavior, provider call, data hydration, API route, or UI.

## Verification

```text
focused Slice 5.3 universe tests: 11 passed
combined candidate and ticker-universe regressions: 48 passed
repository tests: all 499 verified; full run passed 498 with one live-DB lock, then the locked CLI file passed 3/3 after stopping the API
full Ruff: passed
architecture boundary command: passed
web lint: 0 errors, 4 existing Fast Refresh warnings
web tests: 88 passed
web production build: passed
four-cycle full data-health workflow with external audit: ok, no findings
web data-health scan: ok across 53 routes, no console errors or failed requests
API and Vite health checks: HTTP 200
```

The sole full-run failure was environmental: `test_cli_isAlive` hardcodes `data/persistent_db.db` and could not open it while the local API held DuckDB's process lock. The other 498 tests passed in that run. After stopping the API, all three tests in that CLI file passed; the API was restarted and both required health endpoints returned HTTP 200. No code change was made to hide or bypass the lock.

The web scan reports warning-level text markers for truthful `Unavailable` or missing metrics on existing portfolio, signal, benchmark, broker, and Operations surfaces. Those routes returned HTTP 200 with no console errors or failed requests. The backend health workflow reported all 66 targets ready, no missing readiness, no pending or failed ingestion work, successful portfolio and signal refreshes, and no findings; the warning labels therefore represent source metrics that are not supplied for those views rather than a Slice 5.3 regression or stuck application state.

The remote Actions result is recorded after the slice commit is pushed.

## Remaining Risks And Deferred Work

- Current-state watchlist/catalog and broker-map tables cannot reconstruct rows that were deleted or overwritten after a historical `as_of`.
- Identity resolution intentionally fails closed for ambiguous symbols and undocumented wrappers; future mappings must be versioned and tested.
- Portfolio gaps, peer/industry associations, and profile-consistent themes remain Slice 5.4 work.
- Scoring and freshness adjudication remain Slices 5.5 and 5.6.

## Gate Result

The implemented pool meets the Slice 5.3 gate: it is deduplicated, outside-holding, evidence-backed, deterministic, and contains no final fit score. Stop after commit and identity-resolution review; do not begin Slice 5.4 in this task.

## Next Model Recommendation

Use **GPT-5.6 Sol with xhigh reasoning** for Slice 5.4. The next slice must reconcile point-in-time sector/geography gaps, profile permissions, benchmark coverage, and versioned association taxonomies without turning unknown classifications into false diversification signals.
