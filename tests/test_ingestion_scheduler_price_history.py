"""
tests/test_ingestion_schedulers.py

Tests automatic scheduler-style ingestion helpers for:

1. asset metadata refresh scheduling
2. price history backfill scheduling

These tests do not call FMP or Yahoo.
"""

from __future__ import annotations

from datetime import date

import pytest

from dashboard.db.db_conn import DB, init_db
from dashboard.models.storage import DashboardManager
from dashboard.ingestion.price_history.db.ingestion_repo import PriceHistoryIngestionRepository
from dashboard.ingestion.price_history.models import DividendEventRow, SplitEventRow
from dashboard.ingestion.price_history.models import PriceDailyRow
from dashboard.ingestion.price_history.service import PriceHistoryIngestionService


class FakeAssetImporter:
    """
    Fake replacement for AssetImporter.

    Records which asset ids were requested and marks them as successfully synced.
    """

    calls: list[list[str]] = []

    def __init__(self, manager: DashboardManager):
        self.manager = manager

    def import_asset_ids(self, asset_ids):
        asset_ids = list(asset_ids)
        FakeAssetImporter.calls.append(asset_ids)

        for asset_id in asset_ids:
            self.manager.conn.execute(
                """
                UPDATE asset_metadata_sync
                SET
                    sync_status = 'synced',
                    last_attempted_at = now(),
                    last_succeeded_at = now(),
                    last_error = NULL,
                    updated_at = now()
                WHERE asset_id = ?
                """,
                [asset_id],
            )

        return asset_ids


class FakeYahooProvider:
    """
    Fake replacement for YahooPriceProvider.

    Returns two daily quote rows for any requested asset.
    """

    def __init__(self):
        self.price_calls = []

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
                source="fake_yfinance",
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
                source="fake_yfinance",
            ),
        ]

    def fetch_dividends(self, asset_id: str, start_date: date, end_date: date):
        return []

    def fetch_splits(self, asset_id: str, start_date: date, end_date: date):
        return []


@pytest.fixture()
def manager(tmp_path):
    db_path = tmp_path / "scheduler_test.db"
    db = DB(str(db_path))
    init_db(db)
    return DashboardManager(db)


