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
        VALUES
            ('SP500', 'S&P 500', 'Core', 'core_geo', 'USD', TRUE),
            ('SEC_TECH', 'Information Technology Sector', 'Select Sector SPDR', 'sector', 'USD', FALSE)
        """
    )
    db.conn.execute(
        """
        INSERT INTO benchmark_index_daily_metric(index_id, metric_date, return_1d, return_21d, return_252d, volatility_252d_ann)
        VALUES
            ('SP500', '2026-01-02', 0.01, 0.03, 0.11, 0.18),
            ('SEC_TECH', '2026-01-02', 0.02, 0.05, 0.15, 0.24)
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
    assert payload["sector_context"]["sector"] == "Technology"
    assert payload["sector_context"]["benchmark"]["index_id"] == "SEC_TECH"
    assert payload["sector_context"]["benchmark"]["return_252d"] == 0.15
    assert payload["sector_context"]["median"]["pe_ratio"] == 20
    assert round(payload["sector_context"]["median"]["price_to_sales"], 4) == 1.7778
    assert payload["sector_context"]["median"]["market_cap"] == 2000
    assert payload["sector_context"]["median"]["beta"] == 1.5
    assert payload["sector_context"]["left_diff_to_median"]["pe_ratio"] == 0
    assert payload["sector_context"]["right_diff_to_median"]["pe_ratio"] == 5
    assert any("historical P/E average" in item for item in payload["insights"])


def test_comparison_keeps_sector_context_null_without_sector(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name, sector, industry, country, mkt_cap, market_beta)
        VALUES ('CASHLIKE', 'CASHLIKE', 'stock', 'USD', 'Unclassified Holding', NULL, NULL, 'US', NULL, NULL)
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/comparison?left=CASHLIKE")

    assert response.status_code == 200
    payload = response.json()
    assert payload["left"]["symbol"] == "CASHLIKE"
    assert payload["sector_context"] is None


def test_comparison_requires_existing_asset(tmp_path):
    app = create_app(tmp_path / "api.db")

    with TestClient(app) as client:
        response = client.get("/api/v1/comparison?left=NOPE")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_comparison_workspace_batches_assets_and_aligns_history(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name, sector, industry, country, mkt_cap, market_beta)
        VALUES
            ('NVDA', 'NVDA', 'stock', 'USD', 'NVIDIA Corporation', 'Technology', 'Semiconductors', 'US', 2000, 1.7),
            ('AMD', 'AMD', 'stock', 'USD', 'Advanced Micro Devices', 'Technology', 'Semiconductors', 'US', 1600, 1.5)
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        VALUES
            ('NVDA', '2026-01-01', 10, 10, 'test'),
            ('NVDA', '2026-01-02', 12, 12, 'test'),
            ('AMD', '2025-12-31', 18, 18, 'test'),
            ('AMD', '2026-01-01', 20, 20, 'test'),
            ('AMD', '2026-01-02', 22, 22, 'test')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/comparison/workspace?symbols=NVDA,AMD,NVDA,NOPE&period=MAX&mode=total-return&currency=native"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requested_symbols"] == ["NVDA", "AMD", "NOPE"]
    assert payload["coverage"]["resolved_symbols"] == ["NVDA", "AMD"]
    assert payload["coverage"]["failed_symbols"] == ["NOPE"]
    assert payload["coverage"]["common_start_date"] == "2026-01-01"
    nvda = next(item for item in payload["historical_series"] if item["symbol"] == "NVDA")
    amd = next(item for item in payload["historical_series"] if item["symbol"] == "AMD")
    assert nvda["points"][0]["value"] == 100
    assert round(nvda["points"][1]["cumulative_return"], 6) == 0.2
    assert amd["points"][0]["date"] == "2026-01-01"
    assert amd["points"][0]["value"] == 100
    assert "latest_price_date" in payload["freshness"]["NVDA"]


