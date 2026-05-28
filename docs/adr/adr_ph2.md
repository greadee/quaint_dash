# Phase 2 - Metric Ingestion

## ADR-012: Choice of Data Provider(s)

**Decision:** Use Finnhub for semi-real time ticker data and news, and FMP for ticker metadata, earnings, historical data, etc.

**Context:** Need to stay within API rate limits of free versions whilst supplying the most accurate information to the dashboard.

**Rationale:** 
- Finnhub supports websocket streaming 
- The data coming from Finnhub, and from FMP need to be scheduled differently
- Need to keep it to free tiers

## ADR-013: Finnhub: Websocket vs REST API

**Decision:** Implement ticker quotes from Finnhub through websocket streaming to for portfolio symbols only, watchlist symbols require us to evaluate the rate limit with portfolio.

**Context:** API: ~60 calls/min, Websocket: ~50 symbols subscribed; 10 less tickers tracked for streamed data is a worthy tradeoff.

**Rationale:** 
- Managing 50+ tickers concurrently is more in line with institutional portfolio management, and not retail use by one single user.
- Websocket streaming will be better for the semi-real time data, and news updates.
- Do not have to worry about exceeding call rate cap
- May have issues scaling the portfolio/watchlist within the free tier, but that would also be a problem for API calls.

## ADR-014: Ingestion Polling Rates

**Decision:** 
- Earnings calendar refreshed bi-weekly
- Daily close data pulled once per market day after close 
- (Core) index composition refreshed after open, lunch and close

**Context:** What data do we need, does it need to be updated regularly, and when?

**Rationale:**
- Need to keep an updated earnings calendar, (forward 14 days)
- Ingest closing data on days the market is open, instead of deriving closing data; to append to the collection of historical data daily
- Ingest only the main indicies (S&P 500, NAS 100, TSX 60, RUS 2000) intraday, less general indices can be queried

## ADR-015: Ingestion Scheduling Rates

**Decision:** Poll for bi-weekly earnings calendar/data on weekends or off-days to prevent exceeding the usage limits, poll for daily close data on tickers and indices a few minutes after close.

**Context:** We may exceed FMP's usage limits if we need to ingest earnings calendar/data, and also ingest daily close data on that day. 

**Rationale:** 
- The forward 14 day window on the earnings data ensures we are always up to date, as the earnings calendar is pretty concrete.
- Wait a few minutes after close in order to allow FMP to process the daily close data correctly.

## ADR-016: Market Hours Behaviour

**Decision:** 
- Schedule based off of ET time zone
- Convert back to local timezone for display
- Market calendar for determining open and closed days

**Context:** Job scheduling needs a clear definition of the time for market open, lunch and market close.

**Rationale:**
- Daily close data is only meaningful after the data provider has finalized the day's data
- Move as many API calls to after hours to preserve bandwitch for intraday
- Allows for timezone interchangeability for other dashboard users
- Start with a basic Mon-Fri open schedule, and adjust to a more accurate calendar source for handling of holidays and half-days

## ADR-017: Price History vs Live Market Data Separation

**Decision:** Separate historical OHLCV/dividend/split ingestion from forward-looking live market ingestion both conceptually and structurally.

**Context:** 
The original `market` ingestion naming became ambiguous once the system expanded to include:
- historical OHLCV backfill
- dividend/split backfill
- websocket streaming
- future fundamentals ingestion

**Rationale:** 
- Historical ingestion is batch-oriented and archival in nature
- Live websocket ingestion is event-driven and latency-sensitive
- Historical backfill and live streaming will evolve independently
- Fundamentals ingestion should remain isolated from OHLCV ingestion
- Clearer separation of concerns improves maintainability

**Implementation Notes:** 
- Rename `dashboard.ingestion.market` to `dashboard.ingestion.price_history`
- Remove refresh job concepts from historical OHLCV ingestion
- Reserve websocket ingestion for forward-looking live quote updates

## ADR-018: Migration of Historical OHLCV Backfill from FMP to Yahoo Finance

**Decision:** Replace FMP historical OHLCV/dividend/split backfill endpoints with Yahoo Finance (`yfinance`) for Domain A historical price ingestion.

