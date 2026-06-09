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


def test_asset_analytics_exposes_projection_and_valuation_models(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, shares_outstanding)
        VALUES ('AAPL', 'AAPL', 'stock', 'USD', 100)
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        VALUES
            ('AAPL', '2026-01-01', 34, 34, 'test'),
            ('AAPL', '2026-01-02', 35, 35, 'test'),
            ('AAPL', '2026-01-03', 36, 36, 'test')
        """
    )
    db.conn.execute(
        """
        INSERT INTO dividend_event(asset_id, ex_date, dividend_per_share, source)
        VALUES
            ('AAPL', '2025-12-01', 0.30, 'test'),
            ('AAPL', '2025-09-01', 0.30, 'test'),
            ('AAPL', '2025-06-01', 0.30, 'test'),
            ('AAPL', '2025-03-01', 0.30, 'test')
        """
    )
    db.conn.execute(
        """
        INSERT INTO financial_statement(asset_id, statement_type, year, quarter, data_json, source)
        VALUES
            ('AAPL', 'income', 2025, 4, '{"revenue":1200,"grossProfit":720,"operatingIncome":360,"netIncome":240,"eps":2.4,"ebitda":420}', 'test'),
            ('AAPL', 'income', 2024, 4, '{"revenue":1000,"netIncome":200,"eps":2.0}', 'test'),
            ('AAPL', 'balance', 2025, 4, '{"totalStockholdersEquity":800,"totalAssets":1600,"totalDebt":300,"cashAndCashEquivalents":50}', 'test'),
            ('AAPL', 'cashflow', 2025, 4, '{"freeCashFlow":180}', 'test'),
            ('AAPL', 'cashflow', 2024, 4, '{"freeCashFlow":150}', 'test')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/assets/AAPL/analytics")

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["discounted_cash_flow"]["intrinsic_value_per_share"] is not None
    assert report["dividend_discount"]["intrinsic_value_per_share"] is not None
    assert report["valuation_depth"]["dcf_scenarios"][1]["scenario_name"] == "base"
    assert report["forecast"]["simulation"] is not None
