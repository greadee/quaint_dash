# Feature and Widget Segmentation Planning Pass

Planning status: inspection-only architecture inventory. No refactor or behavior change is part of
this pass.

Inspection date: 2026-07-10.

Primary evidence:

- Frontend shell and routes: `web/src/App.tsx`, `web/src/appRoutes.tsx`, `web/src/routes/*`,
  `web/src/benchmarks.tsx`, `web/src/pageFeatures.ts`, `web/src/pageFeatureStore.tsx`,
  `web/src/api.ts`.
- Backend API: `src/dashboard/api/routes.py`, `src/dashboard/api/models.py`,
  `src/dashboard/api/services.py`, `src/dashboard/api/app.py`.
- Domain services: `src/dashboard/analytics/*`, `src/dashboard/news/*`,
  `src/dashboard/ingestion/*`, `src/dashboard/ingestion_sentiment/*`,
  `src/dashboard/brokers/*`, `src/dashboard/services/business_strength/*`.
- Data model: `src/dashboard/db/schema.sql`, `src/dashboard/db/migrations/*`,
  `docs/erd/current_schema.md`.
- Existing documentation and ADRs: `docs/architecture.md`, `docs/codebase_map.md`,
  `docs/news_terminal.md`, `docs/business_strength_scorecard.md`, `docs/adr/*`.
- Test evidence: `tests/api/*`, `tests/ingestion_*/*`, `tests/news/*`,
  `tests/services/*`, `web/src/**/*.test.tsx`, `web/src/**/*.test.ts`,
  `web/e2e/signals.spec.ts`.

## Scope and Method

The current product is a local-first investment dashboard with React/Vite frontend, FastAPI API,
DuckDB persistence, provider-backed ingestion, and API-owned background workers. The frontend has
page-level modules, widget visibility metadata, and a layout preference store. The backend has
large API service classes that combine query orchestration, domain calculations, DTO construction,
and some presentation-adjacent label construction.

This plan treats each independently understandable user-facing capability as a candidate module,
including page panels, cards, tables, charts, controls, status indicators, and background processes
that exist to support those surfaces.

## Product Domain Hierarchy

### Portfolio Management

- Portfolio workspace
  - Portfolio list/cards
  - Aggregate portfolio summary
  - Aggregate allocation panel
  - Aggregate coverage/data-quality panel
  - Optional aggregate fundamentals tab
- Portfolio detail workflow
  - Portfolio identity/summary header
  - Range, chart-type, and benchmark controls
  - Overview tab
  - Holdings tab
  - Risk tab
  - Fundamentals tab
  - Optimization tab
  - Activity tab
  - Portfolio news panel

### Asset Research

- Asset detail route
  - Asset identity header
  - Current price summary
  - Price chart tab
  - Price range selector
  - Chart type selector
  - Asset news/activity tab
  - Fundamentals/analytics tab
  - Business Strength tab
  - Business Strength category audit and full audit controls
  - Compare launcher

### Market Data and Benchmarks

- Benchmark workspace
  - Search/filter controls
  - Market snapshot cards
  - Benchmark comparison chart
  - Benchmark explorer table/mobile cards
  - Leadership and risk watch rankings
  - Freshness/status diagnostics
  - Seed and harden actions
- Benchmark detail
  - Benchmark identity header
  - Benchmark price chart
  - Computed risk panel
  - Benchmark profile panel
  - Freshness/disclosure panel
  - Exposure snapshot
  - Top constituents
  - Manual refresh actions

### News and Sentiment

- News terminal
  - Global feed
  - Presets
  - Search/filter bar
  - Provider/category filters
  - Story list
  - Story detail
  - Read/save state
  - Pagination
- Retail sentiment
  - Summary strip
  - Holdings sentiment table
  - Popular stocks table
  - Ratings add-on panel
  - Methodology note
- Contextual news
  - Asset news panel
  - Portfolio news panel

### Signals and Rankings

- Signal explorer
  - Summary metric strip
  - Priority panels
  - Filter drawer/sidebar
  - Active filter chips
  - Signal table
  - Mobile signal cards
  - Evidence panel
  - Historical efficacy panel
  - Watchlist, reviewed, and alert actions
  - Methodology note
- Signal detail
  - Deep-link signal detail page
  - Alert action

### Comparisons and Analytics

- Compare workflow
  - Ticker input and URL state
  - Benchmark picker
  - Period/mode/currency controls
  - Difference mode controls
  - Performance chart
  - Accessible chart-data table
  - Asset summary strip
  - Valuation metrics
  - Growth metrics
  - Quality/profitability metrics
  - Balance-sheet/risk metrics
  - Capital-allocation metrics
  - Forward scenarios
  - Business Strength comparison
  - Template-adjusted details
  - Methodology/data-quality panel
- Deterministic analytics payloads
  - Asset analytics report
  - Portfolio analytics report
  - AI-ready context and anomaly facts

### Broker Integration

- Broker workspace
  - Broker status header
  - Connect/register existing user
  - Connection cards
  - Account table/cards
  - Assignment/mapping controls
  - Create portfolio from broker account
  - Import preview
  - Reconciliation table
  - Sync history
  - Broker settings
  - Raw payload storage toggle
  - Sync, sync-due, reconnect, and smoke-test actions

### Data Management and Operations

- Operations route
  - Ingestion job table and filters
  - Schedule/run/retry/clear controls
  - Routine ingestion worker card
  - Market freshness worker card
  - Data readiness worker card
  - Retail sentiment status card
  - Projection readiness card
  - Ranking readiness card
- Supporting ingestion
  - Price history jobs
  - Corporate calendar and fundamentals
  - Benchmark ingestion
  - News ingestion
  - Retail/social sentiment ingestion
  - Live price streaming
  - Rate limits and provider fallback handling

### User Customization

- Settings route
  - Theme selector
  - Default holdings count
  - Density selector
  - Feature color toggle
- Page feature/layout system
  - Feature registry
  - Visibility preferences
  - Widget layout preferences
  - Page feature menu
  - Layout toolbar
  - Layout widget wrapper

### System Health and Administration

- Health endpoint
- OpenAPI endpoint
- Provider health endpoints
- Worker status endpoints
- Data-health scripts
- Browser scanner
- CLI commands and smoke checks

## Module Record Legend

Each feature record uses these compact fields:

- ID: stable proposed module ID.
- Status: production, partial, experimental, legacy, deprecated, stub, or unknown.
- Files: current frontend/backend locations.
- Purpose: user problem and decision supported.
- Importance: user importance / product importance / frequency / decision impact.
- Inputs: required and optional inputs, with sensitivity and freshness notes.
- Logic: current processing and where it lives.
- Outputs: visible or API outputs.
- Dependencies: APIs, services, DB tables, providers, tests, docs.
- Platforms: Web, Mobile, Desktop, AI/services, Shared backend.
- Portability: current reuse quality and required modularization.

## Feature Records

### PM-001 Portfolio Workspace Shell

- Status: production.
- Current route and components: `/portfolios`, `PortfolioWorkspacePage`,
  `AggregateWorkspacePanel`, `PortfolioCardGrid`, `GainViewToggle` in
  `web/src/routes/portfolioRoute.tsx`.
- Backend/API: `GET /api/v1/portfolios`, `GET /api/v1/portfolios/aggregate/overview`,
  `GET /api/v1/portfolios/aggregate/positions`, `PortfolioApiService`.
- Tests: `web/src/routes/portfolioRoute.test.tsx`, `tests/api/test_portfolio_api.py`.
- Purpose: lets the user scan all portfolios, choose aggregate vs specific portfolios, and switch
  total-gain vs unrealized-gain interpretation.
