# Phase 5 Slice 5.4 Portfolio Gaps And Associations

**Date:** 2026-08-06

**Branch:** `phase5-prediff`

**Purpose:** add deterministic sector, geography, peer, industry, and profile-theme nomination sources without starting candidate scoring

## Result

Slice 5.4 implements every planned portfolio-gap and association source. It reads only stored local snapshots or effective-dated mappings, preserves source reasons and evidence, blocks profile conflicts, excludes unknown classifications, and reports incomplete coverage without manufacturing candidates.

## Changed Files

- `src/dashboard/rules_and_data/candidates/portfolio_sources.py`
- `src/dashboard/rules_and_data/candidates/source_adapters.py`
- `src/dashboard/rules_and_data/candidates/universe.py`
- `src/dashboard/rules_and_data/candidates/__init__.py`
- `tests/rules_and_data/candidates/test_candidate_portfolio_sources.py`
- `tests/rules_and_data/candidates/test_candidate_universe.py`
- `docs/candidate_contracts.md`
- `docs/adr/adr_ph13_candidate_engine_boundary.md`
- `docs/evidence/2026-08-06-phase5-slice-5-4-gap-associations.md`

No database migration is required.

## Source Decisions

- Sector and country exposure come from the latest `portfolio_analytics_snapshot` at or before `as_of`.
- Comparison weights come from one explicit `benchmark_index_exposure_snapshot` source selected deterministically at or before `as_of`.
- Peer association requires common active `business_strength_peer_member` membership.
- Industry association requires common active `asset_business_classification.industry` values.
- Theme association requires a Phase 4 theme tilt, a versioned explicit alias to a stored theme benchmark, and a dated composition.
- Asset labels and peer-group definitions are current-state mutable sources and report partial historical coverage.

The Phase 4 profile remains descriptive. It does not grant suitability permission. This slice uses matching profile identity/version, adequate observed-data coverage, and exact theme evidence as source gates. Profile mismatch, future snapshots, incompatible versions, insufficient data, and dimension coverage conflicts produce structured blocks.

## Gap Policy

- Portfolio and benchmark exposure totals must each be 95% to 105%.
- Known-classification coverage must be at least 75%.
- Unknown, unclassified, other, and broad-market labels are excluded.
- Sector gaps require at least 40% concentration in one known portfolio sector.
- Geography gaps require at least 60% concentration in one known country.
- Benchmark target weight must be at least 5%.
- The benchmark-minus-portfolio gap must be at least 10 percentage points.
- Theme association requires an observed profile theme weight below 30%.

These thresholds qualify research sources only. They do not calculate diversification benefit, assign candidate scores, or imply that an underweight dimension should be filled.

## Production Data Finding

The current stored TSX Composite proxy exposure snapshot dated 2026-06-20 contains 36.7777503% total exposure and labels that exposure `Unclassified`. It therefore fails both total and known-classification gates. Slice 5.4 truthfully returns incomplete benchmark coverage and no TSX sector/geography gap candidates until a sufficiently classified snapshot exists.

The stored `THEME_AI` proxy composition is available and dated, but constituents that cannot resolve to repository asset identity remain blocked by the Slice 5.3 identity policy.

## Tests

Nine focused fixtures cover:

- concentrated sector and geography gaps;
- balanced portfolios with no artificial gaps;
- unknown and incomplete classifications;
- profile coverage and portfolio-identity conflicts;
- invalid exposure totals;
- deterministic effective-dated peer and industry associations;
- profile-theme aliases and evidence;
- outside-holding pool merging and held-seed exclusion.

All candidate contract, persistence, universe, and Slice 5.4 tests pass: `45 passed`.

## Verification

```text
focused and combined candidate tests: 45 passed
repository tests: 508 passed, 1 existing Starlette/httpx deprecation warning
full Ruff: passed
architecture boundary command: passed
web lint: 0 errors, 4 existing Fast Refresh warnings
web tests: 88 passed
web production build: passed
four-cycle full data-health workflow with external audit: ok, no findings
web data-health scan: ok across 53 routes, no console errors or failed requests
API and Vite health checks: HTTP 200
```

The data-health workflow reported all 66 targets ready, no missing readiness, no pending jobs by cycle 3, no failed portfolio snapshot refreshes, 92 streaming subscriptions with no missing current prices, and zero variance across 12 external price checks.

The web scan reports warning-level text markers for truthful `Unavailable` or missing metrics on existing portfolio, signal, benchmark, broker, and Operations surfaces. All 53 routes returned HTTP 200 with no console errors or failed requests. The backend workflow completed its stored-data refreshes and returned no findings, so these labels represent source metrics that those existing views do not receive rather than a Slice 5.4 regression or stuck application state. Slice 5.4 adds no API route or UI surface.

The remote Actions result is recorded after the slice commit is pushed.

## Explicit Exclusions

This slice adds no quality, value, momentum, fit, diversification, redundancy, freshness, or final candidate score. It adds no recommendation action, trade behavior, provider call, data hydration, API route, or UI.

## Remaining Risks And Deferred Work

- Current production benchmark exposure coverage is not sufficient for several gap comparisons; this is surfaced rather than bypassed.
- Asset and peer-group labels are not immutable historical taxonomies, so source watermarks remain partial.
- The explicit theme alias set is intentionally narrow. Unknown profile themes report missing mappings.
- Slice 5.5 owns deterministic screens, scoring components, and final ordering. Slice 5.6 owns freshness adjudication and remaining guardrails.

## Gate Result

The Slice 5.4 source-coverage and taxonomy gate passes in code and focused fixtures. Stop after full verification and review; do not begin Slice 5.5 in this task.

## Next Model Recommendation

Use **GPT-5.6 Sol with max reasoning** for Slice 5.5. It combines existing quality/value/momentum inputs with profile fit, before/after diversification effects, redundancy, source support, deterministic tie-breaking, and anti-bypass fixtures; small policy errors can reorder every candidate result.
