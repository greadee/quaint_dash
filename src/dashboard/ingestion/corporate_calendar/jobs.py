"""
job creation helpers for corporate calendar ingestion
"""

from __future__ import annotations

from datetime import date

from dashboard.ingestion.corporate_calendar.constants import (
    DATASET_EARNINGS_ACTUALS,
    DATASET_EARNINGS_CALENDAR,
    DATASET_FINANCIAL_STATEMENTS,
    JOB_TYPE_BACKFILL,
    JOB_TYPE_CALENDAR_REFRESH,
    JOB_TYPE_EARNINGS_UPDATE,
    PRIORITY_CALENDAR_REFRESH,
    PRIORITY_CORPORATE_BACKFILL,
    PRIORITY_EARNINGS_UPDATE,
)
from dashboard.ingestion.corporate_calendar.db.ingestion_repo import (
    CorporateCalendarIngestionRepository,
)


def enqueue_calendar_refresh_jobs(
    repo: CorporateCalendarIngestionRepository,
    start_date: date,
    end_date: date,
) -> list[int]:
    job_ids: list[int] = []

    for asset_id in repo.get_tracked_stock_asset_ids():
        job_ids.append(
            repo.create_job(
                asset_id=asset_id,
                job_type=JOB_TYPE_CALENDAR_REFRESH,
                dataset=DATASET_EARNINGS_CALENDAR,
                priority=PRIORITY_CALENDAR_REFRESH,
                start_date=start_date,
                end_date=end_date,
            )
        )

    return job_ids


def enqueue_earnings_update_jobs(
    repo: CorporateCalendarIngestionRepository,
    today: date,
    lookback_days: int = 14,
    max_assets: int = 25,
) -> list[int]:
    job_ids: list[int] = []

    asset_ids = repo.select_due_earnings_update_asset_ids(
        today=today,
        lookback_days=lookback_days,
        limit=max_assets,
    )

    for asset_id in asset_ids:
        job_ids.append(
            repo.create_job(
                asset_id=asset_id,
                job_type=JOB_TYPE_EARNINGS_UPDATE,
                dataset=DATASET_EARNINGS_ACTUALS,
                priority=PRIORITY_EARNINGS_UPDATE,
                start_date=today,
                end_date=today,
            )
        )

        job_ids.append(
            repo.create_job(
                asset_id=asset_id,
                job_type=JOB_TYPE_EARNINGS_UPDATE,
                dataset=DATASET_FINANCIAL_STATEMENTS,
                priority=PRIORITY_EARNINGS_UPDATE - 1,
                start_date=today,
                end_date=today,
            )
        )

    return job_ids


def enqueue_corporate_backfill_jobs(
    repo: CorporateCalendarIngestionRepository,
    start_date: date,
    end_date: date,
) -> list[int]:
    job_ids: list[int] = []

    for asset_id in repo.get_tracked_stock_asset_ids():
        job_ids.append(
            repo.create_job(
                asset_id=asset_id,
                job_type=JOB_TYPE_BACKFILL,
                dataset=DATASET_EARNINGS_ACTUALS,
                priority=PRIORITY_CORPORATE_BACKFILL,
                start_date=start_date,
                end_date=end_date,
            )
        )

        job_ids.append(
            repo.create_job(
                asset_id=asset_id,
                job_type=JOB_TYPE_BACKFILL,
                dataset=DATASET_FINANCIAL_STATEMENTS,
                priority=PRIORITY_CORPORATE_BACKFILL - 1,
                start_date=start_date,
                end_date=end_date,
            )
        )

    return job_ids