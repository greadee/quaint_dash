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
- The public analytics API remains `dashboard.analytics`.
- Focused implementation modules are:
  - `dashboard.analytics.models` for report and metric contracts
  - `dashboard.analytics.repository` for stored-data access
  - `dashboard.analytics.calculations` for deterministic calculations
  - `dashboard.analytics.engine` for report orchestration
  - `dashboard.analytics.persistence` for optional snapshot storage
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
- Valuation depth analytics include:
  - revenue, EPS, and free-cash-flow growth
  - gross, operating, and net margins
  - return on equity and return on assets
  - debt-to-equity and net debt-to-EBITDA
  - payout ratio and valuation multiples
  - bear/base/bull DCF scenarios
- ETF analytics include:
  - expense ratio
  - distribution yield
  - tracking error
  - top holdings
  - sector, country, and currency exposure
  - overlap with direct portfolio holdings
- Forecast analytics include:
  - expected CAGR from valuation mean reversion
  - dividend growth projection
  - fundamental growth assumption
  - blended expected CAGR
  - deterministic p10/p50/p90 simulation bands
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

## ADR-065: AI-Ready Analytics Context

**Decision:** Asset and portfolio analytics reports include structured AI-readiness context inside the existing report payload.

**Context:**
The future AI layer should be able to answer questions from a predictable, compact representation of the latest analytics without reverse-engineering every raw metric object. The context must still be derived from deterministic analytics outputs and should not require analytics storage to be enabled.

**Rationale:**
- Gives the AI layer stable facts, summaries, explanations, and anomaly flags
- Keeps optional storage useful by persisting the same context in report JSON payloads
- Avoids adding new tables before the AI product surface is finalized
- Supports comparing stored snapshots over time through fact-level change detection
- Keeps missing-input caveats visible to downstream consumers

**Implementation Notes:**
- `AssetAnalyticsReport` and `PortfolioAnalyticsReport` include `ai_context`.
- `AIReadinessContext` contains:
  - subject type and id
  - summary
  - structured facts
  - explanations with supporting evidence labels
  - anomaly flags
  - missing inputs
  - snapshot hash
- `compare_ai_snapshot_facts()` reports fact changes between two contexts with absolute and relative change values when both sides are numeric.
- Anomaly flags currently cover missing inputs, high volatility, drawdown, valuation downside, high P/E, leverage, ETF tracking error, concentration, low diversification, and portfolio volatility.

## ADR-066: User-Facing Analytics Commands and Stable Payloads

**Decision:** Analytics reports are available through dashboard CLI commands and can be emitted as a stable JSON payload.

**Context:**
The analytics engine is useful only if users and future application layers can access it through a predictable public boundary. Human-readable command output is useful for quick inspection, while JSON output is needed for dashboard, API, and AI integrations.

**Rationale:**
- Gives users direct asset and portfolio analytics access
- Keeps optional analytics storage configurable without code changes
- Provides a stable report shape for future UI/API/AI consumers
- Avoids coupling downstream layers to internal dataclass layout changes

**Implementation Notes:**
- `analytics asset <asset-id>` prints an asset analytics summary.
- `analytics portfolio <portfolio-id>` prints a portfolio analytics summary.
- `--json` emits `phase3.analytics.v1` payloads with:
  - schema version
  - report type
  - subject id
  - selected benchmark id
  - AI context
  - full report payload
- `analytics storage status|enable|disable|refresh` manages optional analytics snapshot storage.
- `dashboard.models.commands.analytics.AnalyticsCommands` is the application-facing command boundary.

## ADR-067: Benchmark Defaults and Portfolio Valuation Rollups

**Decision:** Asset and portfolio analytics can select default benchmarks, and portfolio reports include weighted valuation rollups.

**Context:**
Alpha, beta, and relative return metrics are easier to use when the system can infer a reasonable benchmark from available data. Portfolio analytics also need a valuation posture, not only risk and return metrics, so users can see how much of the portfolio appears undervalued, overvalued, income-producing, or dependent on expected growth.

**Rationale:**
- Reduces manual benchmark setup for common workflows
- Uses stored ETF profile benchmark IDs when available
- Uses benchmark metadata, geography, and currency before falling back to common core indices
- Makes portfolio valuation explainable through weighted holding metrics
- Adds expected-return contribution by holding for future allocation analysis

**Implementation Notes:**
- Asset reports prefer explicit benchmark, then ETF profile benchmark, then stored benchmark metadata, then available static core index defaults.
- Portfolio reports choose a default benchmark from dominant valued position geography/currency.
- Portfolio valuation rollups include:
  - weighted margin of safety
  - weighted P/E
  - weighted price/free cash flow
  - weighted dividend yield
  - weighted expected CAGR
  - undervalued, fair-value, and overvalued weights
  - holding-level expected CAGR contribution

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

## ADR-068: Focused Analytics Package Boundaries

**Decision:** Keep `dashboard.analytics` as the stable public import surface while splitting analytics implementation into focused model, repository, calculation, orchestration, and persistence modules.

**Context:**
Phase 3 grew from a small set of risk calculations into a broad analytics system covering valuation, ETF analysis, forecasting, portfolio decomposition, AI-ready context, and optional persistence. Keeping all responsibilities in one module made ownership and onboarding harder.

**Rationale:**
- Keeps deterministic calculations independent from database access.
- Keeps report orchestration readable without hiding calculation behavior.
- Isolates optional persistence from ad hoc analytics.
- Preserves existing public imports for downstream commands and tests.
- Gives future contributors clear module ownership.

**Implementation Notes:**
- `AnalyticsRepository` is the only analytics component responsible for reading stored market and portfolio data.
- `AnalyticsEngine` orchestrates repository reads and pure calculation functions into reports.
- `AnalyticsStorageService` owns opt-in snapshot schema creation and refresh behavior.
- Analytics dataclasses in `dashboard.analytics.models` define the stable internal report contracts.
- `dashboard.analytics.__init__` re-exports the supported public API.
- The historical package relationships are preserved in `docs/archive/diagrams/classes/plantuml-code/analytics_ph3.puml`.
