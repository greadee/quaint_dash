from __future__ import annotations

from datetime import datetime

from dashboard.db.db_conn import DB, init_db
from dashboard.ingestion_sentiment.constants import (
    DATASET_REDDIT,
    JOB_TYPE_SENTIMENT_REDDIT_REFRESH,
    PRIORITY_RETAIL_REFRESH,
)
from dashboard.ingestion_sentiment.models import SocialPostInput
from dashboard.ingestion_sentiment.repo import SentimentIngestionRepository
from dashboard.ingestion_sentiment.service import SentimentIngestionService
from dashboard.ingestion_sentiment.worker import SentimentIngestionWorker


class FakeRedditProvider:
    name = "reddit"

    def fetch_posts_for_ticker(self, ticker: str, since: datetime | None):
        return [
            SocialPostInput(
                provider="reddit",
                source_post_id="worker-post-1",
                source_name="reddit",
                body=f"${ticker} looks bullish and strong.",
                published_at=datetime(2026, 1, 5, 12, 0),
            )
        ]


class FailingRedditProvider:
    name = "reddit"

    def fetch_posts_for_ticker(self, ticker: str, since: datetime | None):
        raise RuntimeError("provider unavailable")


def test_sentiment_worker_processes_job_with_fake_provider(tmp_path):
    db = DB(str(tmp_path / "sentiment_worker.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES ('AMD', 'AMD', 'stock', 'USD')
        """
    )
    repo = SentimentIngestionRepository(db.conn)
    job_id = repo.create_job(
        asset_id="AMD",
        job_type=JOB_TYPE_SENTIMENT_REDDIT_REFRESH,
        dataset=DATASET_REDDIT,
        priority=PRIORITY_RETAIL_REFRESH,
    )
    service = SentimentIngestionService(
        db.conn,
        social_providers=[FakeRedditProvider()],
    )
    worker = SentimentIngestionWorker(db.conn, service=service)

    processed = worker.process_jobs(max_jobs=1)

    status = db.conn.execute(
        "SELECT status FROM ingestion_job WHERE job_id = ?",
        [job_id],
    ).fetchone()[0]
    observation_count = db.conn.execute(
        "SELECT COUNT(*) FROM sentiment_observation"
    ).fetchone()[0]

    assert processed == 1
    assert status == "done"
    assert observation_count == 1


def test_sentiment_worker_failure_counts_toward_max_jobs(tmp_path):
    db = DB(str(tmp_path / "sentiment_worker_failure.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES
            ('AMD', 'AMD', 'stock', 'USD'),
            ('NVDA', 'NVDA', 'stock', 'USD')
        """
    )
    repo = SentimentIngestionRepository(db.conn)
    for asset_id in ["AMD", "NVDA"]:
        repo.create_job(
            asset_id=asset_id,
            job_type=JOB_TYPE_SENTIMENT_REDDIT_REFRESH,
            dataset=DATASET_REDDIT,
            priority=PRIORITY_RETAIL_REFRESH,
        )
    service = SentimentIngestionService(
        db.conn,
        social_providers=[FailingRedditProvider()],
    )
    worker = SentimentIngestionWorker(db.conn, service=service)

    processed = worker.process_jobs(max_jobs=1)

    rows = db.conn.execute(
        """
        SELECT asset_id, status, error_message
        FROM ingestion_job
        ORDER BY asset_id
        """
    ).fetchall()
    assert processed == 0
    assert rows[0] == ("AMD", "failed", "provider unavailable")
    assert rows[1] == ("NVDA", "pending", None)
