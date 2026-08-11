# Current Schema ER Diagrams

These diagrams are derived from `src/dashboard/db/schema.sql` and every committed migration under
`src/dashboard/db/migrations/`: live pricing, benchmark indices, Business Strength, financial
news, ticker universe, ingestion-job recovery, and candidate runs. They intentionally split the
schema into scoped domains so the diagrams remain readable.

## Core portfolio schema

```mermaid
erDiagram
    portfolio ||--o{ txn : owns
    portfolio ||--o{ position : has
    portfolio ||--o{ portfolio_ticker : scopes
    asset ||--o{ txn : traded
    asset ||--o{ position : held
    asset ||--o{ portfolio_ticker : tracked
    asset ||--o{ watchlist_ticker : watched
    import_batch ||--o{ txn : groups
    fx_rate }o--|| asset : prices

    portfolio {
      BIGINT portfolio_id PK
      TEXT portfolio_name
      TEXT base_ccy
    }
    asset {
      TEXT asset_id PK
      TEXT symbol
      TEXT asset_type
      TEXT asset_subtype
      TEXT ccy
      BOOLEAN track
    }
    txn {
      BIGINT txn_id PK
      BIGINT portfolio_id FK
      TEXT asset_id FK
      TEXT txn_type
      DOUBLE qty
      DOUBLE price
    }
    position {
      BIGINT portfolio_id FK
      TEXT asset_id FK
      DOUBLE qty
      DOUBLE book_cost
    }
```

Source of truth: transactions are the durable ledger; `position` is a derived/current position
table refreshed from transactions and broker projections.

## Asset metadata and ingestion scope

```mermaid
erDiagram
    asset ||--o{ asset_metadata_sync : syncs
    asset ||--o{ asset_sync_state : has
    asset ||--o{ portfolio_ticker : scopes
    asset ||--o{ watchlist_ticker : scopes
    stock_catalog ||--o{ asset : can_seed

    stock_catalog {
      TEXT asset_id PK
      TEXT symbol
      TEXT exchange_code
      TEXT ccy
      TEXT sector
      TEXT industry
    }
    asset_metadata_sync {
      TEXT asset_id PK
      TEXT sync_status
      TIMESTAMP last_succeeded_at
      TEXT last_error
    }
    asset_sync_state {
      TEXT asset_id
      TEXT domain
      TEXT dataset
      TEXT backfill_status
      TIMESTAMP last_successful_at
    }
```

Source of truth: `asset` stores normalized tracked assets; `stock_catalog` expands search choices
without making every catalog symbol a tracked ingestion asset.

## Market data, live prices, and calendars

```mermaid
erDiagram
    asset ||--o{ asset_quote_daily : has
    asset ||--o{ asset_quote_intraday : has
    asset ||--o{ dividend_event : has
    asset ||--o{ split_event : has
    asset ||--o{ current_asset_price : has
    asset ||--o{ live_price_tick : receives
    live_price_stream_config ||--o{ live_price_subscription_snapshot : snapshots
    live_price_provider_health ||--o{ live_price_tick : monitors
    trading_calendar_sync_state ||--o{ trading_calendar : covers

    asset_quote_daily {
      TEXT asset_id FK
      DATE date
      DOUBLE close
      DOUBLE adj_close
      TEXT ing_source
    }
    current_asset_price {
      TEXT asset_id FK
      TEXT symbol
      DOUBLE price
      TEXT provider
      TEXT market_session
      TIMESTAMP updated_at
    }
    trading_calendar {
      TEXT market_code
      DATE session_date
      BOOLEAN is_open
    }
```

Source of truth: daily bars live in `asset_quote_daily`; live ticks are operational data in
`live_price_tick`, with latest state in `current_asset_price`.

## Ingestion jobs, corporate calendar, and fundamentals

```mermaid
erDiagram
    asset ||--o{ ingestion_job : queues
    asset ||--o{ earnings_calendar_event : reports
    asset ||--o{ corporate_event : has
    asset ||--o{ financial_statement : has
    asset ||--o{ fundamental_subscription : subscribes
    asset ||--o{ fundamental_sync_state : syncs
    ingestion_run ||--o{ ingestion_job : observes

    ingestion_job {
      BIGINT job_id PK
      TEXT asset_id FK
      TEXT domain
      TEXT job_type
      TEXT dataset
      TEXT status
      TEXT error_message
    }
    financial_statement {
      TEXT asset_id FK
      TEXT statement_type
      INTEGER year
      INTEGER quarter
      JSON data_json
      TEXT source
    }
    earnings_calendar_event {
      TEXT asset_id FK
      DATE earnings_date
      DOUBLE eps_actual
      DOUBLE revenue_actual
    }
```

Source of truth: `ingestion_job` records executable work and failures; `financial_statement`
stores provider statement JSON used by analytics and readiness.

## News, retail sentiment, factors, and signals