**Context:** 
The previous FMP historical endpoint returned legacy endpoint deprecation errors and became unreliable for free-tier historical backfill.

**Rationale:** 
- Yahoo Finance provides free OHLCV/dividend/split history
- International tickers (`BN.TO`, `FFH.TO`, etc.) work reliably
- No API key or rate-limit management required
- Existing ingestion architecture already isolates provider logic
- FMP remains more useful for future fundamentals ingestion

**Implementation Notes:** 
- Replace `FMPMarketProvider` with `YahooPriceProvider`
- Install `yfinance` dependency
- Continue using existing ingestion workers/repositories/queues unchanged
- Use Yahoo Finance only for historical OHLCV/dividend/split ingestion


## ADR-019: Provider Abstraction Layer for Ingestion

**Decision:** Isolate external data providers behind provider-specific ingestion adapters.

**Context:** 
Multiple external providers are now used across the ingestion system:
- Yahoo Finance
- FMP
- Finnhub

Provider APIs, rate limits, and endpoint stability may change independently over time.

**Rationale:** 
- Prevent provider-specific logic from leaking into workers/services
- Allow providers to be swapped without changing queue/workflow logic
- Simplify mocking/testing of ingestion pipelines
- Support future fallback providers
- Reduce risk from provider deprecations or outages

**Implementation Notes:** 
- Workers/services depend only on provider interfaces
- Providers expose normalized methods:
  - `fetch_price_daily`
  - `fetch_dividends`
  - `fetch_splits`
  - `fetch_asset_metadata`
- Queue/repository logic remains provider-agnostic

## ADR-020: Automatic Scheduler-Based Ingestion

**Decision:** Run ingestion scheduling automatically during application startup instead of relying on manual CLI execution.

**Context:** 
Backfill and metadata ingestion should occur continuously over time without requiring manual operator intervention.

**Rationale:** 
- Reduces operational burden on the user
- Keeps tracked assets synchronized automatically
- Avoids requiring external schedulers during early development
- Easier to test than cron-based orchestration
- Allows ingestion backlog to drain gradually over multiple app launches

**Implementation Notes:** 
- Startup scheduler checks:
  - stale metadata
  - missing price history
  - failed backfills
- Scheduler enqueues a capped number of jobs per startup
- Workers process a limited number of jobs per run
- Duplicate pending/running jobs are prevented

## ADR-021: Best-Effort Metadata Ingestion

**Decision:** Asset metadata ingestion failures must not block transaction imports.

**Context:** 
External provider failures or rate limits should not prevent users from importing transactions into portfolios.

**Rationale:** 
- Portfolio transaction data is the primary source of truth
- Metadata can be synchronized asynchronously later
- External provider availability is not guaranteed
- Prevents ingestion outages from blocking core functionality
- Improves resilience of the import pipeline

**Implementation Notes:** 
- Metadata ingestion runs after transaction import
- Metadata failures are swallowed and logged
- Sync state tracked separately in `asset_metadata_sync`
- Automatic scheduler retries failed/stale metadata later

## ADR-022: Exchange Trading Calendar Ingestion

**Decision:** 
The system will maintain persisted exchange trading calendars for supported markets.

**Context:** 
Market refreshes, websocket streaming, and future earnings ingestion require accurate knowledge of:
- holidays
- half-days
- exchange closures
- active trading sessions

Weekend-only logic is insufficient.

**Rationale:** 
- Prevents unnecessary ingestion runs
- Avoids streaming closed markets
- Supports deterministic scheduling decisions
- Removes runtime dependency on remote APIs
- Enables future multi-market expansion

**Implementation Notes:** 
- Trading calendars stored in `trading_calendar`
- Sync state tracked in `trading_calendar_sync_state`
- Initial exchanges:
  - XNYS (US)
  - XTSE (CAN)
- Provider: `pandas_market_calendars`
- Calendars refreshed yearly
- Schedulers consult calendar state before ingestion execution

## ADR-023: Session-Aware Market Streaming

**Decision:** 
Realtime streaming must become exchange-session aware.

