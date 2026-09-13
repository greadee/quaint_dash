# Deterministic Business Strength Scorecard

## Purpose

The Business Strength Scorecard evaluates the quality and resilience of an operating business from
stored structured data. It is separate from valuation attractiveness, expected CAGR, risk-adjusted
return, price momentum, and technical indicators.

This phase is deterministic only. It does not call LLMs, browse filings, infer qualitative moat
claims, or fabricate missing data.

## Architecture

Backend code lives in `dashboard.services.business_strength`:

- `analyzer.py`: loads standardized inputs, scores metrics/categories, and persists runs.
- `templates.py`: sector and industry template registry plus classification rules.
- `normalization.py`: absolute, peer, historical, and target-range normalization helpers.
- `explanations.py`: deterministic metric and category explanation templates.
- `persistence.py`: methodology, template, classification, analysis, category, and metric storage.
- `models.py`: deterministic input, score, category, metric, and future research interfaces.

Provider-specific retrieval stays outside the scoring engine. The engine consumes standardized
financial-statement and metadata inputs from DuckDB.

## Score Categories

Default weights sum to 100%:

- Competitive Strength - Quantitative: 15%
- Growth Quality: 12%
- Profitability: 13%
- Earnings and Revenue Durability: 13%
- Financial Strength: 12%
- Capital Efficiency: 12%
- Capital Allocation: 8%
- Cyclicality and Resilience: 8%
- Concentration and Dependency Risk: 7%

The canonical score is 0-100. The UI also displays a 1-10-style value where useful.

## Classification Thresholds

- 90-100: Exceptional
- 80-89: Very Strong
- 70-79: Strong
- 60-69: Above Average
- 50-59: Average
- 40-49: Below Average
- 30-39: Weak
- 0-29: Very Weak

## Templates

The registry includes active templates for semiconductor designers, foundries, equipment, memory,
networking hardware, enterprise software, SaaS, payments networks, banks, insurers, asset managers,
exchanges and financial data, alternative asset managers, medical devices, pharmaceuticals,
industrial compounders, engineering and consulting, waste management, consumer staples, consumer
discretionary, marketplaces, travel, utilities, midstream, REITs, and diversified holding companies.

Ticker-specific mappings are used only for classification of known portfolio examples such as NVDA,
TSM, V, JPM, BN, ISRG, WCN, FTS, ENB, AMZN, and CSU.TO. Scores are never hard-coded by ticker.

## Normalization

Each metric becomes a 0-100 score by deterministic rules:

- absolute threshold scoring
- peer percentile scoring
- historical percentile scoring
- target-range scoring
- caps and floors through clamping

Missing metrics are excluded from score contribution and reduce confidence. They are not converted
to zero. `not_applicable` metrics do not reduce score or confidence.

## Confidence

Confidence reflects available required metrics, peer data, historical data, stale inputs, estimated
inputs, and unknown values. Low confidence is displayed in the asset and compare UI.

Explicit statuses include `reported`, `derived`, `normalized`, `estimated`, `unknown`,
`not_applicable`, `stale`, and `conflicting`.

## Persistence

Schema is defined in `src/dashboard/db/migrations/business_strength.sql`:

- `business_strength_methodology`
- `business_strength_template`
- `asset_business_classification`
- `business_strength_analysis_run`
- `business_strength_category_score`
- `business_strength_metric_result`
- `business_strength_peer_group`
- `business_strength_peer_member`
- `business_strength_override`
- `business_strength_future_research_input`

The future research table is intentionally not populated in this deterministic phase.

## API

- `GET /api/v1/assets/{asset_id}/business-strength`
- `GET /api/v1/assets/{asset_id}/business-strength/history`
- `GET /api/v1/assets/{asset_id}/business-strength/audit`
- `POST /api/v1/assets/{asset_id}/business-strength/recalculate`
- `POST /api/v1/compare/business-strength`
- `GET /api/v1/business-strength/templates`
- `GET /api/v1/business-strength/methodologies`

## UI

The asset detail view has a Business Strength tab. The Compare workflow has a Business Strength
section that reuses selected tickers and supports template-adjusted and common-metric views.

## CLI

Interactive commands:

- `business-strength-run <asset-id|ticker|all> [--force] [--max-assets N]`
- `business-strength-refresh <asset-id|ticker|all> [--max-assets N]`
- `business-strength-show <asset-id|ticker>`
- `business-strength-validate <asset-id|ticker|all> [--max-assets N]`
- `business-strength-template-list`
- `business-strength-template-show <template-code>`

## Scheduler Behavior

Scorecard refresh is safe to run independently. The API returns the latest persisted scorecard when
available and recalculates only when no scorecard exists or explicit recalculation is requested.
Scorecard generation failures do not block transaction imports or core app startup.

## Future Agent Layer

`BusinessStrengthResearchProvider`, `BusinessStrengthQualitativeInput`,
`BusinessStrengthEvidenceRecord`, and `BusinessStrengthOverrideProposal` define inactive extension
points. Future LLM or agent research may propose reviewed qualitative inputs, but deterministic
code remains the owner of numerical scoring.

## Adding Metrics or Templates

Add metrics in `templates.py`, validate directionality and normalization rules, and add regression
fixtures with exact expected outputs. New templates should override category weights or metric sets
only where the sector economics require it.

## Reproducing a Historical Score

Use the persisted analysis run, methodology version, template version, source timestamps, category
rows, and metric rows. Do not recompute older runs with revised current data unless the result is
clearly labeled as restated.
