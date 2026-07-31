from __future__ import annotations

import duckdb

from dashboard.ingestion.ticker_universe import TickerUniverseRepository


def make_new_universe_conn():
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE asset (
            asset_id TEXT PRIMARY KEY,
            symbol TEXT,
            exchange_code TEXT,
            asset_type TEXT,
            track BOOLEAN DEFAULT TRUE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE position (
            portfolio_id BIGINT,
            asset_id TEXT,
            qty DOUBLE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE portfolio_ticker (
            portfolio_id BIGINT,
            asset_id TEXT,
            is_active BOOLEAN,
            source TEXT,
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now(),
            PRIMARY KEY(portfolio_id, asset_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE watchlist_ticker (
            asset_id TEXT PRIMARY KEY,
            is_active BOOLEAN,
            source TEXT,
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now()
        )
        """
    )
    conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, exchange_code, asset_type, track)
        VALUES
            ('AAPL', 'AAPL', 'XNAS', 'stock', TRUE),
            ('MSFT', NULL, 'XNAS', 'stock', TRUE),
            ('SPY', 'SPY', 'ARCX', 'etf', TRUE),
            ('CASH', 'CASH', NULL, 'cash', TRUE),
            ('OLD', 'OLD', 'XNYS', 'stock', TRUE)
        """
    )
    return conn


def test_portfolio_and_watchlist_tables_are_source_of_truth_when_present():
    conn = make_new_universe_conn()
    conn.execute(
        """
        INSERT INTO position(portfolio_id, asset_id, qty)
        VALUES (1, 'OLD', 10)
        """
    )
    conn.execute(
        """
        INSERT INTO portfolio_ticker(portfolio_id, asset_id, is_active, source)
        VALUES
            (1, 'AAPL', TRUE, 'position'),
            (1, 'OLD', FALSE, 'position')
        """
    )
    conn.execute(
        """
        INSERT INTO watchlist_ticker(asset_id, is_active, source)
        VALUES
            ('MSFT', TRUE, 'manual'),
            ('SPY', FALSE, 'manual')
        """
    )

    repo = TickerUniverseRepository(conn)

    assert repo.portfolio_asset_ids() == ["AAPL"]
    assert repo.watchlist_asset_ids() == ["MSFT"]
    assert repo.ingestible_asset_ids() == ["AAPL", "MSFT"]


def test_ingestible_asset_ids_filters_asset_types_after_deduping_sources():
    conn = make_new_universe_conn()
    conn.execute(
        """
        INSERT INTO portfolio_ticker(portfolio_id, asset_id, is_active, source)
        VALUES
            (1, 'AAPL', TRUE, 'position'),
            (1, 'SPY', TRUE, 'position')
        """
    )
    conn.execute(
        """
        INSERT INTO watchlist_ticker(asset_id, is_active, source)
        VALUES ('MSFT', TRUE, 'manual')
        """
    )

    repo = TickerUniverseRepository(conn)

    assert repo.ingestible_asset_ids(asset_types=("stock",)) == ["AAPL", "MSFT"]
    assert repo.ingestible_asset_ids(include_watchlist=False) == ["AAPL", "SPY"]


def test_stream_subscriptions_dedupe_by_symbol_and_portfolio_wins_over_watchlist():
    conn = make_new_universe_conn()
    conn.execute(
        """
        INSERT INTO portfolio_ticker(portfolio_id, asset_id, is_active, source)
        VALUES (1, 'AAPL', TRUE, 'position')
        """
    )
    conn.execute(
        """
        INSERT INTO watchlist_ticker(asset_id, is_active, source)
        VALUES
            ('AAPL', TRUE, 'manual'),
            ('MSFT', TRUE, 'manual')
        """
    )

    subscriptions = TickerUniverseRepository(conn).stream_subscriptions(
        include_watchlist=True
    )

    assert [(item.symbol, item.source_scope) for item in subscriptions] == [
        ("AAPL", "portfolio"),
        ("MSFT", "watchlist"),
    ]
    assert subscriptions[1].asset_id == "MSFT"
    assert subscriptions[1].exchange_code == "XNAS"


def test_stream_subscriptions_fallback_to_asset_id_when_symbol_is_null():
    conn = make_new_universe_conn()
    conn.execute(
        """
        INSERT INTO watchlist_ticker(asset_id, is_active, source)
        VALUES ('MSFT', TRUE, 'manual')
        """
    )

    subscriptions = TickerUniverseRepository(conn).stream_subscriptions(
        include_portfolios=False,
        include_watchlist=True,
    )

    assert subscriptions[0].symbol == "MSFT"


def test_stream_subscriptions_include_cdr_and_underlying_when_cdr_is_held():
    conn = make_new_universe_conn()
    conn.execute("ALTER TABLE asset ADD COLUMN asset_subtype TEXT")
    conn.execute("ALTER TABLE asset ADD COLUMN name TEXT")
    conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, exchange_code, asset_type, asset_subtype, name, track)
        VALUES ('AMD.TO', 'AMD.TO', 'XTSE', 'stock', 'cdr', 'Advanced Micro Devices CDR', TRUE)
        """
    )
    conn.execute(
        """
        INSERT INTO portfolio_ticker(portfolio_id, asset_id, is_active, source)
        VALUES (1, 'AMD.TO', TRUE, 'position')
        """
    )

    subscriptions = TickerUniverseRepository(conn).stream_subscriptions()

    assert [(item.symbol, item.asset_id, item.source_scope) for item in subscriptions] == [
        ("AMD", "AMD", "portfolio_underlying"),
        ("AMD.TO", "AMD.TO", "portfolio"),
    ]
    assert TickerUniverseRepository(conn).earnings_asset_ids() == ["AMD"]


def test_stream_subscriptions_do_not_duplicate_underlying_when_it_is_held_directly():
    conn = make_new_universe_conn()
    conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, exchange_code, asset_type, track)
        VALUES ('AMD', 'AMD', 'XNAS', 'stock', TRUE)
        """
    )
    conn.execute(
        """
        INSERT INTO portfolio_ticker(portfolio_id, asset_id, is_active, source)
        VALUES (1, 'AMD', TRUE, 'position')
        """
    )

    subscriptions = TickerUniverseRepository(conn).stream_subscriptions()

    assert [(item.symbol, item.asset_id, item.source_scope) for item in subscriptions] == [
        ("AMD", "AMD", "portfolio"),
    ]


def test_known_cdr_symbol_resolves_underlying_without_descriptive_metadata():
    conn = make_new_universe_conn()
    conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, exchange_code, asset_type, track)
        VALUES ('BKNG.TO', 'BKNG.TO', 'XTSE', 'stock', TRUE)
        """
    )
    conn.execute(
        """
        INSERT INTO portfolio_ticker(portfolio_id, asset_id, is_active, source)
        VALUES (1, 'BKNG.TO', TRUE, 'position')
        """
    )

    repo = TickerUniverseRepository(conn)

    assert repo.earnings_asset_ids() == ["BKNG"]
    assert [(item.symbol, item.source_scope) for item in repo.stream_subscriptions()] == [
        ("BKNG", "portfolio_underlying"),
        ("BKNG.TO", "portfolio"),
    ]


def test_sync_portfolio_tickers_from_positions_handles_qty_and_ignores_zero_positions():
    conn = make_new_universe_conn()
    conn.execute(
        """
        INSERT INTO position(portfolio_id, asset_id, qty)
        VALUES
            (1, 'AAPL', 10),
            (1, 'MSFT', 0),
            (2, 'SPY', -4)
        """
    )

    count = TickerUniverseRepository(conn).sync_portfolio_tickers_from_positions()

    rows = conn.execute(
        """
        SELECT portfolio_id, asset_id, is_active, source
        FROM portfolio_ticker
        ORDER BY portfolio_id, asset_id
        """
    ).fetchall()

    assert count == 2
    assert rows == [
        (1, "AAPL", True, "position"),
        (2, "SPY", True, "position"),
    ]


def test_sync_portfolio_tickers_from_positions_includes_broker_position_maps():
    conn = make_new_universe_conn()
    conn.execute(
        """
        CREATE TABLE broker_portfolio_position_map (
            provider TEXT,
            provider_account_id TEXT,
            provider_position_id TEXT,
            portfolio_id BIGINT,
            asset_id TEXT,
            quantity DOUBLE,
            book_cost DOUBLE
        )
        """
    )
    conn.execute(
        """
        INSERT INTO broker_portfolio_position_map(
            provider,
            provider_account_id,
            provider_position_id,
            portfolio_id,
            asset_id,
            quantity,
            book_cost
        )
        VALUES
            ('snaptrade', 'acct-1', 'pos-aapl', 1, 'AAPL', 10, 100),
            ('snaptrade', 'acct-1', 'pos-msft', 1, 'MSFT', 0, 0),
            ('snaptrade', 'acct-2', 'pos-spy', 2, 'SPY', 3, 300)
        """
    )

    count = TickerUniverseRepository(conn).sync_portfolio_tickers_from_positions()

    rows = conn.execute(
        """
        SELECT portfolio_id, asset_id, is_active, source
        FROM portfolio_ticker
        ORDER BY portfolio_id, asset_id
        """
    ).fetchall()

    assert count == 2
    assert rows == [
        (1, "AAPL", True, "position"),
        (2, "SPY", True, "position"),
    ]


def test_sync_portfolio_tickers_from_positions_deactivates_unheld_portfolio_tickers():
    conn = make_new_universe_conn()
    conn.execute(
        """
        INSERT INTO position(portfolio_id, asset_id, qty)
        VALUES (1, 'AAPL', 10)
        """
    )
    conn.execute(
        """
        INSERT INTO portfolio_ticker(portfolio_id, asset_id, is_active, source)
        VALUES
            (1, 'AAPL', FALSE, 'position'),
            (1, 'OLD', TRUE, 'position'),
            (2, 'SPY', TRUE, 'position')
        """
    )

    count = TickerUniverseRepository(conn).sync_portfolio_tickers_from_positions()

    rows = conn.execute(
        """
        SELECT portfolio_id, asset_id, is_active
        FROM portfolio_ticker
        ORDER BY portfolio_id, asset_id
        """
    ).fetchall()

    assert count == 1
    assert rows == [
        (1, "AAPL", True),
        (1, "OLD", False),
        (2, "SPY", False),
    ]


def test_legacy_position_and_watchlist_asset_fallbacks_still_work_without_new_tables():
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE asset (
            asset_id TEXT PRIMARY KEY,
            symbol TEXT,
            exchange_code TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE position (
            position_id TEXT PRIMARY KEY,
            portfolio_id TEXT,
            asset_id TEXT,
            quantity DOUBLE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE watchlist_asset (
            watchlist_asset_id TEXT PRIMARY KEY,
            asset_id TEXT,
            is_active BOOLEAN
        )
        """
    )
    conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, exchange_code)
        VALUES
            ('AAPL', 'AAPL', 'XNAS'),
            ('NVDA', 'NVDA', 'XNAS'),
            ('CASH', 'CASH', NULL)
        """
    )
    conn.execute(
        """
        INSERT INTO position(position_id, portfolio_id, asset_id, quantity)
        VALUES
            ('p-aapl', 'p1', 'AAPL', 1),
            ('p-cash', 'p1', 'CASH', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO watchlist_asset(watchlist_asset_id, asset_id, is_active)
        VALUES
            ('w-nvda', 'NVDA', TRUE),
            ('w-aapl', 'AAPL', TRUE)
        """
    )

    repo = TickerUniverseRepository(conn)

    assert repo.portfolio_asset_ids() == ["AAPL"]
    assert repo.watchlist_asset_ids() == ["AAPL", "NVDA"]
    assert [item.symbol for item in repo.stream_subscriptions(include_watchlist=True)] == [
        "AAPL",
        "NVDA",
    ]


def test_tracked_asset_fallback_only_applies_when_no_explicit_lists_have_assets():
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE asset (
            asset_id TEXT PRIMARY KEY,
            asset_type TEXT,
            track BOOLEAN
        )
        """
    )
    conn.execute(
        """
        INSERT INTO asset(asset_id, asset_type, track)
        VALUES
            ('AAPL', 'stock', TRUE),
            ('SPY', 'etf', TRUE),
            ('OLD', 'stock', FALSE)
        """
    )

    repo = TickerUniverseRepository(conn)

    assert repo.ingestible_asset_ids() == ["AAPL", "SPY"]
    assert repo.ingestible_asset_ids(asset_types=("stock",)) == ["AAPL"]
