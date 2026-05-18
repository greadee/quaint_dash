"""
job creation helpers for Domain A market ingestion
"""

from __future__ import annotations

from datetime import date, timedelta

from dashboard.ingestion.market.constants import (
    DATASET_DIVIDENDS,
    DATASET_PRICE_DAILY,
    DATASET_SPLITS,
    JOB_TYPE_BACKFILL,
    JOB_TYPE_REFRESH,
    PRIORITY_MARKET_BACKFILL_DIVIDENDS,
    PRIORITY_MARKET_BACKFILL_PRICE,
    PRIORITY_MARKET_BACKFILL_SPLITS,
    PRIORITY_MARKET_REFRESH_DIVIDENDS,
    PRIORITY_MARKET_REFRESH_PRICE,
    PRIORITY_MARKET_REFRESH_SPLITS,
)
from dashboard.ingestion.market.db.ingestion_repo import MarketIngestionRepository


def enqueue_market_backfill_jobs(
    repo: MarketIngestionRepository,
    asset_id: str,
    start_date: date,
    end_date: date,
    include_dividends: bool = True,
    include_splits: bool = True,
) -> list[int]:
    """
    enqueue market backfill jobs for one asset
    """
    job_ids: list[int] = []

    job_ids.append(
        repo.create_job(
            asset_id=asset_id,
            job_type=JOB_TYPE_BACKFILL,
            dataset=DATASET_PRICE_DAILY,
            priority=PRIORITY_MARKET_BACKFILL_PRICE,
            start_date=start_date,
            end_date=end_date,
        )
    )

    if include_dividends:
        job_ids.append(
            repo.create_job(
                asset_id=asset_id,
                job_type=JOB_TYPE_BACKFILL,
                dataset=DATASET_DIVIDENDS,
                priority=PRIORITY_MARKET_BACKFILL_DIVIDENDS,
                start_date=start_date,
                end_date=end_date,
            )
        )

    if include_splits:
        job_ids.append(
            repo.create_job(
                asset_id=asset_id,
                job_type=JOB_TYPE_BACKFILL,
                dataset=DATASET_SPLITS,
                priority=PRIORITY_MARKET_BACKFILL_SPLITS,
                start_date=start_date,
                end_date=end_date,
            )
        )

    return job_ids


def enqueue_market_refresh_jobs(
    repo: MarketIngestionRepository,
    asset_id: str,
    end_date: date,
    lookback_days_if_empty: int = 30,
    include_dividends: bool = True,
    include_splits: bool = True,
) -> list[int]:
    """
    enqueue refresh jobs for one asset based on latest stored date
    """
    job_ids: list[int] = []

    # price refresh
    latest_price = repo.get_latest_dataset_date(asset_id, DATASET_PRICE_DAILY)
    start_price = (latest_price + timedelta(days=1)) if latest_price else (end_date - timedelta(days=lookback_days_if_empty))
    if start_price <= end_date:
        job_ids.append(
            repo.create_job(
                asset_id=asset_id,
                job_type=JOB_TYPE_REFRESH,
                dataset=DATASET_PRICE_DAILY,
                priority=PRIORITY_MARKET_REFRESH_PRICE,
                start_date=start_price,
                end_date=end_date,
            )
        )

    if include_dividends:
        latest_div = repo.get_latest_dataset_date(asset_id, DATASET_DIVIDENDS)
        start_div = (latest_div + timedelta(days=1)) if latest_div else (end_date - timedelta(days=365))
        if start_div <= end_date:
            job_ids.append(
                repo.create_job(
                    asset_id=asset_id,
                    job_type=JOB_TYPE_REFRESH,
                    dataset=DATASET_DIVIDENDS,
                    priority=PRIORITY_MARKET_REFRESH_DIVIDENDS,
                    start_date=start_div,
                    end_date=end_date,
                )
            )

    if include_splits:
        latest_split = repo.get_latest_dataset_date(asset_id, DATASET_SPLITS)
        start_split = (latest_split + timedelta(days=1)) if latest_split else (end_date - timedelta(days=365))
        if start_split <= end_date:
            job_ids.append(
                repo.create_job(
                    asset_id=asset_id,
                    job_type=JOB_TYPE_REFRESH,
                    dataset=DATASET_SPLITS,
                    priority=PRIORITY_MARKET_REFRESH_SPLITS,
                    start_date=start_split,
                    end_date=end_date,
                )
            )

    return job_ids


def enqueue_market_backfill_for_all_assets(
    repo: MarketIngestionRepository,
    start_date: date,
    end_date: date,
    include_dividends: bool = True,
    include_splits: bool = True,
) -> list[int]:
    """
    enqueue market backfill jobs for all assets
    """
    job_ids: list[int] = []
    for asset_id in repo.get_all_asset_ids():
        job_ids.extend(
            enqueue_market_backfill_jobs(
                repo=repo,
                asset_id=asset_id,
                start_date=start_date,
                end_date=end_date,
                include_dividends=include_dividends,
                include_splits=include_splits,
            )
        )
    return job_ids


def enqueue_market_refresh_for_all_assets(
    repo: MarketIngestionRepository,
    end_date: date,
    include_dividends: bool = True,
    include_splits: bool = True,
) -> list[int]:
    """
    enqueue market refresh jobs for all assets
    """
    job_ids: list[int] = []
    for asset_id in repo.get_all_asset_ids():
        job_ids.extend(
            enqueue_market_refresh_jobs(
                repo=repo,
                asset_id=asset_id,
                end_date=end_date,
                include_dividends=include_dividends,
                include_splits=include_splits,
            )
        )
    return job_ids