def test_comparison_workspace_missing_values_remain_null(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name, sector, industry, country, mkt_cap, market_beta)
        VALUES ('CASHLIKE', 'CASHLIKE', 'stock', 'USD', 'Unclassified Holding', NULL, NULL, 'US', NULL, NULL)
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/comparison/workspace?symbols=CASHLIKE&period=MAX")

    assert response.status_code == 200
    payload = response.json()
    assert payload["assets"][0]["latest_price"] is None
    assert payload["assets"][0]["fundamentals"]["pe_ratio"] is None
    assert payload["historical_series"][0]["observation_count"] == 0


def test_comparison_workspace_uses_historical_fx_without_missing_rate_identity(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name)
        VALUES
            ('CADCO', 'CADCO', 'stock', 'CAD', 'Canadian Co'),
            ('USCO', 'USCO', 'stock', 'USD', 'US Co')
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        VALUES
            ('CADCO', '2026-01-01', 10, 10, 'test'),
            ('CADCO', '2026-01-02', 11, 11, 'test'),
            ('USCO', '2026-01-01', 10, 10, 'test'),
            ('USCO', '2026-01-02', 12, 12, 'test')
        """
    )
    db.conn.execute(
        """
        INSERT INTO fx_rate(from_ccy, to_ccy, rate_date, rate, source)
        VALUES
            ('CAD', 'USD', '2026-01-01', 0.75, 'test-fx'),
            ('CAD', 'USD', '2026-01-02', 0.80, 'test-fx')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/comparison/workspace?symbols=CADCO,USCO&period=MAX&currency=USD")

    assert response.status_code == 200
    payload = response.json()
    cadco = next(item for item in payload["historical_series"] if item["symbol"] == "CADCO")
    assert cadco["currency"] == "USD"
    assert cadco["points"][0]["close"] == 7.5
    assert cadco["points"][1]["close"] == 8.8
    assert round(cadco["points"][1]["cumulative_return"], 6) == round(8.8 / 7.5 - 1, 6)
    assert payload["fx_policy"]["historical"] is True
    assert payload["fx_policy"]["source"] == "test-fx"
    assert payload["fx_policy"]["missing_pairs"] == []


def test_comparison_workspace_skips_history_when_fx_is_missing(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name)
        VALUES ('CADCO', 'CADCO', 'stock', 'CAD', 'Canadian Co')
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        VALUES ('CADCO', '2026-01-01', 10, 10, 'test')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/comparison/workspace?symbols=CADCO&period=MAX&currency=USD")

    assert response.status_code == 200
    payload = response.json()
    assert payload["historical_series"][0]["observation_count"] == 0
    assert payload["fx_policy"]["missing_pairs"] == ["CAD->USD"]
    assert "FX was unavailable" in " ".join(payload["coverage"]["warnings"])


