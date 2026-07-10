# Architecture Overview

This document reflects the current implementation in `src/dashboard`, `web/src`,
`src/dashboard/db/schema.sql`, and `src/dashboard/db/migrations/`.

For the Phase 1.5 target module boundaries, ownership matrix, dependency rules,
public interface catalog, migration sequence, and diagrams, see
[docs/architecture/README.md](architecture/README.md). This page remains the
current-state architecture overview.

## Local-first system

```mermaid
flowchart LR
    CLI["dashboard CLI\nsrc/dashboard/cli.py"] --> Manager["DashboardManager\nstorage facade + command mixins"]
    Web["React + Vite\nweb/src"] --> ApiClient["web/src/api.ts"]
    ApiClient --> API["FastAPI\nsrc/dashboard/api/app.py"]
    API --> Services["API services\nsrc/dashboard/api/services.py"]
    API --> Workers["API background workers"]
    Manager --> DuckDB[("DuckDB\nschema.sql + migrations")]
    Services --> DuckDB
    Workers --> DuckDB
    Services --> Analytics["analytics engine/repository"]
    Services --> Broker["broker sync"]
    Services --> News["news + sentiment services"]
    Services --> Ingestion["ingestion services"]
    Ingestion --> Providers["Yahoo/FMP/Finnhub/Reddit/X/news providers"]
    Broker --> SnapTrade["SnapTrade"]
```

## Database access layer

```mermaid
flowchart TD
    Init["init_db(db)"] --> Base["schema.sql"]
    Init --> Live["live_price_streaming.sql"]
    Init --> Bench["benchmark_indices.sql"]
    Init --> Strength["business_strength.sql"]
    Init --> NewsSchema["financial_news.sql"]
    Init --> Catalog["seed_stock_catalog(conn)"]
    APIReq["FastAPI request"] --> Dep["get_connection(request)"]
    Dep --> Lock["app.state.write_lock"]
    Lock --> Conn["request-scoped DuckDB connection"]
    CLI["CLI startup"] --> DB["DB(data/persistent_db.db)"]
    DB --> Init
```

The API opens and closes one DuckDB connection per request. Writes are serialized by the API
process lock. CLI commands use a long-lived `DB` connection through `DashboardManager`.

## CLI command flow

```mermaid
flowchart TD
    User["terminal input"] --> View["DashboardView / PortfolioView"]
    View --> Parser["argparse + shlex parsing"]
    Parser --> Manager["DashboardManager"]
    Manager --> Commands["Analytics, Broker, BusinessStrength, Ingestion, Streaming mixins"]
    Commands --> DB[("DuckDB")]
    Commands --> Providers["provider clients when command explicitly runs ingestion/sync"]
    DB --> Formatters["table formatters"]
    Formatters --> Output["terminal output"]
```

## Portfolio, transaction, and position flow

```mermaid
flowchart TD
    Import["manual command or txn importer"] --> Txn["txn table"]
    Txn --> Update["DashboardManager.update_positions"]
    Update --> Position["position table"]
    Position --> TickerUniverse["portfolio_ticker sync"]
    Position --> API["portfolio API services"]
    API --> Web["portfolio, asset, compare, signals routes"]
    Txn --> Analytics["transaction-aware analytics"]
```

`position` is derived from transactions and refreshed by command/service code. `portfolio_ticker`
keeps ingestion scope aligned with active holdings.

## Ingestion job and scheduler flow

```mermaid
flowchart TD
    Schedule["CLI/API schedule request or worker tick"] --> CommandSvc["CommandApiService / IngestionCommands"]
    CommandSvc --> Job[("ingestion_job")]
    Runner["run_ingestion_jobs"] --> Job
    Runner --> Market["price history service"]
    Runner --> Corporate["corporate calendar/fundamentals service"]
    Runner --> Sentiment["sentiment scheduler/service"]
    Market --> MarketTables[("asset_quote_daily, dividends, splits, asset_sync_state")]
    Corporate --> CorpTables[("earnings_calendar_event, financial_statement, fundamental_sync_state")]
    Sentiment --> SentTables[("social_post, news_article, ticker_sentiment_daily, factor snapshots")]
    Runner --> Status["done or failed with redacted error"]
```

