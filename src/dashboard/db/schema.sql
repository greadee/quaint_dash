--~/db/ 
-- DuckDB schema for investment dashboard defined by:
    -- transactions (Txn) are the only source of truth (append-only ledger)
    -- positions and cash are derived from the ledger.
    -- portfolio and asset tables for non-transaction derived data. 

BEGIN TRANSACTION;

-- 
CREATE TABLE IF NOT EXISTS portfolio (
    portfolio_id BIGINT PRIMARY KEY,
    portfolio_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT now(), 
    updated_at TIMESTAMP DEFAULT now(),
    base_ccy TEXT DEFAULT 'CAD'
);

CREATE TABLE IF NOT EXISTS asset (
    asset_id TEXT PRIMARY KEY, 
    asset_type TEXT NOT NULL,
    asset_subtype TEXT NOT NULL, 
    ccy TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS position ( 
    portfolio_id BIGINT, 
    asset_id TEXT, 
    qty DOUBLE PRECISION NOT NULL, 
    book_cost DOUBLE PRECISION NOT NULL,
    last_updated TIMESTAMP NOT NULL,

    PRIMARY KEY (portfolio_id, asset_id) 
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
    FOREIGN KEY (asset_id) REFERENCES asset(asset_id),
    FOREIGN KEY (batch_id) REFERENCES import_batch(batch_id)
);

--CREATE INDEX IF NOT EXISTS portfolioTxn_by_time ON txn(portfolio_id, time_stamp);
CREATE INDEX IF NOT EXISTS portolioTxn_by_asset ON txn(portfolio_id, asset_id);

COMMIT; 