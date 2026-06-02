from __future__ import annotations

from datetime import date

from dashboard.db.db_conn import DB, init_db
from dashboard.ingestion_sentiment.scheduler import SentimentIngestionScheduler


def test_sentiment_scheduler_enqueues_expected_jobs(tmp_path):
    db = DB(str(tmp_path / "sentiment_scheduler.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES
            ('AMD', 'AMD', 'stock', 'USD'),
            ('NVDA', 'NVDA', 'stock', 'USD')
        """
    )
    scheduler = SentimentIngestionScheduler(db.conn)

    news_ids = scheduler.enqueue_news_refresh_for_universe(
        universe_type="all",
        today=date(2026, 1, 5),
    )
    retail_ids = scheduler.enqueue_retail_sentiment_refresh_for_universe(
        universe_type="all",
        today=date(2026, 1, 5),
    )
    aggregate_ids = scheduler.enqueue_daily_sentiment_aggregation(
        universe_type="all",
        snapshot_date=date(2026, 1, 5),
    )

    rows = db.conn.execute(
        """
        SELECT asset_id, job_type, dataset, status
        FROM ingestion_job
        WHERE domain = 'sentiment'
        ORDER BY asset_id, job_type
        """
    ).fetchall()

    assert len(news_ids) == 2
    assert len(retail_ids) == 4
    assert len(aggregate_ids) == 2
    assert rows == [
        ("AMD", "news_rss_refresh", "news", "pending"),
        ("AMD", "sentiment_daily_aggregate", "sentiment_daily", "pending"),
        ("AMD", "sentiment_reddit_refresh", "reddit", "pending"),
        ("AMD", "sentiment_x_refresh", "x", "pending"),
        ("NVDA", "news_rss_refresh", "news", "pending"),
        ("NVDA", "sentiment_daily_aggregate", "sentiment_daily", "pending"),
        ("NVDA", "sentiment_reddit_refresh", "reddit", "pending"),
        ("NVDA", "sentiment_x_refresh", "x", "pending"),
    ]