- Importance: Critical / core utility / daily / high impact. If unavailable, the dashboard loses
  its main portfolio entry point. Offline support is useful for last known snapshots; stale data is
  acceptable only with source/as-of badges.
- Inputs: portfolio rows, aggregate summary, aggregate positions, URL selected tab, gain view
  local state, page feature preferences. Portfolio values are sensitive financial data. Prices and
  positions need market-session freshness; names/preferences are platform independent.
- Logic: React Query fetch orchestration in page; portfolio summaries and gain semantics in
  backend service; gain view selection in UI. Domain logic should remain backend-owned.
- Outputs: portfolio cards, aggregate metrics, allocation/data-quality widgets, links to detail
  routes, loading/error/empty states.
- Dependencies: `portfolio`, `position`, `txn`, broker mapping tables, current prices, FX data,
  React Query, page feature store.
- Platforms: Web full; Mobile simplified cards and drilldowns; Desktop full plus multi-window; AI
  consumes portfolio summary; Shared backend required.
- Portability: medium. Needs a platform-neutral `PortfolioSummaryModule` contract and removal of
  route-specific view state from reusable card components.

### PM-002 Aggregate Allocation and Coverage Widgets

- Status: production.
- Files: `AllocationPanel`, `AllocationGrid`, `AllocationPie`, `AllocationHoldingList`,
  `groupPositions`, `exposureSplits` in `web/src/routes/portfolioRoute.tsx`;
  `PositionSummary` in `src/dashboard/api/models.py`; exposure helpers in
  `src/dashboard/api/services.py` and `src/dashboard/analytics/calculations.py`.
- Purpose: shows sector, industry, country, currency, and allocation-class concentration so the
  user can identify exposure risks and understand ETF/CDR split-through holdings.
- Importance: High / core utility / weekly / high impact. Unavailable exposure hides concentration
  risk. Offline support is useful; stale exposure is acceptable if position prices are timestamped.
- Inputs: positions, market values, weights, allocation class, sector/industry/country/currency
  exposure maps, selected dimension, grid vs pie control.
- Logic: grouping and display split logic currently lives in the UI; canonical sector and CDR
  exposure logic lives in backend helpers. Presentation grouping can be shared, but exposure
  derivation should stay backend/domain-owned.
- Outputs: exposure tiles, pie chart, selected group holding drawer/list, data-quality summary.
- Dependencies: `asset`, `position`, ETF/CDR metadata, backend position summaries.
- Platforms: Web full; Mobile should use list-first plus tap-to-detail; Desktop can add nested
  drilldowns; AI consumes normalized exposures; Shared backend should return explicit exposure
  groups.
- Portability: medium-low. Extract chart/list UI and move `groupPositions`/`exposureSplits` into a
  shared view-model utility or backend response.

### PM-003 Portfolio Detail Header and Navigation

- Status: production.
- Files: `PortfolioDetailPage`, `TabBar`, `RangeSelector`, `ChartTypeToggle`,
  `Benchmark` input in `web/src/routes/portfolioRoute.tsx` and `routeShared.tsx`.
- Purpose: gives context for a selected portfolio and controls the time window, benchmark, chart
  type, and tab workflow used by all portfolio detail analytics.
- Importance: Critical / core utility / continuous while on detail / high impact. Without it,
  portfolio analytics become disconnected. Offline can display cached portfolio metadata; benchmark
  and range controls are deterministic.
- Inputs: `portfolioId` route param, `tab`, `range`, `chart`, `benchmark` query params, portfolio
  summary.
- Logic: URL-state parsing and tab gating in UI; validation is mostly UI-side. Backend validates
  benchmark/range on endpoint calls.
- Outputs: title, actions, controls, selected tab, links, loading/error state.
- Dependencies: portfolio API, page feature controls.
- Platforms: Web full; Mobile condensed tab/dropdown; Desktop persistent inspector; AI/services
  not direct; Shared backend none beyond portfolio identity.
- Portability: high if converted to a `PortfolioRouteState` model and reusable header component.

### PM-004 Portfolio Performance Widget

- Status: production.
- Files: `PortfolioPerformanceView` in `web/src/routes/portfolioRoute.tsx`;
  `GET /api/v1/portfolios/{id}/performance`; `PortfolioApiService.performance`;
  `portfolio_performance_metrics` in `src/dashboard/analytics/calculations.py`.
- Purpose: presents time-weighted portfolio value and benchmark return so users can judge whether
  their portfolio outperformed a selected benchmark.
- Importance: Critical / core differentiator / weekly / high impact. Missing data weakens the
  product's main analytical value. Offline support should show cached series with as-of timestamp;
  stale prices are acceptable only when labeled.
- Inputs: portfolio ID, benchmark ID, range, daily position/transaction data, daily prices,
  benchmark prices, FX policy, calendar alignment.
- Logic: backend builds actual daily values, aligns benchmark series, computes CAGR/excess CAGR and
  coverage. UI renders chart and summary. Correct split is mostly achieved.
- Outputs: performance chart, CAGR/excess/coverage metrics, missing input list, loading/empty state.
- Dependencies: `asset_quote_daily`, `benchmark_index_daily_price`, `txn`, `position`,
  analytics calculations, tests.
- Platforms: Web full; Mobile summary plus simplified chart; Desktop advanced overlays; AI consumes
  series and metrics; Shared backend required.
- Portability: high after standardizing a `PerformanceSeries` domain DTO for assets, portfolios,
  and benchmarks.

### PM-005 Portfolio Risk and Concentration Widgets

- Status: production.
- Files: `PortfolioRiskView`, overview risk panel in `portfolioRoute.tsx`;
  `GET /api/v1/portfolios/{id}/risk`; `PortfolioApiService.risk`;
  `portfolio_risk_decomposition`, `correlation_matrix`, `dimension_exposure` in analytics
  calculations.
- Purpose: quantifies volatility, drawdown, Sharpe/Sortino, beta, correlation, effective holdings,
  HHI, and concentration maps to guide risk decisions.
- Importance: High / core differentiator / weekly / high impact. If unavailable, risk comparison
  becomes manual. Offline cached risk is useful; stale risk acceptable if lookback and as-of are
  visible.
- Inputs: portfolio ID, benchmark, lookback range, risk-free rate, holdings, daily returns,
  benchmark returns, exposure metadata.
- Logic: backend analytical calculations; UI formats metric grid. Some label and card grouping are
  presentation logic in UI.
- Outputs: risk tab metrics, overview risk card, concentration values, missing inputs.
- Dependencies: analytics calculations, daily prices, benchmark prices, position weights.
- Platforms: Web full; Mobile prioritized cards; Desktop matrix/correlation view; AI consumes
  auditable risk facts; Shared backend required.
- Portability: high for data; medium for UI due to card-specific composition.

### PM-006 Portfolio Fundamentals Rollup

- Status: production/partial depending on provider coverage.
- Files: `PortfolioFundamentalsView` and overview fundamentals card in `portfolioRoute.tsx`;
  `GET /api/v1/portfolios/{id}/fundamentals`; `PortfolioApiService.fundamentals`;
  valuation helpers in `src/dashboard/analytics/calculations.py`.
- Purpose: gives weighted expected CAGR, valuation, yield, margin-of-safety, and holding coverage
  to evaluate portfolio quality and expected return.
- Importance: High / core differentiator / weekly / high impact. Missing provider data must be
  explicit, not zeroed. Offline cached values can work if timestamped; stale fundamentals are often
  acceptable for days/weeks when source period is shown.
- Inputs: portfolio holdings/weights, price, shares outstanding, statements, dividend history,
  horizon years, valuation asset mapping for CDRs/wrappers.
