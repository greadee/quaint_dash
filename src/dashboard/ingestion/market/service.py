"""
service layer for Domain A market job enqueueing and worker execution
    higher level entry point for the cli
"""

from __future__ import annotations

from datetime import date, timedelta

from dashboard.ingestion.market.jobs_repo import (
    enqueue_market_backfill_for_all_assets,
    enqueue_market_backfill_jobs,
    enqueue_market_refresh_for_all_assets,
    enqueue_market_refresh_jobs,
)
from dashboard.ingestion.market.provider_fmp import FMPMarketProvider
from dashboard.ingestion.market.db.ingestion_repo import MarketIngestionRepository
from dashboard.ingestion.market.backfill_worker import MarketBackfillWorker
from dashboard.ingestion.market.refresh_worker import MarketRefreshWorker


class MarketIngestionService:
    """
    service wrapper for Domain A enqueue and processing actions
    """

    def __init__(self, conn, provider: FMPMarketProvider | None = None) -> None:
        self.conn = conn
        self.repo = MarketIngestionRepository(conn)
        self.provider = provider or FMPMarketProvider()

    def enqueue_backfill_one(
        self,
        asset_id: str,
        years: int = 10,
        include_dividends: bool = True,
        include_splits: bool = True,
    ) -> list[int]:
        end_date = date.today()
        start_date = end_date - timedelta(days=365 * years)

        return enqueue_market_backfill_jobs(
            repo=self.repo,
            asset_id=asset_id,
            start_date=start_date,
            end_date=end_date,
            include_dividends=include_dividends,
            include_splits=include_splits,
        )

    def enqueue_backfill_all(
        self,
        years: int = 10,
        include_dividends: bool = True,
        include_splits: bool = True,
    ) -> list[int]:
        end_date = date.today()
        start_date = end_date - timedelta(days=365 * years)

        return enqueue_market_backfill_for_all_assets(
            repo=self.repo,
            start_date=start_date,
            end_date=end_date,
            include_dividends=include_dividends,
            include_splits=include_splits,
        )

    def enqueue_refresh_one(
        self,
        asset_id: str,
        include_dividends: bool = True,
        include_splits: bool = True,
    ) -> list[int]:
        end_date = date.today()
        return enqueue_market_refresh_jobs(
            repo=self.repo,
            asset_id=asset_id,
            end_date=end_date,
            include_dividends=include_dividends,
            include_splits=include_splits,
        )

    def enqueue_refresh_all(
        self,
        include_dividends: bool = True,
        include_splits: bool = True,
    ) -> list[int]:
        end_date = date.today()
        return enqueue_market_refresh_for_all_assets(
            repo=self.repo,
            end_date=end_date,
            include_dividends=include_dividends,
            include_splits=include_splits,
        )

    def process_backfill_jobs(self, max_jobs: int = 1) -> int:
        worker = MarketBackfillWorker(self.conn, self.provider)
        completed = 0
        for _ in range(max_jobs):
            did_work = worker.run_once()
            if not did_work:
                break
            completed += 1
        return completed

    def process_refresh_jobs(self, max_jobs: int = 1) -> int:
        worker = MarketRefreshWorker(self.conn, self.provider)
        completed = 0
        for _ in range(max_jobs):
            did_work = worker.run_once()
            if not did_work:
                break
            completed += 1
        return completed