def test_comparison_workspace_returns_statement_estimate_and_capital_allocation_metrics(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name, mkt_cap, shares_outstanding)
        VALUES ('NVDA', 'NVDA', 'stock', 'USD', 'NVIDIA Corporation', 2000, 100)
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        VALUES ('NVDA', '2026-01-02', 20, 20, 'test')
        """
    )
    db.conn.execute(
        """
        INSERT INTO financial_statement(asset_id, statement_type, year, quarter, period_end_date, data_json, source)
        VALUES
            ('NVDA', 'income', 2025, 4, '2025-10-02', '{"revenue": 900, "grossProfit": 500, "operatingIncome": 250, "netIncome": 180, "eps": 1.8, "ebitda": 350, "researchAndDevelopmentExpenses": 80}', 'test'),
            ('NVDA', 'income', 2026, 1, '2026-01-02', '{"revenue": 1000, "grossProfit": 600, "operatingIncome": 300, "netIncome": 200, "eps": 2, "ebitda": 400, "weightedAverageShsOutDil": 95, "researchAndDevelopmentExpenses": 100, "customerConcentration": 35, "revenueConcentration": 45}', 'test'),
            ('NVDA', 'balance', 2025, 4, '2025-10-02', '{"cashAndCashEquivalents": 100, "totalDebt": 40, "totalCurrentAssets": 250, "totalCurrentLiabilities": 100, "totalStockholdersEquity": 360}', 'test'),
            ('NVDA', 'balance', 2026, 1, '2026-01-02', '{"cashAndCashEquivalents": 150, "totalDebt": 50, "totalCurrentAssets": 300, "totalCurrentLiabilities": 100, "totalStockholdersEquity": 500}', 'test'),
            ('NVDA', 'cashflow', 2026, 1, '2026-01-02', '{"freeCashFlow": 250, "stockBasedCompensation": 25, "commonStockRepurchased": -40, "capitalExpenditure": -120, "acquisitionsNet": -80}', 'test')
        """
    )
    db.conn.execute(
        """
        INSERT INTO earnings_calendar_event(asset_id, earnings_date, eps_estimated, revenue_estimated, source)
        VALUES ('NVDA', '2026-04-01', 2.5, 1200, 'test-estimates')
        """
    )
    db.conn.execute(
        """
        INSERT INTO dividend_event(asset_id, ex_date, dividend_per_share, source)
        VALUES ('NVDA', CURRENT_DATE - INTERVAL 30 DAY, 0.5, 'test-dividends')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/comparison/workspace?symbols=NVDA&period=MAX")

    assert response.status_code == 200
    fundamentals = response.json()["assets"][0]["fundamentals"]
    assert fundamentals["forward_eps"] == 2.5
    assert fundamentals["forward_revenue"] == 1200
    assert fundamentals["forward_pe"] == 8
    assert fundamentals["gross_margin"] == 0.6
    assert fundamentals["operating_margin"] == 0.3
    assert fundamentals["net_margin"] == 0.2
    assert fundamentals["free_cash_flow"] == 250
    assert fundamentals["free_cash_flow_yield"] == 0.125
    assert fundamentals["cash"] == 150
    assert fundamentals["total_debt"] == 50
    assert fundamentals["net_debt"] == -100
    assert fundamentals["current_ratio"] == 3
    assert fundamentals["debt_to_equity"] == 0.1
    assert fundamentals["shares_outstanding"] == 95
    assert fundamentals["dividend_yield"] == 0.025
    assert fundamentals["buyback_yield"] == 0.02
    assert fundamentals["stock_based_compensation"] == 25
    assert fundamentals["acquisition_intensity"] == 0.08
    assert fundamentals["reinvestment_rate"] == 0.3
    assert round(fundamentals["roic"], 6) == round((300 * 0.79) / 400, 6)
    assert round(fundamentals["roic_on_reinvestment"], 6) == round(((300 * 0.79) - (250 * 0.79)) / 100, 6)
    assert fundamentals["customer_concentration"] == 0.35
    assert fundamentals["revenue_concentration"] == 0.45