- Logic: backend computes coverage-aware weighted metrics. UI only renders summary/table.
- Outputs: metric cards, holding-level fundamental rows, coverage and missing-input messages.
- Dependencies: financial statements, current prices, dividends, readiness worker, analytics
  repository.
- Platforms: Web full; Mobile summary plus holding drilldown; Desktop full scenario controls; AI
  consumes audit-ready facts; Shared backend required.
- Portability: high if exposed as a standalone `PortfolioFundamentalsReport`.

### PM-007 Holdings Table and Holding Kiviat Grades

- Status: production.
- Files: `HoldingsTable`, `HoldingKiviatGrid`, `HoldingKiviatCard`, `FactorSummary` in
  `portfolioRoute.tsx`; `GET /api/v1/portfolios/{id}/positions`,
  `GET /api/v1/holdings/signals`; `PortfolioApiService.holding_signals`.
- Purpose: shows each holding's quantity, price, value, weight, gain, data status, and factor-grade
  radar components so the user can decide which holdings need review.
- Importance: Critical / core utility and differentiator / continuous / high impact. If unavailable,
  users lose position truth and holding-quality triage. Offline should show cached positions; stale
  price/factor data must be labeled.
- Inputs: portfolio ID, positions, holding signals, timeframe, search query, sort order, price
  timestamps, factor components.
- Logic: backend owns factor component scores; UI filters/sorts holdings and draws radar chart.
  Search/sort is presentation logic; factor scoring in `api/services.py` should be moved to a
  domain scoring module during refactor.
- Outputs: holdings table, asset links, factor radar, factor summary list, methodology note, empty
  states.
- Dependencies: position summaries, comparison profiles, stock ranking components, sentiment and
  fundamentals tables.
- Platforms: Web full; Mobile table becomes cards; Desktop sortable/pinnable table; AI consumes
  holding factor summaries; Shared backend required.
- Portability: medium. Radar card and score view model should be extracted; score generation should
  leave `api/services.py`.

### PM-008 Portfolio Optimization Preview

- Status: production/experimental.
- Files: `PortfolioOptimizationPanel` in `portfolioRoute.tsx`;
  `POST /api/v1/portfolios/{id}/optimization/preview`; `PortfolioApiService.optimization_preview`.
- Purpose: previews suggested reweights for max expected CAGR or risk-adjusted return without
  persisting allocation changes.
- Importance: Medium / experimental differentiator / occasional / medium-high impact. If
  unavailable, no existing portfolio data is lost. Offline is not necessary; stale inputs are not
  acceptable unless clearly shown.
- Inputs: portfolio ID, objective, constraints, current weights, expected CAGR, volatility, sector
  exposure, excluded/locked assets.
- Logic: deterministic backend optimization preview currently in API service; no solver dependency
  is evident. UI triggers mutations and displays before/after.
- Outputs: status, solver message, current/optimized weights, deltas, before/after metrics,
  warnings, assumptions.
- Dependencies: portfolio fundamentals, risk metrics, backend optimization helpers.
- Platforms: Web guarded; Mobile omit or read-only; Desktop advanced; AI can explain suggestions;
  Shared backend should own all optimization.
- Portability: medium-low until optimization is moved into an explicit analytics module and given an
  audit trail.

### PM-009 Portfolio Activity and Contextual News

- Status: production.
- Files: activity tab and `PortfolioNewsPanel` in `portfolioRoute.tsx`;
  `GET /api/v1/portfolios/{id}/transactions`, `GET /api/v1/portfolios/{id}/news`;
  `NewsApiService.portfolio_feed`.
- Purpose: gives transaction history and relevant news for holdings so the user can connect
  portfolio movement to recent events and ledger activity.
- Importance: Medium-high / supporting utility / weekly / medium impact. Offline cached activity is
  useful; news should clearly show publication time and source.
- Inputs: portfolio ID, pagination, category/sort, transactions, news article mappings, underlying
  asset mapping for wrappers/CDRs.
- Logic: backend maps portfolio holdings to news assets; UI displays list/detail. Read/save state is
  shared with News Terminal.
- Outputs: transaction table/page, contextual news cards, links to `/news` and asset pages.
- Dependencies: `txn`, broker import maps, `news_article_asset`, `news_article_category`.
- Platforms: Web full; Mobile condensed timeline; Desktop split ledger/news; AI consumes context;
  Shared backend required.
- Portability: high if converted to reusable timeline/feed components.

### AR-001 Asset Detail Shell and Price Chart

- Status: production.
- Files: `AssetDetailPage`, `AssetNewsPanel`, `RangeSelector`, `ChartTypeToggle` in
  `web/src/routes/assetRoute.tsx`; `GET /api/v1/assets/{asset_id}`,
  `GET /api/v1/assets/{asset_id}/prices`; `AssetApiService`.
- Purpose: lets users research a single asset, inspect identity and current price, and view stored
  price history across ranges.
- Importance: Critical / core utility / daily-weekly / high impact. Offline cached details are
  useful; price data requires clear timestamp/source.
- Inputs: asset ID route param, tab/range/chart query params, asset metadata, latest price, daily
  price history.
- Logic: backend normalizes asset detail and price range; UI controls tab/range/chart and renders
  Recharts chart. Route `/assets/:assetId` exists alongside `/asset/:assetId`, with historical
  collision risk.
- Outputs: asset title, current price, price chart, tab navigation, compare/back links, loading and
  empty states.
- Dependencies: `asset`, `asset_quote_daily`, `current_asset_price`, page feature controls.
- Platforms: Web full; Mobile essential summary/chart; Desktop advanced charting; AI consumes asset
  profile; Shared backend required.
- Portability: medium. Extract route state and chart into reusable components; retire duplicate
  route after compatibility plan.

### AR-002 Asset Fundamentals and Analytics Report

- Status: production/partial based on data coverage.
- Files: `AssetAnalyticsPanel` in `web/src/routes/routeAnalytics.tsx`;
  `GET /api/v1/assets/{id}/analytics`; `AssetApiService.analytics`;
  `AnalyticsEngine.asset_report`.
- Purpose: presents deterministic asset-level valuation, risk, forecast, ETF, exposure, and
  AI-ready context so users can evaluate an asset beyond price movement.
- Importance: High / core differentiator / weekly / high impact. Offline cached report is useful;
  stale fundamentals must be labeled.
- Inputs: asset ID, benchmark index ID, price history, benchmark history, statements, dividends,
  asset profile, ETF holdings, analytics persistence.
- Logic: analytics engine builds report and AI context; UI recursively renders blocks via
  `AnalyticsPanel` and data-health panels. Some generic rendering is presentation logic.
- Outputs: metric sections, valuation summaries, forecasts, anomalies, facts, data health issues.
- Dependencies: analytics repository/calculations, financial statements, price history, benchmark
  prices.
- Platforms: Web full; Mobile selected sections; Desktop full report and export; AI/services direct
  consumer; Shared backend required.
- Portability: high for data, medium for rendering due to generic object-panel UI.

### AR-003 Business Strength Scorecard

- Status: production with future research fields stubbed off.
- Files: `BusinessStrengthPanel`, `BusinessStrengthMetricTable` in `assetRoute.tsx`;
  `GET /api/v1/assets/{id}/business-strength`,
  `POST /api/v1/assets/{id}/business-strength/recalculate`,
  `BusinessStrengthAnalyzer`, `BusinessStrengthTemplateRegistry`.
- Purpose: presents sector-aware deterministic business-quality scoring across profitability,
  efficiency, balance sheet, growth, and other template metrics to decide whether a company is an
  easy hold or needs more research.
- Importance: High / core differentiator / weekly / high impact. Offline cached scorecard is useful;
  stale source data must be explicit.
