# Phase 4 Deterministic Investor Profile Recovery

**Date:** 2026-08-05

**Branch:** `phase5-prediff`

**Purpose:** satisfy the missing Phase 4 prerequisite identified by the Phase 5 Slice 5.0 audit

## Result

Phase 4's deterministic investor-profile contract and inference engine are now implemented under `src/dashboard/rules_and_data`. The engine is pure backend code, uses no LLM or provider calls, preserves missing values, carries stable evidence IDs, rejects future evidence, and produces versioned deterministic output.

## Requirement Traceability

| Phase 4 requirement | Implementation |
| --- | --- |
| Holdings and allocation weights | `ProfileHolding.asset_id`, `ProfileHolding.weight` |
| Sectors and geographies | direct and look-through sector/geography fields |
| Asset classes | `ProfileHolding.asset_class` and allocation-mix inference |
| Volatility and risk | holding/portfolio volatility plus deterministic risk bands |
| Dividend and income | normalized income score with dividend-yield fallback |
| Valuation and factor metrics | normalized growth, value, quality, income, and speculative inputs |
| Concentration | direct and ETF look-through effective exposure and HHI |
| Turnover | optional turnover input in observed risk posture |
| Watchlist behavior | optional bounded speculative adjustment and evidence |
| Archetype labels | deterministic labels in `InvestorProfile.archetype_labels` |
| Factor scores and balance | five `ProfileDimension` outputs |
| Risk posture | `observed_risk_posture`, explicitly separate from suitability |
| Concentration profile | diversified, moderate, concentrated, or unknown |
| Domestic/international tilt | point-in-time look-through geography inference |
| Sector/theme tilt | deterministic exposure thresholds and stable ordering |
| ETF/passive/stock-picking mix | `AllocationMix` |
| Confidence | per-dimension and overall coverage/evidence quality |
| Evidence refs | validated `EvidenceRef` input and stable output IDs |
| Data gaps | sorted machine-readable gap codes without zero coercion |
| Explainable thresholds | `docs/investor_profile.md` |

## Fixture Gate

The required fixture classes are covered in `tests/rules_and_data/test_investor_profile.py`:

- concentrated growth;
- dividend/income;
- broad ETF-heavy;
- speculative small-cap;
- balanced;
- insufficient data.

Additional tests prove deterministic ordering and hashing, profile versioning, stated-suitability separation, watchlist behavior use, stale-evidence confidence reduction, future-evidence rejection, and invalid-input rejection.

## Safety Boundary

The output describes observed portfolio behavior. It does not assert stated risk tolerance, time horizon, liquidity capacity, suitability, or a recommendation. When stated preferences are absent, `suitability_status` is `not_assessed_missing_stated_inputs`. When they are present, it is `stated_inputs_present_not_assessed`.

## Verification

```text
ruff focused profile and architecture files: passed
profile plus architecture tests: 15 passed
architecture boundary command: passed
API health: 200, status ok, database connected
Vite application: 200
web data-health scan: passed process gate across 53 routes
web console errors: none
web failed requests: none
```

The repository-required four-cycle data-health workflow was attempted after starting the local API. It did not produce its JSON verdict before a ten-minute command timeout while provider-backed batches retried unavailable market data for `HQD.TO`, `HSU.TO`, and `RNW.TO`.

The independent web scan completed with `ok: true`, but it reported pre-existing `Unavailable`/`missing` markers on portfolio and related data pages plus failed-job text on Operations. These remain repository data-readiness blockers for later source-adapter and integration work. This recovery slice does not add a source adapter, API, persistence, or UI path, so those findings do not invalidate the deterministic contract and fixture gate claimed here.

## Slice 5.0 Gate Recheck

The Phase 4 blocker is resolved:

- versioned profile contract: present;
- deterministic inference: present;
- confidence and data gaps: present;
- stable evidence references: present;
- six required fixture classes: present;
- framework/provider independence: enforced by architecture check.

Slice 5.1 may begin after this recovery slice is committed and reviewed. No Slice 5.1 domain models were added here.

## Next Model Recommendation

Use **GPT-5.6 Sol with high reasoning** for Slice 5.1. Canonical candidate identities, serialization, and evidence invariants are contract-heavy and expensive to revise, but the work remains narrower than the cross-source identity and scoring slices that justify `xhigh` or `max`.
