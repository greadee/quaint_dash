"""
tests/test_market_cli_ingestion.py

Tests Domain A market ingestion through the CLI View layer.

Covers:
  - market-backfill-enqueue
  - market-backfill-run
  - market-refresh-enqueue
  - market-refresh-run
  - ingestion_job queue behavior
  - asset_sync_state behavior
  - asset_quote_daily inserts
  - refresh starts after latest stored daily quote

These tests mock the FMP provider, so they do not consume API calls.
"""

from __future__ import annotations

from datetime import date
import pytest

from dashboard.db.db_conn import DB, init_db
from dashboard.models.storage import DashboardManager
from dashboard.models.cli_view import DashboardView
from dashboard.ingestion.price_history.models import PriceDailyRow
from dashboard.ingestion.price_history.service import PriceHistoryIngestionService


class FakeYahooPriceProvider:
    """
    Fake FMP provider used to avoid real API calls.

    It records calls so we can assert that backfill and refresh requested
    the expected date ranges.
    """

    def __init__(self):
        self.price_calls = []
        self.dividend_calls = []
        self.split_calls = []

    def fetch_price_daily(self, asset_id: str, start_date: date, end_date: date):
        self.price_calls.append((asset_id, start_date, end_date))

        return [
            PriceDailyRow(
                asset_id=asset_id,
                price_date=date(2024, 1, 2),
                open_price=100.0,
                high_price=105.0,
                low_price=99.0,
                close_price=104.0,
                adj_close_price=104.0,
                volume=1000000,
                source="fake_fmp",
            ),
            PriceDailyRow(
                asset_id=asset_id,
                price_date=date(2024, 1, 3),
                open_price=104.0,
                high_price=108.0,
                low_price=103.0,
                close_price=107.0,
                adj_close_price=107.0,
                volume=1200000,
                source="fake_fmp",
            ),
        ]

    def fetch_dividends(self, asset_id: str, start_date: date, end_date: date):
        self.dividend_calls.append((asset_id, start_date, end_date))
        return []

    def fetch_splits(self, asset_id: str, start_date: date, end_date: date):
        self.split_calls.append((asset_id, start_date, end_date))
        return []


@pytest.fixture()
def test_manager(tmp_path, monkeypatch):
    """
    Creates a temporary DuckDB database and patches MarketIngestionService
    inside dashboard.models.storage so DashboardManager uses our fake provider.
    """

    db_path = tmp_path / "market_ingestion_test.db"
    db = DB(str(db_path))
    init_db(db)

    fake_provider = FakeYahooPriceProvider()

    def fake_market_service_factory(conn):
        return PriceHistoryIngestionService(conn, provider=fake_provider)

    # Important:
    # Patch the symbol used by DashboardManager, not the original service module.
    monkeypatch.setattr(
        "dashboard.models.storage.PriceHistoryIngestionService",
        fake_market_service_factory,
    )

    manager = DashboardManager(db)

    # Insert one asset directly so the ingestion jobs have a valid FK target.
    manager.conn.execute(
        """
        INSERT INTO asset (
            asset_id,
            asset_type,
            ccy,
            name,
            track,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, TRUE, now(), now())
        ON CONFLICT(asset_id)
        DO NOTHING
        """,
        ["BN.TO", "stock", "CAD", "Brookfield Corporation"],
    )

    return manager, fake_provider


def test_cli_market_backfill_enqueue_prices_only(test_manager):
    """
    CLI should enqueue one price_daily backfill job when --prices-only is used.
    """

    manager, _ = test_manager
    view = DashboardView(manager)

    next_view = view.handle_input(
        "market-backfill-enqueue BN.TO --years 10 --prices-only"
    )

    assert next_view is view

    rows = manager.conn.execute(
        """
        SELECT asset_id, domain, job_type, dataset, status, priority
        FROM ingestion_job
        ORDER BY job_id
        """
    ).fetchall()

    assert len(rows) == 1

    assert rows[0][0] == "BN.TO"
    assert rows[0][1] == "market"
    assert rows[0][2] == "backfill"
    assert rows[0][3] == "price_daily"
    assert rows[0][4] == "pending"