**Context:** 
Streaming markets continuously wastes websocket capacity and ignores:
- holidays
- half-days
- premarket sessions
- afterhours sessions

US and Canadian exchanges operate on different schedules.

**Rationale:** 
- Reduces unnecessary websocket usage
- Prevents invalid market-state assumptions
- Supports future extended-hours functionality
- Improves scheduler coordination

**Implementation Notes:** 
- Streaming checks trading calendar state before startup
- Supported session states:
  - regular
  - premarket
  - afterhours
  - half-day
  - closed
- Streaming enablement determined per market

## ADR-024: Asset Market Identification Model

**Decision:** 
Market identity will be exchange-driven rather than ticker-suffix-driven.

**Context:** 
Ticker suffix inference is unreliable for:
- ADRs
- dual listings
- OTC securities
- international exchanges

Future ingestion and scheduling require authoritative exchange identity.

**Rationale:** 
- Improves international scalability
- Enables accurate session scheduling
- Supports complex listing structures
- Removes unreliable ticker parsing assumptions

**Implementation Notes:** 
- Assets will eventually maintain:
  - `primary_exchange_code`
  - `market_code`
  - `timezone`
- Trading calendars and schedulers depend on exchange identity
- Initial supported exchanges:
  - XNYS
  - XTSE

  ## ADR-025: Earnings Calendar as Trigger Table

**Decision:** 
The earnings calendar will be stored and used as a trigger table, not as the final source of truth for fundamentals.

**Context:** 
The earnings calendar identifies when a company is expected to report or has recently reported earnings.

However, full fundamentals are released through separate earnings and financial statement endpoints.

**Rationale:** 
- Avoids polling every tracked stock every day
- Creates an explainable reason for each fundamentals ingestion job
- Supports post-event retries when financial statements lag
- Separates event scheduling from fundamental data storage

**Implementation Notes:** 
- Store calendar rows in:
  - `earnings_calendar_event`
- Calendar rows may include:
  - `earnings_date`
  - `fiscal_year`
  - `fiscal_quarter`
  - `eps_estimated`
  - `eps_actual`
  - `revenue_estimated`
  - `revenue_actual`
- After an earnings date passes, enqueue:
  - `earnings_actuals`
  - `financial_statements`

## ADR-027: Shared Ingestion Job Model for Corporate Data

**Decision:** 
Corporate calendar and fundamentals ingestion will reuse the shared ingestion job and sync-state model.

**Context:** 
Market price-history ingestion already uses:
- `ingestion_job`
- `asset_sync_state`
- service layer
- repository layer
- worker layer

Corporate ingestion needs the same enqueue, claim, process, success, and failure lifecycle.

**Rationale:** 
- Keeps ingestion architecture consistent
- Avoids creating a second scheduling system
- Makes CLI and future automation easier to maintain
- Allows all ingestion domains to share status tracking

**Implementation Notes:** 
- Corporate jobs use:
  - `domain = 'corporate'`
- Supported datasets:
  - `earnings_calendar`
  - `earnings_actuals`
  - `financial_statements`
- Supported job types:
  - `calendar_refresh`
  - `earnings_update`
  - `backfill`
- Workers must always filter by domain

## ADR-028: Corporate Calendar Refresh Cadence

**Decision:** 
The earnings calendar will refresh daily using a rolling date window.

**Context:** 
Earnings dates can change before the event. Actual EPS and revenue values can also appear after the event.

Full financial statements may lag the earnings announcement.

**Rationale:** 
- Captures changed earnings dates
- Captures late EPS and revenue updates
- Reduces unnecessary API calls
- Provides a predictable daily refresh model
- Supports free-tier-friendly ingestion

**Implementation Notes:** 
- Calendar refresh window:
  - `today - 7 days`
  - `today + 90 days`
- Post-event update window:
  - `today - 14 days`
  - `today`
- Scheduler should prevent duplicate jobs when matching jobs are:
  - pending
  - running
  - already created today

## ADR-029: Raw JSON Storage for Financial Statements

**Decision:** 
Financial statements will initially be stored as raw JSON payloads.