- Inputs: asset ID, stored statements, asset metadata, sector/industry template, metric definitions,
  optional recalculation action.
- Logic: domain service computes category/metric scores, explanations, confidence/completeness, and
  warnings. UI renders score, strengths, weaknesses, categories, metric audit table.
- Outputs: overall score/classification, category scores, metric table, warning/missing/stale lists,
  refresh action result.
- Dependencies: `business_strength_*` tables, financial statements, templates docs/tests.
- Platforms: Web full; Mobile summary and category drilldown; Desktop compare/audit; AI consumes
  scorecard facts; Shared backend required.
- Portability: high. Extract scorecard UI from asset route and use a stable `BusinessStrengthCard`
  contract.

### AR-004 Asset News and Activity Context

- Status: production.
- Files: `AssetNewsPanel` in `assetRoute.tsx`; `GET /api/v1/assets/{id}/news`,
  `GET /api/v1/assets/{id}/activity`; `NewsApiService.asset_feed`,
  `PortfolioApiService.list_asset_activity`.
- Purpose: gives asset-specific news and account/portfolio activity so users can connect research
  and ownership context.
- Importance: Medium-high / supporting utility / weekly / medium impact. Offline activity useful;
  news staleness must be visible.
- Inputs: asset ID, news filters, activity pagination, holdings/activity rows, news mappings.
- Logic: contextual mapping and relevance ranking backend; UI displays feed.
- Outputs: news list, activity table/page, source and sentiment badges.
- Dependencies: news tables, txn, broker transaction tables.
- Platforms: Web full; Mobile feed; Desktop split research/activity; AI consumes context; Shared
  backend required.
- Portability: high after reusable feed/timeline extraction.

### MD-001 Benchmark Workspace

- Status: production.
- Files: `BenchmarksWorkspacePage`, `BenchmarkSnapshot`, `BenchmarkComparisonChart`,
  `BenchmarkExplorer`, `BenchmarkLeadership`, `BenchmarkStatusPanel` in `web/src/benchmarks.tsx`;
  `web/src/benchmarkUtils.ts`.
- Backend/API: `/api/v1/benchmarks`, `/benchmarks/{id}/prices`, `/benchmarks/seed`,
  `/benchmarks/harden`, `BenchmarkApiService`.
- Purpose: lets users search benchmark universe, compare selected indexes, inspect market
  leadership/risk, and diagnose benchmark data freshness.
- Importance: High / core utility / weekly / medium-high impact. If unavailable, comparison and
  performance context degrades. Offline cached benchmark metadata/series is useful; freshness
  labels are required.
- Inputs: search, category, period, baseline, currency, proxy/freshness filters, selected IDs,
  benchmark summaries, price series.
- Logic: UI currently computes normalized series, selection limits, market snapshot, sorting, and
  freshness labels; backend owns benchmark facts and refresh operations.
- Outputs: controls, snapshot cards, line/bar comparison chart, table/mobile cards, rankings,
  status panel, action notifications.
- Dependencies: benchmark tables, index providers, Recharts, page feature registry, tests.
- Platforms: Web full; Mobile simplified explorer; Desktop advanced screener; AI consumes
  benchmark context; Shared backend required.
- Portability: medium. Move normalization/freshness view-model utilities to shared package and
  extract explorer/chart components.

### MD-002 Benchmark Detail

- Status: production.
- Files: `BenchmarkDetailPage`, `BenchmarkDetailHeader`, `BenchmarkDetailChart`,
  `BenchmarkRiskPanel`, `BenchmarkIdentityPanel`, `BenchmarkQualityPanel`,
  `BenchmarkExposurePanel`, `BenchmarkConstituentPanel` in `web/src/benchmarks.tsx`.
- Backend/API: `/benchmarks/{id}`, `/prices`, `/metrics`, `/constituents`, `/exposures`,
  `/refresh`, `/harden`.
- Purpose: provides a single benchmark's identity, price history, risk statistics, composition,
  constituents, data-quality state, and refresh actions.
- Importance: Medium-high / supporting utility / occasional-weekly / medium impact. Offline cached
  detail is acceptable with as-of labels.
- Inputs: benchmark ID route param, price/metric/exposure/constituent rows, refresh job type.
- Logic: backend supplies metrics and composition; UI computes latest metric view and draws chart.
- Outputs: header, price chart, risk cards, drawdown chart, profile/disclosure, exposure and
  constituent lists, refresh buttons.
- Dependencies: benchmark services and ingestion scheduler.
- Platforms: Web full; Mobile overview plus tabs; Desktop full diagnostics; AI consumes benchmark
  facts; Shared backend required.
- Portability: high for data, medium for UI because detail panels are route-local.

### MD-003 Price History, Live Prices, and Market Freshness

- Status: production/supporting.
- Files: `src/dashboard/ingestion/price_history/*`, `src/dashboard/ingestion/websocket/*`,
  `src/dashboard/api/market_freshness_background.py`; operations cards in `operationsRoute.tsx`.
- Purpose: maintains daily/intraday/current prices used by nearly every financial feature and
  surfaces freshness operational status.
- Importance: Critical / core utility / continuous / high impact. Without it, portfolio value,
  returns, charts, and signals degrade. Offline cached current prices can be shown if timestamps are
  prominent; stale data is not acceptable silently.
- Inputs: tracked tickers, watchlist, market session, provider credentials, job config/env vars,
  Yahoo/Finnhub/FMP responses, current price table.
- Logic: backend providers normalize prices, workers poll/tick, stream resolver determines
  subscriptions. UI only displays status controls.
- Outputs: price tables, current price rows, provider health, streaming status, freshness worker
  status, ingestion jobs.
- Dependencies: price tables, `current_asset_price`, `live_price_*`, providers, rate limits.
- Platforms: Shared backend mandatory; Web/Operations status; Mobile consumes cached API; Desktop
  can subscribe live; AI consumes timestamped facts.
- Portability: high if exposed as provider-neutral market-data service.

### NS-001 News Terminal

- Status: production with bundled deterministic mock provider for development.
- Files: `NewsTerminalPage`, `NewsRow`, `NewsDetail`, `categoryMatchesPreset` in
  `web/src/routes/newsRoute.tsx`; `NewsApiService`, `NewsRepository`, `NewsIngestionService`.
- Backend/API: `/news`, `/news/latest`, `/news/breaking`, `/news/search`, `/news/articles/{id}`,
  `/news/providers`, `/news/categories`, read/save endpoints.
- Purpose: global financial news workspace for browsing, filtering, selecting, reading, and saving
  news tied to assets, categories, sentiment, and clusters.
- Importance: High / supporting differentiator / daily-weekly / medium-high impact. If unavailable,
  price/portfolio changes lose narrative context. Offline cached headlines are useful; stale news
  must be obvious.
- Inputs: query, provider, source, asset, portfolio, category, sentiment, breaking/press release,
  date range, sort, limit/offset, article read/save state.
- Logic: backend normalizes, classifies, resolves entities, clusters, ranks, and filters. UI manages
  preset filters, selected article, density, pagination, and save/read mutations.
- Outputs: feed rows, detail panel, category/sentiment/source badges, provider/category filters,
  pagination, empty/errors.
- Dependencies: news tables, provider health, mock provider, tests, ADR PH8.
- Platforms: Web full; Mobile list/detail; Desktop terminal layout; AI consumes curated context;
  Shared backend required.
- Portability: high after feed/list/detail components become platform-neutral.

### NS-002 News Alerts

- Status: partial/hidden in UI.
- Files: route endpoints in `src/dashboard/api/routes.py`; `NewsApiService.alert_rules`.
- Purpose: stores alert rules for news criteria so future in-app/email/push/webhook alert workflows
  can notify the user.