def test_cli_market_backfill_run_inserts_daily_quotes(test_manager):
    """
    Backfill run should claim the queued job, fetch fake FMP daily rows,
    insert them into asset_quote_daily, and mark the job done.
    """

    manager, fake_provider = test_manager
    view = DashboardView(manager)

    view.handle_input("market-backfill-enqueue BN.TO --years 10 --prices-only")
    view.handle_input("market-backfill-run --max-jobs 1")

    job_row = manager.conn.execute(
        """
        SELECT status, attempt_count, error_message
        FROM ingestion_job
        WHERE asset_id = 'BN.TO'
          AND job_type = 'backfill'
          AND dataset = 'price_daily'
        """
    ).fetchone()

    assert job_row is not None
    assert job_row[2] is None, f"Worker failed with error: {job_row[2]}"
    assert job_row[0] == "done"
    assert job_row[1] == 1  

    quote_rows = manager.conn.execute(
        """
        SELECT
        "asset_id",
        "date",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "ing_source"
        FROM asset_quote_daily
        WHERE asset_id = 'BN.TO'
        ORDER BY "date"
        """
    ).fetchall()

    assert len(quote_rows) == 2

    assert quote_rows[0][0] == "BN.TO"
    assert quote_rows[0][1] == date(2024, 1, 2)
    assert quote_rows[0][2] == 100.0
    assert quote_rows[0][5] == 104.0
    assert quote_rows[0][7] == 1000000
    assert quote_rows[0][8] == "fake_fmp"

    assert quote_rows[1][1] == date(2024, 1, 3)
    assert quote_rows[1][5] == 107.0

    assert len(fake_provider.price_calls) == 1
    assert fake_provider.price_calls[0][0] == "BN.TO"


def test_cli_market_backfill_updates_sync_state(test_manager):
    """
    Backfill run should create/update asset_sync_state for market price_daily.
    """

    manager, _ = test_manager
    view = DashboardView(manager)

    view.handle_input("market-backfill-enqueue BN.TO --years 10 --prices-only")
    view.handle_input("market-backfill-run --max-jobs 1")

    sync_row = manager.conn.execute(
        """
        SELECT
            asset_id,
            domain,
            dataset,
            backfill_status,
            last_successful_date,
            needs_repair
        FROM asset_sync_state
        WHERE asset_id = 'BN.TO'
          AND domain = 'market'
          AND dataset = 'price_daily'
        """
    ).fetchone()

    assert sync_row is not None
    assert sync_row[0] == "BN.TO"
    assert sync_row[1] == "market"
    assert sync_row[2] == "price_daily"
    assert sync_row[3] == "done"
    assert sync_row[4] == date(2024, 1, 3)
    assert sync_row[5] is False


def test_cli_market_refresh_enqueue_uses_latest_quote_date(test_manager):
    """
    Refresh enqueue should start after the latest stored quote date.

    Since fake backfill inserts through 2024-01-03,
    the refresh job should start on 2024-01-04.
    """

    manager, _ = test_manager
    view = DashboardView(manager)

    view.handle_input("market-backfill-enqueue BN.TO --years 10 --prices-only")
    view.handle_input("market-backfill-run --max-jobs 1")

    view.handle_input("market-refresh-enqueue BN.TO --prices-only")

    refresh_job = manager.conn.execute(
        """
        SELECT
            job_type,
            dataset,
            status,
            requested_start_date,
            requested_end_date
        FROM ingestion_job
        WHERE asset_id = 'BN.TO'
          AND job_type = 'refresh'
          AND dataset = 'price_daily'
        ORDER BY job_id DESC
        LIMIT 1
        """
    ).fetchone()

    assert refresh_job is not None
    assert refresh_job[0] == "refresh"
    assert refresh_job[1] == "price_daily"
    assert refresh_job[2] == "pending"
    assert refresh_job[3] == date(2024, 1, 4)


def test_cli_market_backfill_enqueue_all_prices_only(test_manager):
    """
    CLI should enqueue backfill jobs for all assets when target is 'all'.
    """

    manager, _ = test_manager
    view = DashboardView(manager)

    manager.conn.execute(
        """
        INSERT INTO asset (
            asset_id,
            asset_type,
            ccy,
            name,
            track,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, TRUE, now(), now())
        ON CONFLICT(asset_id)
        DO NOTHING
        """,
        ["AAPL", "stock", "USD", "Apple Inc."],
    )

    view.handle_input("market-backfill-enqueue all --years 10 --prices-only")

    rows = manager.conn.execute(
        """
        SELECT asset_id, job_type, dataset, status
        FROM ingestion_job
        WHERE job_type = 'backfill'
          AND dataset = 'price_daily'
        ORDER BY asset_id
        """
    ).fetchall()

    assert len(rows) == 2

    assert rows[0][0] == "AAPL"
    assert rows[0][1] == "backfill"
    assert rows[0][2] == "price_daily"
    assert rows[0][3] == "pending"

    assert rows[1][0] == "BN.TO"
    assert rows[1][1] == "backfill"
    assert rows[1][2] == "price_daily"
    assert rows[1][3] == "pending"