**Context:** 
FMP statement endpoints return large payloads with many fields.

The dashboard will eventually derive metrics such as:
- revenue growth
- margins
- EPS
- free cash flow
- debt
- cash
- shares outstanding

Normalizing every field immediately would add schema complexity before the analytics model is finalized.

**Rationale:** 
- Preserves the original provider response
- Avoids premature schema design
- Makes backfills easier
- Supports future derived metrics
- Keeps ingestion simple while analytics mature

**Implementation Notes:** 
- Store statements in:
  - `financial_statement.data_json`
- Use statement types:
  - `income`
  - `balance`
  - `cashflow`
- Use key:
  - `asset_id`
  - `statement_type`
  - `year`
  - `quarter`
- Normalized metric tables or views can be added later

## ADR-030: Benchmark Index Domain Separation

**Decision:** 
Benchmark indices will be stored in dedicated benchmark index tables instead of the normal `asset` table.

**Context:** 
Indices such as S&P 500, Nasdaq 100, TSX, FTSE 100, Nikkei 225, Developed International, Emerging Markets, and Frontier Markets are reference benchmarks.

They are different from tradable holdings such as:
- ETFs
- stocks
- funds
- ADRs

**Rationale:** 
- Keeps portfolio holdings separate from benchmark data
- Avoids treating non-tradable indices as assets
- Supports index-specific composition snapshots
- Supports geographic and sector comparison
- Keeps analytics cleaner for dashboard benchmarking

**Implementation Notes:** 
- Store index metadata in:
  - `benchmark_index`
- Store provider symbols in:
  - `benchmark_index_symbol`
- Keep benchmark ingestion separate from:
  - asset metadata ingestion
  - ticker streaming
  - portfolio transactions

  ## ADR-031: Index Provider Priority and Proxy Policy

**Decision:** 
Index ingestion will prefer low-cost accurate sources first, then fall back to paid/provider API calls only when needed.

**Context:** 
The dashboard uses both yfinance and FMP.

Daily and intraday prices can often be fetched from yfinance without using FMP calls.

Composition data is harder to source for free, especially for:
- international indices
- developed international
- emerging markets
- frontier markets
- sector/theme indices

**Rationale:** 
- Reduces FMP API usage
- Keeps ingestion cheaper
- Preserves provider flexibility
- Allows proxy data when exact index data is unavailable
- Prevents ETF proxy data from being confused with official index data

**Implementation Notes:** 
- Prefer yfinance for:
  - daily index prices
  - intraday index bars
- Prefer FMP for:
  - supported index constituents
  - fallback price ingestion
- Mark proxy data with:
  - `is_proxy = TRUE`
- Store proxy symbols in:
  - `benchmark_index_symbol`
- Never hide whether data came from:
  - official index source
  - provider API
  - ETF proxy

## ADR-032: Index Composition Snapshots

**Decision:** 
Index constituents will be stored as dated composition snapshots.

**Context:** 
Index membership and weights change over time.

The dashboard needs historical context for:
- sector exposure
- country exposure
- currency exposure
- industry exposure
- benchmark comparison

**Rationale:** 
- Preserves historical index composition
- Supports future exposure trend analysis
- Avoids overwriting old benchmark state
- Allows monthly or weekly refreshes
- Supports official and proxy composition data

**Implementation Notes:** 
- Store snapshot metadata in:
  - `benchmark_index_composition_snapshot`
- Store constituents in:
  - `benchmark_index_constituent`
- Use key:
  - `index_id`
  - `snapshot_date`
  - `source`
- Replace same-day same-source constituents on refresh
- Track quality with:
  - `data_quality`
  - `source_type`
  - `is_proxy`

## ADR-032: Derived Index Exposure Snapshots

**Decision:** 
Country, sector, industry, and currency exposures will be stored separately from raw constituents.

**Context:** 
The dashboard frequently needs summarized benchmark exposure data.

Recomputing exposures from constituents every time would add repeated query complexity.

**Rationale:** 
- Speeds up dashboard comparison views
- Keeps constituent data and exposure summaries separate
- Supports geographic allocation analysis
- Supports sector and industry comparison
- Allows exposure data from factsheets or computed constituents

