-- DuckDB schema for investment dashboard defined by:
    -- transactions are the ONLY source of truth (append-only ledger)
    -- positions and cash (and in turn, portfolios) are DERIVED from the ledger via views
    -- "state tables" exist only as caches (portfolio, position)

-- Design: 
    -- Minimal schema: portfolio, asset, transaction, position
    -- Portfolios consist of cash, or asset positions. 
    -- Asset positions are aggregated transactions over (asset_id | portfolio_id)
    -- Cash positions are aggregated transactions over portfolio_id.
    -- Positions are computed ON DEMAND.


BEGIN TRANSACTION; -- all or nothing 

-- Derived Tables
CREATE TABLE IF NOT EXISTS portfolio (
    portfolio_id TEXT PRIMARY KEY,
    base_ccy TEXT NOT NULL DEFAULT 'CAD',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS asset (
    asset_id TEXT PRIMARY KEY, 
    asset_type TEXT NOT NULL,
    ccy TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE SEQUENCE IF NOT EXISTS seq_txn_id;

-- Append-only transaction table
CREATE TABLE IF NOT EXISTS txn (
    txn_id BIGINT PRIMARY KEY DEFAULT nextval('seq_txn_id')
    portfolio_id TEXT NOT NULL, 
    time_stamp TIMESTAMP NOT NULL DEFAULT NOW()

    -- for asset transactions, nullible.
    asset_id TEXT,
    qty DOUBLE PRECISION,
    price DOUBLE PRECISION,
    
    -- cash data per transaction needed for assets too.
    txn_ccy TEXT,
    cash_amt DOUBLE PRECISION NOT NULL,
    fee_amt DOUBLE PRECISION NOT NULL DEFAULT 0.0,

    -- transaction metadata 
    external_ref TEXT NOT NULL, 
    notes TEXT, 

    FOREIGN KEY (portfolio_id) REFERENCES portfolio(portfolio_id),
    FOREIGN KEY (asset_id) REFERENCES asset(asset_id)
);

CREATE INDEX IF NOT EXISTS portfolioTxn_by_time ON txn(portfolio_id, time_stamp);
CREATE INDEX IF NOT EXISTS portolioTxn_by_asset ON txn(portfolio_id, asset_id);

-- Ledger process inserts transactions in batches to the database.
    -- Reset portfolio state to as of some batch
CREATE TABLE IF NOT EXISTS txn_batch (
    batch_id BIGINT PRIMARY KEY, 
    portfolio_id TEXT NOT NULL, 
    appended_from TIMESTAMP NOT NULL, 
    appended_to TIMESTAMP NOT NULL, 

    FOREIGN KEY (portfolio_id) REFERENCES portfolio(portfolio_id),
);

-- Derived views (snapshot) for faster querying of volatile metrics

-- quantity of the asset making up a position
CREATE OR REPLACE VIEW positionQty_view AS 
SELECT
    t.portfoli_id, t.asset_id, 
    SUM(
        CASE 
            WHEN t.txn_type = 'BUY' THEN COALESCE(t.qty, 0)
            WHEN t.txn_type = 'SELL' THEN -COALESCE(t.qty, 0)
            ELSE 0
        END
    ) 
AS quantity FROM txn t 
WHERE t.asset_id IS NOT NULL 
GROUP BY t.portfolio_id, t.asset_id;

-- total cash balance of a single portfolio
CREATE OR REPLACE VIEW cashBal_view AS 
SELECT 
    t.portfolio_d, t.asset_id, t.cash_amt
FROM txn t 
GROUP BY t.portfolio_id, t.asset_id;

-- total asset + cash balance of a single portfolio
CREATE OR REPLACE VIEW portfolioFlows_view AS 
SELECT 
    t.portfolio_id, DATE_TRUNC('day', t.time_stamp) AS some_day, 
    SUM(CASE WHEN t.txn_type IN ('CONTRIBUTION') THEN t.cash_amt ELSE 0 END) AS contributions, 
    SUM(CASE WHEN t.txn_type IN ('WITHDRAWAL') THEN t.cash_amt ELSE 0 END) AS withdrawals,
    SUM(CASE WHEN t.txn_type IN ('DIVIDEND', 'INTEREST') THEN t.cash_amt ELSE 0 END) AS income,
    SUM(CASE WHEN t.txn_type IN ('FEE', 'TAX') THEN t.cash_amt ELSE 0 END) AS expenses,
FROM txn t 
GROUP BY t.portfolio_id, some_day; 

COMMIT; -- EO