def test_comparison_workspace_uses_underlying_fundamentals_for_cdr_wrapper(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute(
        """
        INSERT INTO asset(
            asset_id, symbol, asset_type, asset_subtype, ccy, name, country, mkt_cap, market_beta, shares_outstanding
        )
        VALUES
            ('NVDA', 'NVDA', 'stock', NULL, 'USD', 'NVIDIA Corporation', 'US', 2000, 1.7, 100),
            ('NVDA.TO', 'NVDA.TO', 'stock', 'cdr', 'CAD', 'NVIDIA Canadian Depositary Receipt', 'CA', 50, NULL, NULL)
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        VALUES
            ('NVDA.TO', '2026-01-01', 25, 25, 'wrapper-price'),
            ('NVDA.TO', '2026-01-02', 20, 20, 'wrapper-price')
        """
    )
    db.conn.execute(
        """
        INSERT INTO financial_statement(asset_id, statement_type, year, quarter, period_end_date, data_json, source)
        VALUES
            ('NVDA', 'income', 2026, 1, '2026-01-02', '{"revenue": 1000, "grossProfit": 600, "operatingIncome": 300, "netIncome": 200, "eps": 2, "ebitda": 400, "weightedAverageShsOutDil": 95}', 'test'),
            ('NVDA', 'balance', 2026, 1, '2026-01-02', '{"cashAndCashEquivalents": 150, "totalDebt": 50, "totalCurrentAssets": 300, "totalCurrentLiabilities": 100, "totalStockholdersEquity": 500}', 'test'),
            ('NVDA', 'cashflow', 2026, 1, '2026-01-02', '{"freeCashFlow": 250}', 'test')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/comparison/workspace?symbols=NVDA.TO&period=MAX")

    assert response.status_code == 200
    payload = response.json()
    asset = payload["assets"][0]
    assert asset["asset_id"] == "NVDA.TO"
    assert asset["fundamental_asset_id"] == "NVDA"
    assert asset["market_beta"] == 1.7
    assert asset["market_cap"] == 2000
    assert asset["fundamentals"]["gross_margin"] == 0.6
    assert asset["fundamentals"]["operating_margin"] == 0.3
    assert round(asset["fundamentals"]["roic"], 6) == round((300 * 0.79) / 400, 6)
    assert payload["historical_series"][0]["points"][0]["close"] == 25
    assert payload["historical_series"][0]["points"][1]["close"] == 20


def test_comparison_workspace_can_compare_benchmark_as_asset(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute(
        """
        INSERT INTO benchmark_index(index_id, index_name, index_family, index_category, currency, is_core)
        VALUES ('SP500', 'S&P 500', 'Core', 'core_geo', 'USD', TRUE)
        """
    )
    db.conn.execute(
        """
        INSERT INTO benchmark_index_daily_price(index_id, price_date, close, adj_close, source, source_symbol, is_proxy)
        VALUES
            ('SP500', '2026-01-01', 100, 100, 'test', 'SPY', FALSE),
            ('SP500', '2026-01-02', 110, 110, 'test', 'SPY', FALSE)
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/comparison/workspace?symbols=SP500&period=MAX")

    assert response.status_code == 200
    payload = response.json()
    assert payload["assets"][0]["asset_type"] == "benchmark"
    assert payload["assets"][0]["symbol"] == "SP500"
    assert payload["historical_series"][0]["asset_id"] == "benchmark:SP500"
    assert round(payload["historical_series"][0]["points"][1]["value"], 6) == 110


def test_comparison_workspace_can_resolve_portfolio_symbol(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute(
        """
        INSERT INTO portfolio(portfolio_id, portfolio_name, base_ccy)
        VALUES (1, 'Core Portfolio', 'CAD')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/comparison/workspace?symbols=PF1&period=MAX")

    assert response.status_code == 200
    payload = response.json()
    assert payload["assets"][0]["asset_type"] == "portfolio"
    assert payload["assets"][0]["symbol"] == "PF1"
    assert payload["assets"][0]["currency"] == "CAD"


def test_comparison_workspace_portfolio_uses_position_history_when_transactions_missing(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute(
        """
        INSERT INTO portfolio(portfolio_id, portfolio_name, base_ccy)
        VALUES (1, 'Core Portfolio', 'CAD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name)
        VALUES ('NVDA', 'NVDA', 'stock', 'USD', 'NVIDIA Corporation')
        """
    )
    db.conn.execute(
        """
        INSERT INTO position(portfolio_id, asset_id, qty, book_cost, created_at, updated_at)
        VALUES (1, 'NVDA', 2, 10, now(), now())
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        VALUES
            ('NVDA', '2026-01-01', 10, 10, 'test'),
            ('NVDA', '2026-01-02', 12, 12, 'test')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/comparison/workspace?symbols=PF1&period=MAX")

    assert response.status_code == 200
    series = response.json()["historical_series"][0]
    assert series["source"] == "current_position_backtest:test"
    assert series["points"][0]["close"] == 20
    assert series["points"][1]["value"] == 120
