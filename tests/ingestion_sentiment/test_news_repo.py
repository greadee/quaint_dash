from __future__ import annotations

from datetime import datetime

from dashboard.db.db_conn import DB, init_db
from dashboard.ingestion_sentiment.models import NewsArticleInput
from dashboard.ingestion_sentiment.repo import SentimentIngestionRepository
from dashboard.ingestion_sentiment.ticker_matching import find_ticker_mentions


def test_articles_are_upserted_idempotently(tmp_path):
    db = DB(str(tmp_path / "news_repo.db"))
    init_db(db)
    repo = SentimentIngestionRepository(db.conn)

    article = NewsArticleInput(
        source_item_id="abc-1",
        source_name="Test News",
        provider="fake-news",
        title="AMD expands data center roadmap",
        url="https://example.test/amd",
        published_at=datetime(2026, 1, 1, 14, 30),
    )

    first_id = repo.upsert_article(article)
    second_id = repo.upsert_article(
        NewsArticleInput(
            source_item_id="abc-1",
            source_name="Test News",
            provider="fake-news",
            title="AMD expands data center roadmap, updated",
            url="https://example.test/amd",
            published_at=datetime(2026, 1, 1, 14, 30),
        )
    )

    rows = db.conn.execute("SELECT article_id, title FROM news_article").fetchall()

    assert first_id == second_id
    assert rows == [(first_id, "AMD expands data center roadmap, updated")]


def test_article_mentions_can_map_one_article_to_multiple_tickers(tmp_path):
    db = DB(str(tmp_path / "news_mentions.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name)
        VALUES
            ('AMD', 'AMD', 'stock', 'USD', 'Advanced Micro Devices'),
            ('NVDA', 'NVDA', 'stock', 'USD', 'NVIDIA Corporation')
        """
    )
    repo = SentimentIngestionRepository(db.conn)
    article = NewsArticleInput(
        source_item_id="multi-1",
        source_name="Test News",
        provider="fake-news",
        title="$AMD and NVDA compete for AI accelerator demand",
    )

    article_id = repo.upsert_article(article)
    mentions = find_ticker_mentions(article.title, repo.asset_refs())
    repo.upsert_article_mentions(article_id, mentions)

    rows = db.conn.execute(
        """
        SELECT article_id, asset_id, ticker, mention_reason
        FROM news_article_asset_mention
        ORDER BY ticker
        """
    ).fetchall()

    assert rows == [
        (article_id, "AMD", "AMD", "cashtag"),
        (article_id, "NVDA", "NVDA", "ticker"),
    ]

