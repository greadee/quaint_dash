from __future__ import annotations

from datetime import datetime, timedelta

import duckdb
import pytest

from dashboard.ingestion.fundamentals.schema import ensure_fundamental_phase1_schema
from dashboard.ingestion.fundamentals.subscription_service import FundamentalSubscriptionService


def make_asset_id_conn():
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE asset (
            asset_id TEXT PRIMARY KEY,
            asset_type TEXT,
            ccy TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO asset(asset_id, asset_type, ccy)
        VALUES
            ('AAPL', 'stock', 'USD'),
            ('MSFT', 'stock', 'USD')
        """
    )
    return conn


def make_legacy_ticker_conn():
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE asset (
            id TEXT PRIMARY KEY,
            ticker TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO asset(id, ticker)
        VALUES
            ('asset-aapl', 'AAPL'),
            ('asset-msft', 'MSFT')
        """
    )
    return conn


def test_schema_uses_text_asset_ids_and_is_idempotent():
    conn = make_asset_id_conn()

    ensure_fundamental_phase1_schema(conn)
    ensure_fundamental_phase1_schema(conn)

    subscription_cols = {
        row[1]: row[2]
        for row in conn.execute("PRAGMA table_info('fundamental_subscription')").fetchall()
    }
    sync_cols = {
        row[1]: row[2]
        for row in conn.execute("PRAGMA table_info('fundamental_sync_state')").fetchall()
    }

    assert subscription_cols["asset_id"].upper() == "VARCHAR"
    assert sync_cols["asset_id"].upper() == "VARCHAR"


def test_subscribe_ticker_creates_active_subscription_for_asset_id_schema():
    conn = make_asset_id_conn()
    service = FundamentalSubscriptionService(conn)

    asset_id = service.subscribe_ticker(
        "aapl",
        refresh_interval_days=14,
        subscription_source="portfolio",
    )

    assert asset_id == "AAPL"

    row = conn.execute(
        """
        SELECT asset_id, is_active, refresh_interval_days, subscription_source, next_refresh_at
        FROM fundamental_subscription
        WHERE asset_id = 'AAPL'
        """
    ).fetchone()

    assert row[0] == "AAPL"
    assert row[1] is True
    assert row[2] == 14
    assert row[3] == "portfolio"
    assert row[4] is not None


def test_subscribe_ticker_supports_legacy_id_and_ticker_columns():
    conn = make_legacy_ticker_conn()
    service = FundamentalSubscriptionService(conn)

    asset_id = service.subscribe_ticker("msft")

    assert asset_id == "asset-msft"
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM fundamental_subscription
        WHERE asset_id = 'asset-msft'
        """
    ).fetchone()[0] == 1


def test_subscribe_asset_is_idempotent_and_reactivates_without_resetting_existing_due_date():
    conn = make_asset_id_conn()
    service = FundamentalSubscriptionService(conn)
    original_due = datetime.now() + timedelta(days=3)

    service.subscribe_asset("AAPL", refresh_interval_days=7, subscription_source="manual")
    conn.execute(
        """
        UPDATE fundamental_subscription
        SET is_active = FALSE,
            next_refresh_at = ?,
            subscription_source = 'old'
        WHERE asset_id = 'AAPL'
        """,
        [original_due],
    )

    service.subscribe_asset("AAPL", refresh_interval_days=21, subscription_source="watchlist")

    row = conn.execute(
        """
        SELECT is_active, refresh_interval_days, subscription_source, next_refresh_at
        FROM fundamental_subscription
        WHERE asset_id = 'AAPL'
        """
    ).fetchone()

    assert row[0] is True
    assert row[1] == 21
    assert row[2] == "watchlist"
    assert row[3] == original_due


def test_unsubscribe_ticker_deactivates_subscription_and_active_listing_filters_it_out():
    conn = make_asset_id_conn()
    service = FundamentalSubscriptionService(conn)

    service.subscribe_ticker("AAPL")
    service.subscribe_ticker("MSFT")
    service.unsubscribe_ticker("aapl")

    active = service.list_active_subscriptions()

    assert [row["asset_id"] for row in active] == ["MSFT"]
    assert active[0]["ticker"] == "MSFT"


def test_unknown_ticker_errors_without_creating_subscription():
    conn = make_asset_id_conn()
    service = FundamentalSubscriptionService(conn)

    with pytest.raises(ValueError, match="Ticker 'NVDA' does not exist"):
        service.subscribe_ticker("NVDA")

    assert conn.execute("SELECT COUNT(*) FROM fundamental_subscription").fetchone()[0] == 0


def test_missing_asset_identifier_columns_raise_clear_runtime_error():
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE asset (name TEXT)")

    with pytest.raises(RuntimeError, match="Could not find asset id column"):
        FundamentalSubscriptionService(conn).find_asset_id_by_ticker("AAPL")
