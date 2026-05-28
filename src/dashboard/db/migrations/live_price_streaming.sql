CREATE TABLE IF NOT EXISTS live_price_stream_config (
    config_key TEXT PRIMARY KEY,
    config_value TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

INSERT OR IGNORE INTO live_price_stream_config(config_key, config_value)
VALUES
    ('stream_portfolio_assets', 'true'),
    ('stream_watchlist_assets', 'false'),
    ('enable_extended_hours', 'true'),
    ('extended_hours_provider', 'fmp'),
    ('regular_hours_provider', 'finnhub'),
    ('gap_repair_provider', 'yfinance'),
    ('fmp_extended_poll_seconds', '60'),
    ('raw_tick_retention_days', '7');

CREATE TABLE IF NOT EXISTS live_price_subscription_snapshot (
    snapshot_id UUID DEFAULT uuid(),
    asset_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange_code TEXT,
    source_scope TEXT NOT NULL,       -- portfolio, watchlist
    subscribed_at TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (snapshot_id)
);

CREATE INDEX IF NOT EXISTS live_price_subscription_symbol_idx
ON live_price_subscription_snapshot(symbol);

CREATE TABLE IF NOT EXISTS live_price_tick (
    tick_id UUID DEFAULT uuid(),
    asset_id TEXT,
    symbol TEXT NOT NULL,

    provider TEXT NOT NULL,           -- finnhub, fmp, yfinance
    market_session TEXT NOT NULL,     -- pre, regular, after, closed, unknown

    price DOUBLE NOT NULL,
    volume DOUBLE,
    bid DOUBLE,
    ask DOUBLE,

    trade_ts_utc TIMESTAMP,
    received_at TIMESTAMP NOT NULL DEFAULT now(),

    raw_json JSON,

    PRIMARY KEY (tick_id)
);

CREATE INDEX IF NOT EXISTS live_price_tick_symbol_received_idx
ON live_price_tick(symbol, received_at);

CREATE TABLE IF NOT EXISTS current_asset_price (
    asset_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,

    price DOUBLE NOT NULL,
    volume DOUBLE,
    bid DOUBLE,
    ask DOUBLE,

    provider TEXT NOT NULL,
    market_session TEXT NOT NULL,

    trade_ts_utc TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT now(),

    raw_json JSON
);

CREATE TABLE IF NOT EXISTS live_price_provider_health (
    provider TEXT PRIMARY KEY,
    status TEXT NOT NULL,             -- healthy, degraded, down
    last_success_at TIMESTAMP,
    last_error_at TIMESTAMP,
    last_error_message TEXT,
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);