**Implementation Notes:** 
- Store exposure summaries in:
  - `benchmark_index_exposure_snapshot`
- Supported dimensions:
  - `country`
  - `region`
  - `sector`
  - `industry`
  - `currency`
- Exposure rows can be generated from:
  - constituents
  - factsheets
  - ETF proxy holdings
- Use key:
  - `index_id`
  - `snapshot_date`
  - `dimension_type`
  - `dimension_value`
  - `source`

## ADR-033: Local Index Metric Computation

**Decision:** 
Index returns, volatility, moving averages, drawdowns, beta, and correlation will be computed locally from stored price data.

**Context:** 
Different providers may define metrics differently.

The dashboard needs consistent metrics across all benchmark indices.

**Rationale:** 
- Makes metrics reproducible
- Avoids provider-specific metric definitions
- Reduces API dependency
- Supports testing with fake price data
- Keeps analytics consistent across all indices

**Implementation Notes:** 
- Store daily metrics in:
  - `benchmark_index_daily_metric`
- Store relative metrics in:
  - `benchmark_index_relative_metric`
- Compute from:
  - `benchmark_index_daily_price`
- Core metrics include:
  - returns
  - annualized volatility
  - SMA 50
  - SMA 200
  - 52-week high/low
  - drawdown
  - beta
  - correlation

## ADR-034: Benchmark Index Service Factory

**Decision:** 
Provider registry creation will live in a small service factory module.

**Context:** 
The benchmark index service needs both yfinance and FMP providers.

Creating providers directly inside the scheduler or manager would duplicate setup logic.

**Rationale:** 
- Keeps provider wiring centralized
- Avoids repeated registry creation code
- Makes tests easier to mock
- Keeps scheduler focused on timing
- Keeps service focused on ingestion logic

**Implementation Notes:** 
- Store factory logic in:
  - `index_service_factory.py`
- Factory creates:
  - provider registry
  - ingestion service
  - scheduler
- Provider priority is controlled by:
  - `benchmark_index_symbol.is_primary`
  - `benchmark_index_symbol.is_proxy`
- Tests can bypass the factory and inject fake providers directly


## ADR-035: Non-Core Benchmark Universe

**Decision:** 
Sector, industry, and theme benchmarks will use the same benchmark index domain as core geographic benchmarks.

**Context:** 
The dashboard needs comparison data beyond broad market indices.

Non-core benchmarks include:
- all 11 major sectors
- semiconductors
- software
- cloud
- cybersecurity
- AI
- robotics
- solar
- uranium and nuclear
- biotech
- medical devices
- aerospace and defense
- infrastructure
- fintech
- clean energy
- battery technology

**Rationale:** 
- Reuses the existing benchmark schema
- Avoids creating duplicate ingestion systems
- Keeps analytics consistent across benchmark types
- Allows the same price, volatility, composition, and exposure logic
- Makes future benchmark additions configuration-driven

**Implementation Notes:** 
- Store non-core definitions in:
  - `sector_industry_index_universe.py`
- Use:
  - `index_category = 'sector'`
  - `index_category = 'industry'`
  - `index_category = 'theme'`
- Keep:
  - `is_core = FALSE`
- Seed with:
  - `seed_sector_industry_universe()`
  - `seed_all_universes()`


## ADR-036: ETF Proxy Benchmarks for Sectors and Themes

**Decision:** 
Sector, industry, and theme benchmarks will initially use liquid ETF proxies.

**Context:** 
Official sector and industry index data is not always freely available with daily price, intraday price, holdings, and weights.

ETF proxies provide practical benchmark coverage for:
- sector price movement
- intraday movement
- composition
- sector exposure
- country exposure
- industry exposure

**Rationale:** 
- Enables implementation now
- Avoids expensive index licensing
- Supports daily and intraday refreshes
- Provides holdings for exposure calculations
- Keeps proxy status explicit

**Implementation Notes:** 
- Use yfinance first for proxy prices
- Use FMP for proxy holdings
- Mark rows with:
  - `is_proxy = TRUE`
