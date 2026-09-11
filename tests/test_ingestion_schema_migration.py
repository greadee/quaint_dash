from __future__ import annotations

from pathlib import Path

import duckdb

from dashboard.db.db_conn import DB, init_db
from dashboard.news.models import NewsIngestionResult, ProviderCapabilities
from dashboard.news.repository import NewsRepository


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


def test_init_db_deactivates_stale_ticker_without_deleting_history(tmp_path: Path):
    db = DB(str(tmp_path / "stale_ticker.db"))
    init_db(db)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Core')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES ('AAPL', 'AAPL', 'stock', 'USD'), ('HQD.TO', 'HQD.TO', 'etf', 'CAD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO position(portfolio_id, asset_id, qty, book_cost, created_at, updated_at)
        VALUES (1, 'AAPL', 10, 1000, now(), now())
        """
    )
    db.conn.execute("INSERT INTO import_batch(batch_id, batch_type) VALUES (1, 'manual-entry')")
    db.conn.execute(
        """
        INSERT INTO txn(portfolio_id, txn_type, asset_id, qty, price, ccy, batch_id)
        VALUES (1, 'buy', 'HQD.TO', 20, 10, 'CAD', 1)
        """
    )
    db.conn.execute(
        """
        INSERT INTO portfolio_ticker(portfolio_id, asset_id, is_active, source)
        VALUES (1, 'HQD.TO', TRUE, 'position')
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, ing_source)
        VALUES ('HQD.TO', DATE '2024-09-10', 10, 'historical')
        """
    )

    init_db(db)

    assert db.conn.execute(
        "SELECT is_active FROM portfolio_ticker WHERE asset_id = 'HQD.TO'"
    ).fetchone() == (False,)
    assert db.conn.execute(
        "SELECT COUNT(*) FROM txn WHERE asset_id = 'HQD.TO'"
    ).fetchone() == (1,)
    assert db.conn.execute(
        "SELECT COUNT(*) FROM asset_quote_daily WHERE asset_id = 'HQD.TO'"
    ).fetchone() == (1,)


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


def test_init_db_routes_provider_blocked_work_to_available_fallbacks(tmp_path: Path):
    db = DB(str(tmp_path / "provider_reconciliation.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES ('AAPL', 'AAPL', 'stock', 'USD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO ingestion_job(
            job_id, asset_id, domain, job_type, dataset, status, priority,
            attempt_count, error_message
        )
        VALUES (
            500, 'AAPL', 'corporate', 'backfill', 'financial_statements',
            'dead_letter', 90, 3, 'Provider request limit reached.'
        ), (
            501, 'AAPL', 'corporate', 'refresh', 'financial_statements',
            'failed', 90, 1, 'FMP HTTP error 402: plan does not include this endpoint'
        )
        """
    )
    repo = NewsRepository(db.conn)
    provider_id = repo.upsert_provider(
        provider_code="fmp_news",
        provider_name="Financial Modeling Prep News",
        provider_type="api",
        base_url="https://financialmodelingprep.com/stable",
        capabilities=ProviderCapabilities(supports_latest_news=True),
    )
    repo.mark_ingestion_state(
        provider_id,
        "subscribed",
        NewsIngestionResult(
            provider_code="fmp_news",
            status="failed",
            error_message="FMP HTTP error 402",
        ),
    )

    init_db(db)

    assert db.conn.execute(
        """
        SELECT status, attempt_count, error_message
        FROM ingestion_job
        WHERE job_id IN (500, 501)
        ORDER BY job_id
        """
    ).fetchall() == [("pending", 3, None), ("pending", 1, None)]
    db.conn.execute("UPDATE ingestion_job SET status = 'failed', error_message = 'FMP HTTP error 402' WHERE job_id = 501")
    init_db(db)
    assert db.conn.execute("SELECT status, max_attempts FROM ingestion_job WHERE job_id = 501").fetchone() == ("failed", 6)
    assert db.conn.execute(
        "SELECT is_enabled FROM news_provider WHERE provider_id = ?",
        [provider_id],
    ).fetchone() == (False,)


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
