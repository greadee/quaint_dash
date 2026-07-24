from __future__ import annotations

from datetime import datetime, timedelta, timezone

from dashboard.db.db_conn import DB, init_db
from dashboard.news.entity_resolution import EntityResolver
from dashboard.news.ingestion import NewsIngestionService
from dashboard.news.models import ProviderCapabilities, ProviderHealthStatus, ProviderNewsArticle
from dashboard.news.normalization import NewsValidationError, normalize_provider_article
from dashboard.news.providers.fmp_provider import FmpNewsProvider
from dashboard.news.providers.mock_provider import MockNewsProvider

UTC = timezone.utc


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


class _SubscribedProvider:
    provider_code = "test_live"
    provider_name = "Test Live News"
    provider_type = "api"
    base_url = "https://provider.test"
    capabilities = ProviderCapabilities(supports_symbol_news=True, supports_press_releases=True)

    def fetch_latest(self, since=None, limit=100):
        return []

    def fetch_for_symbols(self, symbols, since=None, limit=100):
        assert "NVDA" in symbols
        return [
            ProviderNewsArticle(
                provider_article_id="live-nvda",
                headline="NVIDIA signs material supply agreement",
                source_name="Wire",
                published_at=datetime(2026, 6, 30, 14, 0, tzinfo=UTC),
                url="https://provider.test/nvda?utm_source=x",
                symbols=["NVDA"],
                provider_categories=["contract_award"],
            )
        ]

    def fetch_article(self, provider_article_id):
        raise LookupError(provider_article_id)

    def health_check(self):
        return ProviderHealthStatus("test_live", "healthy", datetime.now(UTC))


def test_subscribed_ingestion_uses_portfolio_and_watchlist_symbols(tmp_path):
    db = _db(tmp_path)
    _seed_assets(db.conn)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Core')")
    db.conn.execute(
        """
        INSERT INTO portfolio_ticker(portfolio_id, asset_id, is_active, source)
        VALUES (1, 'NVDA', TRUE, 'position')
        """
    )

    result = NewsIngestionService(db.conn).ingest_subscribed(_SubscribedProvider())
    rows = db.conn.execute(
        """
        SELECT a.provider, aa.asset_id, aa.match_method
        FROM news_article a
        JOIN news_article_asset aa ON aa.article_id = a.article_id
        """
    ).fetchall()

    assert result.articles_inserted == 1
    assert rows == [("test_live", "NVDA", "provider_symbol")]


def test_earnings_events_are_normalized_into_news_feed(tmp_path):
    db = _db(tmp_path)
    _seed_assets(db.conn)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Core')")
    db.conn.execute(
        """
        INSERT INTO portfolio_ticker(portfolio_id, asset_id, is_active, source)
        VALUES (1, 'NVDA', TRUE, 'position')
        """
    )
    db.conn.execute(
        """
        INSERT INTO earnings_calendar_event(
            asset_id, earnings_date, fiscal_year, fiscal_quarter, time,
            eps_estimated, eps_actual, revenue_estimated, revenue_actual, source
        )
        VALUES ('NVDA', current_date + 7, 2026, 2, 'amc', 1.25, NULL, 40000000000, NULL, 'fmp')
        """
    )

    result = NewsIngestionService(db.conn).ingest_earnings_events()
    row = db.conn.execute(
        """
        SELECT a.provider, a.headline, c.category_code, aa.asset_id
        FROM news_article a
        JOIN news_article_category ac ON ac.article_id = a.article_id
        JOIN news_category c ON c.category_id = ac.category_id
        JOIN news_article_asset aa ON aa.article_id = a.article_id
        WHERE c.category_code = 'earnings_upcoming'
        """
    ).fetchone()

    assert result.articles_inserted == 1
    assert row[0] == "corporate_calendar"
    assert "scheduled to report earnings" in row[1]
    assert row[2:] == ("earnings_upcoming", "NVDA")


def test_fmp_provider_parses_stock_news_payload_without_secrets():
    provider = FmpNewsProvider(api_key="test-key")
    payload = [
        {
            "symbol": "NVDA",
            "publishedDate": "2026-06-30 14:30:00",
            "title": "NVIDIA expands data center platform",
            "site": "Example Wire",
            "url": "https://example.test/story",
            "text": "Provider supplied summary.",
            "apikey": "must-not-persist",
        }
    ]

    parsed = provider._parse_items(payload, default_symbols=[])

    assert parsed[0].symbols == ["NVDA"]
    assert parsed[0].published_at.tzinfo is not None
    assert parsed[0].raw_payload["symbol"] == "NVDA"
    assert "apikey" not in parsed[0].raw_payload
