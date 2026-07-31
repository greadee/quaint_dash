from __future__ import annotations

from pathlib import Path

import duckdb

from dashboard.db.db_conn import DB, init_db


def table_columns(conn, table_name: str) -> dict[str, str]:
    return {
        row[1]: row[2]
        for row in conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    }


def test_init_db_adds_new_asset_columns_to_existing_asset_table(tmp_path: Path):
    db_path = tmp_path / "legacy_asset.db"
    conn = duckdb.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE asset (
            asset_id TEXT PRIMARY KEY,
            asset_type TEXT,
            ccy TEXT NOT NULL,
            name TEXT,
            sector TEXT,
            industry TEXT,
            country TEXT,
            region TEXT,
            size TEXT,
            mkt_cap DOUBLE,
            market_beta DOUBLE,
            track BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute(
        """
        INSERT INTO asset(asset_id, asset_type, ccy, name)
        VALUES ('AAPL', 'stock', 'USD', 'Apple Inc.')
        """
    )
    conn.close()

    db = DB(str(db_path))
    init_db(db)

    columns = table_columns(db.conn, "asset")
    row = db.conn.execute(
        """
        SELECT symbol, exchange_code, asset_subtype, description, shares_outstanding
        FROM asset
        WHERE asset_id = 'AAPL'
        """
    ).fetchone()

    assert "symbol" in columns
    assert "exchange_code" in columns
    assert "asset_subtype" in columns
    assert "description" in columns
    assert "shares_outstanding" in columns
    assert row == ("AAPL", None, None, None, None)


def test_init_db_creates_ticker_universe_tables_and_backfills_from_positions(tmp_path: Path):
    db = DB(str(tmp_path / "ticker_tables.db"))
    init_db(db)

    db.conn.execute(
        """
        INSERT INTO portfolio(portfolio_id, portfolio_name)
        VALUES (1, 'Core')
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES
            ('AAPL', 'AAPL', 'stock', 'USD'),
            ('CASH', 'CASH', 'cash', 'CAD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO position(portfolio_id, asset_id, qty, book_cost, created_at, updated_at)
        VALUES
            (1, 'AAPL', 5, 100, now(), now()),
            (1, 'CASH', 0, 0, now(), now())
        """
    )

    init_db(db)

    rows = db.conn.execute(
        """
        SELECT portfolio_id, asset_id, is_active, source
        FROM portfolio_ticker
        ORDER BY asset_id
        """
    ).fetchall()

    assert rows == [(1, "AAPL", True, "position")]
    assert "asset_id" in table_columns(db.conn, "watchlist_ticker")


def test_init_db_keeps_fundamental_sync_state_asset_id_as_text(tmp_path: Path):
    db = DB(str(tmp_path / "fundamental_schema.db"))
    init_db(db)

    columns = table_columns(db.conn, "fundamental_sync_state")

    assert columns["asset_id"].upper() == "VARCHAR"


def test_init_db_repairs_ingestion_job_sequence_after_explicit_ids(tmp_path: Path):
    db = DB(str(tmp_path / "ingestion_sequence.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, asset_type, ccy, name)
        VALUES ('AAPL', 'stock', 'USD', 'Apple Inc.')
        """
    )
    db.conn.execute(
        """
        INSERT INTO ingestion_job(
            job_id, asset_id, domain, job_type, dataset, status, priority
        )
        VALUES (10000, 'AAPL', 'market', 'refresh', 'price_daily', 'done', 100)
        """
    )

    init_db(db)

    allocated = db.conn.execute(
        """
        SELECT nextval('seq_ingestion_job_id'), nextval('seq_ingestion_job_id')
        """
    ).fetchone()
    assert allocated == (10001, 10002)


def test_init_db_adds_backfill_columns_to_existing_fundamental_subscription(tmp_path: Path):
    db_path = tmp_path / "legacy_fundamental_subscription.db"
    conn = duckdb.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE asset (
            asset_id TEXT PRIMARY KEY,
            ccy TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE fundamental_subscription (
            asset_id TEXT PRIMARY KEY,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            refresh_interval_days INTEGER NOT NULL DEFAULT 7,
            next_refresh_at TIMESTAMP,
            last_refresh_attempted_at TIMESTAMP,
            last_refresh_succeeded_at TIMESTAMP,
            subscription_source TEXT NOT NULL DEFAULT 'manual',
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fundamental_subscription(
            asset_id, is_active, next_refresh_at, subscription_source
        )
        VALUES ('MSFT', FALSE, TIMESTAMP '9999-12-31', 'legacy')
        """
    )
    conn.close()

    db = DB(str(db_path))
    init_db(db)

    columns = table_columns(db.conn, "fundamental_subscription")

    assert "last_backfill_requested_at" in columns
    assert "last_backfill_succeeded_at" in columns
    assert db.conn.execute(
        """
        SELECT COUNT(*)
        FROM duckdb_constraints()
        WHERE table_name = 'fundamental_subscription'
          AND constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE')
        """
    ).fetchone() == (0,)
    assert db.conn.execute(
        """
        SELECT COUNT(*)
        FROM duckdb_indexes()
        WHERE table_name = 'fundamental_subscription'
        """
    ).fetchone() == (0,)
    migrated = db.conn.execute(
        """
        SELECT is_active, next_refresh_at, subscription_source
        FROM fundamental_subscription
        WHERE asset_id = 'MSFT'
        """
    ).fetchone()
    assert migrated[0] is False
    assert str(migrated[1]).startswith("9999-12-31")
    assert migrated[2] == "legacy"
