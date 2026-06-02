--~/db/ 
-- DuckDB schema for investment dashboard defined by:
    -- transactions (Txn) are the only source of truth (append-only ledger)
    -- positions and cash are derived from the ledger.
    -- portfolio and asset tables for non-transaction derived data. 
    -- ingestion domain A: daily quotes, dividends, splits, ingestion jobs and sync state
    -- ingestion domain B: fundamentals seperate (later)

BEGIN TRANSACTION;

-- 
CREATE TABLE IF NOT EXISTS portfolio (
    portfolio_id BIGINT PRIMARY KEY,
    portfolio_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT now(), 
    updated_at TIMESTAMP DEFAULT now(),
    base_ccy TEXT DEFAULT 'CAD'
);

CREATE TABLE IF NOT EXISTS position ( 
    portfolio_id BIGINT, 
    asset_id TEXT, 
    qty DOUBLE PRECISION NOT NULL, 
    book_cost DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,

    PRIMARY KEY (portfolio_id, asset_id) 
);

CREATE TABLE IF NOT EXISTS asset (
    asset_id TEXT PRIMARY KEY, 
    symbol TEXT,
    exchange_code TEXT,
    asset_type TEXT,
    asset_subtype TEXT,
    ccy TEXT NOT NULL,
    name TEXT,
    description TEXT,

    -- for tickers 
    sector TEXT, 
    industry TEXT,
    country TEXT, 
    region TEXT, 
    size TEXT, -- large, mid, small, micro
    mkt_cap DOUBLE PRECISION,
    shares_outstanding DOUBLE PRECISION,
    market_beta DOUBLE PRECISION,

    track BOOLEAN NOT NULL DEFAULT TRUE, -- untracked assets can just sit idle for now
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
);

ALTER TABLE asset ADD COLUMN IF NOT EXISTS symbol TEXT;
ALTER TABLE asset ADD COLUMN IF NOT EXISTS exchange_code TEXT;
ALTER TABLE asset ADD COLUMN IF NOT EXISTS asset_subtype TEXT;
ALTER TABLE asset ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE asset ADD COLUMN IF NOT EXISTS shares_outstanding DOUBLE PRECISION;

UPDATE asset
SET symbol = asset_id
WHERE symbol IS NULL;

CREATE TABLE IF NOT EXISTS portfolio_ticker (
    portfolio_id BIGINT NOT NULL,
    asset_id TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    source TEXT NOT NULL DEFAULT 'position',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (portfolio_id, asset_id),
    FOREIGN KEY (portfolio_id) REFERENCES portfolio(portfolio_id),
    FOREIGN KEY (asset_id) REFERENCES asset(asset_id)
);

CREATE TABLE IF NOT EXISTS watchlist_ticker (
    asset_id TEXT PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),

    FOREIGN KEY (asset_id) REFERENCES asset(asset_id)
);

INSERT INTO portfolio_ticker (
    portfolio_id,
    asset_id,
    is_active,
    source,
    created_at,
    updated_at
)
SELECT DISTINCT
    portfolio_id,
    asset_id,
    TRUE,
    'position',
    now(),
    now()
FROM position
WHERE asset_id IS NOT NULL
  AND COALESCE(qty, 0) <> 0
ON CONFLICT (portfolio_id, asset_id)
DO UPDATE SET
    is_active = TRUE,
    updated_at = now();

CREATE TABLE IF NOT EXISTS asset_metadata_sync (
    asset_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'fmp',
    sync_status TEXT NOT NULL DEFAULT 'pending', -- pending, running, synced, failed, stale
    last_attempted_at TIMESTAMP,
    last_succeeded_at TIMESTAMP,
    next_retry_at TIMESTAMP,
    attempt_count BIGINT NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),

    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

CREATE SEQUENCE IF NOT EXISTS seq_batch_id;

CREATE TABLE IF NOT EXISTS import_batch (
    batch_id BIGINT PRIMARY KEY DEFAULT nextval('seq_batch_id'), 
    batch_type TEXT NOT NULL, -- manual-entry, csv-import, broker-ingest
    import_time TIMESTAMP NOT NULL DEFAULT NOW(),
);

