# tests/fixtures_websocket.py

from __future__ import annotations

import duckdb
import pytest


LIVE_PRICE_TEST_SCHEMA = """
CREATE TABLE IF NOT EXISTS asset (
    asset_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    exchange_code TEXT
);

CREATE TABLE IF NOT EXISTS position (
    position_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    quantity DOUBLE NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist_asset (
    watchlist_asset_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    is_active BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS live_price_tick (
    tick_id TEXT DEFAULT CAST(random() AS TEXT),
    asset_id TEXT,
    symbol TEXT NOT NULL,

    provider TEXT NOT NULL,
    market_session TEXT NOT NULL,

    price DOUBLE NOT NULL,
    volume DOUBLE,
    bid DOUBLE,
    ask DOUBLE,

    trade_ts_utc TIMESTAMP,
    received_at TIMESTAMP NOT NULL DEFAULT now(),

    raw_json JSON,

    PRIMARY KEY (tick_id)
);

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
    status TEXT NOT NULL,
    last_success_at TIMESTAMP,
    last_error_at TIMESTAMP,
    last_error_message TEXT,
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS trading_calendar (
    market_code TEXT NOT NULL,
    session_date DATE NOT NULL,
    is_open BOOLEAN NOT NULL,
    open_time_utc TIMESTAMP,
    close_time_utc TIMESTAMP,

    PRIMARY KEY (market_code, session_date)
);
"""


def create_live_price_tables(conn) -> None:
    """
    Create all live-price/websocket tables needed by live streaming tests.

    This is a plain helper so the root conftest.py can compose it with other
    schema setup helpers.
    """
    conn.execute(LIVE_PRICE_TEST_SCHEMA)


@pytest.fixture()
def websocket_conn():
    """
    Standalone connection for websocket/live-price-only tests.

    Most tests should use the shared root `conn` fixture from conftest.py.
    This is only here if a test specifically wants an isolated websocket schema.
    """
    connection = duckdb.connect(":memory:")
    create_live_price_tables(connection)

    yield connection

    connection.close()


@pytest.fixture()
def seeded_assets(conn):
    """
    Seed assets for live price subscription and worker-routing tests.

    AAPL and MSFT are portfolio holdings.
    NVDA is watchlist only.
    CASH has zero quantity and should not stream.
    """
    conn.execute(
        """
        INSERT OR REPLACE INTO asset(asset_id, symbol, exchange_code)
        VALUES
            ('AAPL', 'AAPL', 'XNYS'),
            ('MSFT', 'MSFT', 'XNAS'),
            ('NVDA', 'NVDA', 'XNAS'),
            ('CASH', 'CASH', NULL);
        """
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO position(position_id, portfolio_id, asset_id, quantity)
        VALUES
            ('pos-aapl', 'p1', 'AAPL', 10),
            ('pos-msft', 'p1', 'MSFT', 5),
            ('pos-cash', 'p1', 'CASH', 0);
        """
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO watchlist_asset(watchlist_asset_id, asset_id, is_active)
        VALUES
            ('wl-nvda', 'NVDA', TRUE),
            ('wl-aapl', 'AAPL', TRUE);
        """
    )

    return conn