# Phase 5 Candidate Engine Prerequisite Audit

**Audit date:** 2026-08-05

**Branch:** `phase5-prediff`

**Slice:** 5.0 - Prerequisite Audit And Contract Freeze

**Scope:** deterministic outside-holding candidate engine prerequisites only

## Gate Result

**Blocked. Do not begin Slice 5.1.**

The repository has substantial deterministic analytics, ranking, benchmark, watchlist, and evidence-adjacent foundations. It does not have the required Phase 4 deterministic investor-profile contract or its fixture coverage.

`AIReadinessContext` is not an investor profile. It summarizes computed portfolio or asset facts, explanations, anomalies, missing inputs, and a snapshot hash. It does not represent user objectives, time horizon, liquidity needs, risk tolerance, income preference, stated constraints, profile confidence, profile methodology version, or profile evidence references (`src/dashboard/analytics/models.py:294-302`, `src/dashboard/analytics/calculations.py:1273-1469`).

Phase 5 may not infer those profile fields inside candidate scoring. The next implementation task must complete or formally recover Phase 4 before Slice 5.1 starts.

## Status Vocabulary

- **Available:** a stored or deterministic local source exists with usable tests and a reasonably narrow adapter boundary.
- **Partial:** relevant behavior exists, but the Phase 5 contract, provenance, freshness, identity, or coverage requirement is incomplete.
- **Missing:** no implementation matching the required contract was found.
- **Stale-capable:** timestamps or snapshots exist, but candidate-specific freshness policy is not implemented.
- **Unsupported:** the current system explicitly represents the input as not applicable or unavailable by design. No required Phase 5 source family is globally waived by this status.

## Dependency Matrix