CREATE SEQUENCE IF NOT EXISTS seq_txn_id;

-- Append-only
CREATE TABLE IF NOT EXISTS txn (
    txn_id BIGINT PRIMARY KEY DEFAULT nextval('seq_txn_id'),
    portfolio_id BIGINT NOT NULL, 
    time_stamp TIMESTAMP NOT NULL DEFAULT NOW(),
    txn_type TEXT NOT NULL,

    -- for asset transactions
    asset_id TEXT,              
    qty DOUBLE PRECISION,
    price DOUBLE PRECISION,
    
    -- cash data per transaction needed for assets too.
    ccy TEXT,
    cash_amt DOUBLE PRECISION,
    fee_amt DOUBLE PRECISION DEFAULT 0.0,

    batch_id BIGINT NOT NULL,

    FOREIGN KEY (portfolio_id) REFERENCES portfolio(portfolio_id),
    FOREIGN KEY (asset_id) REFERENCES asset(asset_id), -- no constraint if cash transaction
    FOREIGN KEY (batch_id) REFERENCES import_batch(batch_id)
);


--CREATE INDEX IF NOT EXISTS portfolioTxn_by_time ON txn(portfolio_id, time_stamp);
CREATE INDEX IF NOT EXISTS portolioTxn_by_asset ON txn(portfolio_id, asset_id);

--------------------------
--      ingestion domain a
-------------------------