- Importance: Medium / future utility / occasional / medium impact. Not currently a primary UI
  feature. Offline not necessary.
- Inputs: rule name, target scope, keyword, min importance, sentiment threshold, breaking flag,
  delivery channel, asset IDs, portfolio IDs.
- Logic: backend CRUD exists; UI does not expose a full alert management workflow.
- Outputs: alert rule records and action result.
- Dependencies: `news_alert_rule` and mapping tables.
- Platforms: Shared backend; Desktop/Web future management UI; Mobile notification settings; AI can
  propose rules.
- Portability: low current reuse because it is API-only. Needs explicit alert domain module and UI.

### NS-003 Retail Sentiment Workspace

- Status: production.
- Files: `RetailSentimentPage`, `RatingsAddOnPanel`, `RetailSentimentTable`,
  `RetailSentimentCard`, `SentimentBadge` in `web/src/routes/retailSentimentRoute.tsx`;
  `PortfolioApiService.retail_sentiment_overview`, sentiment ingestion services.
- Backend/API: `/retail-sentiment`, `/rankings/stocks`, `/ingestion/retail-sentiment/status`.
- Purpose: combines Reddit/X/social post activity, sentiment aggregates, holdings relevance, and
  ranking add-ons so the user can see where retail attention may affect holdings or opportunities.
- Importance: Medium-high / differentiator / weekly / medium impact. If unavailable, core portfolio
  accounting still works. Offline cached snapshots are acceptable if date-stamped.
- Inputs: limit, held/watchlisted flags, sentiment daily snapshots, social posts, ranking factor
  response, provider config/status.
- Logic: backend aggregates scores and labels; UI splits holdings vs popular, summary counts,
  add-on rating panel, methodology note.
- Outputs: summary strip, holdings/popular tables and cards, sentiment badges, latest posts,
  methodology.
- Dependencies: `social_post`, `sentiment_observation`, `ticker_sentiment_daily`, Reddit/X
  providers, ranking service.
- Platforms: Web full; Mobile summary/cards; Desktop social drilldown; AI consumes sentiment facts;
  Shared backend required.
- Portability: medium-high. Extract table/card and standardize sentiment snapshot DTO.

### SG-001 Signals Explorer

- Status: production.
- Files: `StockRankingsPage`, `SignalFilterPanel`, `SignalPrioritySection`, `SignalTableRow`,
  `SignalEvidencePanel`, `SignalEfficacyBox`, `SignalMobileCard` in
  `web/src/routes/signalsRoute.tsx`.
- Backend/API: `/signals`, `/signals/{id}`, `/signals/{id}/user-state`,
  `/signals/{id}/alerts`, `/watchlist/assets/{asset_id}`; `PortfolioApiService.signals_summary`.
- Purpose: ranks actionable signals with evidence, confidence, priority, and portfolio impact so
  users can triage opportunities and risks.
- Importance: High / core differentiator / daily-weekly / high impact. If unavailable, proactive
  review value drops. Offline cached signals are useful; stale/freshness must be labeled.
- Inputs: filters, portfolio ID, owned state, category, direction, status, strength/confidence,
  freshness/completeness, include retail add-on, sort, pagination, signal detail ID.
- Logic: backend composes signals from rankings and evidence, persists evaluations/user state,
  calculates confidence/freshness/effectiveness. UI owns filters, URL state, expanded row, and
  action mutations.
- Outputs: summary strip, priority panels, table/mobile cards, evidence panel, user-state badges,
  watchlist/review/alert actions, methodology note.
- Dependencies: ranking snapshots, sentiment, news, portfolio impacts, watchlist, signal tables.
- Platforms: Web full; Mobile triage-first; Desktop advanced filtering; AI consumes evidence graph;
  Shared backend required.
- Portability: medium. Move signal row/evidence view models to shared contract; keep actions in
  platform adapters.

### SG-002 Stock Rankings and Watchlist Action

- Status: production.
- Files: API client `stockRankings`, `refreshStockRankingSnapshots`, `addWatchlistAsset`; UI in
  signals and retail sentiment.
- Backend/API: `/rankings/stocks`, `/rankings/stocks/snapshots`, `/watchlist/assets/{asset_id}`.
- Purpose: ranks stocks by aggregate/momentum/news/retail/earnings/institutional factors and lets
  users add interesting names to watchlist.
- Importance: Medium-high / differentiator / weekly / medium impact. Offline snapshots are useful;
  stale rankings must be labeled.
- Inputs: factor, universe, direction, timeframe, include retail sentiment, limit/offset, asset ID
  for watchlist.
- Logic: ranking components and factor scores currently live in `PortfolioApiService` helper
  methods; should become a domain service.
- Outputs: ranking items, component scores, action/confidence/data status, watchlist state.
- Dependencies: price history, news/sentiment, corporate calendar, institutional/proxy inputs,
  watchlist tables.
- Platforms: Web full; Mobile top lists; Desktop screener; AI consumes ranked universe; Shared
  backend required.
- Portability: medium-low until ranking logic leaves API service.

### SG-003 Signal Detail Page

- Status: production.
- Files: `SignalDetailPage` in `signalsRoute.tsx`.
- Backend/API: `/signals/{signal_id}`.
- Purpose: provides a deep-linkable signal page for evidence inspection and alert creation.
- Importance: Medium / supporting utility / occasional / medium impact.
- Inputs: encoded signal ID route param, detail response, alert mutation.
- Logic: backend returns detail; UI renders common evidence panel.
- Outputs: detail header, evidence, alert button, back link.
- Dependencies: signal detail endpoint and common signal components.
- Platforms: Web full; Mobile full; Desktop full; AI context; Shared backend required.
- Portability: high after evidence panel extraction.

### CP-001 Compare Workspace Shell and State

- Status: production.
- Files: `ComparePage` in `compareRoute.tsx`; `parseComparisonState`, `serializeComparisonState`,
  `metricRegistry` in `comparisonUtils.ts`; `TickerPicker`, `BenchmarkPicker`.
- Backend/API: `/comparison/workspace`, `/benchmarks/associations/asset/{asset_id}`,
  `/compare/business-strength`.
- Purpose: compares multiple tickers/portfolios/benchmarks by performance, fundamentals, valuation,
  risk, and business strength using URL-shareable state.
- Importance: High / core differentiator / weekly / high impact. Offline cached comparison useful
  for last viewed set; stale data must be labeled.
- Inputs: symbols, benchmark, period, mode, currency, hidden series, chart type, difference mode,
  selected metric groups.
- Logic: backend builds comparison workspace; frontend computes chart rows, series metrics, rank
  display, local URL validation, and metric registry metadata. Some calculations are duplicated in
  frontend and should move to shared/domain layer.
- Outputs: controls, chart, metric sections, business strength comparison, warnings, methodology.
- Dependencies: comparison service, asset/benchmark picker APIs, Recharts, page feature registry.
- Platforms: Web full; Mobile reduced two-asset compare; Desktop advanced workspace; AI consumes
  comparison snapshot; Shared backend required.
- Portability: medium. URL state and metric registry should become a platform-neutral module.

### CP-002 Comparison Performance Chart and Chart Data Table

- Status: production.
- Files: chart section and `ComparisonChartTable` in `compareRoute.tsx`;
  chart utilities in `comparisonUtils.ts`.
- Purpose: visualizes aligned historical performance/drawdown/relative modes and provides a table
  fallback for accessibility.
- Importance: High / core utility / weekly / high impact.
- Inputs: historical series, hidden symbols, chart mode, period, benchmark, common start date.
- Logic: backend returns series; UI transforms to chart rows and table. Series metric calculations
  such as CAGR/drawdown/volatility are frontend-side in `comparisonUtils.ts`.
