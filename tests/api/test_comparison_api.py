from fastapi.testclient import TestClient

from dashboard.api.app import create_app
from dashboard.db.db_conn import DB


def test_asset_comparison_returns_valuation_context_and_benchmark(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name, sector, industry, country, mkt_cap, market_beta)
        VALUES
            ('NVDA', 'NVDA', 'stock', 'USD', 'NVIDIA Corporation', 'Technology', 'Semiconductors', 'US', 2000, 1.7),
            ('AMD', 'AMD', 'stock', 'USD', 'Advanced Micro Devices', 'Technology', 'Semiconductors', 'US', 1600, 1.5),
            ('MSFT', 'MSFT', 'stock', 'USD', 'Microsoft Corporation', 'Technology', 'Software', 'US', 5000, 1.1)
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        VALUES
            ('NVDA', '2025-12-31', 60, 60, 'test'),
            ('NVDA', '2026-01-01', 18, 18, 'test'),
            ('NVDA', '2026-01-02', 20, 20, 'test'),
            ('AMD', '2026-01-01', 15, 15, 'test'),
            ('AMD', '2026-01-02', 16, 16, 'test'),
            ('MSFT', '2026-01-01', 45, 45, 'test'),
            ('MSFT', '2026-01-02', 50, 50, 'test')
        """
    )
    db.conn.execute(
        """
        INSERT INTO financial_statement(asset_id, statement_type, year, quarter, period_end_date, data_json, source)
        VALUES
            ('NVDA', 'income', 2025, 4, '2025-12-31', '{"revenue": 1000, "netIncome": 100, "eps": 1}', 'test'),
            ('NVDA', 'income', 2026, 1, '2026-01-02', '{"revenue": 1200, "netIncome": 120, "eps": 1}', 'test'),
            ('AMD', 'income', 2026, 1, '2026-01-02', '{"revenue": 900, "netIncome": 90, "eps": 1}', 'test'),
            ('MSFT', 'income', 2026, 1, '2026-01-02', '{"revenue": 2000, "netIncome": 200, "eps": 2}', 'test')
        """
    )
    db.conn.execute(
        """
        INSERT INTO benchmark_index(index_id, index_name, index_family, index_category, currency, is_core)
        VALUES ('SP500', 'S&P 500', 'Core', 'core_geo', 'USD', TRUE)
        """
    )
    db.conn.execute(
        """
        INSERT INTO benchmark_index_daily_metric(index_id, metric_date, return_1d, return_21d, return_252d, volatility_252d_ann)
        VALUES ('SP500', '2026-01-02', 0.01, 0.03, 0.11, 0.18)
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/comparison?left=NVDA&right=MSFT&benchmark_index_id=SP500")

    assert response.status_code == 200
    payload = response.json()
    assert payload["left"]["symbol"] == "NVDA"
    assert payload["right"]["symbol"] == "MSFT"
    assert payload["benchmark"]["index_id"] == "SP500"
    assert payload["left"]["fundamentals"]["pe_ratio"] == 20
    assert payload["left"]["valuation"]["historical_pe_average"] == 40
    assert payload["left"]["valuation"]["historical_pe_discount"] == -0.5
    assert payload["left"]["valuation"]["sector_pe_average"] == 20.5
    assert round(payload["left"]["valuation"]["sector_pe_premium"], 4) == -0.0244
    assert payload["left"]["returns"]["return_1d"] == 20 / 18 - 1
    assert payload["benchmark"]["return_252d"] == 0.11
    assert any("historical P/E average" in item for item in payload["insights"])


def test_comparison_requires_existing_asset(tmp_path):
    app = create_app(tmp_path / "api.db")

    with TestClient(app) as client:
        response = client.get("/api/v1/comparison?left=NOPE")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