| Dependency | Status | Verified implementation | Gap before use by Phase 5 |
| --- | --- | --- | --- |
| Deterministic investor profile | **Missing - blocker** | No matching model, table, service, API contract, or fixture suite was found by repository search. | Complete Phase 4 with a versioned profile, confidence, missing inputs, evidence references, deterministic bands, and the six required portfolio fixtures. |
| Portfolio analytics context | Partial, stale-capable | `AIReadinessContext`, `portfolio_ai_context()`, analytics report serialization, and daily analytics persistence exist (`src/dashboard/analytics/models.py:294-302`, `src/dashboard/analytics/calculations.py:1273-1523`, `src/dashboard/analytics/persistence.py:168-221`). | Context has no `as_of`, freshness, coverage, stable evidence IDs, methodology version, or source-record identity. It must be adapted through a Phase 5 evidence snapshot rather than treated as the profile. |
| Existing analytics snapshot hash | Partial | `_ai_snapshot_hash()` hashes facts, anomalies, and missing inputs with sorted object keys (`src/dashboard/analytics/calculations.py:1761-1774`). Tests confirm a hash is present (`tests/test_analytics.py:186-189`, `tests/test_analytics.py:299-302`). | The hash omits schema version, subject identity, `as_of`, source watermarks, numeric precision policy, and explicit list ordering. It is not sufficient as the Phase 5 input snapshot identity. |
| Portfolio analytics persistence | Partial, stale-capable | Daily asset and portfolio snapshots persist JSON payloads; portfolio rows include a state signature (`src/dashboard/db/schema.sql:20-35`, `src/dashboard/analytics/persistence.py:107-221`). | Same-day rows are mutable upserts. Candidate runs need immutable input identity, source watermarks, and compatibility checks. |
| Stock ranking inputs | Available with adapter limits | Deterministic ranking models, `stock_rankings()`, all/tracked universes, item construction, snapshots, and API tests exist (`src/dashboard/api/models.py:597-637`, `src/dashboard/api/services.py:5038-5093`, `src/dashboard/api/services.py:5317-5386`, `tests/api/test_portfolio_api.py:1158-1270`). | The all universe includes held assets. Ranking items are nominations, not candidate reviews, and expose no stable evidence references, fit, diversification, redundancy, or candidate guardrails. |
| Ranking freshness | Partial, stale-capable | Ranking items carry `latest_data_date`, missing inputs, data status, and confidence (`src/dashboard/api/models.py:606-624`, `src/dashboard/api/services.py:5726-5782`). | Candidate-specific stale/block policy is absent. Ranking confidence bottoms out at a nonzero freshness contribution for data older than 90 days (`src/dashboard/api/services.py:9026-9048`). |
| Active watchlist | Available | `watchlist_ticker` has active state and source; ranking universe joins it (`src/dashboard/db/schema.sql:126-134`, `src/dashboard/api/services.py:5469-5504`). Tests cover watchlist persistence (`tests/api/test_portfolio_api.py:1533`). | Phase 5 needs a source adapter with point-in-time identity and evidence references. |
| All-universe asset discovery | Partial | `_stock_ranking_universe("all")` reads stock assets and catalog-derived assets and marks held, tracked, and watchlisted state (`src/dashboard/api/services.py:5440-5525`). | The method lives in the API service, triggers input hydration elsewhere in the ranking path, and has no candidate-safe pagination/snapshot contract. |
| Sector and geography exposure | Available with adapter limits | Portfolio risk decomposition calculates sector and country exposure plus concentration and diversification (`src/dashboard/analytics/calculations.py:292-339`, `src/dashboard/analytics/models.py:119-132`). Tests cover concentration, sector, and country outputs (`tests/test_analytics.py:992-1038`). | Phase 5 needs an explicit comparison target and profile-permission policy. Existing exposure alone does not prove that an underweight dimension should be filled. |
| Benchmark constituents and proxies | Available, coverage-dependent | Benchmark constituent storage, sector/industry/theme proxy universe, and ingestion services exist (`src/dashboard/ingestion/indices/index_queries.py:194-218`, `src/dashboard/ingestion/indices/sector_industry_index_universe.py`, `src/dashboard/ingestion/indices/index_ingestion_service.py:337-404`). Tests cover constituents and proxy categories (`tests/ingestion_benchmarks/test_index_composition.py:82`, `tests/ingestion_benchmarks/test_benchmark_sector_industry_seed.py:10-113`). | Candidate adapters must preserve constituent snapshot dates, proxy status, provider coverage, and missing composition rather than treating proxies as direct constituents. |
| Peer and industry associations | Partial | Assets carry sector/industry metadata; benchmark association and sector-peer financial metrics exist (`src/dashboard/api/services.py:9544-9582`, `src/dashboard/ingestion/indices/benchmark_financial_metrics.py:96-125`). Tests cover benchmark associations and peer coverage (`tests/api/test_benchmark_api.py:328-411`, `tests/ingestion_benchmarks/test_benchmark_financial_metrics.py:125-163`). | No versioned company-to-peer association contract exists. Sector medians and ETF proxy associations cannot be mislabeled as direct company peers. |
| Theme associations | Partial | Versioned-in-code theme ETF proxies are seeded as non-core benchmarks (`src/dashboard/ingestion/indices/sector_industry_index_universe.py:247-332`, `src/dashboard/ingestion/indices/sector_industry_index_universe.py:570-637`). | Profile alignment is impossible until Phase 4 exists. Theme proxy membership and company-theme evidence need distinct reason codes. |
| Quality, value, and momentum metrics | Partial | Holding factor components include Value, Growth, Quality, Momentum, and Sentiment (`src/dashboard/api/services.py:4957-5028`); ranking includes price momentum and aggregate factor inputs (`src/dashboard/api/services.py:5726-5788`). Tests cover factor availability (`tests/api/test_portfolio_api.py:1344-1442`). | Logic is embedded in `PortfolioApiService` and oriented to holdings. Phase 5 needs read-only adapters, stable methodology versions, missing-value preservation, and outside-holding coverage. |
| Valuation highlights | Available with coverage limits | Asset and portfolio analytics expose DCF/DDM, P/E, price-to-free-cash-flow, margin of safety, and forecast facts (`src/dashboard/analytics/calculations.py:1153-1197`, `src/dashboard/analytics/calculations.py:1373-1421`). | Candidate evidence needs source dates, applicable-asset rules, and critical versus noncritical missing-field policy. |
| Risk highlights | Available with coverage limits | Risk-return and portfolio decomposition include volatility, drawdown, beta, concentration, and diversification (`src/dashboard/analytics/models.py:66-132`, `src/dashboard/analytics/calculations.py:292-339`). | Candidate guardrails need explicit thresholds, liquidity/speculative-risk inputs, and point-in-time evidence references. |
| Sentiment highlights | Available with coverage limits | Stored news and retail sentiment feed ranking components and daily snapshots (`src/dashboard/api/services.py:5738-5741`, `src/dashboard/api/services.py:5830-6086`). | Sentiment must not act as sole material support. Source dates, provider coverage, and stale/conflicting evidence policy remain to be defined in Slice 5.6. |
| Stable evidence references | **Missing - blocker for candidate emission** | Signal evidence stores labels, metrics, values, source, and `as_of`; database rows include positional evidence IDs (`src/dashboard/api/models.py:698-705`, `src/dashboard/db/schema.sql:241-252`). | API evidence items expose no evidence ID, and persisted IDs such as `supporting-0` are scoped by list position (`src/dashboard/api/services.py:4572-4597`). Phase 5 needs stable source-record-derived references. |
| Economic-exposure identity | Partial | CDR underlying resolution and ETF overlap analytics exist (`src/dashboard/api/services.py:6375-6380`, `src/dashboard/analytics/calculations.py:807-857`). Tests cover CDR fundamentals and ETF overlap (`tests/test_analytics.py:604`, `tests/test_analytics.py:963-964`). | There is no unified canonical economic-exposure resolver for direct holdings, CDRs, ETFs, duplicates, and unresolved mappings. Slice 5.3 must fail closed according to ADR PH13. |
| Missing-data reporting | Available with adapter limits | Analytics and ranking models preserve missing inputs instead of universally coercing them to zero (`src/dashboard/analytics/models.py:301`, `src/dashboard/api/models.py:623`, `src/dashboard/api/services.py:5747-5781`). | Candidate contracts need structured criticality, source identity, guardrail effect, and deterministic ordering. |
| Candidate persistence | Missing | No candidate run, review, source-match, warning, or candidate-evidence tables were found. | Slice 5.2 adds only the minimum candidate persistence after Slice 5.1 contracts pass. |
| Candidate engine tests | Missing | Existing tests cover analytics, rankings, signals, benchmarks, and watchlists. | No tests currently prove held-asset exclusion, evidence-required emission, stale downgrade/block, candidate missing metrics, or deterministic candidate ties. |

