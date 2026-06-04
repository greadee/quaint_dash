from fastapi.testclient import TestClient

from dashboard.api.app import create_app
from dashboard.db.db_conn import DB


def _seed_asset(db_path):
    db = DB(db_path)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Main')")
    db.conn.execute(
        """
        INSERT INTO asset(
            asset_id, symbol, asset_type, ccy, name, sector, country, market_beta
        )
        VALUES ('AAPL', 'AAPL', 'stock', 'USD', 'Apple Inc.', 'Technology', 'US', 1.2)
        """
    )
    db.conn.execute("INSERT INTO import_batch(batch_id, batch_type) VALUES (1, 'manual-entry')")
    db.conn.execute(
        """
        INSERT INTO txn(txn_id, portfolio_id, txn_type, asset_id, qty, price, ccy, batch_id)
        VALUES (1, 1, 'buy', 'AAPL', 2, 100, 'USD', 1)
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        VALUES
            ('AAPL', '2026-01-02', 100, 100, 'test'),
            ('AAPL', '2026-01-03', 125, 125, 'test')
        """
    )
    db.conn.close()


def test_asset_detail_and_price_history(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    _seed_asset(db_path)

    with TestClient(app) as client:
        detail = client.get("/api/v1/assets/aapl")
        prices = client.get("/api/v1/assets/AAPL/prices?limit=1")

    assert detail.status_code == 200
    assert detail.json()["name"] == "Apple Inc."
    assert detail.json()["latest_price"] == 125
    assert prices.json() == [{"date": "2026-01-03", "close": 125.0}]


def test_asset_and_portfolio_analytics_preserve_phase3_contract(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    _seed_asset(db_path)

    with TestClient(app) as client:
        asset = client.get("/api/v1/assets/AAPL/analytics")
        portfolio = client.get("/api/v1/portfolios/1/analytics")

    assert asset.status_code == 200
    assert asset.json()["schema_version"] == "phase3.analytics.v1"
    assert asset.json()["report_type"] == "asset"
    assert portfolio.status_code == 200
    assert portfolio.json()["schema_version"] == "phase3.analytics.v1"
    assert portfolio.json()["report_type"] == "portfolio"
