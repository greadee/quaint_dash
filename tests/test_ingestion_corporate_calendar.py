from datetime import date, timedelta

import duckdb

from dashboard.ingestion.fundamentals.schema import ensure_fundamental_phase1_schema
from dashboard.ingestion.corporate_calendar.models import (
    CorporateCalendarEventRow,
    FinancialStatementRow,
)
from dashboard.ingestion.corporate_calendar.service import (
    CorporateCalendarIngestionService,
)


class FakeCorporateProvider:
    source = "fake"

    def fetch_earnings_calendar(self, start_date, end_date):
        return [
            CorporateCalendarEventRow(
                asset_id="AAPL",
                earnings_date=date.today() + timedelta(days=20),
                fiscal_year=2026,
                fiscal_quarter=2,
                time="amc",
                eps_estimated=2.0,
                eps_actual=None,
                revenue_estimated=100.0,
                revenue_actual=None,
                source="fake",
            )
        ]

    def fetch_earnings_for_symbol(self, asset_id, limit=16):
        return [
            CorporateCalendarEventRow(
                asset_id=asset_id,
                earnings_date=date.today() - timedelta(days=1),
                fiscal_year=2026,
                fiscal_quarter=1,
                time="amc",
                eps_estimated=1.5,
                eps_actual=1.7,
                revenue_estimated=90.0,
                revenue_actual=95.0,
                source="fake",
            )
        ]

    def fetch_quarterly_statements(self, asset_id, limit=16):
        return [
            FinancialStatementRow(
                asset_id=asset_id,
                statement_type="income",
                fiscal_year=2026,
                fiscal_quarter=1,
                period_end_date=date(2026, 3, 31),
                report_date=date.today(),
                data_json={"revenue": 95.0, "eps": 1.7},
                source="fake",
            )
        ]


def make_conn():
    conn = duckdb.connect(":memory:")

    conn.execute("CREATE SEQUENCE seq_ingestion_job_id START 1")

    conn.execute("""
        CREATE TABLE asset (
            asset_id TEXT PRIMARY KEY,
            asset_type TEXT,
            ccy TEXT DEFAULT 'USD',
            track BOOLEAN DEFAULT TRUE
        )
    """)

    conn.execute("""
        CREATE TABLE ingestion_job (
            job_id BIGINT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            domain TEXT NOT NULL,
            job_type TEXT NOT NULL,
            dataset TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            priority INTEGER NOT NULL DEFAULT 0,
            requested_start_date DATE,
            requested_end_date DATE,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        )
    """)

    conn.execute("""
        CREATE TABLE asset_sync_state (
            asset_id TEXT NOT NULL,
            domain TEXT NOT NULL,
            dataset TEXT NOT NULL,
            backfill_status TEXT NOT NULL DEFAULT 'not_started',
            backfill_start_date DATE,
            backfill_end_date DATE,
            last_successful_date DATE,
            last_attempted_at TIMESTAMP,
            last_successful_at TIMESTAMP,
            last_error TEXT,
            needs_repair BOOLEAN NOT NULL DEFAULT FALSE,
            PRIMARY KEY(asset_id, domain, dataset)
        )
    """)

    conn.execute("""
        CREATE TABLE earnings_calendar_event (
            asset_id TEXT NOT NULL,
            earnings_date DATE NOT NULL,
            fiscal_year INTEGER,
            fiscal_quarter INTEGER,
            time TEXT,
            eps_estimated DOUBLE,
            eps_actual DOUBLE,
            revenue_estimated DOUBLE,
            revenue_actual DOUBLE,
            source TEXT NOT NULL,
            as_of_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(asset_id, earnings_date)
        )
    """)

    conn.execute("""
        CREATE TABLE financial_statement (
            asset_id TEXT NOT NULL,
            statement_type TEXT NOT NULL,
            year INTEGER NOT NULL,
            quarter INTEGER NOT NULL,
            period_end_date DATE,
            report_date DATE,
            data_json JSON,
            source TEXT NOT NULL,
            ingested_at_utc TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(asset_id, statement_type, year, quarter)
        )
    """)

    conn.execute("""
        INSERT INTO asset(asset_id, asset_type, ccy, track)
        VALUES ('AAPL', 'stock', 'USD', TRUE)
    """)

    return conn


