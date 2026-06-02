"""Worker for processing queued sentiment ingestion jobs."""

from __future__ import annotations

from datetime import date

from dashboard.ingestion_sentiment.constants import (
    JOB_TYPE_FACTOR_SNAPSHOT_REFRESH,
    JOB_TYPE_NEWS_PROVIDER_REFRESH,
    JOB_TYPE_NEWS_RSS_REFRESH,
    JOB_TYPE_QUANT_RATING_REFRESH,
    JOB_TYPE_SENTIMENT_DAILY_AGGREGATE,
    JOB_TYPE_SENTIMENT_REDDIT_REFRESH,
    JOB_TYPE_SENTIMENT_X_REFRESH,
)
from dashboard.ingestion_sentiment.repo import SentimentIngestionRepository
from dashboard.ingestion_sentiment.service import SentimentIngestionService


class SentimentIngestionWorker:
    def __init__(
        self,
        conn,
        service: SentimentIngestionService | None = None,
    ) -> None:
        self.conn = conn
        self.repo = SentimentIngestionRepository(conn)
        self.service = service or SentimentIngestionService(conn)

    def process_jobs(self, max_jobs: int = 1) -> int:
        processed = 0
        while processed < max_jobs:
            job = self.repo.claim_next_pending_job()
            if job is None:
                break

            try:
                self._process_job(job)
            except Exception as exc:
                self.repo.mark_job_failed(job.job_id, str(exc))
            else:
                self.repo.mark_job_done(job.job_id)
                processed += 1

        return processed

    def _process_job(self, job) -> None:
        ticker = job.asset_id
        snapshot_date = job.requested_end_date or date.today()

        if job.job_type == JOB_TYPE_SENTIMENT_REDDIT_REFRESH:
            self.service.refresh_social_for_ticker(ticker, provider_name="reddit")
            return

        if job.job_type == JOB_TYPE_SENTIMENT_X_REFRESH:
            self.service.refresh_social_for_ticker(ticker, provider_name="x")
            return

        if job.job_type in {JOB_TYPE_NEWS_RSS_REFRESH, JOB_TYPE_NEWS_PROVIDER_REFRESH}:
            self.service.refresh_news_for_ticker(ticker)
            return

        if job.job_type == JOB_TYPE_SENTIMENT_DAILY_AGGREGATE:
            self.service.aggregate_daily_sentiment(ticker, snapshot_date)
            return

        if job.job_type in {JOB_TYPE_FACTOR_SNAPSHOT_REFRESH, JOB_TYPE_QUANT_RATING_REFRESH}:
            return

        raise ValueError(f"Unsupported sentiment job type: {job.job_type}")

