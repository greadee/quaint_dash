# ADR Index

This index was audited against the current repository on 2026-07-09. Historical ADR numbers are
preserved even when older files contain duplicate IDs. Use this index for current status rather
than renumbering old records.

Status vocabulary: Proposed, Accepted, Implemented, Superseded, Deprecated, Rejected.

| ADR | Title | Status | Current marker | Superseded by | Evidence |
| --- | --- | --- | --- | --- | --- |
| ADR-000 | Focus on app function over form | Implemented | Current as project principle |  | `README.md`, `src/dashboard/cli.py`, `web/src/` |
| ADR-001 | Test CLI using monkeypatch and capsys | Implemented | Current for CLI tests |  | `tests/cli/`, `tests/test_broker_sync.py` |
| ADR-003 | Use DuckDB as the primary database | Implemented | Current |  | `src/dashboard/db/db_conn.py`, `src/dashboard/db/schema.sql` |
| ADR-004 | Introduce a DB wrapper class | Implemented | Current but narrow |  | `src/dashboard/db/db_conn.py` |
| ADR-005 | Separate domain models from storage logic | Implemented | Current |  | `src/dashboard/models/domain.py`, `src/dashboard/models/storage.py` |
| ADR-064 | PortfolioManager belongs to, but is not a DashboardManager | Accepted | Current for CLI facade |  | `src/dashboard/models/storage.py` |
| ADR-007 | Normalize date inputs before SQL queries | Implemented | Current for CLI-era date commands |  | `src/dashboard/models/storage.py`, `tests/cli/` |
| ADR-008 | Keep database as source of truth for positions | Implemented | Current |  | `txn`, `position`, `portfolio_ticker`, API portfolio tests |
| ADR-009 | CLI view layer separate from CLI | Implemented | Current |  | `src/dashboard/cli.py`, `src/dashboard/models/cli_view.py` |
| ADR-010 | Introduce a Formatter class over pandas | Implemented | Current for CLI display |  | `src/dashboard/services/table_formatter.py` |
| ADR-011 | Separate Formatter UML diagram | Implemented | Current as historical diagram |  | `docs/classes/plantuml-code/formatters_ph1.puml` |
| ADR-012 | Choice of data providers | Implemented | Partially current; provider set expanded | ADR PH9 documents current provider mix | `src/dashboard/ingestion/`, `docs/environment_setup.md` |
| ADR-013 | Finnhub websocket vs REST API | Implemented | Current for regular-session live stream |  | `src/dashboard/ingestion/websocket/` |
| ADR-014 | Ingestion polling rates | Implemented | Current as principle; exact env knobs evolved | ADR PH9 documents safe worker defaults | `.env.example`, `src/dashboard/api/*background.py` |
| ADR-015 | Ingestion scheduling rates | Implemented | Current as principle |  | `IngestionBackgroundConfig`, `MarketFreshnessConfig` |
| ADR-016 | Market hours behaviour | Implemented | Current |  | `trading_calendar`, live stream session classifier |
| ADR-017 | Price history vs live market data separation | Implemented | Current |  | `asset_quote_daily`, `live_price_tick`, `current_asset_price` |
| ADR-018 | Historical OHLCV backfill moved from FMP to Yahoo Finance | Implemented | Current |  | `dashboard.ingestion.price_history.provider_yahoo` |
| ADR-019 | Provider abstraction layer for ingestion | Implemented | Current |  | provider classes under `src/dashboard/ingestion` |
| ADR-020 | Automatic scheduler-based ingestion | Implemented | Current but safe-off in API by default | ADR PH9 updates worker safety posture | `IngestionBackgroundWorker`, `.env.example` |
| ADR-021 | Best-effort metadata ingestion | Implemented | Current |  | `src/dashboard/services/asset_importer.py` |
| ADR-022 | Exchange trading calendar ingestion | Implemented | Current |  | `src/dashboard/ingestion/trading_calendar/` |
| ADR-023 | Session-aware market streaming | Implemented | Current |  | `src/dashboard/ingestion/websocket/session_classifier.py` |
| ADR-024 | Asset market identification model | Implemented | Current |  | `asset` columns and ticker universe code |
| ADR-027 | Shared ingestion job model for corporate data | Implemented | Current |  | `ingestion_job`, corporate service tests |
| ADR-028 | Corporate calendar refresh cadence | Implemented | Current |  | corporate scheduler and tests |
| ADR-029 | Raw JSON storage for financial statements | Implemented | Current |  | `financial_statement.data_json` |
| ADR-030 | Benchmark index domain separation | Implemented | Current |  | `src/dashboard/ingestion/indices/` |
| ADR-032 | Index composition snapshots | Implemented | Current |  | `benchmark_index_composition_snapshot` |
| ADR-032 | Derived index exposure snapshots | Implemented | Current; duplicate number preserved |  | `benchmark_index_exposure_snapshot` |
| ADR-033 | Local index metric computation | Implemented | Current |  | `BenchmarkIndexIngestionService.compute_daily_metrics` |
| ADR-034 | Benchmark index service factory | Implemented | Current |  | `index_service_factory.py` |
| ADR-035 | Non-core benchmark universe | Implemented | Current |  | `sector_industry_index_universe.py` |
| ADR-036 | ETF proxy benchmarks for sectors and themes | Implemented | Current |  | benchmark provider tests |
| ADR-037 | Unified benchmark refresh methods | Implemented | Current |  | benchmark API refresh routes |
| ADR-038 | FMP ETF holdings for proxy composition | Implemented | Current with yfinance fallback | ADR PH9 notes provider mix | `fmp_index_provider.py`, `yfinance_index_provider.py` |
| ADR-039 | Local metrics for sector and industry benchmarks | Implemented | Current |  | benchmark metric tests |
| ADR-040 | FMP for extended-hours price polling | Implemented | Current |  | `fmp_extended_hours_poller.py` |
| ADR-041 | yfinance as gap repair provider only | Implemented | Partially current; yfinance also backs market freshness and benchmark proxy fallback | ADR PH9 documents current provider usage | `market_freshness_background.py`, `yfinance_index_provider.py` |
| ADR-042 | Portfolio-first live price subscriptions | Implemented | Current |  | `LivePriceSubscriptionResolver` |
| ADR-043 | Optional watchlist streaming | Implemented | Current |  | live stream resolver and worker options |
| ADR-044 | Separate current price state from raw live ticks | Implemented | Current |  | `live_price_tick`, `current_asset_price` |
| ADR-045 | Provider health tracking for live streaming | Implemented | Current |  | `live_price_provider_health` |
| ADR-046 | Session-based live price routing | Implemented | Current |  | `StreamSessionClassifier` |
| ADR-047 | Pure parser for Finnhub trade payloads | Implemented | Current |  | `finnhub_stream.py`, streaming tests |
| ADR-048 | Live price tables are operational data | Implemented | Current |  | live price migration and API status |
| ADR-049 | Deduplicated symbol subscription snapshot | Implemented | Current |  | live price subscription snapshot tests |
| ADR-050 | Configurable extended-hours streaming | Implemented | Current |  | live stream command/options |
| ADR-051 | Existing statement ingestion as canonical path | Implemented | Current |  | fundamentals services and data-readiness fallback |
| ADR-052 | Subscription refresh jobs | Implemented | Current |  | `fundamental_subscription` |
| ADR-053 | Refresh and backfill separation | Implemented | Current |  | fundamental refresh/backfill scheduler |
| ADR-054 | Partial fundamental backfill success | Implemented | Current |  | corporate ingestion tests |
| ADR-055 | Post-earnings fundamental refresh | Implemented | Current |  | corporate scheduler |
| ADR-056 | Unified corporate ingestion job table | Implemented | Current |  | `ingestion_job` |
| ADR-057 | Fundamentals as enrichment data | Implemented | Current |  | analytics and readiness services |
| ADR-058 | Subscription-gated fundamentals backfill | Implemented | Current |  | `fundamental_subscription` |
| ADR-059 | Provider call budgets for fundamentals backfill | Implemented | Current |  | `dashboard.ingestion.rate_limits` |
| ADR-060 | Failed backfill jobs are recorded, not process-crashing | Implemented | Current |  | retry and provider failure tests |
| ADR-061 | Calculation-first analytics layer | Implemented | Current |  | `src/dashboard/analytics/` |
| ADR-062 | Existing data before new ingestion | Implemented | Current |  | analytics repository/services |
| ADR-063 | Optional analytics snapshot storage | Implemented | Current |  | analytics persistence commands |
| ADR-065 | AI-ready analytics context | Implemented | Current as local context payloads |  | analytics models and reports |
| ADR-066 | User-facing analytics commands and stable payloads | Implemented | Current |  | CLI analytics tests |
| ADR-067 | Benchmark defaults and portfolio valuation rollups | Implemented | Current |  | benchmark default API tests |
| ADR-064 | Daily and portfolio-change refresh cadence | Implemented | Current; duplicate number preserved |  | analytics persistence |
| ADR-068 | Focused analytics package boundaries | Implemented | Current |  | `src/dashboard/analytics/` |
| ADR-068 | Read-only broker sync through SnapTrade | Implemented | Current; duplicate number preserved |  | `src/dashboard/brokers/` |
| ADR-069 | Immutable broker users and secret storage | Implemented | Current |  | `broker_user`, `LocalSecretCipher` |
| ADR-069A | Broker lifecycle commands | Implemented | Current |  | broker CLI and API routes |
| ADR-070 | Direct SnapTrade REST client with request signatures | Implemented | Current |  | `snaptrade.py` |
| ADR-070A | Real credential smoke test | Implemented | Current |  | `broker snaptrade smoke-test` |
| ADR-071 | Broker sync storage before portfolio import | Implemented | Current |  | broker repository and import tests |
| ADR-072 | Explicit account mapping and idempotent portfolio projection | Implemented | Current |  | `broker_portfolio_txn_map` |
| ADR-072A | Paginated activity sync and broker transaction normalization | Implemented | Current |  | broker sync tests |
| ADR-072B | Optional raw provider payload storage | Implemented | Current |  | broker storage config |
| ADR-073 | Daily due sync scheduler | Implemented | Current; API background default is now opt-in | ADR PH9 updates safe-off default | `BrokerBackgroundConfig` |
| ADR-074 | Current limits and next phase hooks | Implemented | Current as historical boundary |  | README and web app docs |
| ADR-075 | Focused broker-sync service boundaries | Implemented | Current |  | `src/dashboard/brokers/` |
| ADR-076 | Local-first API and web client | Implemented | Current |  | `src/dashboard/api/app.py`, `web/src` |
| ADR-077 | Request-scoped DuckDB access | Implemented | Current |  | `api/dependencies.py` |
| ADR-078 | Stable analytics and redacted broker responses | Implemented | Current |  | API models and redaction tests |
| ADR-079 | Signals are versioned evaluations, not alerts or factor scores | Implemented | Current |  | signal tables and API route |
| ADR-080 | Deterministic server-side signal querying | Implemented | Current |  | `GET /api/v1/signals` |
| ADR-081 | Portfolio priority and freshness lifecycle | Implemented | Current |  | signals API/tests |
| ADR-079 | Backend-owned portfolio management analytics | Implemented | Current; duplicate number preserved |  | portfolio API service/tests |
| ADR-080 | Optimization is preview-only | Implemented | Current; duplicate number preserved |  | optimization preview route/tests |
| ADR PH6 | Metric hydration identity | Accepted | Current |  | `valuation_asset_id`, comparison payload fields |
| ADR PH7 | Deterministic business strength scorecard and sector-aware templates | Accepted | Current |  | business strength migration/service/docs |
| ADR PH8 | Provider-neutral financial news terminal | Accepted | Current |  | `docs/news_terminal.md`, news migration/service/tests |
| ADR PH9 | Current architecture documentation and safe local operations | Accepted | Current |  | docs added in this pass, `.env.example`, worker defaults |

## Supersession notes

- ADR PH9 does not delete or rewrite historical ADRs. It supersedes stale onboarding and diagram
  assumptions by documenting the current API/web/schema/safety baseline.
- ADR-041 is partially superseded in practice because yfinance now does more than gap repair:
  current market freshness and benchmark proxy fallback use it.
- ADR-073 remains true for explicit broker sync scheduling, but the API periodic background worker
  now defaults safe-off and must be explicitly enabled.