- Store proxy holdings through:
  - `benchmark_index_constituent`
- Store proxy exposure through:
  - `benchmark_index_exposure_snapshot`

## ADR-037: Unified Benchmark Refresh Methods

**Decision:** 
The scheduler will support core and non-core benchmark refreshes through category-based methods.

**Context:** 
Core, sector, industry, and theme benchmarks all need the same refresh types.

Refresh types include:
- daily price
- intraday price
- composition
- daily metrics
- relative metrics

**Rationale:** 
- Reduces duplicated scheduler code
- Keeps benchmark refresh behavior consistent
- Allows targeted category refreshes
- Supports full benchmark refreshes
- Makes tests easier to write

**Implementation Notes:** 
- Add scheduler methods:
  - `run_non_core_daily_refresh`
  - `run_non_core_intraday_refresh`
  - `run_non_core_composition_refresh`
  - `run_sector_daily_refresh`
  - `run_industry_daily_refresh`
  - `run_theme_daily_refresh`
- Category refreshes use:
  - `benchmark_index.index_category`
- Intraday refresh still checks market-open state

## ADR-038: FMP ETF Holdings for Proxy Composition

**Decision:** 
ETF proxy composition will be ingested from FMP ETF holdings where available.

**Context:** 
The benchmark domain needs composition data for sector and industry benchmarks.

For non-core benchmarks, official constituent feeds may be unavailable or licensed.

**Rationale:** 
- Provides usable composition snapshots
- Supports sector and country exposure views
- Avoids manual holding entry
- Keeps all composition rows dated
- Preserves proxy status

**Implementation Notes:** 
- Fetch proxy holdings through:
  - FMP ETF holdings endpoint
- Store snapshot metadata in:
  - `benchmark_index_composition_snapshot`
- Store holdings in:
  - `benchmark_index_constituent`
- Mark source type as:
  - `etf_proxy`
- Mark rows with:
  - `is_proxy = TRUE`

## ADR-039: Local Metrics for Sector and Industry Benchmarks

**Decision:** 
Sector, industry, and theme benchmark metrics will be computed locally from stored benchmark prices.

**Context:** 
Provider performance endpoints may define returns and valuation metrics differently.

The dashboard needs comparable metrics across:
- core indices
- sectors
- industries
- themes

**Rationale:** 
- Keeps metric definitions consistent
- Avoids provider-specific return formulas
- Supports deterministic testing
- Avoids additional API calls
- Reuses existing benchmark metric tables

**Implementation Notes:** 
- Store price rows in:
  - `benchmark_index_daily_price`
- Store computed metrics in:
  - `benchmark_index_daily_metric`
- Compute:
  - returns
  - volatility
  - moving averages
  - drawdown
- Relative metrics can compare against:
  - `SP500`

## ADR-040: FMP for Extended-Hours Price Polling

**Decision:** 
FMP will be used for pre-market and after-hours quote polling when extended-hours streaming is enabled.

**Context:** 
Finnhub WebSocket is used for regular-session streaming, but extended-hours coverage may not be reliable or available through the same stream.

The dashboard needs optional support for:
- pre-market prices
- after-hours prices
- NYSE/NASDAQ extended-hours tickers

**Rationale:** 
- FMP provides explicit extended-hours endpoints
- Avoids assuming Finnhub WebSocket covers all sessions
- Keeps extended-hours logic provider-specific
- Supports batch polling across many symbols
- Allows extended-hours support to be disabled

**Implementation Notes:** 
- Extended-hours polling uses:
  - `FmpExtendedHoursClient`
- Batch quote results are parsed into:
  - `LivePriceTick`
- Worker routes sessions:
  - `pre` -> FMP
  - `after` -> FMP
  - `regular` -> Finnhub
- Extended-hours behavior is controlled by:
  - `enable_extended_hours`
  - `--no-extended-hours`

## ADR-041: yfinance as Gap Repair Provider Only

**Decision:** 
yfinance will not be used as the primary live streaming provider.

**Context:** 
The project already uses yfinance for market data, but live streaming should be handled by Finnhub and extended-hours polling should be handled by FMP.