def insert_asset(manager: DashboardManager, asset_id: str, ccy: str = "CAD"):
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
        VALUES (?, 'stock', ?, ?, TRUE, now(), now())
        ON CONFLICT(asset_id)
        DO NOTHING
        """,
        [asset_id, ccy, asset_id],
    )

    manager.conn.execute(
        """
        INSERT INTO asset_metadata_sync (
            asset_id,
            source,
            sync_status,
            created_at,
            updated_at
        )
        VALUES (?, 'fmp', 'pending', now(), now())
        ON CONFLICT(asset_id)
        DO NOTHING
        """,
        [asset_id],
    )


def test_market_job_ids_stay_above_existing_rows(manager):
    insert_asset(manager, "BN.TO")
    manager.conn.execute(
        """
        INSERT INTO ingestion_job(
            job_id, asset_id, domain, job_type, dataset, status, priority,
            requested_start_date, requested_end_date, attempt_count, error_message,
            created_at, updated_at
        )
        VALUES (100, 'BN.TO', 'market', 'refresh', 'price_daily', 'done', 100, NULL, NULL, 0, NULL, now(), now())
        """
    )

    repo = PriceHistoryIngestionRepository(manager.conn)

    assert repo.next_job_id() == 101


def test_market_claim_skips_obsolete_pending_jobs_with_newer_done_job(manager):
    insert_asset(manager, "BN.TO")
    manager.conn.execute(
        """
        INSERT INTO ingestion_job(
            job_id, asset_id, domain, job_type, dataset, status, priority,
            requested_start_date, requested_end_date, attempt_count, error_message,
            created_at, updated_at
        )
        VALUES
            (10, 'BN.TO', 'market', 'refresh', 'dividends', 'pending', 90, DATE '2026-01-01', DATE '2026-01-02', 1, NULL, TIMESTAMP '2026-01-01 00:00:00', now()),
            (11, 'BN.TO', 'market', 'refresh', 'dividends', 'done', 90, DATE '2026-01-01', DATE '2026-01-02', 1, NULL, TIMESTAMP '2026-01-02 00:00:00', now()),
            (12, 'BN.TO', 'market', 'refresh', 'splits', 'pending', 80, DATE '2026-01-01', DATE '2026-01-02', 0, NULL, TIMESTAMP '2026-01-03 00:00:00', now())
        """
    )

    repo = PriceHistoryIngestionRepository(manager.conn)
    job = repo.claim_next_pending_job()

    assert job is not None
    assert job.job_id == 12
    rows = manager.conn.execute(
        """
        SELECT job_id, status
        FROM ingestion_job
        WHERE job_id IN (10, 12)
        ORDER BY job_id
        """
    ).fetchall()
    assert rows == [(10, "pending"), (12, "running")]


def test_market_claim_skips_pending_jobs_already_satisfied_by_sync_state(manager):
    insert_asset(manager, "BN.TO")
    manager.conn.execute(
        """
        INSERT INTO ingestion_job(
            job_id, asset_id, domain, job_type, dataset, status, priority,
            requested_start_date, requested_end_date, attempt_count, error_message,
            created_at, updated_at
        )
        VALUES
            (10, 'BN.TO', 'market', 'refresh', 'dividends', 'pending', 90, DATE '2026-01-01', DATE '2026-01-02', 1, NULL, TIMESTAMP '2026-01-01 00:00:00', TIMESTAMP '2026-01-01 00:00:00'),
            (11, 'BN.TO', 'market', 'refresh', 'splits', 'pending', 80, DATE '2026-01-01', DATE '2026-01-02', 0, NULL, TIMESTAMP '2026-01-03 00:00:00', TIMESTAMP '2026-01-03 00:00:00')
        """
    )
    manager.conn.execute(
        """
        INSERT INTO asset_sync_state(
            asset_id, domain, dataset, backfill_status, last_successful_at, last_successful_date
        )
        VALUES ('BN.TO', 'market', 'dividends', 'done', TIMESTAMP '2026-01-02 00:00:00', DATE '2026-01-02')
        """
    )

    repo = PriceHistoryIngestionRepository(manager.conn)
    job = repo.claim_next_pending_job()

    assert job is not None
    assert job.job_id == 11
    rows = manager.conn.execute(
        """
        SELECT job_id, status
        FROM ingestion_job
        WHERE job_id IN (10, 11)
        ORDER BY job_id
        """
    ).fetchall()
    assert rows == [(10, "pending"), (11, "running")]


def test_metadata_scheduler_refreshes_pending_assets(manager, monkeypatch):
    """
    refresh_due_asset_metadata should select pending metadata rows and pass them
    to AssetImporter.
    """

    FakeAssetImporter.calls = []

    insert_asset(manager, "BN.TO")
    insert_asset(manager, "AAPL", ccy="USD")

    monkeypatch.setattr(
        "dashboard.services.asset_importer.AssetImporter",
        FakeAssetImporter,
    )

    n_synced = manager.refresh_due_asset_metadata(max_assets=5)

    assert n_synced == 2

    assert FakeAssetImporter.calls == [["AAPL", "BN.TO"]] or FakeAssetImporter.calls == [["BN.TO", "AAPL"]]

    rows = manager.conn.execute(
        """
        SELECT asset_id, sync_status, last_succeeded_at, last_error
        FROM asset_metadata_sync
        ORDER BY asset_id
        """
    ).fetchall()

    assert rows[0][1] == "synced"
    assert rows[0][2] is not None
    assert rows[0][3] is None

    assert rows[1][1] == "synced"
    assert rows[1][2] is not None
    assert rows[1][3] is None


def test_metadata_scheduler_respects_max_assets(manager, monkeypatch):
    """
    Scheduler should only process max_assets rows.
    """

    FakeAssetImporter.calls = []

    insert_asset(manager, "BN.TO")
    insert_asset(manager, "AAPL", ccy="USD")
    insert_asset(manager, "MSFT", ccy="USD")

    monkeypatch.setattr(
        "dashboard.services.asset_importer.AssetImporter",
        FakeAssetImporter,
    )

    n_synced = manager.refresh_due_asset_metadata(max_assets=1)

    assert n_synced == 1
    assert len(FakeAssetImporter.calls) == 1
    assert len(FakeAssetImporter.calls[0]) == 1


def test_metadata_refresh_pipeline_forces_all_ingestible_assets(manager, monkeypatch):
    """
    metadata-refresh bypasses due checks so fixed metadata mappings can repair
    already-synced asset rows.
    """

    FakeAssetImporter.calls = []

    insert_asset(manager, "BN.TO")
    insert_asset(manager, "AAPL", ccy="USD")

    manager.conn.execute(
        """
        UPDATE asset_metadata_sync
        SET sync_status = 'synced', last_succeeded_at = now()
        """
    )

    monkeypatch.setattr(
        "dashboard.services.asset_importer.AssetImporter",
        FakeAssetImporter,
    )

    n_synced = manager.schedule_ingestion_jobs(pipeline="metadata-refresh")

    assert n_synced == 2
    assert FakeAssetImporter.calls == [["AAPL", "BN.TO"]] or FakeAssetImporter.calls == [["BN.TO", "AAPL"]]


def test_price_history_scheduler_enqueues_backfill_jobs(manager):
    """
    schedule_due_price_history_backfills should enqueue backfill jobs for tracked
    assets with no completed price history sync state.
    """

    insert_asset(manager, "BN.TO")
    insert_asset(manager, "AAPL", ccy="USD")

    n_jobs = manager.schedule_due_price_history_backfills(
        max_assets=2,
        years=1,
    )

    # Each asset gets price_daily, dividends, and splits backfill jobs.
    assert n_jobs == 6

    rows = manager.conn.execute(
        """
        SELECT asset_id, job_type, dataset, status
        FROM ingestion_job
        ORDER BY asset_id, dataset
        """
    ).fetchall()

    assert len(rows) == 6

    assert all(row[1] == "backfill" for row in rows)
    assert all(row[3] == "pending" for row in rows)

    datasets = sorted({row[2] for row in rows})
    assert datasets == ["dividends", "price_daily", "splits"]


def test_price_history_scheduler_does_not_duplicate_pending_jobs(manager):
    """
    Running the scheduler twice should not enqueue duplicate pending backfill jobs.
    """

    insert_asset(manager, "BN.TO")

    first_count = manager.schedule_due_price_history_backfills(
        max_assets=1,
        years=1,
    )
    second_count = manager.schedule_due_price_history_backfills(
        max_assets=1,
        years=1,
    )

    assert first_count == 3
    assert second_count == 0

    n_jobs = manager.conn.execute(
        """
        SELECT COUNT(*)
        FROM ingestion_job
        WHERE asset_id = 'BN.TO'
        """
    ).fetchone()[0]

    assert n_jobs == 3


def test_market_scheduler_can_target_one_portfolio_ticker(manager):
    insert_asset(manager, "AAPL", ccy="USD")
    insert_asset(manager, "MSFT", ccy="USD")
    manager.conn.execute(
        """
        INSERT INTO portfolio(portfolio_id, portfolio_name)
        VALUES (1, 'Core')
        """
    )
    manager.conn.execute(
        """
        INSERT INTO portfolio_ticker(portfolio_id, asset_id, is_active, source)
        VALUES
            (1, 'AAPL', TRUE, 'position'),
            (1, 'MSFT', TRUE, 'position')
        """
    )

    n_jobs = manager.schedule_ingestion_jobs(
        pipeline="market",
        asset_id="AAPL",
        max_assets=10,
        years=1,
    )

    rows = manager.conn.execute(
        """
        SELECT DISTINCT asset_id
        FROM ingestion_job
        ORDER BY asset_id
        """
    ).fetchall()

    assert n_jobs == 6
    assert rows == [("AAPL",)]


def test_price_history_scheduler_processes_one_backfill_job(manager, monkeypatch):
    """
    Scheduler can enqueue jobs, then run one queued price history backfill job.

    The provider is mocked, so this does not call Yahoo.
    """

    insert_asset(manager, "BN.TO")

    fake_provider = FakeYahooProvider()

    monkeypatch.setattr(
        "dashboard.ingestion.price_history.service.YahooPriceProvider",
        lambda: fake_provider,
        )

    n_jobs = manager.schedule_due_price_history_backfills(
        max_assets=1,
        years=1,
    )

    assert n_jobs == 3

    processed = manager.run_price_history_backfill_jobs(max_jobs=1)

    assert processed == 1

    latest_job = manager.conn.execute(
        """
        SELECT status, error_message
        FROM ingestion_job
        WHERE asset_id = 'BN.TO'
          AND dataset = 'price_daily'
        ORDER BY job_id DESC
        LIMIT 1
        """
    ).fetchone()

    assert latest_job is not None
    assert latest_job[0] == "done"
    assert latest_job[1] is None

    quote_rows = manager.conn.execute(
        """
        SELECT asset_id, "date", "close", ing_source
        FROM asset_quote_daily
        WHERE asset_id = 'BN.TO'
        ORDER BY "date"
        """
    ).fetchall()

    assert len(quote_rows) == 2
    assert quote_rows[0][0] == "BN.TO"
    assert quote_rows[0][1] == date(2024, 1, 2)
    assert quote_rows[0][2] == 104.0
    assert quote_rows[0][3] == "fake_yfinance"


def test_market_ingestion_upserts_dividends_and_splits_on_conflict(manager):
    """
    Dividend and split upserts should work for both new rows and conflict updates.
    """

    insert_asset(manager, "AAPL")
    repo = PriceHistoryIngestionRepository(manager.conn)

    repo.upsert_dividend_rows(
        [
            DividendEventRow(
                asset_id="AAPL",
                ex_date=date(2024, 1, 5),
                payment_date=None,
                record_date=None,
                declaration_date=None,
                dividend_per_share=0.24,
                currency="USD",
                source="test",
            )
        ]
    )
    repo.upsert_dividend_rows(
        [
            DividendEventRow(
                asset_id="AAPL",
                ex_date=date(2024, 1, 5),
                payment_date=None,
                record_date=None,
                declaration_date=None,
                dividend_per_share=0.25,
                currency="USD",
                source="test",
            )
        ]
    )
    repo.upsert_split_rows(
        [
            SplitEventRow(
                asset_id="AAPL",
                ex_date=date(2024, 2, 1),
                split_from=1,
                split_to=2,
                source="test",
            )
        ]
    )
    repo.upsert_split_rows(
        [
            SplitEventRow(
                asset_id="AAPL",
                ex_date=date(2024, 2, 1),
                split_from=1,
                split_to=4,
                source="test",
            )
        ]
    )

    dividend = manager.conn.execute(
        """
        SELECT dividend_per_share, currency
        FROM dividend_event
        WHERE asset_id = 'AAPL'
        """
    ).fetchone()
    split = manager.conn.execute(
        """
        SELECT split_from, split_to
        FROM split_event
        WHERE asset_id = 'AAPL'
        """
    ).fetchone()

    assert dividend == (0.25, "USD")
    assert split == (1, 4)


def test_price_history_scheduler_ignores_completed_asset(manager):
    """
    Assets with completed price_daily sync state should not be scheduled again.
    """

    insert_asset(manager, "BN.TO")

    manager.conn.execute(
        """
        INSERT INTO asset_sync_state (
            asset_id,
            domain,
            dataset,
            backfill_status,
            backfill_start_date,
            backfill_end_date,
            last_successful_date,
            last_attempted_at,
            last_successful_at,
            last_error,
            needs_repair
        )
        VALUES (
            'BN.TO',
            'market',
            'price_daily',
            'done',
            DATE '2023-01-01',
            DATE '2024-01-01',
            DATE '2024-01-01',
            now(),
            now(),
            NULL,
            FALSE
        )
        ON CONFLICT(asset_id, domain, dataset)
        DO UPDATE SET
            backfill_status = excluded.backfill_status,
            last_successful_date = excluded.last_successful_date
        """
    )

    n_jobs = manager.schedule_due_price_history_backfills(
        max_assets=1,
        years=1,
    )

    assert n_jobs == 0


def test_price_history_enqueue_all_uses_portfolio_and_watchlist_ticker_universe(manager):
    """
    Bulk enqueueing should target explicit portfolio/watchlist ticker tables,
    not every tracked asset row.
    """

    insert_asset(manager, "AAPL", ccy="USD")
    insert_asset(manager, "MSFT", ccy="USD")
    insert_asset(manager, "OLD", ccy="USD")

    manager.conn.execute(
        """
        INSERT INTO portfolio(portfolio_id, portfolio_name)
        VALUES (1, 'Core')
        """
    )
    manager.conn.execute(
        """
        INSERT INTO portfolio_ticker(portfolio_id, asset_id, is_active, source)
        VALUES
            (1, 'AAPL', TRUE, 'position'),
            (1, 'OLD', FALSE, 'position')
        """
    )
    manager.conn.execute(
        """
        INSERT INTO watchlist_ticker(asset_id, is_active, source)
        VALUES ('MSFT', TRUE, 'manual')
        """
    )

    service = PriceHistoryIngestionService(manager.conn)

    job_ids = service.enqueue_backfill_all(
        years=1,
        include_dividends=False,
        include_splits=False,
    )

    rows = manager.conn.execute(
        """
        SELECT asset_id, dataset
        FROM ingestion_job
        ORDER BY asset_id
        """
    ).fetchall()

    assert len(job_ids) == 2
    assert rows == [
        ("AAPL", "price_daily"),
        ("MSFT", "price_daily"),
    ]
