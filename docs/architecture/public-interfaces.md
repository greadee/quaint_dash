# Public Interface Specifications

Interfaces listed here are target contracts. They are not all implemented in
Phase 1.5.

## Portfolio

### `GetPortfolioSummary`

- Owner: Portfolio application module.
- Purpose: Return portfolio value, return, allocation, and contribution summary.
- Input: `portfolio_id`, optional `date_range`, optional benchmark id,
  authenticated user context.
- Output: `PortfolioSummary` with holdings, valuation, return metrics,
  allocation groups, provenance, freshness, and warnings.
- Errors: not found, unauthorized, insufficient data, stale data warning.
- Behavior: read-only, cacheable by portfolio/date range, deterministic.
- Consumers: web overview, mobile summary, desktop research, AI explanation.

### `GetHoldingBreakdown`

- Owner: Holdings.
- Input: `portfolio_id`, grouping dimensions, optional as-of date.
- Output: positions, exposure groups, contribution rows, scorecard references.
- Freshness: price and fundamentals timestamps required.

## Asset Research

### `GetAssetOverview`

- Owner: Asset Research.
- Input: `asset_id` or normalized symbol, optional market/currency preference.
- Output: identity, quote summary, price history summary, fundamentals summary,
  news references, scorecard references, data quality state.
- Consumers: asset page, compare workspace, mobile asset card, AI research.

### `GetAssetPriceHistory`

- Owner: Market Prices.
- Input: asset id, date range, interval, adjustment preference.
- Output: ordered `PricePoint[]`, currency, adjustment status, provenance.
- Errors: unknown asset, no price history, provider unavailable.

### `GetAssetFundamentals`

- Owner: Fundamentals.
- Input: asset id, metric set, period preference.
- Output: typed metric values with fiscal period, provider, freshness, and
  missing-value explanations.

## Analytics

### `CalculatePortfolioPerformance`

- Owner: Performance Analytics.
- Input: portfolio positions/transactions, price series, benchmark optional,
  date range.
- Output: total return, CAGR, drawdown, volatility-ready series, benchmark delta.
- Audit: calculation version and input references required.

### `CalculatePortfolioRisk`

- Owner: Risk Analytics.
- Input: return series, benchmark series, risk-free assumption if required.
- Output: volatility, beta, correlation, Sharpe-style values, missing data notes.

### `CalculateBusinessStrengthScore`

- Owner: Business Strength.
- Input: normalized fundamentals, price context, sector/industry context.
- Output: category grades, aggregate grade, evidence rows, missing inputs.
- Consumers: asset page, holding cards, compare workspace.

## News And Sentiment

### `GetTickerNews`

- Owner: News.
- Input: asset id/symbol, date range, pagination, source filters.
- Output: news items, sentiment tags, provider/source metadata, freshness.
- Mobile: payload should support compact summary mode.

### `GetSentimentSignals`

- Owner: Sentiment.
- Input: asset ids or universe, signal date range, provider set.
- Output: normalized sentiment metrics, confidence, missing coverage.

## Operations And Data Quality

### `GetOperationsStatus`

- Owner: Operations/Data Quality.
- Input: authenticated admin/operator context.
- Output: ingestion worker, market freshness, data readiness, ranking readiness,
  and job queue status.
- Authorization: admin/operator only for write controls; read status can be
  broadened later if needed.
- Freshness: every status section includes `checked_at` or equivalent.

### `RunIngestionJob`

- Owner: Operations/Data Quality.
- Input: job type, domain/symbol filters, run limits, authenticated operator.
- Output: accepted job/result summary and idempotency key.
- Idempotency: required for external provider-sensitive jobs.

## Preferences And Widgets

### `GetWidgetConfiguration`

- Owner: Widget Configuration/User Preferences.
- Input: user id, platform, page id.
- Output: feature availability and layout preferences.
- Platform: web and desktop may expose full layout; mobile exposes supported
  cards only.

### `UpdateWidgetConfiguration`

- Owner: Widget Configuration/User Preferences.
- Input: page id, widget ids, visibility/order, platform.
- Output: stored configuration version.
- Authorization: user-owned write.

## AI

### `GenerateTickerInsight`

- Owner: AI Insights.
- Input: subject asset id, deterministic metric references, news references,
  prompt/template version, user consent context.
- Output: `AIInsight` with text, evidence, model id, generated timestamp,
  confidence, limitations, and data freshness.
- Rule: may not create or overwrite deterministic metrics.