yfinance can still be useful for repairing missed intraday or extended-hours gaps.

**Rationale:** 
- Avoids mixing polling-based repair with live streaming
- Keeps provider responsibilities clear
- Reduces dependency on yfinance for real-time behavior
- Supports historical reconciliation after outages
- Keeps the worker routing easier to test

**Implementation Notes:** 
- yfinance is reserved for:
  - gap repair
  - missed intraday bars
  - fallback reconciliation
- yfinance should not be called by:
  - regular live stream routing
  - extended-hours FMP polling
- Future repair jobs can write to:
  - intraday price history tables
  - sync state tables

## ADR-042: Portfolio-First Live Price Subscriptions

**Decision:** 
Live price streaming will subscribe to tickers from active portfolio positions by default.

**Context:** 
The dashboard’s most important live prices are the assets the user currently owns.

Watchlist streaming is useful, but it can increase provider usage and is not required for core portfolio valuation.

**Rationale:** 
- Prioritizes portfolio holdings
- Avoids unnecessary provider subscriptions
- Keeps default stream smaller
- Reduces rate-limit and connection pressure
- Aligns with portfolio-first project direction

**Implementation Notes:** 
- Default subscriptions come from non-zero portfolio positions
- Zero-quantity positions are excluded
- Subscription resolution is handled by:
  - `LivePriceSubscriptionResolver`
- Portfolio assets are selected from:
  - `position`
  - `asset`
- Duplicate symbols are streamed once

## ADR-043: Optional Watchlist Streaming

**Decision:** 
Watchlist streaming will be available behind an explicit option.

**Context:** 
The dashboard may eventually support live watchlist monitoring, but watchlist streaming should not be enabled automatically.

Some users may have large watchlists, which could increase provider load.

**Rationale:** 
- Keeps default streaming focused
- Prevents unnecessary API usage
- Allows user-controlled expansion
- Supports future watchlist dashboards
- Keeps tests deterministic

**Implementation Notes:** 
- Watchlist streaming is enabled with:
  - `--include-watchlist`
- Programmatic worker option:
  - `include_watchlist=True`
- Watchlist assets are selected from:
  - `watchlist_asset`
  - `asset`
- Portfolio and watchlist duplicates are deduplicated by symbol

## ADR-044: Separate Current Price State from Raw Live Ticks

**Decision:** 
The dashboard will store latest live prices separately from raw tick history.

**Context:** 
Live streaming produces frequent tick updates.

The dashboard needs:
- one latest price per asset for display
- raw tick rows for audit/debugging

These use cases should not share the same table.

**Rationale:** 
- Keeps dashboard reads simple
- Prevents expensive latest-price queries
- Preserves raw provider data for debugging
- Avoids polluting historical price tables
- Supports short-retention tick cleanup later

**Implementation Notes:** 
- Latest dashboard-ready prices are stored in:
  - `current_asset_price`
- Raw streamed ticks are stored in:
  - `live_price_tick`
- Each saved tick:
  - inserts into `live_price_tick`
  - replaces latest row in `current_asset_price`
- Historical backfills remain separate from live tick storage

## ADR-045: Provider Health Tracking for Live Streaming

**Decision:** 
Live price providers will record health status during streaming and polling.

**Context:** 
Live data depends on external providers.

Providers may fail because of:
- network outages
- invalid API keys
- rate limits
- provider downtime
- malformed responses

**Rationale:** 
- Makes failures visible
- Supports dashboard/provider diagnostics
- Helps distinguish stale data from working streams
- Improves operational debugging
- Enables future retry/backoff policies

**Implementation Notes:** 
- Provider health is stored in:
  - `live_price_provider_health`
- Health rows track:
  - provider
  - status
  - last success time
  - last error time
  - last error message
- Supported provider states:
  - `healthy`
  - `degraded`
  - `down`
- Worker updates health after:
  - successful Finnhub stream handling
  - successful FMP poll
  - provider exceptions

## ADR-046: Session-Based Live Price Routing

**Decision:** 
The live price worker will route provider calls based on market session.

**Context:** 
Different providers are better suited for different market sessions.