-- Main source of asset truth for intraday
-- Ingestion via Websocket streaming for intraday quotes
CREATE TABLE IF NOT EXISTS asset_quote_intraday (
    asset_id TEXT NOT NULL, 
    time_stamp TIMESTAMP NOT NULL, -- round to minute
    price DOUBLE PRECISION, 
    volume BIGINT, 

    ing_source TEXT NOT NULL, 
    ing_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (asset_id, time_stamp),
    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

-- Main source of asset truth for >day
    -- 10y backfill if possible
-- daily ingestion of daily bar via FMP REST API
CREATE TABLE IF NOT EXISTS asset_quote_daily (
    asset_id TEXT NOT NULL, 
    date DATE NOT NULL,
    open DOUBLE PRECISION, 
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    adj_close DOUBLE PRECISION,
    volume BIGINT, 

    ing_source TEXT NOT NULL, 
    ing_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (asset_id, date),
    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

CREATE TABLE IF NOT EXISTS dividend_event (
    asset_id TEXT NOT NULL,
    ex_date DATE NOT NULL,
    payment_date DATE,
    record_date DATE,
    declaration_date DATE,
    dividend_per_share DOUBLE PRECISION,
    currency TEXT,
    source TEXT NOT NULL DEFAULT 'fmp',
    as_of_ts TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (asset_id, ex_date),
    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

CREATE TABLE IF NOT EXISTS split_event (
    asset_id TEXT NOT NULL,
    ex_date DATE NOT NULL,
    split_from BIGINT,
    split_to BIGINT,
    source TEXT NOT NULL DEFAULT 'fmp',
    as_of_ts TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (asset_id, ex_date),
    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

----------------------------------
-- ingestion domain a jobs 
----------------------------------

CREATE SEQUENCE IF NOT EXISTS seq_ingestion_job_id START 1;

CREATE TABLE IF NOT EXISTS ingestion_job (
    job_id BIGINT PRIMARY KEY DEFAULT nextval('seq_ingestion_job_id'),

    asset_id TEXT NOT NULL,
    domain TEXT NOT NULL,              -- market, fundamentals
    job_type TEXT NOT NULL,            -- backfill, refresh
    dataset TEXT NOT NULL,             -- price_daily, dividends, splits

    status TEXT NOT NULL DEFAULT 'pending', -- pending, running, done, failed
    priority INTEGER NOT NULL DEFAULT 0,

    requested_start_date DATE,
    requested_end_date DATE,

    attempt_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),

    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

CREATE INDEX IF NOT EXISTS ingestion_job_pending_idx
ON ingestion_job(domain, status, priority, created_at);

CREATE TABLE IF NOT EXISTS asset_sync_state (
    asset_id TEXT NOT NULL,
    domain TEXT NOT NULL,              -- market, fundamentals
    dataset TEXT NOT NULL,             -- price_daily, dividends, splits

    backfill_status TEXT NOT NULL DEFAULT 'not_started',
    backfill_start_date DATE,
    backfill_end_date DATE,

    last_successful_date DATE,
    last_attempted_at TIMESTAMP,
    last_successful_at TIMESTAMP,
    last_error TEXT,

    needs_repair BOOLEAN NOT NULL DEFAULT FALSE,

    PRIMARY KEY (asset_id, domain, dataset),
    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);


------------------------------
-- trading day calendar
------------------------------

CREATE TABLE IF NOT EXISTS trading_calendar (
    market_code TEXT NOT NULL,        -- US, CAN
    exchange_code TEXT NOT NULL,      -- XNYS, XTSE
    session_date DATE NOT NULL,

    is_open BOOLEAN NOT NULL,
    is_half_day BOOLEAN NOT NULL DEFAULT FALSE,

    open_time_utc TIMESTAMP,
    close_time_utc TIMESTAMP,

    open_time_local TEXT,
    close_time_local TEXT,
    timezone TEXT NOT NULL,

    holiday_name TEXT,
    source TEXT NOT NULL,             -- pandas_market_calendars
    source_version TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (market_code, session_date)
);

CREATE INDEX IF NOT EXISTS trading_calendar_date_idx
ON trading_calendar(session_date);

CREATE TABLE IF NOT EXISTS trading_calendar_sync_state (
    market_code TEXT PRIMARY KEY,
    exchange_code TEXT NOT NULL,
    source TEXT NOT NULL,

    last_start_date DATE,
    last_end_date DATE,
    last_attempted_at TIMESTAMP,
    last_succeeded_at TIMESTAMP,

    sync_status TEXT NOT NULL DEFAULT 'pending', -- pending, running, synced, failed, stale
    attempt_count BIGINT NOT NULL DEFAULT 0,
    last_error TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

-------------------------------
-- ingestion domain b
-------------------------------

CREATE TABLE IF NOT EXISTS earnings_calendar_event (
    asset_id TEXT NOT NULL,
    earnings_date DATE NOT NULL,

    fiscal_year INTEGER,
    fiscal_quarter INTEGER,

    time TEXT,

    eps_estimated DOUBLE,
    eps_actual DOUBLE,
    revenue_estimated DOUBLE,
    revenue_actual DOUBLE,

    source TEXT NOT NULL DEFAULT 'fmp',
    as_of_ts TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (asset_id, earnings_date),
    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

CREATE TABLE IF NOT EXISTS corporate_event (
    asset_id TEXT NOT NULL,
    event_type TEXT NOT NULL, -- 'earnings', 'split', 'dividend', etc.
    event_time_utc TIMESTAMP NOT NULL, -- event timestamp in UTC
    event_time_local TIMESTAMP, -- event timestamp in local time -- needs setting 
    exchange_tz TEXT, -- timezone that the ingested data is coming in 

    -- event metadata
    year INTEGER NOT NULL, 
    quarter INTEGER NOT NULL,
    confirmed BOOLEAN,
    description TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    source TEXT NOT NULL,         -- 'finnhub', 'fmp'

    PRIMARY KEY(asset_id, event_type, event_time_utc),
    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

-- duckdb supports JSON type
CREATE TABLE IF NOT EXISTS financial_statement (
    asset_id TEXT NOT NULL,
    statement_type TEXT NOT NULL, -- 'income', 'balance', 'cashflow', 'equity'
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL,
    period_end_date DATE, -- specific to finnhub/FMP
    report_date DATE, 

    data_json JSON, -- the financial statement

    source TEXT NOT NULL,
    ingested_at_utc TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY(asset_id, statement_type, year, quarter),
    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);


-- default ingestion run log

CREATE TABLE IF NOT EXISTS ingestion_run (
    run_id BIGINT PRIMARY KEY,
    job_name TEXT NOT NULL,        
    started_at TIMESTAMP NOT NULL DEFAULT now(),
    ended_at TIMESTAMP,
    status TEXT NOT NULL, -- 'success', 'failed', 'partial', 'skipped'
    rows_written BIGINT NOT NULL DEFAULT 0,
    source TEXT, -- 'finnhub', 'fmp'
);






CREATE TABLE IF NOT EXISTS fundamental_subscription (
    asset_id TEXT PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    refresh_interval_days INTEGER NOT NULL DEFAULT 7,
    next_refresh_at TIMESTAMP NOT NULL DEFAULT now(),

    last_refresh_attempted_at TIMESTAMP,
    last_refresh_succeeded_at TIMESTAMP,
    last_backfill_requested_at TIMESTAMP,
    last_backfill_succeeded_at TIMESTAMP,

    subscription_source TEXT NOT NULL DEFAULT 'manual',

    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),

    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

ALTER TABLE fundamental_subscription
ADD COLUMN IF NOT EXISTS last_backfill_requested_at TIMESTAMP;

ALTER TABLE fundamental_subscription
ADD COLUMN IF NOT EXISTS last_backfill_succeeded_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS fundamental_sync_state (
    asset_id TEXT NOT NULL,
    dataset VARCHAR NOT NULL,
    sync_mode VARCHAR NOT NULL,

    status VARCHAR NOT NULL,
    last_attempted_at TIMESTAMP,
    last_succeeded_at TIMESTAMP,
    error_message VARCHAR,
    source VARCHAR,

    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (asset_id, dataset, sync_mode)
);

CREATE INDEX IF NOT EXISTS idx_fundamental_subscription_due
ON fundamental_subscription (is_active, next_refresh_at);

CREATE INDEX IF NOT EXISTS idx_fundamental_sync_state_asset
ON fundamental_sync_state (asset_id);

-------------------------------
-- ingestion domain c: sentiment
-------------------------------

CREATE SEQUENCE IF NOT EXISTS seq_news_source_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_news_article_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_social_source_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_social_post_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_sentiment_observation_id START 1;

CREATE TABLE IF NOT EXISTS news_source (
    source_id BIGINT PRIMARY KEY DEFAULT nextval('seq_news_source_id'),
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    base_url TEXT,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS news_article (
    article_id BIGINT PRIMARY KEY DEFAULT nextval('seq_news_article_id'),
    source_item_id TEXT,
    source_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    url TEXT,
    author TEXT,
    published_at TIMESTAMP,
    fetched_at TIMESTAMP NOT NULL DEFAULT now(),
    raw_payload_json TEXT,
    content_hash TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE(provider, source_item_id),
    UNIQUE(content_hash)
);

CREATE TABLE IF NOT EXISTS news_article_asset_mention (
    article_id BIGINT NOT NULL,
    asset_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    relevance_score DOUBLE NOT NULL DEFAULT 1.0,
    mention_reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (article_id, asset_id),
    FOREIGN KEY(article_id) REFERENCES news_article(article_id),
    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

CREATE TABLE IF NOT EXISTS social_source (
    social_source_id BIGINT PRIMARY KEY DEFAULT nextval('seq_social_source_id'),
    source_name TEXT NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS social_post (
    post_id BIGINT PRIMARY KEY DEFAULT nextval('seq_social_post_id'),
    provider TEXT NOT NULL,
    source_post_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    author TEXT,
    title TEXT,
    body TEXT,
    url TEXT,
    published_at TIMESTAMP,
    fetched_at TIMESTAMP NOT NULL DEFAULT now(),
    score INTEGER,
    comment_count INTEGER,
    like_count INTEGER,
    repost_count INTEGER,
    reply_count INTEGER,
    raw_payload_json TEXT,
    content_hash TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE(provider, source_post_id)
);

CREATE TABLE IF NOT EXISTS social_post_asset_mention (
    post_id BIGINT NOT NULL,
    asset_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    relevance_score DOUBLE NOT NULL DEFAULT 1.0,
    mention_reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (post_id, asset_id),
    FOREIGN KEY(post_id) REFERENCES social_post(post_id),
    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

CREATE TABLE IF NOT EXISTS sentiment_observation (
    observation_id BIGINT PRIMARY KEY DEFAULT nextval('seq_sentiment_observation_id'),
    asset_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    item_type TEXT NOT NULL,
    item_id BIGINT NOT NULL,
    provider TEXT NOT NULL,
    sentiment_label TEXT NOT NULL,
    sentiment_score DOUBLE NOT NULL,
    confidence DOUBLE NOT NULL DEFAULT 0.5,
    relevance_score DOUBLE NOT NULL DEFAULT 1.0,
    source_weight DOUBLE NOT NULL DEFAULT 1.0,
    engagement_weight DOUBLE NOT NULL DEFAULT 1.0,
    explanation TEXT,
    observed_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

CREATE TABLE IF NOT EXISTS ticker_sentiment_daily (
    asset_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    date DATE NOT NULL,
    retail_sentiment_score DOUBLE,
    news_sentiment_score DOUBLE,
    analyst_sentiment_score DOUBLE,
    blended_sentiment_score DOUBLE,
    reddit_post_count INTEGER NOT NULL DEFAULT 0,
    x_post_count INTEGER NOT NULL DEFAULT 0,
    article_count INTEGER NOT NULL DEFAULT 0,
    bullish_count INTEGER NOT NULL DEFAULT 0,
    neutral_count INTEGER NOT NULL DEFAULT 0,
    bearish_count INTEGER NOT NULL DEFAULT 0,
    sentiment_momentum_1d DOUBLE,
    sentiment_momentum_7d DOUBLE,
    sentiment_momentum_30d DOUBLE,
    unusual_volume_flag BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, date),
    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

CREATE TABLE IF NOT EXISTS ticker_news_daily (
    asset_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    date DATE NOT NULL,
    article_count INTEGER NOT NULL DEFAULT 0,
    high_relevance_article_count INTEGER NOT NULL DEFAULT 0,
    bullish_article_count INTEGER NOT NULL DEFAULT 0,
    bearish_article_count INTEGER NOT NULL DEFAULT 0,
    neutral_article_count INTEGER NOT NULL DEFAULT 0,
    top_article_ids_json TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, date),
    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

CREATE TABLE IF NOT EXISTS ticker_factor_snapshot (
    asset_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    snapshot_date DATE NOT NULL,
    growth_score DOUBLE,
    value_score DOUBLE,
    quality_score DOUBLE,
    momentum_score DOUBLE,
    defensive_score DOUBLE,
    dividend_score DOUBLE,
    volatility_score DOUBLE,
    revision_score DOUBLE,
    overall_factor_score DOUBLE,
    factor_labels_json TEXT,
    explanation TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, snapshot_date),
    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

CREATE TABLE IF NOT EXISTS ticker_quant_rating_snapshot (
    asset_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    snapshot_date DATE NOT NULL,
    overall_quant_score DOUBLE,
    overall_quant_rating TEXT,
    growth_rating TEXT,
    value_rating TEXT,
    quality_rating TEXT,
    momentum_rating TEXT,
    defensive_rating TEXT,
    dividend_rating TEXT,
    volatility_rating TEXT,
    factor_profile TEXT,
    explanation TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, snapshot_date),
    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

CREATE TABLE IF NOT EXISTS sentiment_ingestion_state (
    source_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    universe_type TEXT NOT NULL,
    last_attempted_at TIMESTAMP,
    last_succeeded_at TIMESTAMP,
    last_cursor TEXT,
    sync_status TEXT,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (source_name, provider, universe_type)
);

CREATE INDEX IF NOT EXISTS sentiment_observation_asset_date_idx
ON sentiment_observation(asset_id, observed_at);

CREATE INDEX IF NOT EXISTS news_article_published_idx
ON news_article(published_at);

CREATE INDEX IF NOT EXISTS social_post_published_idx
ON social_post(published_at);

COMMIT; 
