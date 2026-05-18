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
    asset_type TEXT,
    asset_subtype TEXT,
    ccy TEXT NOT NULL,
    name TEXT,

    -- for tickers 
    sector TEXT, 
    industry TEXT,
    country TEXT, 
    region TEXT, 
    size TEXT, -- large, mid, small, micro
    mkt_cap DOUBLE PRECISION,
    market_beta DOUBLE PRECISION,

    track BOOLEAN NOT NULL DEFAULT TRUE, -- untracked assets can just sit idle for now
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
);

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


-------------------------------
-- ingestion domain b
-------------------------------


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

COMMIT; 