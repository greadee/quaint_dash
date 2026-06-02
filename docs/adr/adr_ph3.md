# Phase 3 - Analytics

## ADR-061: Calculation-First Analytics Layer

**Decision:** Phase 3 analytics will begin as a calculation layer over existing stored data, without triggering new provider ingestion.

**Context:**
The project already stores transactions, positions, daily asset prices, dividends, splits, raw financial statements, benchmark prices, and benchmark metrics. Not every user or database will have all of those tables populated.

Analytics must therefore work with partial data and identify missing inputs clearly.

**Rationale:**
- Reuses existing ingestion outputs before adding more provider calls
- Keeps calculations deterministic and testable
- Avoids hiding provider gaps behind guessed assumptions
- Allows risk metrics to work from price history even when valuation inputs are missing
- Keeps future ingestion decisions separate from analytics model design

**Implementation Notes:**
- Analytics live in:
  - `dashboard.analytics`
- Core asset analytics include:
  - cumulative return
  - expected CAGR
  - annualized volatility
  - Sharpe ratio
  - Sortino ratio
  - max drawdown
  - best/worst daily return
- Relative analytics can compare against benchmark price history:
  - beta
  - annualized alpha
  - correlation
  - R-squared
  - excess CAGR
- Intrinsic value analytics include:
  - dividend discount model
  - discounted cash flow model
  - margin of safety
  - implied priced-in growth
- Missing dividends, financial statements, market prices, or benchmark data are reported as missing inputs.

## ADR-062: Existing Data Before New Ingestion

**Decision:** Analytics should inspect and use already-stored project data before requesting or scheduling any new ingestion.

**Context:**
The phase 3 analytics layer depends on several data domains:
- historical prices from `asset_quote_daily`
- dividends from `dividend_event`
- financial statements from `financial_statement`
- portfolio holdings from `position`
- benchmark history from `benchmark_index_daily_price`

Some local databases may contain prices but not fundamentals, dividends, positions, or benchmark tables.

**Rationale:**
- Prevents unnecessary provider usage
- Keeps analytics available offline once data exists
- Makes local data gaps visible
- Preserves free-tier provider capacity
- Aligns with the project rule that portfolio transactions remain the source of truth

**Implementation Notes:**
- `AnalyticsRepository.data_coverage()` reports available input coverage.
- DDM returns no intrinsic value when annual dividends are missing.
- DCF returns no intrinsic value when free cash flow per share is missing.
- Relative metrics are optional and require benchmark price overlap.
- No new ingestion provider was added for phase 3 analytics.

## ADR-063: Optional Analytics Snapshot Storage

**Decision:** Analytics storage will be opt-in, not mandatory.

**Context:**
Advanced analytics can produce many derived values and JSON payloads. These snapshots will be useful for later AI features, but some users may not want the storage overhead or derived-data persistence.

**Rationale:**
- Gives users control over storage growth
- Keeps ad hoc analytics lightweight
- Avoids forcing derived data on every installation
- Provides an AI-ready cache for users who opt in
- Keeps snapshot tables out of databases where analytics persistence is disabled

**Implementation Notes:**
- Optional persistence is handled by:
  - `AnalyticsStorageService`
- Default behavior:
  - disabled
  - no analytics snapshot tables are created
  - `refresh_due()` returns a skipped result
- When enabled, the service creates:
  - `analytics_storage_config`
  - `asset_analytics_snapshot`
  - `portfolio_analytics_snapshot`
  - `analytics_refresh_state`
- Snapshot tables store:
  - compact queryable metric columns
  - full JSON payloads for future AI context
  - missing-input JSON
  - refresh timestamps

## ADR-064: Daily and Portfolio-Change Refresh Cadence

**Decision:** Stored analytics snapshots should refresh at least daily, and portfolio snapshots should refresh again when portfolio state changes.

**Context:**
Analytics values can change because of:
- new daily prices
- new dividends
- new financial statements
- new benchmark data
- changed portfolio positions

For AI use, the latest snapshot should be fresh enough to answer current questions while avoiding repeated recomputation on every read.

**Rationale:**
- Keeps stored analytics reasonably current
- Avoids unnecessary same-day rewrites when nothing changed
- Captures same-day portfolio edits immediately
- Provides a stable latest-snapshot surface for future AI prompts
- Keeps refresh behavior deterministic and easy to test

**Implementation Notes:**
- Asset snapshots are due when:
  - no asset refresh state exists
  - the last asset snapshot date is before the requested snapshot date
- Portfolio snapshots are due when:
  - no portfolio refresh state exists
  - the last portfolio snapshot date is before the requested snapshot date
  - the portfolio state signature changed
- Portfolio signatures include:
  - asset ids
  - quantities
  - book costs
  - position update timestamps
  - latest available price dates
- Refresh state is stored in:
  - `analytics_refresh_state`