## Verified Reuse Boundaries

Phase 5 should reuse these capabilities through adapters:

- analytics calculations and persisted reports for portfolio and asset metrics;
- stock-ranking snapshots as one nomination source;
- `watchlist_ticker` as one nomination source;
- benchmark constituent and proxy snapshots with their actual source dates;
- asset classification, CDR underlying resolution, and ETF overlap calculations;
- structured missing inputs from analytics and ranking outputs.

Phase 5 must not:

- import API response models as domain contracts;
- add candidate orchestration to `PortfolioApiService`;
- call `_ensure_stock_ranking_inputs()` or any provider/hydration path during a candidate run;
- treat `AIReadinessContext` as an investor profile;
- reuse positional signal evidence IDs as stable candidate evidence IDs;
- mutate existing snapshots to represent a candidate run.

## Frozen Consumer Requirements For Phase 4

Before Slice 5.1, Phase 4 must provide a deterministic profile containing at least:

- stable profile ID and portfolio scope;
- profile schema and methodology versions;
- point-in-time `as_of` value and input snapshot hash;
- objective/style bands, including growth, income, capital preservation, and speculative tolerance where evidence supports them;
- risk-capacity and observed-risk bands kept distinct from stated risk tolerance;
- time horizon, liquidity needs, constraints, and suitability inputs when supplied by the user;
- confidence and coverage per inferred dimension;
- structured missing inputs and blocking conditions;
- stable evidence references for every inferred dimension;
- deterministic fixture coverage for concentrated growth, dividend/income, broad ETF-heavy, speculative small-cap, balanced, and insufficient-data portfolios.

If user-stated suitability inputs do not exist, the profile must state that limitation. Observed holdings must not be presented as proof of the user's stated goals or capacity for loss.

## Slice 5.0 Stop Report

### Changed Files

- `docs/evidence/2026-08-05-phase5-candidate-prerequisite-audit.md`
- `docs/adr/adr_ph13_candidate_engine_boundary.md`
- `docs/adr/index.md`

No runtime code, schema, API, provider, or UI behavior changed.

### Implemented

- Classified every Phase 5 prerequisite as available, partial, missing, stale-capable, or unsupported.
- Separated analytics context from investor-profile inference.
- Identified safe reuse boundaries and prohibited coupling.
- Froze the candidate vocabulary, point-in-time policy, canonical identity rules, precision rules, and hashing policy in ADR PH13.

### Gate Outcome

Failed because the Phase 4 investor-profile contract and fixtures are missing. Slice 5.1 is not authorized by the completion plan until that prerequisite is complete.

### Next Work, Not Started

Complete the Phase 4 deterministic investor-profile contract and fixtures, then rerun the Slice 5.0 gate. After that gate passes, proceed to Slice 5.1.

### Recommended Model

Use **GPT-5.6 Sol with high reasoning** for the Phase 4 recovery slice. The work requires contract design, financial-domain distinctions, deterministic inference bands, and fixture review, but it should remain narrower than the cross-source identity and scoring slices that justify `xhigh` or `max`.

## Recheck After Phase 4 Recovery

The blocker recorded by this point-in-time audit was resolved later on 2026-08-05. The versioned deterministic profile contract, evidence handling, confidence, data gaps, and six fixture classes are documented in `docs/evidence/2026-08-05-phase4-investor-profile-recovery.md`.

The original gate result above is preserved as audit history. Commit `7035661` was reviewed as the Phase 4 recovery input, and the Slice 5.0 gate was rerun before starting Slice 5.1.

### Recheck Evidence

- The original master prompt's Phase 4 output list maps to `InvestorProfile`: archetypes, five factor scores, observed risk posture, concentration, geography, sector/theme tilts, allocation mix, confidence, evidence IDs, and data gaps.
- `InvestorProfile` carries stable profile identity, schema and methodology versions, a UTC point-in-time timestamp, and an input snapshot hash.
- `EvidenceRef` validates stable content-derived IDs, source schema, payload hash, status, and timezone-aware `as_of`; future evidence is rejected.
- Stated preferences remain separate from observed behavior and do not produce a suitability conclusion.
- The required six portfolio classes and determinism, stale-evidence, future-evidence, and malformed-input invariants are covered by `tests/ai_brain/test_investor_profile.py`.
- The architecture boundary includes `src/dashboard/ai_brain` in the framework-independent backend core.

```text
python -m pytest tests/ai_brain/test_investor_profile.py tests/test_architecture_boundaries.py -q
15 passed

python -m tools.check_architecture_boundaries
Architecture boundary check passed.
```

### Recheck Result

**Passed.** The Phase 4 prerequisite is available and tested. Slice 5.1 is authorized. No candidate schema, persistence, adapter, ranking, scoring, API, provider, or UI behavior was added by this recheck.