- Outputs: line chart, chart controls, hidden-series state, accessible data table.
- Dependencies: comparison workspace response, Recharts.
- Platforms: Web full; Mobile simplified; Desktop advanced charting; AI consumes series; Shared
  backend should provide computed metrics.
- Portability: medium-low until chart view model and series metric calculations are shared.

### CP-003 Comparison Metric Sections

- Status: production.
- Files: `ComparisonMetricSection`, `MetricDefinitionDisclosure`, `displayMetricCell` in
  `compareRoute.tsx`; `metricRegistry`, `assetMetricValue`, `rankValues` in `comparisonUtils.ts`.
- Purpose: compares valuation, growth, quality, balance-sheet/risk, and capital-allocation metrics
  with directionality, formulas, sources, ranks, and difference mode.
- Importance: High / core differentiator / weekly / high impact.
- Inputs: comparison assets, metric definitions, current series metrics, reference asset, difference
  mode, currency.
- Logic: metric definitions/formulas are frontend-side; underlying fundamental values are backend.
  This is the largest portability concern because analytical definitions are mixed into UI code.
- Outputs: metric tables, best/worst classes, formula disclosure, source/as-of text, unavailable
  cells.
- Dependencies: comparison workspace DTO, financial statements, asset metadata.
- Platforms: Web full; Mobile grouped cards; Desktop sortable grid; AI consumes metric registry;
  Shared backend/service should own definitions.
- Portability: low-medium. Move metric registry and display semantics to a shared analytics
  metadata package.

### CP-004 Business Strength Comparison

- Status: production.
- Files: `BusinessStrengthComparison`, `TemplateAdjustedDetails`, `CommonMetricComparison` in
  `compareRoute.tsx`; `POST /api/v1/compare/business-strength`.
- Purpose: compares deterministic scorecards for two to eight symbols and highlights common metric
  differences, template mismatches, strengths, weaknesses, and failed symbols.
- Importance: Medium-high / differentiator / weekly / medium-high impact.
- Inputs: symbols, scorecards, common metric codes, sorting field.
- Logic: backend computes scorecards; UI sorts/renders category and metric comparisons.
- Outputs: scorecard comparison cards/table, template details, common metric comparison.
- Dependencies: Business Strength domain services and templates.
- Platforms: Web full; Mobile summary; Desktop full comparison; AI consumes scorecards; Shared
  backend required.
- Portability: high if scorecard comparison UI extracted.

### CP-005 Forward Scenarios and Methodology Panel

- Status: partial/production.
- Files: `ComparisonForwardScenarios`, `ComparisonMethodology` in `compareRoute.tsx`.
- Purpose: shows simple scenario implications and documents coverage, FX policy, warnings, insights,
  benchmark context, and metric definitions.
- Importance: Medium / supporting differentiator / occasional / medium impact.
- Inputs: assets, series metrics, coverage, FX policy, warnings, insights, benchmark, registry.
- Logic: UI derives simple forward scenario displays; backend provides coverage and FX policy.
- Outputs: scenario rows, methodology notes, warning lists.
- Dependencies: comparison workspace response.
- Platforms: Web optional; Mobile omit or summary; Desktop full; AI consumes methodology; Shared
  backend should generate auditable scenario data.
- Portability: low-medium until scenarios are formal backend outputs.

### BR-001 Broker Workspace and Connection Flow

- Status: production.
- Files: `BrokersPage`, `BrokerEmptyState`, `BrokerConnectionCard`, `BrokerRefreshProgress` in
  `web/src/routes/brokersRoute.tsx`; `brokerUtils.ts`.
- Backend/API: `/brokers/status`, `/brokers/connections`, `/brokers/accounts`,
  `/brokers/snaptrade/users`, `/existing-user`, `/portal`, `/sync`, `/sync-due`, `/smoke-test`.
- Purpose: manages read-only SnapTrade connection state and refresh operations so broker data can
  flow into local portfolio views without direct trading authority.
- Importance: High / core utility for linked accounts / daily-weekly / high impact for broker users.
  Offline status can be cached; sync actions require live provider.
- Inputs: provider config/env vars, broker user key, connection status, accounts, portal payload,
  sync options, provider errors.
- Logic: backend owns SnapTrade integration, secret handling, sync scheduling, redaction; UI manages
  tabs/actions and state labels.
- Outputs: connection cards, account counts, status pills, portal URL, sync progress, notifications.
- Dependencies: SnapTrade provider, broker tables, local secret cipher.
- Platforms: Web full; Mobile status/connect only; Desktop full diagnostics; AI only summarized
  account state; Shared backend required.
- Portability: medium due to provider-specific UI labels and local storage state.

### BR-002 Broker Account Mapping and Portfolio Creation

- Status: production.
- Files: `AccountsTab`, `BrokerAccountTable`, `BrokerAccountCard`, `AssignmentControl`,
  `AccountIdentity` in `brokersRoute.tsx`.
- Backend/API: `/brokers/accounts/{account_id}/mapping`, `/portfolios` create endpoint.
- Purpose: maps broker accounts to local portfolios or creates portfolios from broker accounts so
  positions/transactions can be reconciled and imported intentionally.
- Importance: High / core broker utility / occasional / high impact. Incorrect mapping has major
  data consequences.
- Inputs: broker account ID, selected portfolio ID, account balances, portfolio list, account state.
- Logic: backend persists mapping; UI filters/accounts and triggers mutations.
- Outputs: mapping controls, account cards/table, portfolio creation result.
- Dependencies: broker account and portfolio tables.
- Platforms: Web full; Mobile constrained mapping; Desktop bulk mapping; AI can recommend but not
  execute without confirmation; Shared backend required.
- Portability: medium-high with explicit mapping command DTO.

### BR-003 Import Preview and Reconciliation

- Status: production.
- Files: `ImportReconciliationTab`, `ImportPreview`, `ImportPreviewGroup`,
  `ReconciliationTable` in `brokersRoute.tsx`.
- Backend/API: `/brokers/import-preview`, `/brokers/reconciliation`,
  `/brokers/import-transactions`.
- Purpose: previews importable broker transactions and compares broker vs local holdings before
  importing into the local ledger.
- Importance: Critical for broker workflow / core utility / occasional / high impact. Must not be
  stale for import; offline preview is not appropriate for execution.
- Inputs: broker transactions, local transactions, account mapping, portfolio filter, reconciliation
  filter, import action.
- Logic: backend normalizes broker activity, categorizes status, reconciles quantities/values;
  UI filters and groups results.
- Outputs: grouped preview counts, transaction rows, reconciliation differences/status, import
  action result.
- Dependencies: broker_transaction, broker_position_snapshot, local txn, portfolio maps.
- Platforms: Web full; Mobile review-only; Desktop full; AI can summarize discrepancies; Shared
  backend required.
- Portability: high for data, medium for UI.

### BR-004 Broker Settings and Sync History

- Status: production.
- Files: `SyncHistoryTab`, `BrokerSettings`, `StatusPill`, `Fact`, `FactTerm` in
  `brokersRoute.tsx`.
- Backend/API: `/brokers/sync-history`, `/brokers/settings/raw-payload-storage`.
- Purpose: audits sync runs and controls raw payload storage for debugging/privacy.
- Importance: Medium / administrative utility / occasional / medium impact. Raw payload toggle has
  privacy sensitivity.
- Inputs: sync history rows, storage enabled flag, force refresh/test actions.
- Logic: backend owns history and setting persistence; UI displays facts and actions.
- Outputs: sync run table, configuration facts, toggle state.
- Dependencies: broker sync run tables, storage config.
- Platforms: Web full; Mobile minimal; Desktop full; AI not direct due to sensitive payloads; Shared
  backend required.
