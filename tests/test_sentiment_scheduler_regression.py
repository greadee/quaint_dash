"""Exercise the audited scheduler SQL on DuckDB using an isolated, real schema.

These checks deliberately execute the correlated queries, rather than mocking
their results, so an alias/binder regression prevents the scheduler from passing.
No provider requests or application database connections are involved.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from dashboard.db.db_conn import DB, init_db
from dashboard.ingestion_sentiment.constants import (
    DATASET_FACTOR_SNAPSHOT,
    DATASET_QUANT_RATING,
    DATASET_SENTIMENT_DAILY,
    JOB_TYPE_FACTOR_SNAPSHOT_REFRESH,
    JOB_TYPE_QUANT_RATING_REFRESH,
    JOB_TYPE_SENTIMENT_DAILY_AGGREGATE,
)
from dashboard.ingestion_sentiment.repo import SentimentIngestionRepository
from dashboard.models.storage import DashboardManager


SNAPSHOT_SPECS = [
    (
        "ticker_sentiment_daily",
        "date",
        DATASET_SENTIMENT_DAILY,
        JOB_TYPE_SENTIMENT_DAILY_AGGREGATE,
    ),
    (
        "ticker_factor_snapshot",
        "snapshot_date",
        DATASET_FACTOR_SNAPSHOT,
        JOB_TYPE_FACTOR_SNAPSHOT_REFRESH,
    ),
    (
        "ticker_quant_rating_snapshot",
        "snapshot_date",
        DATASET_QUANT_RATING,
        JOB_TYPE_QUANT_RATING_REFRESH,
    ),
]
SNAPSHOT_DATE = date(2026, 9, 7)
ASSET_IDS = [f"AUDIT_{letter}" for letter in "ABCDEFG"]


@pytest.fixture
def manager(tmp_path):
    db = DB(tmp_path / "scheduler-regression.duckdb")
    try:
        init_db(db)
        db.conn.executemany(
            """
            INSERT INTO asset(asset_id, symbol, asset_type, ccy, track)
            VALUES (?, ?, 'stock', 'USD', TRUE)
            """,
            [(asset_id, asset_id) for asset_id in ASSET_IDS],
        )
        yield DashboardManager(db)
    finally:
        db.conn.close()


def insert_snapshot(manager, spec, asset_id, snapshot_date):
    table_name, date_column, _, _ = spec
    manager.conn.execute(
        f"INSERT INTO {table_name}(asset_id, ticker, {date_column}) VALUES (?, ?, ?)",
        [asset_id, asset_id, snapshot_date],
    )


def due_assets(manager, spec, asset_ids=ASSET_IDS, max_assets=25):
    table_name, date_column, dataset, job_type = spec
    return manager._due_sentiment_snapshot_assets(
        asset_ids=asset_ids,
        dataset=dataset,
        job_type=job_type,
        table_name=table_name,
        date_column=date_column,
        snapshot_date=SNAPSHOT_DATE,
        max_assets=max_assets,
    )


@pytest.mark.parametrize("spec", SNAPSHOT_SPECS, ids=[spec[0] for spec in SNAPSHOT_SPECS])
def test_due_snapshot_query_scopes_current_snapshots_to_the_asset_and_date(manager, spec):
    insert_snapshot(manager, spec, "AUDIT_A", SNAPSHOT_DATE)
    insert_snapshot(manager, spec, "AUDIT_B", SNAPSHOT_DATE - timedelta(days=1))
    insert_snapshot(manager, spec, "AUDIT_C", SNAPSHOT_DATE + timedelta(days=1))
    insert_snapshot(manager, spec, "AUDIT_E", SNAPSHOT_DATE)

    # Only an exact-day snapshot satisfies the request. An unrelated asset's
    # snapshot cannot suppress another asset, and input order is not output order.
    assert due_assets(
        manager, spec, asset_ids=["AUDIT_D", "AUDIT_C", "AUDIT_A", "AUDIT_B"]
    ) == ["AUDIT_B", "AUDIT_C", "AUDIT_D"]
    assert due_assets(manager, spec, max_assets=1) == ["AUDIT_B"]
    assert due_assets(manager, spec, max_assets=0) == []


@pytest.mark.parametrize("spec", SNAPSHOT_SPECS, ids=[spec[0] for spec in SNAPSHOT_SPECS])
def test_open_jobs_deduplicate_only_the_matching_snapshot_work(manager, spec):
    _, _, dataset, job_type = spec
    repo = SentimentIngestionRepository(manager.conn)
    job_variants = [
        ("AUDIT_A", "pending", "sentiment", dataset, job_type),
        ("AUDIT_B", "running", "sentiment", dataset, job_type),
        ("AUDIT_C", "done", "sentiment", dataset, job_type),
        ("AUDIT_D", "failed", "sentiment", dataset, job_type),
        ("AUDIT_E", "pending", "market", dataset, job_type),
        ("AUDIT_F", "pending", "sentiment", "other_dataset", job_type),
        ("AUDIT_G", "pending", "sentiment", dataset, "other_job_type"),
    ]
    for asset_id, status, domain, job_dataset, job_kind in job_variants:
        job_id = repo.create_job(
            asset_id=asset_id,
            job_type=job_kind,
            dataset=job_dataset,
            priority=50,
            start_date=SNAPSHOT_DATE - timedelta(days=1),
            end_date=SNAPSHOT_DATE - timedelta(days=1),
        )
        manager.conn.execute(
            "UPDATE ingestion_job SET status = ?, domain = ? WHERE job_id = ?",
            [status, domain, job_id],
        )

    # Open work also blocks a newer requested date; done/failed work without a
    # current snapshot remains due. Unrelated pipelines do not block this one.
    assert due_assets(manager, spec) == ASSET_IDS[2:]


def test_scheduler_limits_each_family_and_advances_without_duplicating_open_jobs(manager):
    scheduled_date = date.today()

    # max_assets is an existing per-family limit, not a total job limit.
    assert manager.schedule_due_sentiment_snapshot_refreshes(max_assets=2) == 6
    assert manager.conn.execute(
        """
        SELECT DISTINCT asset_id, requested_start_date, requested_end_date
        FROM ingestion_job WHERE domain = 'sentiment' ORDER BY asset_id
        """
    ).fetchall() == [
        ("AUDIT_A", scheduled_date, scheduled_date),
        ("AUDIT_B", scheduled_date, scheduled_date),
    ]
    assert manager.schedule_due_sentiment_snapshot_refreshes(max_assets=2) == 6
    assert manager.schedule_due_sentiment_snapshot_refreshes(max_assets=25) == 9
    assert manager.schedule_due_sentiment_snapshot_refreshes(max_assets=25) == 0
    rows = manager.conn.execute(
        """
        SELECT asset_id, dataset, job_type, status, COUNT(*)
        FROM ingestion_job WHERE domain = 'sentiment'
        GROUP BY asset_id, dataset, job_type, status
        ORDER BY asset_id, dataset
        """
    ).fetchall()
    assert rows == sorted(
        (asset_id, dataset, job_type, "pending", 1)
        for asset_id in ASSET_IDS
        for _, _, dataset, job_type in SNAPSHOT_SPECS
    )


def test_scheduler_honors_snapshot_dates_independently_for_each_family(manager):
    scheduled_date = date.today()
    for spec, asset_id in zip(SNAPSHOT_SPECS, ASSET_IDS):
        insert_snapshot(manager, spec, asset_id, scheduled_date)

    assert manager.schedule_due_sentiment_snapshot_refreshes(max_assets=25) == 18
    rows = manager.conn.execute(
        """
        SELECT asset_id, dataset FROM ingestion_job
        WHERE domain = 'sentiment' ORDER BY asset_id, dataset
        """
    ).fetchall()
    satisfied = {(asset_id, spec[2]) for spec, asset_id in zip(SNAPSHOT_SPECS, ASSET_IDS)}
    assert rows == sorted(
        (asset_id, dataset)
        for asset_id in ASSET_IDS
        for _, _, dataset, _ in SNAPSHOT_SPECS
        if (asset_id, dataset) not in satisfied
    )
