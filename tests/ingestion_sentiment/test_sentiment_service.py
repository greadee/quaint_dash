from __future__ import annotations

from datetime import datetime

from dashboard.db.db_conn import DB, init_db
from dashboard.ingestion_sentiment.models import NewsArticleInput, SocialPostInput
from dashboard.ingestion_sentiment.service import SentimentIngestionService


class FakeNewsProvider:
    name = "fake-news"

    def fetch_articles_for_ticker(self, ticker: str, since: datetime | None):
        return [
            NewsArticleInput(
                source_item_id="news-1",
                source_name="Fake News",
                provider=self.name,
                title=f"${ticker} beats expectations",
                summary="Strong growth and upside.",
                published_at=datetime(2026, 1, 5, 12, 0),
            )
        ]


class FakeSocialProvider:
    name = "reddit"

    def fetch_posts_for_ticker(self, ticker: str, since: datetime | None):
        return [
            SocialPostInput(
                provider=self.name,
                source_post_id="post-1",
                source_name="reddit",
                title=f"{ticker} earnings",
                body=f"Bullish on ${ticker} after strong guidance.",
                published_at=datetime(2026, 1, 5, 13, 0),
                score=20,
                comment_count=3,
            )
        ]


def test_refresh_ticker_with_fake_providers_writes_mentions_and_observations(tmp_path):
    db = DB(str(tmp_path / "sentiment_service.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name)
        VALUES ('AMD', 'AMD', 'stock', 'USD', 'Advanced Micro Devices')
        """
    )
    service = SentimentIngestionService(
        db.conn,
        news_providers=[FakeNewsProvider()],
        social_providers=[FakeSocialProvider()],
    )

    written = service.refresh_ticker("AMD")

    assert written == 2
    assert db.conn.execute("SELECT COUNT(*) FROM news_article").fetchone()[0] == 1
    assert db.conn.execute("SELECT COUNT(*) FROM social_post").fetchone()[0] == 1
    assert db.conn.execute("SELECT COUNT(*) FROM news_article_asset_mention").fetchone()[0] == 1
    assert db.conn.execute("SELECT COUNT(*) FROM social_post_asset_mention").fetchone()[0] == 1
    rows = db.conn.execute(
        """
        SELECT item_type, provider, sentiment_label
        FROM sentiment_observation
        ORDER BY item_type
        """
    ).fetchall()
    assert rows == [
        ("news_article", "fake-news", "bullish"),
        ("social_post", "reddit", "bullish"),
    ]


def test_refresh_unknown_ticker_raises_clear_error(tmp_path):
    db = DB(str(tmp_path / "sentiment_service_unknown.db"))
    init_db(db)
    service = SentimentIngestionService(db.conn, news_providers=[FakeNewsProvider()])

    try:
        service.refresh_ticker("AMD")
    except ValueError as exc:
        assert "Unknown sentiment ticker: AMD" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unknown ticker")