- Portability: medium.

### OP-001 Operations Route and Ingestion Job Controls

- Status: production.
- Files: `OperationsPage` in `web/src/routes/operationsRoute.tsx`; `CommandApiService` ingestion
  methods; `tools/run_full_data_health_workflow.py`.
- Backend/API: `/ingestion/jobs`, `/ingestion/schedule`, `/ingestion/run`,
  `/ingestion/retry-failed`, `DELETE /ingestion/jobs`.
- Purpose: gives an operator-visible control panel for scheduling, running, retrying, and clearing
  ingestion work.
- Importance: High / administrative core utility / daily during development, occasional in use /
  high impact. Offline is not appropriate for actions; stale status is acceptable briefly if
  refreshed.
- Inputs: job status/domain filters, job limit, schedule/run parameters, pipeline/domain, max
  assets/jobs, ranking options, missing/stale flags.
- Logic: UI validates bounded ints and confirms destructive-ish actions; backend creates/runs jobs
  and serializes writes.
- Outputs: job table, action counts, failure messages, loading/error states.
- Dependencies: ingestion_job, all ingestion services, write lock.
- Platforms: Web full; Mobile read-only/status; Desktop full admin; AI can diagnose jobs; Shared
  backend required.
- Portability: medium. Action commands should be explicit command objects with audit logs.

### OP-002 Worker Status Cards

- Status: production.
- Files: `IngestionBackgroundCard`, `MarketFreshnessCard`, `DataReadinessCard` in
  `operationsRoute.tsx`; `ingestion_background.py`, `market_freshness_background.py`,
  `data_readiness_background.py`.
- Backend/API: `/ingestion/background/*`, `/market/freshness/*`, `/data/readiness/*`.
- Purpose: surfaces safe-off background automation and manual start/stop/tick controls for routine
  ingestion, current-price freshness, and valuation-critical data readiness.
- Importance: High / administrative utility / daily-weekly / high impact for data quality. Offline
  status only; actions need live API.
- Inputs: worker status, env-configured intervals/caps, start/stop/tick commands, latest errors.
- Logic: workers own scheduling/ticks; UI displays status detail strings and action buttons.
- Outputs: enabled/running badges, last tick counts/errors, control buttons.
- Dependencies: app state workers, ingestion services, provider budgets.
- Platforms: Web full; Mobile status only; Desktop admin; AI can recommend operations; Shared
  backend required.
- Portability: high if worker status model is normalized.

### OP-003 Readiness and Retail Sentiment Operational Cards

- Status: production.
- Files: `RetailSentimentCard`, `IngestionReadinessCard`, `RankingReadinessCard` in
  `operationsRoute.tsx`; `CommandApiService.retail_sentiment_status`,
  `ingestion_readiness`, `stock_ranking_readiness`.
- Purpose: shows provider readiness, pending/failed jobs, valuation projection readiness, and
  ranking input coverage so missing data can be scheduled deliberately.
- Importance: High / data-quality utility / weekly / high impact for trust. Offline read-only OK;
  stale readiness can mislead and needs as-of.
- Inputs: sentiment status, provider config, snapshots/posts, readiness requirements, selected
  ranking universe, schedule actions.
- Logic: backend assesses readiness requirements; UI displays requirements and schedules targeted
  jobs.
- Outputs: status cards, requirement lists, schedule buttons, recent posts/snapshots.
- Dependencies: sentiment tables, financial/price tables, ingestion jobs.
- Platforms: Web full; Mobile read-only/schedule minimal; Desktop full; AI data-health agent
  consumes readiness; Shared backend required.
- Portability: medium-high.

### UC-001 Settings Route

- Status: production.
- Files: `SettingsPage` in `web/src/routes/settingsRoute.tsx`; settings load/save in
  `web/src/App.tsx`.
- Purpose: lets the user adjust theme, density, default holdings shown, and feature color accents.
- Importance: Medium / convenience feature / occasional / low-medium impact. Offline required
  because preferences are local.
- Inputs: localStorage `quaint_dash_app_settings`, theme, mover default, density, feature color.
- Logic: UI-only local preferences. No backend.
- Outputs: app-shell classes, document theme data attribute, select/toggle/button state.
- Dependencies: browser localStorage, CSS.
- Platforms: Web full; Mobile full; Desktop should sync profile eventually; AI not direct.
- Portability: low-medium until settings model moves to a shared preference schema.

### UC-002 Page Feature and Widget Layout System

- Status: production/partial layout customization.
- Files: `pageFeatures.ts`, `pageFeatureStore.tsx`, `PageFeatureMenu`, `PageLayoutButton`,
  `PageLayoutToolbar`, `LayoutWidget`, `OptionalFeaturesEmpty`.
- Purpose: lets users hide/show, resize, and organize optional page widgets while preserving fixed
  workflow controls.
- Importance: Medium-high / supporting utility / occasional / medium impact. Offline/local storage
  required.
- Inputs: registry definitions, page ID, feature ID, default enabled/order/size, localStorage
  `quaint_dash_page_features`.
- Logic: frontend normalizes feature preferences and layouts. All business/data truth remains in
  backend.
- Outputs: feature menu, layout toolbar, widget wrappers, visibility and size state.
- Dependencies: React context/localStorage/CSS.
- Platforms: Web full; Mobile probably simplified hide/show only; Desktop full drag/resizable;
  AI/services can read layout preferences for personalization.
- Portability: medium. Needs platform-neutral feature registry and platform-specific layout
  adapters.

### SH-001 Shared UI Primitives

- Status: production.
- Files: `routeShared.tsx`, `routePickers.tsx`, `routeFormatters.ts`,
  `routeAnalytics.tsx`.
- Purpose: provides common metric cards, loading/error/empty states, tabs, range and chart controls,
  paging, ticker/benchmark pickers, formatters, analytics blocks, exposure bars, and issue lists.
- Importance: High / shared utility / continuous / medium impact. These are essential for
  consistent platform UX.
- Inputs: UI props, query text, selected values, API results.
- Logic: presentation logic and simple formatting; some formatters may need shared cross-platform
  implementation.
- Outputs: reusable UI components and controls.
- Dependencies: API client, CSS, React Query, local formatter helpers.
- Platforms: Web current; Mobile/Desktop should use analogous native components with same view
  models; AI/services not direct.
- Portability: medium. Separate component view models from React DOM implementation.

### SYS-001 Health, API Shell, and Error Handling

- Status: production.
- Files: `src/dashboard/api/app.py`, `src/dashboard/api/routes.py`, `web/src/App.tsx`,
  `RouteErrorBoundary`, `ErrorPanel`.
- Purpose: establishes API version, database health, SPA route serving, CORS/dev origin, and
  user-facing error boundaries.
- Importance: Critical / platform foundation / continuous / high impact. Offline health not
  meaningful except cached diagnostics.
- Inputs: API request, database connection, app state, route errors, fetch failures.
- Logic: FastAPI app factory and exception behavior; UI route boundary catches render errors.
- Outputs: `/api/v1/health`, OpenAPI, error JSON, error panels.
- Dependencies: DuckDB init, app state workers, frontend route shell.
- Platforms: Shared backend; Web full; Mobile/Desktop clients consume health.
- Portability: high after standard error envelope is shared with clients.

### SYS-002 CLI and Operational Scripts

- Status: production/supporting; some CLI-era storage facade is legacy.
- Files: `src/dashboard/cli.py`, `src/dashboard/models/storage.py`,
  `src/dashboard/models/commands/*`, `scripts/qd.cmd`, `tools/*`.