def test_stage_1_calendar_refresh_enqueues_and_ingests_event():
    conn = make_conn()
    service = CorporateCalendarIngestionService(conn, provider=FakeCorporateProvider())

    job_ids = service.enqueue_calendar_refresh()
    assert len(job_ids) == 1

    done = service.process_jobs(max_jobs=1)
    assert done == 1

    row = conn.execute("""
        SELECT asset_id, eps_estimated, eps_actual
        FROM earnings_calendar_event
        WHERE asset_id = 'AAPL'
    """).fetchone()

    assert row == ("AAPL", 2.0, None)


def test_stage_2_due_earnings_update_appends_actuals_and_financials():
    conn = make_conn()

    conn.execute("""
        INSERT INTO earnings_calendar_event(
            asset_id,
            earnings_date,
            fiscal_year,
            fiscal_quarter,
            source
        )
        VALUES ('AAPL', ?, 2026, 1, 'fake')
    """, [date.today() - timedelta(days=1)])

    service = CorporateCalendarIngestionService(conn, provider=FakeCorporateProvider())

    job_ids = service.enqueue_due_earnings_updates(lookback_days=14, max_assets=10)
    assert len(job_ids) == 2

    done = service.process_jobs(max_jobs=2)
    assert done == 2

    eps_actual = conn.execute("""
        SELECT eps_actual
        FROM earnings_calendar_event
        WHERE asset_id = 'AAPL'
          AND earnings_date = ?
    """, [date.today() - timedelta(days=1)]).fetchone()[0]

    assert eps_actual == 1.7

    stmt = conn.execute("""
        SELECT statement_type, year, quarter
        FROM financial_statement
        WHERE asset_id = 'AAPL'
    """).fetchone()

    assert stmt == ("income", 2026, 1)


def test_stage_3_backfill_enqueues_earnings_and_statement_jobs():
    conn = make_conn()
    service = CorporateCalendarIngestionService(conn, provider=FakeCorporateProvider())

    job_ids = service.enqueue_backfill(years=10)
    assert len(job_ids) == 2

    done = service.process_jobs(max_jobs=2)
    assert done == 2

    statuses = conn.execute("""
        SELECT status, COUNT(*)
        FROM ingestion_job
        GROUP BY status
    """).fetchall()

    assert statuses == [("done", 2)]

def test_scheduler_calendar_refresh_only_runs_when_due():
    conn = make_conn()
    service = CorporateCalendarIngestionService(conn, provider=FakeCorporateProvider())

    first_job_ids = service.schedule_calendar_refresh_if_due()
    assert len(first_job_ids) == 1

    # Pending job already exists, so no duplicate calendar refresh job.
    second_job_ids = service.schedule_calendar_refresh_if_due()
    assert len(second_job_ids) == 0

    done = service.process_jobs(max_jobs=1)
    assert done == 1

    # Just succeeded, so still no duplicate refresh.
    third_job_ids = service.schedule_calendar_refresh_if_due()
    assert len(third_job_ids) == 0

def test_scheduler_enqueues_fundamental_updates_after_earnings_event():
    conn = make_conn()
    service = CorporateCalendarIngestionService(conn, provider=FakeCorporateProvider())

    conn.execute("""
        INSERT INTO earnings_calendar_event (
            asset_id,
            earnings_date,
            fiscal_year,
            fiscal_quarter,
            source
        )
        VALUES ('AAPL', ?, 2026, 1, 'fake')
    """, [date.today() - timedelta(days=1)])

    job_ids = service.schedule_fundamental_updates_after_events(
        lookback_days=14,
        max_assets=10,
    )

    assert len(job_ids) == 2

    rows = conn.execute("""
        SELECT dataset, status
        FROM ingestion_job
        WHERE domain = 'corporate'
        ORDER BY dataset
    """).fetchall()

    assert rows == [
        ("earnings_actuals", "pending"),
        ("financial_statements", "pending"),
    ]