Failure behavior is recorded in `ingestion_job.error_message` and domain sync-state tables. Retry
logic skips newer successes and provider-permanent failures such as known entitlement limits.

## Provider integration flow

```mermaid
flowchart LR
    Services["ingestion/news/broker services"] --> Registry["provider factory or registry"]
    Registry --> Yahoo["yfinance"]
    Registry --> FMP["FMP"]
    Registry --> Finnhub["Finnhub websocket"]
    Registry --> Reddit["Reddit OAuth"]
    Registry --> X["X recent search"]
    Registry --> Snap["SnapTrade"]
    Services --> Rate["rate limits and call budgets"]
    Services --> Redact["error redaction before persistence"]
    Services --> DB[("normalized DuckDB tables")]
```

Provider credentials are read from environment variables. Tests use fake providers and monkeypatches
instead of real network calls.

## Background workers

```mermaid
flowchart TD
    Lifespan["FastAPI lifespan"] --> IngestionWorker["IngestionBackgroundWorker\nsafe-off by default"]
    Lifespan --> FreshnessWorker["MarketFreshnessWorker\nsafe-off by default"]
    Lifespan --> ReadinessWorker["DataReadinessWorker\nsafe-off by default"]
    Lifespan --> BrokerWorker["BrokerBackgroundWorker\nsafe-off by default"]
    IngestionWorker --> Routine["bounded routine scheduling + run batches"]
    FreshnessWorker --> CurrentPrices["Yahoo recent bars -> current_asset_price"]
    ReadinessWorker --> ValuationInputs["valuation-critical price/fundamental readiness"]
    BrokerWorker --> SnapDue["SnapTrade sync-due"]
```

The worker controls are exposed on the Operations route and `/api/v1/*/status` endpoints.

## Live quote and websocket flow

```mermaid
flowchart TD
    Resolver["LivePriceSubscriptionResolver"] --> Universe["portfolio_ticker + optional watchlist"]
    Universe --> Session["StreamSessionClassifier"]
    Session --> Regular["regular session"]
    Session --> Extended["pre/after hours"]
    Regular --> Finnhub["FinnhubWebSocketClient"]
    Extended --> FMPPoller["FmpExtendedHoursClient"]
    Finnhub --> Repo["LivePriceRepository"]
    FMPPoller --> Repo
    Repo --> Tick[("live_price_tick")]
    Repo --> Current[("current_asset_price")]
    Repo --> Health[("live_price_provider_health")]
    API["GET /api/v1/market/streaming/status"] --> Repo
```

## Benchmark ingestion flow

```mermaid
flowchart TD
    Seed["seed benchmark universes"] --> Index[("benchmark_index, benchmark_index_symbol")]
    Refresh["POST /api/v1/benchmarks/{id}/refresh"] --> Scheduler["index scheduler"]
    Scheduler --> Provider["FMP and yfinance index providers"]
    Provider --> Prices[("benchmark_index_daily_price, intraday_price")]
    Provider --> Composition[("composition_snapshot, constituent, exposure_snapshot")]
    Prices --> Metrics[("daily_metric, relative_metric, financial_metric")]
    Scheduler --> Sync[("benchmark_index_sync_state")]
```

## Test and CI flow

```mermaid
flowchart LR
    Change["code or docs change"] --> Py["ruff + pytest"]
    Change --> Web["eslint + tsc + vite build + vitest"]
    WebFacing["web-facing change"] --> Live["API health + Vite refresh"]
    IngestionRelated["ingestion/valuation/signals/operations change"] --> Health["full data-health workflow + browser scan"]
```

See `docs/testing.md` for exact commands.