- Purpose: provides local commands, setup/verify workflow, data-health scans, benchmark repairs,
  hydration audits, profiling, and worker runners.
- Importance: High for development/admin / supporting utility / occasional / high impact for data
  repair. Offline/local by nature.
- Inputs: command args, DB path, provider env vars, local app URL, tool parameters.
- Logic: command mixins wrap ingestion, analytics, broker, streaming, business-strength operations;
  tools orchestrate repeatable checks.
- Outputs: terminal tables/JSON reports/logs, data-health artifacts.
- Dependencies: DuckDB, API app, providers, Playwright/Node for browser scans.
- Platforms: Desktop/admin only; AI agents can run tools; Shared backend not direct.
- Portability: medium-low. Keep as admin package, not shared product module.

## Backend Supporting Capability Inventory

| ID | Capability | Current files | Supports | Status | Portability recommendation |
| --- | --- | --- | --- | --- | --- |
| CAP-PRICE | Price history ingestion | `ingestion/price_history/*`, `api/services.py` | asset charts, portfolio performance, compare, signals | production | Shared market-data service with provider adapters |
| CAP-LIVE | Live streaming/current prices | `ingestion/websocket/*`, `market_freshness_background.py` | current values, freshness, streaming status | production | Shared live-price service, platform subscriptions |
| CAP-FUND | Fundamentals/corporate calendar | `ingestion/corporate_calendar/*`, `ingestion/fundamentals/*` | fundamentals, business strength, rankings | production/partial provider | Shared fundamentals service with entitlement status |
| CAP-BENCH | Benchmark ingestion | `ingestion/indices/*` | benchmarks, performance, compare | production | Shared benchmark service and view models |
| CAP-NEWS | News ingestion/classification | `news/*`, `news/providers/*` | news terminal, asset/portfolio news, signals | production with mock default | Provider-neutral news service, live providers behind config |
| CAP-SENT | Retail sentiment | `ingestion_sentiment/*` | retail sentiment, rankings, signals | production | Shared sentiment service with normalized snapshots |
| CAP-ANALYTICS | Deterministic analytics | `analytics/*` | asset, portfolio, compare, AI context | production | Core shared analytical service package |
| CAP-BSTRENGTH | Business strength | `services/business_strength/*` | asset scorecards, compare | production | Reusable scoring module and card DTO |
| CAP-BROKER | Broker sync/import | `brokers/*`, `CommandApiService` | broker workspace, portfolio projection/import | production | Provider-neutral broker domain; strict confirmation commands |
| CAP-OPS | Background workers | `api/*_background.py`, app state | operations, data health | production | Normalize worker status/actions |
| CAP-FX | Currency conversion | `ComparisonApiService._fx_rate`, `fx_rate` table | portfolios, compare | partial | Create explicit FX service and dated-rate provider |
| CAP-AI | AI-ready context | `analytics/calculations.py`, analytics models | future AI services | partial/no LLM call | Keep deterministic facts separate from prompt/model layer |

## Hidden, Partial, Duplicate, and Legacy Surfaces

- Duplicate asset detail routes: `/assets/:assetId` and `/asset/:assetId` both point to
  `AssetDetailPage`. Prior architecture notes warn of collision with static `/assets`; keep both
  only for compatibility and plan a deprecation.
- Legacy redirect route: `/compare-` redirects to `/compare`.
- News alert CRUD exists in API but no full UI management route exists.
- Business Strength audit/history/template/methodology endpoints exist; asset UI exposes scorecard
  and optional audit pieces, but not a full scorecard administration workflow.
- Business Strength future research fields exist but are intentionally disabled/stubbed.
- News provider is deterministic `mock_news` by default in docs/tests; live provider registration is
  a future integration concern.
- `fx_rate` schema exists, but dated FX provider ingestion is documented as a gap.
- `src/dashboard/models/storage.py` remains a legacy CLI facade.
- Some analytical definitions and calculations live in frontend utilities (`comparisonUtils.ts`),
  which should not remain the only source of metric semantics for mobile, desktop, or AI services.
- Large API service classes combine orchestration, domain logic, SQL access, and DTO shaping. This
  is workable now but weak for portability.

## Cross-Platform Support Matrix

| Module group | Web app | Simplified mobile | Advanced desktop | AI/services | Shared backend |
| --- | --- | --- | --- | --- | --- |
| Portfolio workspace/detail | Full | Summary, holdings, alerts, drilldowns | Full with multi-panel layout | Portfolio facts, risk, anomalies | Required |
| Asset research | Full | Identity, chart, score summaries, news | Full research/audit | Asset facts and scorecards | Required |
| Compare | Full | Two-asset simplified compare | Full multi-asset workspace | Comparison snapshots | Required |
| Benchmarks | Full | Snapshot and basic detail | Full explorer/diagnostics | Benchmark context | Required |
| News | Full terminal | Feed/detail/save | Full terminal | Context retrieval/summarization | Required |
| Retail sentiment | Full | Summary/cards | Full drilldowns | Sentiment facts | Required |
| Signals | Full | Triage cards/actions | Full screener | Evidence graph/recommendations | Required |
| Brokers | Full | Status, mapping, import review | Full admin/reconciliation | Summaries only, guarded actions | Required |
| Operations | Full admin | Read-only plus narrow actions | Full admin | Data-health agent | Required |
| Settings/layout | Full local | Simplified preferences | Full layout customization | Personalization metadata | Optional/shared preference service |

## Refactor Boundaries for Later Work

1. Shared domain contracts first:
   - `PortfolioSummary`, `PositionSummary`, `PerformanceSeries`, `RiskReport`,
     `FundamentalsRollup`, `BusinessStrengthScorecard`, `NewsFeed`, `SignalEvidence`,
     `ComparisonWorkspace`, `BenchmarkSnapshot`, `WorkerStatus`.
2. Shared analytical services:
   - Move stock ranking, holding factor grade, comparison metric registry, FX policy, and
     optimization preview out of `api/services.py` and frontend utilities into explicit domain
     modules.
3. Platform adapters:
   - Keep React components as web adapters over shared view models.
   - Build mobile from compact cards/lists, not the current dense tables.
   - Build desktop from the same modules with richer layout/persistence.
4. Operations separation:
   - Treat job scheduling, worker control, broker import, and raw payload toggles as command modules
     with confirmation, audit, and permission boundaries.
5. AI service separation:
   - AI should consume deterministic facts and source-attributed snapshots. It should not query
     raw UI state or reconstruct formulas from frontend components.

## Priority Module Extraction Plan

This is not an implementation sequence for the current task; it is the recommended future refactor
order.

1. Extract shared type/view-model package from `web/src/api.ts` and `src/dashboard/api/models.py`.
2. Extract comparison metric registry and series metric calculations from `comparisonUtils.ts` into
   shared analytics metadata.
3. Extract holding factor-grade and stock-ranking scoring from `PortfolioApiService` into a ranking
   domain service.
4. Extract reusable portfolio/asset/benchmark/news card and table components from route files.
5. Normalize worker/action command DTOs for Operations and broker workflows.
6. Introduce platform-specific layout adapters over the existing page-feature registry.
7. Deprecate duplicate/legacy routes only after compatibility telemetry or explicit migration.

## Documentation Gaps to Fill Later

- Add endpoint-to-module OpenAPI tags when routes are split.
- Add module-level ADRs for comparison metrics, ranking/factor scoring, and platform view models.
- Add a formal stale-data policy by data class: current price, daily price, fundamentals, news,
  sentiment, broker, benchmark composition.
- Add a permission model before mobile/desktop clients expose destructive or provider-touching
  actions.
- Add AI audit-trail requirements for every generated summary/recommendation.
