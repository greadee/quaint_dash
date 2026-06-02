"""Scheduler helpers for sentiment ingestion jobs."""

from __future__ import annotations

from datetime import date

from dashboard.ingestion.ticker_universe import TickerUniverseRepository
from dashboard.ingestion_sentiment.constants import (
    DATASET_FACTOR_SNAPSHOT,
    DATASET_NEWS,
    DATASET_QUANT_RATING,
    DATASET_REDDIT,
    DATASET_SENTIMENT_DAILY,
    DATASET_X,
    JOB_TYPE_FACTOR_SNAPSHOT_REFRESH,
    JOB_TYPE_NEWS_PROVIDER_REFRESH,
    JOB_TYPE_NEWS_RSS_REFRESH,
    JOB_TYPE_QUANT_RATING_REFRESH,
    JOB_TYPE_SENTIMENT_DAILY_AGGREGATE,
    JOB_TYPE_SENTIMENT_REDDIT_REFRESH,
    JOB_TYPE_SENTIMENT_X_REFRESH,
    PRIORITY_DAILY_AGGREGATE,
    PRIORITY_FACTOR_REFRESH,
    PRIORITY_NEWS_REFRESH,
    PRIORITY_QUANT_REFRESH,
    PRIORITY_RETAIL_REFRESH,
)
from dashboard.ingestion_sentiment.repo import SentimentIngestionRepository
from dashboard.ingestion_sentiment.worker import SentimentIngestionWorker


class SentimentIngestionScheduler:
    def __init__(self, conn) -> None:
        self.conn = conn
        self.repo = SentimentIngestionRepository(conn)
        self.universe = TickerUniverseRepository(conn)

    def enqueue_news_refresh_for_universe(
        self,
        universe_type: str = "all",
        today: date | None = None,
        provider_kind: str = "rss",
    ) -> list[int]:
        job_type = (
            JOB_TYPE_NEWS_RSS_REFRESH
            if provider_kind == "rss"
            else JOB_TYPE_NEWS_PROVIDER_REFRESH
        )
        return [
            self.repo.create_job(
                asset_id=asset_id,
                job_type=job_type,
                dataset=DATASET_NEWS,
                priority=PRIORITY_NEWS_REFRESH,
                start_date=today,
                end_date=today,
            )
            for asset_id in self._asset_ids_for_universe(universe_type)
        ]

    def enqueue_retail_sentiment_refresh_for_universe(
        self,
        universe_type: str = "all",
        today: date | None = None,
        source: str = "all",
    ) -> list[int]:
        job_specs: list[tuple[str, str]] = []
        if source in {"all", "reddit"}:
            job_specs.append((JOB_TYPE_SENTIMENT_REDDIT_REFRESH, DATASET_REDDIT))
        if source in {"all", "x"}:
            job_specs.append((JOB_TYPE_SENTIMENT_X_REFRESH, DATASET_X))

        job_ids: list[int] = []
        for asset_id in self._asset_ids_for_universe(universe_type):
            for job_type, dataset in job_specs:
                job_ids.append(
                    self.repo.create_job(
                        asset_id=asset_id,
                        job_type=job_type,
                        dataset=dataset,
                        priority=PRIORITY_RETAIL_REFRESH,
                        start_date=today,
                        end_date=today,
                    )
                )
        return job_ids

    def enqueue_daily_sentiment_aggregation(
        self,
        universe_type: str = "all",
        snapshot_date: date | None = None,
    ) -> list[int]:
        return self._enqueue_snapshot_jobs(
            universe_type=universe_type,
            job_type=JOB_TYPE_SENTIMENT_DAILY_AGGREGATE,
            dataset=DATASET_SENTIMENT_DAILY,
            priority=PRIORITY_DAILY_AGGREGATE,
            snapshot_date=snapshot_date,
        )

    def enqueue_factor_snapshot_refresh(
        self,
        universe_type: str = "all",
        snapshot_date: date | None = None,
    ) -> list[int]:
        return self._enqueue_snapshot_jobs(
            universe_type=universe_type,
            job_type=JOB_TYPE_FACTOR_SNAPSHOT_REFRESH,
            dataset=DATASET_FACTOR_SNAPSHOT,
            priority=PRIORITY_FACTOR_REFRESH,
            snapshot_date=snapshot_date,
        )

    def enqueue_quant_rating_refresh(
        self,
        universe_type: str = "all",
        snapshot_date: date | None = None,
    ) -> list[int]:
        return self._enqueue_snapshot_jobs(
            universe_type=universe_type,
            job_type=JOB_TYPE_QUANT_RATING_REFRESH,
            dataset=DATASET_QUANT_RATING,
            priority=PRIORITY_QUANT_REFRESH,
            snapshot_date=snapshot_date,
        )

    def run_sentiment_jobs(self, max_jobs: int = 1) -> int:
        return SentimentIngestionWorker(self.conn).process_jobs(max_jobs=max_jobs)

    def _enqueue_snapshot_jobs(
        self,
        universe_type: str,
        job_type: str,
        dataset: str,
        priority: int,
        snapshot_date: date | None,
    ) -> list[int]:
        return [
            self.repo.create_job(
                asset_id=asset_id,
                job_type=job_type,
                dataset=dataset,
                priority=priority,
                start_date=snapshot_date,
                end_date=snapshot_date,
            )
            for asset_id in self._asset_ids_for_universe(universe_type)
        ]

    def _asset_ids_for_universe(self, universe_type: str) -> list[str]:
        universe_type = universe_type.lower()
        if universe_type == "portfolio":
            return self.universe.portfolio_asset_ids()
        if universe_type == "watchlist":
            return self.universe.watchlist_asset_ids()
        if universe_type == "all":
            return [asset.asset_id for asset in self.repo.asset_refs()]
        raise ValueError(f"Unsupported sentiment universe: {universe_type}")

