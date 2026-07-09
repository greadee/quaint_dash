from __future__ import annotations

from fastapi.testclient import TestClient

from dashboard.api.app import create_app
from dashboard.db.db_conn import DB, init_db
from dashboard.news.ingestion import NewsIngestionService
from dashboard.news.providers.mock_provider import MockNewsProvider


def _seed_news_db(db_path):
    db = DB(db_path)
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO portfolio(portfolio_id, portfolio_name, base_ccy)
        VALUES (1, 'Max CAGR', 'USD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, exchange_code, asset_type, ccy, name, sector, track)
        VALUES
            ('NVDA', 'NVDA', 'XNAS', 'stock', 'USD', 'NVIDIA Corporation', 'Technology', TRUE),
            ('MSFT', 'MSFT', 'XNAS', 'stock', 'USD', 'Microsoft Corporation', 'Technology', TRUE),
            ('NOW', 'NOW', 'XNYS', 'stock', 'USD', 'ServiceNow Inc.', 'Technology', TRUE)
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_entity_alias(asset_id, alias, alias_type, confidence)
        VALUES ('NOW', 'ServiceNow', 'company_name', 0.88)
        """
    )
    db.conn.execute(
        """
        INSERT INTO position(portfolio_id, asset_id, qty, book_cost, created_at, updated_at)
        VALUES
            (1, 'NVDA', 10, 5000, now(), now()),
            (1, 'MSFT', 2, 100, now(), now())
        """
    )
    NewsIngestionService(db.conn).ingest_latest(MockNewsProvider())
    db.conn.close()


def test_news_feed_filters_search_and_detail(tmp_path):
    db_path = tmp_path / "api-news.db"
    app = create_app(db_path)
    _seed_news_db(db_path)

    with TestClient(app) as client:
        feed = client.get("/api/v1/news?sort=recency")
        search = client.get("/api/v1/news/search?q=antitrust")
        providers = client.get("/api/v1/news/providers")
        categories = client.get("/api/v1/news/categories")
        article_id = feed.json()["items"][0]["article_id"]
        detail = client.get(f"/api/v1/news/articles/{article_id}")

    assert feed.status_code == 200
    assert feed.json()["total"] == 3
    assert feed.json()["items"][0]["provider_code"] == "mock_news"
    assert search.status_code == 200
    assert search.json()["items"][0]["assets"][0]["asset_id"] == "MSFT"
    assert providers.status_code == 200
    assert providers.json()[0]["provider_code"] == "mock_news"
    assert categories.status_code == 200
    assert any(item["category_code"] == "earnings" for item in categories.json())
    assert detail.status_code == 200
    assert detail.json()["article_id"] == article_id
    assert detail.json()["cluster"]["article_count"] == 1


def test_asset_and_portfolio_news_feeds_rank_context(tmp_path):
    db_path = tmp_path / "api-news-context.db"
    app = create_app(db_path)
    _seed_news_db(db_path)

    with TestClient(app) as client:
        asset_feed = client.get("/api/v1/assets/NVDA/news")
        portfolio_feed = client.get("/api/v1/portfolios/1/news?sort=relevance")

    assert asset_feed.status_code == 200
    assert asset_feed.json()["total"] == 1
    assert asset_feed.json()["items"][0]["assets"][0]["asset_id"] == "NVDA"
    assert portfolio_feed.status_code == 200
    assert portfolio_feed.json()["total"] == 2
    assert portfolio_feed.json()["items"][0]["assets"][0]["asset_id"] == "NVDA"


def test_cdr_asset_and_portfolio_news_feeds_use_underlying_symbol(tmp_path):
    db_path = tmp_path / "api-news-cdr-context.db"
    app = create_app(db_path)
    _seed_news_db(db_path)
    db = DB(db_path)
    db.conn.execute(
        """
        INSERT INTO portfolio(portfolio_id, portfolio_name, base_ccy)
        VALUES (2, 'CDR', 'CAD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, exchange_code, asset_type, asset_subtype, ccy, name, sector, track)
        VALUES
            ('NVDA.TO', 'NVDA.TO', 'XTSE', 'stock', 'cdr', 'CAD', 'NVIDIA Canadian Depositary Receipt', 'Technology', TRUE),
            ('MSFT.TO', 'MSFT.TO', 'XTSE', 'stock', 'cdr', 'CAD', 'Microsoft Canadian Depositary Receipt', 'Technology', TRUE)
        """
    )
    db.conn.execute(
        """
        INSERT INTO position(portfolio_id, asset_id, qty, book_cost, created_at, updated_at)
        VALUES
            (2, 'NVDA.TO', 10, 5000, now(), now()),
            (2, 'MSFT.TO', 2, 100, now(), now())
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        asset_feed = client.get("/api/v1/assets/NVDA.TO/news")
        portfolio_feed = client.get("/api/v1/portfolios/2/news?sort=relevance")
        terminal_feed = client.get("/api/v1/news?asset_id=NVDA.TO")

    assert asset_feed.status_code == 200
    assert asset_feed.json()["total"] == 1
    assert asset_feed.json()["items"][0]["assets"][0]["asset_id"] == "NVDA"
    assert portfolio_feed.status_code == 200
    assert portfolio_feed.json()["total"] == 2
    assert portfolio_feed.json()["items"][0]["assets"][0]["asset_id"] == "NVDA"
    assert terminal_feed.status_code == 200
    assert terminal_feed.json()["total"] == 1


def test_news_read_and_saved_state_persists(tmp_path):
    db_path = tmp_path / "api-news-state.db"
    app = create_app(db_path)
    _seed_news_db(db_path)

    with TestClient(app) as client:
        article_id = client.get("/api/v1/news").json()["items"][0]["article_id"]
        read = client.post(f"/api/v1/news/articles/{article_id}/read")
        saved = client.post(f"/api/v1/news/articles/{article_id}/save")
        detail = client.get(f"/api/v1/news/articles/{article_id}")
        unsaved = client.delete(f"/api/v1/news/articles/{article_id}/save")

    assert read.status_code == 200
    assert read.json()["is_read"] is True
    assert saved.status_code == 200
    assert saved.json()["is_saved"] is True
    assert detail.json()["is_read"] is True
    assert detail.json()["is_saved"] is True
    assert unsaved.json()["is_saved"] is False


def test_news_provider_health_and_alert_rules(tmp_path):
    db_path = tmp_path / "api-news-ops.db"
    app = create_app(db_path)
    _seed_news_db(db_path)

    payload = {
        "rule_name": "NVDA breaking regulatory",
        "target_scope": "asset",
        "keyword_query": "regulatory",
        "min_importance": 0.7,
        "breaking_only": True,
        "asset_ids": ["NVDA"],
        "portfolio_ids": [1],
    }

    with TestClient(app) as client:
        health = client.get("/api/v1/news/health")
        created = client.post("/api/v1/news/alerts", json=payload)
        alert_id = created.json()["alert_rule_id"]
        listed = client.get("/api/v1/news/alerts")
        updated = client.patch(
            f"/api/v1/news/alerts/{alert_id}",
            json={**payload, "rule_name": "NVDA high importance", "breaking_only": False},
        )
        deleted = client.delete(f"/api/v1/news/alerts/{alert_id}")

    assert health.status_code == 200
    assert health.json()[0]["provider_code"] == "mock_news"
    assert health.json()[0]["status"] in {"healthy", "stale"}
    assert created.status_code == 201
    assert created.json()["asset_ids"] == ["NVDA"]
    assert created.json()["portfolio_ids"] == [1]
    assert listed.status_code == 200
    assert listed.json()[0]["alert_rule_id"] == alert_id
    assert updated.status_code == 200
    assert updated.json()["rule_name"] == "NVDA high importance"
    assert updated.json()["breaking_only"] is False
    assert deleted.status_code == 200
    assert deleted.json()["result"]["alert_rule_id"] == alert_id