def test_worker_processes_post_event_fundamental_jobs():
    conn = make_conn()
    service = CorporateCalendarIngestionService(conn, provider=FakeCorporateProvider())

    conn.execute("""
        INSERT INTO earnings_calendar_event (
            asset_id,
            earnings_date,
            fiscal_year,
            fiscal_quarter,
            source
        )
        VALUES ('AAPL', ?, 2026, 1, 'fake')
    """, [date.today() - timedelta(days=1)])

    job_ids = service.schedule_fundamental_updates_after_events(
        lookback_days=14,
        max_assets=10,
    )

    assert len(job_ids) == 2

    done = service.process_jobs(max_jobs=2)
    assert done == 2

    eps_actual = conn.execute("""
        SELECT eps_actual
        FROM earnings_calendar_event
        WHERE asset_id = 'AAPL'
          AND earnings_date = ?
    """, [date.today() - timedelta(days=1)]).fetchone()[0]

    assert eps_actual == 1.7

    statement_row = conn.execute("""
        SELECT statement_type, year, quarter
        FROM financial_statement
        WHERE asset_id = 'AAPL'
    """).fetchone()

    assert statement_row == ("income", 2026, 1)


def test_scheduler_recurring_fundamental_refreshes_respect_ticker_universe():
    conn = make_conn()
    ensure_fundamental_phase1_schema(conn)
    service = CorporateCalendarIngestionService(conn, provider=FakeCorporateProvider())

    conn.execute(
        """
        INSERT INTO asset(asset_id, asset_type, ccy, track)
        VALUES
            ('MSFT', 'stock', 'USD', TRUE),
            ('SPY', 'etf', 'USD', TRUE)
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
        INSERT INTO portfolio_ticker(portfolio_id, asset_id, is_active, source)
        VALUES (1, 'AAPL', TRUE, 'position')
        """
    )
    conn.execute(
        """
        INSERT INTO watchlist_ticker(asset_id, is_active, source)
        VALUES
            ('MSFT', FALSE, 'manual'),
            ('SPY', TRUE, 'manual')
        """
    )
    conn.execute(
        """
        INSERT INTO fundamental_subscription(asset_id, is_active, next_refresh_at)
        VALUES
            ('AAPL', TRUE, now() - INTERVAL 1 DAY),
            ('MSFT', TRUE, now() - INTERVAL 1 DAY),
            ('SPY', TRUE, now() - INTERVAL 1 DAY)
        """
    )

    job_ids = service.schedule_calendar_refresh_if_due()
    assert len(job_ids) == 1

    recurring_ids = service.schedule_fundamental_updates_after_events()
    assert recurring_ids == []

    recurring_ids = service.schedule_calendar_refresh_if_due()
    assert recurring_ids == []

    scheduler_ids = service.schedule_fundamental_updates_after_events()
    assert scheduler_ids == []

    subscription_ids = service.schedule_due_fundamental_subscription_refreshes(
        max_assets=10
    )

    rows = conn.execute(
        """
        SELECT asset_id, job_type, dataset, status
        FROM ingestion_job
        WHERE dataset = 'financial_statements'
        ORDER BY asset_id
        """
    ).fetchall()

    assert len(subscription_ids) == 1
    assert rows == [
        ("AAPL", "refresh", "financial_statements", "pending"),
    ]