The app must distinguish:
- pre-market
- regular session
- after-hours
- closed market

**Rationale:** 
- Keeps provider behavior predictable
- Avoids calling Finnhub when FMP is preferred
- Avoids extended-hours polling when the market is closed
- Makes worker routing easy to test
- Supports future market-specific routing

**Implementation Notes:** 
- Session classification is handled by:
  - `MarketSessionClassifier`
- Routing behavior:
  - `regular` -> Finnhub WebSocket
  - `pre` -> FMP extended-hours polling
  - `after` -> FMP extended-hours polling
  - `closed` -> no provider call
- US session windows depend on:
  - `trading_calendar`
  - configured extended-hours windows
- Worker routing is tested through:
  - `run_once`

## ADR-047: Pure Parser for Finnhub Trade Payloads

**Decision:** 
Finnhub trade payload parsing will be implemented as a pure helper function.

**Context:** 
Parser tests should not require a real WebSocket connection.

The original stream module imported the WebSocket dependency during module import, which caused CI failures when the dependency was missing.

**Rationale:** 
- Keeps parser tests dependency-light
- Avoids WebSocket imports during test collection
- Improves CI reliability
- Makes payload parsing independently testable
- Keeps stream connection logic separate from message parsing

**Implementation Notes:** 
- Pure parser function:
  - `parse_finnhub_trade_payload`
- Input types:
  - `str`
  - `dict`
- Output type:
  - `list[LivePriceTick]`
- Non-trade messages return:
  - empty list
- WebSocket dependency is imported lazily inside:
  - `FinnhubWebSocketClient.stream`

## ADR-048: Live Price Tables Are Operational Data

**Decision:** 
Live streaming tables will be treated as operational data, not long-term market history.

**Context:** 
The app already has or will have historical market price ingestion for backfills and refreshes.

Live streaming data serves a different purpose:
- current dashboard display
- short-term audit/debugging
- provider health checks

**Rationale:** 
- Prevents noisy tick data from polluting historical tables
- Keeps historical prices cleaner
- Allows raw tick retention policies
- Supports different storage lifecycles
- Keeps backfill/refresh jobs independent from live streaming

**Implementation Notes:** 
- Operational live tables:
  - `current_asset_price`
  - `live_price_tick`
  - `live_price_provider_health`
- Historical market tables remain separate
- Raw live ticks can use short retention
- Historical repair can be handled later through:
  - yfinance
  - FMP
  - existing market ingestion jobs

## ADR-049: Deduplicated Symbol Subscription Snapshot

**Decision:** 
Live price subscriptions will deduplicate symbols before provider calls.

**Context:** 
The same ticker can appear in:
- multiple portfolios
- portfolio holdings and watchlists
- repeated position rows

Streaming the same symbol multiple times wastes provider capacity and complicates tick handling.

**Rationale:** 
- Avoids duplicate WebSocket subscriptions
- Reduces provider usage
- Keeps worker routing simple
- Prevents repeated current-price updates from duplicate subscriptions
- Supports cleaner tests

**Implementation Notes:** 
- Deduplication key:
  - `symbol`
- Resolver output:
  - one subscription per symbol
- Portfolio subscription source:
  - `position`
- Watchlist subscription source:
  - `watchlist_asset`
- Tests verify:
  - duplicate AAPL portfolio/watchlist rows stream once

## ADR-050: Configurable Extended-Hours Streaming

**Decision:** 
Extended-hours streaming will be configurable via .env and enabled by default for supported providers.

**Context:** 
Some users may want pre-market and after-hours prices, while others may only want regular-session data.

Extended-hours polling may increase API usage.

**Rationale:** 
- Gives users control over provider usage
- Supports NYSE/NASDAQ extended-hours monitoring
- Allows CI and tests to disable extended-hours behavior
- Keeps regular-session streaming independent
- Supports future provider changes

**Implementation Notes:** 
- CLI disable flag:
  - `--no-extended-hours`
- Worker option:
  - `enable_extended_hours`
- When disabled:
  - pre-market does not call FMP
  - after-hours does not call FMP
  - closed market does not call providers
- Tests verify both enabled and disabled routing