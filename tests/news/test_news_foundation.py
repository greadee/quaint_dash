from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dashboard.db.db_conn import DB, init_db
from dashboard.news.entity_resolution import EntityResolver
from dashboard.news.ingestion import NewsIngestionService
from dashboard.news.models import ProviderNewsArticle
from dashboard.news.normalization import NewsValidationError, normalize_provider_article
from dashboard.news.providers.mock_provider import MockNewsProvider


def _db(tmp_path):
    db = DB(str(tmp_path / "news.db"))
    init_db(db)
    return db


def _seed_assets(conn):
    conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, exchange_code, asset_type, ccy, name, sector, track)
        VALUES
            ('NVDA', 'NVDA', 'XNAS', 'stock', 'USD', 'NVIDIA Corporation', 'Technology', TRUE),
            ('MSFT', 'MSFT', 'XNAS', 'stock', 'USD', 'Microsoft Corporation', 'Technology', TRUE),
            ('NOW', 'NOW', 'XNYS', 'stock', 'USD', 'ServiceNow Inc.', 'Technology', TRUE),
            ('CAT', 'CAT', 'XNYS', 'stock', 'USD', 'Caterpillar Inc.', 'Industrials', TRUE)
        """
    )
    conn.execute(
        """
        INSERT INTO asset_entity_alias(asset_id, alias, alias_type, confidence)
        VALUES ('NOW', 'ServiceNow', 'company_name', 0.88)
        """
    )


def test_financial_news_schema_initializes(tmp_path):
    db = _db(tmp_path)

    categories = db.conn.execute(
        "SELECT category_code FROM news_category WHERE category_code IN ('earnings', 'general') ORDER BY category_code"
    ).fetchall()
    provider_columns = db.conn.execute("DESCRIBE news_provider").fetchall()

    assert categories == [("earnings",), ("general",)]
    assert any(row[0] == "supports_symbol_news" for row in provider_columns)


def test_normalization_cleans_url_html_and_sentiment():
    article = ProviderNewsArticle(
        provider_article_id="abc",
        headline="  NVIDIA &amp; partners <b>raise</b> guidance  ",
        source_name="Wire",
        published_at=datetime(2026, 6, 30, 14, 0, tzinfo=UTC),
        url="HTTPS://Example.Test/story?utm_source=x&keep=1#frag",
        provider_categories=["M&A", "Press Releases"],
        sentiment_score=2.5,
    )

    normalized = normalize_provider_article("mock", article)

    assert normalized.headline == "NVIDIA & partners raise guidance"
    assert normalized.canonical_url == "https://example.test/story?keep=1"
    assert normalized.categories == ["merger_acquisition", "press_release"]
    assert normalized.sentiment_score == 1.0
    assert normalized.sentiment_label == "very_positive"


def test_normalization_rejects_future_timestamps():
    article = ProviderNewsArticle(
        provider_article_id="future",
        headline="Future headline",
        source_name="Wire",
        published_at=datetime.now(UTC) + timedelta(days=2),
    )

    try:
        normalize_provider_article("mock", article)
    except NewsValidationError as exc:
        assert "future" in str(exc)
    else:
        raise AssertionError("future article was accepted")


def test_entity_resolution_uses_provider_symbols_and_blocks_common_word_tickers(tmp_path):
    db = _db(tmp_path)
    _seed_assets(db.conn)
    resolver = EntityResolver(db.conn)

    provider_symbol_article = normalize_provider_article(
        "mock",
        ProviderNewsArticle(
            provider_article_id="nvda",
            headline="Data center guidance rises",
            source_name="Wire",
            published_at=datetime(2026, 6, 30, 14, 0, tzinfo=UTC),
            symbols=["NVDA"],
        ),
    )
    ambiguous_article = normalize_provider_article(
        "mock",
        ProviderNewsArticle(
            provider_article_id="ambiguous",
            headline="Cat demand is now improving for industrial products",
            source_name="Wire",
            published_at=datetime(2026, 6, 30, 14, 0, tzinfo=UTC),
        ),
    )
    alias_article = normalize_provider_article(
        "mock",
        ProviderNewsArticle(
            provider_article_id="servicenow",
            headline="ServiceNow announces enterprise workflow product launch",
            source_name="Wire",
            published_at=datetime(2026, 6, 30, 14, 0, tzinfo=UTC),
        ),
    )

    assert [(m.asset_id, m.match_method, m.confidence_score) for m in resolver.resolve(provider_symbol_article)] == [
        ("NVDA", "provider_symbol", 0.95)
    ]
    assert resolver.resolve(ambiguous_article) == []
    assert [(m.asset_id, m.match_method) for m in resolver.resolve(alias_article)] == [
        ("NOW", "alias_match")
    ]


def test_mock_provider_ingestion_is_idempotent_and_clusters(tmp_path):
    db = _db(tmp_path)
    _seed_assets(db.conn)
    provider = MockNewsProvider()
    service = NewsIngestionService(db.conn)

    first = service.ingest_latest(provider)
    second = service.ingest_latest(provider)

    article_count = db.conn.execute("SELECT COUNT(*) FROM news_article WHERE provider = 'mock_news'").fetchone()[0]
    asset_links = db.conn.execute("SELECT asset_id, match_method FROM news_article_asset ORDER BY asset_id").fetchall()
    state = db.conn.execute(
        """
        SELECT sync_status, articles_received, articles_inserted, articles_updated, articles_rejected
        FROM news_ingestion_state s
        JOIN news_provider p ON p.provider_id = s.provider_id
        WHERE p.provider_code = 'mock_news'
        """
    ).fetchone()
    clusters = db.conn.execute("SELECT COUNT(*), SUM(article_count) FROM news_story_cluster").fetchone()

    assert first.articles_received == 3
    assert first.articles_inserted == 3
    assert second.articles_inserted == 0
    assert second.articles_updated == 3
    assert article_count == 3
    assert ("NVDA", "provider_symbol") in asset_links
    assert ("MSFT", "provider_symbol") in asset_links
    assert ("NOW", "alias_match") in asset_links
    assert state == ("success", 3, 0, 3, 0)
    assert clusters == (3, 3)
