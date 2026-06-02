from __future__ import annotations

from datetime import date, datetime

from dashboard.db.db_conn import DB, init_db
from dashboard.ingestion_sentiment.models import SentimentObservationInput
from dashboard.ingestion_sentiment.repo import SentimentIngestionRepository
from dashboard.ingestion_sentiment.scoring import DailySentimentAggregator


def test_daily_sentiment_aggregation_renormalizes_missing_buckets(tmp_path):
    db = DB(str(tmp_path / "sentiment_aggregation.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES ('AMD', 'AMD', 'stock', 'USD')
        """
    )
    repo = SentimentIngestionRepository(db.conn)
    observed_at = datetime(2026, 1, 5, 16, 0)

    repo.insert_sentiment_observation(
        SentimentObservationInput(
            asset_id="AMD",
            ticker="AMD",
            item_type="social_post",
            item_id=1,
            provider="reddit",
            sentiment_label="bullish",
            sentiment_score=0.8,
            confidence=1.0,
            observed_at=observed_at,
        )
    )
    repo.insert_sentiment_observation(
        SentimentObservationInput(
            asset_id="AMD",
            ticker="AMD",
            item_type="news_article",
            item_id=2,
            provider="fake-news",
            sentiment_label="neutral",
            sentiment_score=0.2,
            confidence=1.0,
            observed_at=observed_at,
        )
    )

    snapshot = DailySentimentAggregator(repo).aggregate_for_ticker(
        asset_id="AMD",
        ticker="AMD",
        snapshot_date=date(2026, 1, 5),
    )

    expected_blended = (0.8 * (0.35 / 0.80)) + (0.2 * (0.45 / 0.80))

    assert snapshot.retail_sentiment_score == 0.8
    assert snapshot.news_sentiment_score == 0.2
    assert snapshot.analyst_sentiment_score is None
    assert snapshot.blended_sentiment_score == expected_blended
    assert snapshot.reddit_post_count == 1
    assert snapshot.article_count == 1


def test_daily_sentiment_aggregation_computes_momentum(tmp_path):
    db = DB(str(tmp_path / "sentiment_momentum.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES ('AMD', 'AMD', 'stock', 'USD')
        """
    )
    repo = SentimentIngestionRepository(db.conn)
    previous = date(2026, 1, 4)
    today = date(2026, 1, 5)
    db.conn.execute(
        """
        INSERT INTO ticker_sentiment_daily(asset_id, ticker, date, blended_sentiment_score)
        VALUES ('AMD', 'AMD', ?, 0.1)
        """,
        [previous],
    )
    repo.insert_sentiment_observation(
        SentimentObservationInput(
            asset_id="AMD",
            ticker="AMD",
            item_type="social_post",
            item_id=1,
            provider="reddit",
            sentiment_label="bullish",
            sentiment_score=0.6,
            confidence=1.0,
            observed_at=datetime(2026, 1, 5, 16, 0),
        )
    )

    snapshot = DailySentimentAggregator(repo).aggregate_for_ticker("AMD", "AMD", today)

    assert snapshot.sentiment_momentum_1d == 0.5