```mermaid
erDiagram
    news_provider ||--o{ news_article : publishes
    news_article ||--o{ news_article_asset : maps
    news_article ||--o{ news_article_entity : mentions
    news_article ||--o{ news_article_category : classifies
    news_story_cluster ||--o{ news_story_cluster_article : groups
    asset ||--o{ news_article_asset : mentioned
    social_source ||--o{ social_post : publishes
    social_post ||--o{ social_post_asset_mention : mentions
    asset ||--o{ sentiment_observation : observed
    asset ||--o{ ticker_sentiment_daily : aggregates
    signal_definition ||--o{ signal_evaluation : evaluates

    news_article {
      BIGINT article_id PK
      BIGINT provider_id FK
      TEXT headline
      TEXT canonical_url
      TIMESTAMP published_at
      DOUBLE importance_score
    }
    social_post {
      BIGINT post_id PK
      BIGINT source_id FK
      TEXT provider_post_id
      TIMESTAMP published_at
    }
    ticker_sentiment_daily {
      TEXT asset_id FK
      DATE date
      DOUBLE blended_sentiment_score
      INTEGER article_count
    }
```

Source of truth: normalized news and social posts feed daily sentiment/factor snapshots. Raw
provider payloads are for debugging/reprocessing, not direct UI display.

## Broker schema

```mermaid
erDiagram
    broker_user ||--o{ broker_connection : owns
    broker_connection ||--o{ broker_account : has
    broker_account ||--o{ broker_position_snapshot : snapshots
    broker_account ||--o{ broker_transaction : records
    broker_account ||--o{ broker_portfolio_position_map : maps
    portfolio ||--o{ broker_portfolio_txn_map : imports
    txn ||--o{ broker_portfolio_txn_map : projected
    broker_sync_run ||--o{ broker_connection : updates

    broker_user {
      TEXT provider
      TEXT user_key
      TEXT provider_user_id
      TEXT encrypted_user_secret
      TEXT status
    }
    broker_account {
      TEXT provider_account_id PK
      TEXT account_name
      TEXT account_type
      DOUBLE balance
      BIGINT portfolio_id FK
    }
    broker_transaction {
      TEXT provider_transaction_id PK
      TEXT provider_account_id FK
      TEXT transaction_type
      DATE trade_date
      TEXT asset_id
    }
```

Source of truth: broker tables mirror read-only provider data. Local portfolio transactions become
authoritative only after explicit mapped import into `txn`.

## Benchmark schema

```mermaid
erDiagram
    benchmark_index ||--o{ benchmark_index_symbol : has
    benchmark_index ||--o{ benchmark_index_daily_price : prices
    benchmark_index ||--o{ benchmark_index_intraday_price : intraday
    benchmark_index ||--o{ benchmark_index_composition_snapshot : snapshots
    benchmark_index_composition_snapshot ||--o{ benchmark_index_constituent : contains
    benchmark_index_composition_snapshot ||--o{ benchmark_index_exposure_snapshot : summarizes
    benchmark_index ||--o{ benchmark_index_daily_metric : metrics
    benchmark_index ||--o{ benchmark_index_relative_metric : relative
    benchmark_index ||--o{ benchmark_index_financial_metric : financials
    benchmark_index ||--o{ benchmark_index_sync_state : syncs

    benchmark_index {
      TEXT index_id PK
      TEXT index_name
      TEXT index_category
      TEXT currency
      BOOLEAN is_core
    }
    benchmark_index_symbol {
      TEXT index_id FK
      TEXT provider
      TEXT provider_symbol
      TEXT symbol_purpose
      BOOLEAN is_proxy
    }
    benchmark_index_sync_state {
      TEXT index_id FK
      TEXT job_type
      DATE last_success_date
      TEXT last_error
    }
```

Source of truth: benchmark universe and provider symbols live in `benchmark_index` and
`benchmark_index_symbol`; prices, composition, exposure, metrics, and sync-state tables are derived
or ingested facts.

## Deterministic Candidate-Run Schema

```mermaid
erDiagram
    candidate_run ||--o{ candidate_source_watermark : records
    candidate_run ||--o{ candidate_review : contains
    candidate_review ||--o{ candidate_review_reason : explains
    candidate_review ||--o{ candidate_source_match : traces
    candidate_review ||--o{ candidate_evidence : supports
    candidate_review ||--o{ candidate_missing_metric : reports
    candidate_review ||--o{ candidate_warning : reports

    candidate_run {
      TEXT run_id PK
      BIGINT portfolio_id
      TEXT policy_version
      TEXT status
      TIMESTAMP created_at
    }
    candidate_review {
      TEXT run_id FK
      TEXT asset_id
      TEXT review_state
      DOUBLE score
    }
    candidate_evidence {
      TEXT run_id FK
      TEXT asset_id
      TEXT metric_key
      TEXT source_name
      DOUBLE numeric_value
    }
```

Source of truth: these tables persist deterministic outside-holding research runs, source
watermarks, evidence, missing metrics, and warnings. They do not represent recommendations,
suitability decisions, orders, or LLM output. See the [candidate engine guide](../../features/candidate-engine.md).

## Known schema gaps

- `fx_rate` exists, but provider ingestion for dated FX rates is not implemented.
- Business-strength tables are present in `business_strength.sql` and are documented separately in
  `docs/features/business-strength.md`.
- Historical SVG ER diagrams under `docs/archive/diagrams/database/` may lag the current schema.
  Prefer this document for the live schema.
