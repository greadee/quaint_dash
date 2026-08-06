# Deterministic Investor Profile

The investor-profile engine describes observed portfolio behavior from stored, point-in-time evidence. It does not determine suitability, capacity for loss, or whether an asset should be bought or sold.

## Boundary

The public backend contract lives in `dashboard.ai_brain`:

- `InvestorProfileInput` is the normalized, provider-neutral input.
- `InvestorProfileEngine.infer()` is the pure deterministic inference boundary.
- `InvestorProfile` is the versioned output consumed by later portfolio-intelligence work.
- `EvidenceRef` identifies every source record used by the inference.

The package does not import FastAPI, DuckDB, provider clients, API response models, or UI code. Source adapters are responsible for translating stored analytics and evidence snapshots into `InvestorProfileInput`.

## Input Contract

Each run requires:

- portfolio ID;
- timezone-aware point-in-time `as_of`;
- domestic-country comparison code;
- positive-weight holdings with stable evidence;
- source schema version.

Holdings can provide:

- allocation weight;
- asset class;
- direct or look-through sector and geography exposure;
- themes and market-cap band;
- ETF/passive classification and look-through holding count;
- annualized volatility and dividend yield;
- normalized growth, value, quality, income, and speculative scores.

Portfolio-level volatility, turnover, watchlist behavior, and stated preferences are optional. If a supplied metric has no evidence, validation fails. Evidence newer than the profile `as_of` also fails.

## Output Contract

Every profile includes:

- deterministic profile ID and input snapshot hash;
- schema and methodology versions;
- archetype labels;
- growth, value, quality, income, and speculative dimensions;
- observed risk posture;
- concentration profile;
- domestic/international tilt;
- sector and theme tilts;
- ETF/passive/direct-stock mix;
- overall and dimension confidence;
- stable evidence IDs;
- structured data-gap codes;
- explicit inference and suitability boundaries.

`inference_scope` is always `observed_portfolio_behavior`. Stated preferences are preserved as evidence but do not turn the output into a suitability assessment.

## Factor Methodology

Explicit normalized factor inputs use a 0-100 scale. Holdings are weighted by portfolio allocation. Missing factors are excluded from the calculation and reduce coverage; they are never converted to zero.

Factor labels are:

| Score | Label |
| ---: | --- |
| below 35 | low |
| 35 to below 65 | moderate |
| 65 or above | high |

When no normalized income score exists, annual dividend yield maps linearly from 0% to 5%; 5% or above maps to 100. This is an observed income-orientation proxy, not a forecast.

When no normalized speculative score exists, the engine combines market-cap and volatility bands. Micro/small-cap and high-volatility holdings receive higher speculative scores. An available watchlist speculative ratio contributes a bounded 15% to the speculative dimension and cannot replace missing portfolio evidence.

## Risk Methodology

Observed risk posture combines only available components:

| Component | Weight |
| --- | ---: |
| portfolio or weighted holding volatility | 40% |
| speculative factor | 30% |
| concentration | 20% |
| turnover | 10% |

Risk labels are conservative through 35, moderate above 35 through 65, and aggressive above 65. If less than 50% of weighted risk evidence is available, the label is `unknown` even when a partial numeric score can be calculated.

Observed risk posture is not stated risk tolerance or capacity for loss.

## Concentration And Exposure

Direct holdings contribute their full squared weight to concentration. An ETF with a known look-through holding count divides its concentration contribution by up to 100 holdings. An ETF without look-through evidence receives no assumed diversification credit.

Concentration labels use effective largest exposure and HHI:

- diversified: largest exposure at most 15% and HHI at most 0.10;
- moderate: largest exposure at most 30% and HHI at most 0.25;
- concentrated: above either moderate threshold.

Geography uses look-through exposure when available, then direct geography as fallback. Domestic or international weight of at least 70% receives that tilt; at least 30% on both sides is balanced.

Sector tilts require more than 30% portfolio weight. Theme tilts require more than 15%. Generic `Other`, `Unknown`, and `Broad Market` classifications cannot become sector tilts.

## Archetypes

Archetypes are deterministic labels derived from the dimensions:

- `growth_oriented` and `value_oriented` require a score of at least 65 and a 10-point lead over the opposite factor;
- `quality_focused` requires quality of at least 70;
- `income_focused` and `speculative` require their factor to reach 65;
- `passive_allocator` and `stock_picker` require at least 70% corresponding allocation;
- `concentrated` follows the concentration profile;
- `balanced` requires all four core factors, a spread no greater than 20 points, speculative score below 55, and no aggressive or concentrated label;
- confidence below 0.35 returns only `insufficient_data`.

## Confidence And Evidence

Confidence measures coverage and evidence quality, not predictive accuracy. Evidence quality multipliers are:

- reported or derived: 1.00;
- estimated or proxied: 0.75;
- stale: 0.50;
- unsupported: 0.00.

Every positive-weight holding requires evidence. Stable evidence IDs use `evidence:<lowercase SHA-256>`. Duplicate IDs must identify identical evidence. Stale evidence remains visible through `evidence.stale` and lowers confidence.

## Determinism

Input hashing uses canonical UTF-8 JSON with sorted keys, stable holding/evidence ordering, UTC whole-second timestamps, and decimal strings quantized to eight places using round-half-even. Equivalent input ordering produces the same profile ID and output.

Current versions:

- schema: `investor-profile.v1`;
- methodology: `investor-profile.deterministic.v1`.

Any threshold or semantic change requires a methodology-version change. Any contract-shape change requires a schema-version change.

## Verification

```powershell
.\.venv\Scripts\python.exe -m ruff check src\dashboard\ai_brain tests\ai_brain
.\.venv\Scripts\python.exe -m pytest tests\ai_brain\test_investor_profile.py -q
.\.venv\Scripts\python.exe -m tools.check_architecture_boundaries
```

The fixture suite covers concentrated growth, dividend/income, broad ETF-heavy, speculative small-cap, balanced, and insufficient-data portfolios.