def test_scheduler_fundamental_backfill_queues_only_active_subscribed_universe_assets():
    conn = make_conn()
    ensure_fundamental_phase1_schema(conn)
    service = CorporateCalendarIngestionService(conn, provider=FakeCorporateProvider())

    conn.execute(
        """
        INSERT INTO asset(asset_id, asset_type, ccy, track)
        VALUES
            ('MSFT', 'stock', 'USD', TRUE),
            ('SPY', 'etf', 'USD', TRUE)
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
        INSERT INTO portfolio_ticker(portfolio_id, asset_id, is_active, source)
        VALUES (1, 'AAPL', TRUE, 'position')
        """
    )
    conn.execute(
        """
        INSERT INTO watchlist_ticker(asset_id, is_active, source)
        VALUES
            ('MSFT', TRUE, 'manual'),
            ('SPY', TRUE, 'manual')
        """
    )
    conn.execute(
        """
        INSERT INTO fundamental_subscription(asset_id, is_active, next_refresh_at)
        VALUES
            ('AAPL', TRUE, now()),
            ('MSFT', FALSE, now()),
            ('SPY', TRUE, now())
        """
    )

    job_ids = service.schedule_due_fundamental_subscription_backfills(max_assets=10)

    rows = conn.execute(
        """
        SELECT asset_id, job_type, dataset, status
        FROM ingestion_job
        ORDER BY asset_id
        """
    ).fetchall()

    assert len(job_ids) == 1
    assert rows == [
        ("AAPL", "backfill", "financial_statements", "pending"),
    ]

    requested_at = conn.execute(
        """
        SELECT last_backfill_requested_at
        FROM fundamental_subscription
        WHERE asset_id = 'AAPL'
        """
    ).fetchone()[0]

    assert requested_at is not None


def test_scheduler_fundamental_backfill_does_not_duplicate_open_jobs():
    conn = make_conn()
    ensure_fundamental_phase1_schema(conn)
    service = CorporateCalendarIngestionService(conn, provider=FakeCorporateProvider())

    conn.execute(
        """
        INSERT INTO fundamental_subscription(asset_id, is_active, next_refresh_at)
        VALUES ('AAPL', TRUE, now())
        """
    )

    first_job_ids = service.schedule_due_fundamental_subscription_backfills(max_assets=10)
    second_job_ids = service.schedule_due_fundamental_subscription_backfills(max_assets=10)

    count = conn.execute(
        """
        SELECT COUNT(*)
        FROM ingestion_job
        WHERE job_type = 'backfill'
          AND dataset = 'financial_statements'
        """
    ).fetchone()[0]

    assert len(first_job_ids) == 1
    assert second_job_ids == []
    assert count == 1


def test_worker_marks_fundamental_backfill_succeeded_after_statement_ingestion():
    conn = make_conn()
    ensure_fundamental_phase1_schema(conn)
    service = CorporateCalendarIngestionService(conn, provider=FakeCorporateProvider())

    conn.execute(
        """
        INSERT INTO fundamental_subscription(asset_id, is_active, next_refresh_at)
        VALUES ('AAPL', TRUE, now())
        """
    )

    job_ids = service.schedule_due_fundamental_subscription_backfills(max_assets=10)
    assert len(job_ids) == 1

    processed = service.process_jobs(max_jobs=1)

    subscription_row = conn.execute(
        """
        SELECT last_backfill_requested_at, last_backfill_succeeded_at
        FROM fundamental_subscription
        WHERE asset_id = 'AAPL'
        """
    ).fetchone()
    statement_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM financial_statement
        WHERE asset_id = 'AAPL'
        """
    ).fetchone()[0]

    assert processed == 1
    assert subscription_row[0] is not None
    assert subscription_row[1] is not None
    assert statement_count == 1


def test_worker_marks_fundamental_refresh_succeeded_after_statement_ingestion():
    conn = make_conn()
    ensure_fundamental_phase1_schema(conn)
    service = CorporateCalendarIngestionService(conn, provider=FakeCorporateProvider())

    conn.execute(
        """
        INSERT INTO fundamental_subscription(asset_id, is_active, next_refresh_at)
        VALUES ('AAPL', TRUE, now() - INTERVAL 1 DAY)
        """
    )

    job_ids = service.schedule_due_fundamental_subscription_refreshes(max_assets=10)
    assert len(job_ids) == 1

    processed = service.process_jobs(max_jobs=1)

    last_refresh_succeeded_at = conn.execute(
        """
        SELECT last_refresh_succeeded_at
        FROM fundamental_subscription
        WHERE asset_id = 'AAPL'
        """
    ).fetchone()[0]

    assert processed == 1
    assert last_refresh_succeeded_at is not None
