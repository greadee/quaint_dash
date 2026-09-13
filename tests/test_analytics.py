from __future__ import annotations

from datetime import date, timedelta
import json

import pytest

from dashboard.analytics import (
    ANALYTICS_REPORT_SCHEMA_VERSION,
    AIReadinessContext,
    AnalyticsFact,
    AnalyticsEngine,
    AnalyticsRepository,
    AnalyticsStorageService,
    PricePoint,
    allocation_class,
    analytics_report_payload,
    compare_ai_snapshot_facts,
    discounted_cash_flow_model,
    dividend_discount_model,
    implied_dcf_growth_rate,
    money_weighted_return,
    projected_dividend_growth,
    simulated_forecast_band,
    valuation_depth_metrics,
    portfolio_risk_decomposition,
    portfolio_performance_metrics,
    relative_risk_metrics,
    risk_return_metrics,
)
from dashboard.db.db_conn import DB, init_db


def test_risk_return_metrics_calculate_core_ratios():
    prices = [
        PricePoint(date(2025, 1, 1), 100.0),
        PricePoint(date(2025, 1, 2), 110.0),
        PricePoint(date(2025, 1, 3), 105.0),
        PricePoint(date(2025, 1, 4), 120.0),
    ]

    metrics = risk_return_metrics(prices)

    assert metrics.observations == 4
    assert metrics.cumulative_return == pytest.approx(0.20)
    assert metrics.annualized_volatility is not None
    assert metrics.sortino_ratio is not None
    assert metrics.max_drawdown == pytest.approx((105.0 / 110.0) - 1.0)
    assert metrics.best_daily_return == pytest.approx((120.0 / 105.0) - 1.0)
    assert metrics.worst_daily_return == pytest.approx((105.0 / 110.0) - 1.0)


def test_risk_return_metrics_sorts_prices_before_drawdown():
    prices = [
        PricePoint(date(2025, 1, 3), 80.0),
        PricePoint(date(2025, 1, 1), 100.0),
        PricePoint(date(2025, 1, 2), 120.0),
        PricePoint(date(2025, 1, 4), 90.0),
    ]

    metrics = risk_return_metrics(prices)

    assert metrics.start_date == date(2025, 1, 1)
    assert metrics.end_date == date(2025, 1, 4)
    assert metrics.max_drawdown == pytest.approx((80.0 / 120.0) - 1.0)


def test_allocation_class_splits_stocks_cdrs_etfs_and_money_market():
    assert allocation_class(symbol="AAPL", asset_type="stock") == "Stock"
    assert allocation_class(symbol="SPY", asset_type="etf") == "ETF"
    assert allocation_class(
        symbol="NOWS.TO",
        asset_type="stock",
        name="ServiceNow Inc Canadian Depository Receipt (CAD Hedged)",
    ) == "CDR"
    assert allocation_class(
        symbol="AMD.TO",
        asset_type="stock",
        name="Advanced Micro Devices, Inc. CDR",
    ) == "CDR"
    assert allocation_class(
        symbol="ASML.TO",
        asset_type="stock",
        name="ASML Holding N.V. Depositary Receipt",
    ) == "CDR"
    assert allocation_class(symbol="UBER.TO", asset_type="stock", name="UBER") == "CDR"
    assert (
        allocation_class(
            symbol="VUN.TO",
            asset_type="stock",
            name="Vanguard U.S. Total Market Index Fund",
        )
        == "ETF"
    )
    assert allocation_class(
        symbol="CASH.TO",
        asset_type="etf",
        asset_subtype="money_market",
        name="Global X High Interest Savings ETF",
    ) == "Money market"
    assert allocation_class(symbol="CASH", asset_type="cash") == "Cash"


def test_relative_metrics_calculate_beta_alpha_and_correlation():
    start = date(2025, 1, 1)
    benchmark = [
        PricePoint(start + timedelta(days=i), close)
        for i, close in enumerate([100.0, 102.0, 101.0, 104.0, 108.0, 107.0])
    ]
    asset = [
        PricePoint(start + timedelta(days=i), close)
        for i, close in enumerate([100.0, 104.0, 102.0, 108.0, 116.0, 114.0])
    ]

    metrics = relative_risk_metrics(asset, benchmark, risk_free_rate=0.02)

    assert metrics.observations == 5
    assert metrics.beta is not None
    assert metrics.beta > 1.0
    assert metrics.alpha_annualized is not None
    assert metrics.correlation is not None
    assert metrics.r_squared == pytest.approx(metrics.correlation * metrics.correlation)


def test_valuation_models_report_intrinsic_value_and_implied_growth():
    ddm = dividend_discount_model(
        annual_dividend=2.0,
        market_price=40.0,
        discount_rate=0.09,
        growth_rate=0.03,
    )

    assert ddm.intrinsic_value_per_share == pytest.approx(34.3333333)
    assert ddm.margin_of_safety == pytest.approx((34.3333333 / 40.0) - 1.0)
    assert ddm.implied_growth_rate == pytest.approx((40.0 * 0.09 - 2.0) / 42.0)

    dcf = discounted_cash_flow_model(
        cashflow_per_share=5.0,
        market_price=100.0,
        discount_rate=0.10,
        growth_rate=0.05,
        terminal_growth_rate=0.03,
        forecast_years=5,
    )

    assert dcf.intrinsic_value_per_share is not None
    assert dcf.implied_growth_rate is not None
    assert implied_dcf_growth_rate(100.0, 5.0, 0.10, 0.03, 5) == pytest.approx(
        dcf.implied_growth_rate
    )


def test_asset_report_uses_existing_db_inputs_and_marks_missing_fundamentals(tmp_path):
    db = DB(str(tmp_path / "analytics.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, shares_outstanding)
        VALUES ('AAPL', 'AAPL', 'stock', 'USD', 1000)
        """
    )

    start = date(2025, 1, 1)
    for i in range(300):
        close = 100.0 + i
        db.conn.execute(
            """
            INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
            VALUES ('AAPL', ?, ?, ?, 'test')
            """,
            [start + timedelta(days=i), close, close],
        )

    report = AnalyticsEngine(AnalyticsRepository(db.conn)).asset_report("AAPL")

    assert report.latest_price == pytest.approx(399.0)
    assert report.data_coverage.daily_price_count == 300
    assert report.risk.observations == 300
    assert report.dividend_discount.intrinsic_value_per_share is None
    assert "annual dividend" in report.dividend_discount.missing_inputs
    assert report.discounted_cash_flow.intrinsic_value_per_share is None
    assert "cash flow per share" in report.discounted_cash_flow.missing_inputs
    assert "income statement" in report.valuation_depth.missing_inputs
    assert report.etf is None
    assert "fundamental growth history" in report.forecast.missing_inputs
    assert report.ai_context.subject_type == "asset"
    assert report.ai_context.snapshot_hash is not None
    assert any(fact.key == "latest_price" for fact in report.ai_context.facts)
    assert any(anomaly.metric == "missing_inputs" for anomaly in report.ai_context.anomalies)


def test_asset_report_uses_default_benchmark_from_asset_metadata(tmp_path):
    db = DB(str(tmp_path / "analytics_default_benchmark.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO benchmark_index(
            index_id,
            index_name,
            index_family,
            index_category,
            country_code,
            currency,
            is_core,
            is_active
        )
        VALUES ('SP500', 'S&P 500', 'S&P', 'core_geo', 'US', 'USD', TRUE, TRUE)
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, country)
        VALUES ('AAPL', 'AAPL', 'stock', 'USD', 'US')
        """
    )
    start = date(2025, 1, 1)
    for i in range(6):
        db.conn.execute(
            """
            INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
            VALUES ('AAPL', ?, ?, ?, 'test')
            """,
            [start + timedelta(days=i), 100.0 + i, 100.0 + i],
        )
        db.conn.execute(
            """
            INSERT INTO benchmark_index_daily_price(
                index_id,
                price_date,
                close,
                adj_close,
                source,
                source_symbol
            )
            VALUES ('SP500', ?, ?, ?, 'test', 'SPY')
            """,
            [start + timedelta(days=i), 200.0 + i, 200.0 + i],
        )

    report = AnalyticsEngine(AnalyticsRepository(db.conn)).asset_report("AAPL")

    assert report.benchmark_index_id == "SP500"
    assert report.relative is not None
    assert report.relative.beta is not None


def test_portfolio_report_builds_weighted_return_series(tmp_path):
    db = DB(str(tmp_path / "portfolio_analytics.db"))
    init_db(db)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Core')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES ('AAA', 'AAA', 'stock', 'USD'), ('BBB', 'BBB', 'etf', 'USD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO position(portfolio_id, asset_id, qty, book_cost, created_at, updated_at)
        VALUES
            (1, 'AAA', 2, 200, now(), now()),
            (1, 'BBB', 1, 100, now(), now())
        """
    )

    start = date(2025, 1, 1)
    for i in range(10):
        db.conn.execute(
            """
            INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
            VALUES
                ('AAA', ?, ?, ?, 'test'),
                ('BBB', ?, ?, ?, 'test')
            """,
            [
                start + timedelta(days=i),
                100.0 + i,
                100.0 + i,
                start + timedelta(days=i),
                50.0 + (i * 0.5),
                50.0 + (i * 0.5),
            ],
        )

    report = AnalyticsEngine(AnalyticsRepository(db.conn)).portfolio_report(1)

    assert report.market_value == pytest.approx((2 * 109.0) + 54.5)
    assert report.benchmark_index_id is None
    assert len(report.positions) == 2
    assert sum(p.weight for p in report.positions if p.weight is not None) == pytest.approx(1.0)
    assert report.risk is not None
    assert report.risk.observations == 10
    assert report.performance.ending_market_value == pytest.approx(report.market_value)
    assert report.risk_decomposition.asset_count == 2
    assert report.risk_decomposition.diversification_score == pytest.approx(64.0)
    assert report.forecast.simulation is not None
    assert report.valuation.weighted_pe_ratio is None
    assert report.missing_inputs == []
    assert report.ai_context.subject_type == "portfolio"
    assert report.ai_context.snapshot_hash is not None
    assert any(fact.key == "market_value" for fact in report.ai_context.facts)
    assert any(anomaly.metric == "concentration" for anomaly in report.ai_context.anomalies)


def test_portfolio_performance_tracks_cash_flows_income_and_gains():
    transactions = [
        (1, 1, date(2025, 1, 1), "contribution", None, None, None, "USD", 1000.0, 0.0),
        (2, 1, date(2025, 1, 2), "buy", "AAA", 5.0, 100.0, "USD", None, 5.0),
        (3, 1, date(2025, 2, 1), "dividend", "AAA", 5.0, 1.0, "USD", None, 0.0),
        (4, 1, date(2025, 3, 1), "sell", "AAA", 2.0, 120.0, "USD", None, 2.0),
        (5, 1, date(2025, 3, 15), "withdrawal", None, None, None, "USD", 100.0, 0.0),
    ]

    metrics = portfolio_performance_metrics(
        transactions=transactions,
        ending_market_value=360.0,
        unrealized_gain=57.0,
    )

    assert metrics.net_contributions == pytest.approx(1000.0)
    assert metrics.net_withdrawals == pytest.approx(100.0)
    assert metrics.net_external_cash_flow == pytest.approx(900.0)
    assert metrics.dividend_income == pytest.approx(5.0)
    assert metrics.realized_gain == pytest.approx(36.0)
    assert metrics.unrealized_gain == pytest.approx(57.0)
    assert metrics.total_gain == pytest.approx(98.0)
    assert metrics.modified_dietz_return is not None
    assert metrics.money_weighted_return is not None
    assert metrics.missing_inputs == []


def test_money_weighted_return_solves_cash_flow_irr():
    flows = [
        (date(2025, 1, 1), -100.0),
        (date(2026, 1, 1), 110.0),
    ]

    assert money_weighted_return(flows) == pytest.approx(0.10, abs=0.001)


def test_portfolio_report_includes_ledger_performance_metrics(tmp_path):
    db = DB(str(tmp_path / "portfolio_performance.db"))
    init_db(db)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Core')")
    db.conn.execute("INSERT INTO import_batch(batch_id, batch_type) VALUES (1, 'manual-entry')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES ('AAA', 'AAA', 'stock', 'USD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO txn(
            txn_id,
            portfolio_id,
            time_stamp,
            txn_type,
            asset_id,
            qty,
            price,
            ccy,
            cash_amt,
            fee_amt,
            batch_id
        )
        VALUES
            (1, 1, '2025-01-01 09:00:00', 'contribution', NULL, NULL, NULL, 'USD', 1000, 0, 1),
            (2, 1, '2025-01-02 09:00:00', 'buy', 'AAA', 5, 100, 'USD', NULL, 5, 1),
            (3, 1, '2025-02-01 09:00:00', 'dividend', 'AAA', 5, 1, 'USD', NULL, 0, 1),
            (4, 1, '2025-03-01 09:00:00', 'sell', 'AAA', 2, 120, 'USD', NULL, 2, 1)
        """
    )
    db.conn.execute(
        """
        INSERT INTO position(portfolio_id, asset_id, qty, book_cost, created_at, updated_at)
        VALUES (1, 'AAA', 3, 303, now(), now())
        """
    )
    start = date(2025, 1, 1)
    for i in range(10):
        close = 100.0 + i
        db.conn.execute(
            """
            INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
            VALUES ('AAA', ?, ?, ?, 'test')
            """,
            [start + timedelta(days=i), close, close],
        )

    report = AnalyticsEngine(AnalyticsRepository(db.conn)).portfolio_report(1)

    assert report.performance.net_contributions == pytest.approx(1000.0)
    assert report.performance.dividend_income == pytest.approx(5.0)
    assert report.performance.realized_gain == pytest.approx(36.0)
    assert report.performance.unrealized_gain == pytest.approx((3 * 109.0) - 303.0)


def test_valuation_depth_extracts_fundamental_ratios_and_scenarios():
    metrics = valuation_depth_metrics(
        income_statements=[
            {
                "data": {
                    "revenue": 1200.0,
                    "grossProfit": 720.0,
                    "operatingIncome": 360.0,
                    "netIncome": 240.0,
                    "eps": 2.4,
                    "ebitda": 420.0,
                }
            },
            {
                "data": {
                    "revenue": 1000.0,
                    "netIncome": 200.0,
                    "eps": 2.0,
                }
            },
        ],
        balance_sheets=[
            {
                "data": {
                    "totalStockholdersEquity": 800.0,
                    "totalAssets": 1600.0,
                    "totalDebt": 300.0,
                    "cashAndCashEquivalents": 50.0,
                }
            }
        ],
        cashflow_statements=[
            {"data": {"freeCashFlow": 180.0}},
            {"data": {"freeCashFlow": 150.0}},
        ],
        market_price=36.0,
        shares_outstanding=100.0,
        annual_dividend=1.2,
        discount_rate=0.10,
        base_growth_rate=0.04,
        terminal_growth_rate=0.03,
        forecast_years=5,
    )

    assert metrics.revenue_growth_yoy == pytest.approx(0.20)
    assert metrics.eps_growth_yoy == pytest.approx(0.20)
    assert metrics.free_cash_flow_growth_yoy == pytest.approx(0.20)
    assert metrics.gross_margin == pytest.approx(0.60)
    assert metrics.operating_margin == pytest.approx(0.30)
    assert metrics.net_margin == pytest.approx(0.20)
    assert metrics.return_on_equity == pytest.approx(0.30)
    assert metrics.return_on_assets == pytest.approx(0.15)
    assert metrics.debt_to_equity == pytest.approx(0.375)
    assert metrics.net_debt_to_ebitda == pytest.approx(250.0 / 420.0)
    assert metrics.payout_ratio == pytest.approx(0.50)
    assert metrics.pe_ratio == pytest.approx(15.0)
    assert metrics.price_to_book == pytest.approx(4.5)
    assert metrics.price_to_sales == pytest.approx(3.0)
    assert metrics.price_to_free_cash_flow == pytest.approx(20.0)
    assert metrics.ev_to_ebitda == pytest.approx(3850.0 / 420.0)
    assert [scenario.scenario_name for scenario in metrics.dcf_scenarios] == [
        "bear",
        "base",
        "bull",
    ]
    assert all(scenario.intrinsic_value_per_share is not None for scenario in metrics.dcf_scenarios)
    assert metrics.missing_inputs == []


def test_asset_report_includes_valuation_depth_from_statement_json(tmp_path):
    db = DB(str(tmp_path / "valuation_depth.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, shares_outstanding)
        VALUES ('AAPL', 'AAPL', 'stock', 'USD', 100)
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        VALUES ('AAPL', DATE '2026-01-05', 36, 36, 'test')
        """
    )
    db.conn.execute(
        """
        INSERT INTO dividend_event(asset_id, ex_date, dividend_per_share, source)
        VALUES
            ('AAPL', DATE '2025-12-01', 0.30, 'test'),
            ('AAPL', DATE '2025-09-01', 0.30, 'test'),
            ('AAPL', DATE '2025-06-01', 0.30, 'test'),
            ('AAPL', DATE '2025-03-01', 0.30, 'test')
        """
    )
    db.conn.execute(
        """
        INSERT INTO financial_statement(
            asset_id,
            statement_type,
            year,
            quarter,
            data_json,
            source
        )
        VALUES
            ('AAPL', 'income', 2025, 4, ?, 'test'),
            ('AAPL', 'income', 2024, 4, ?, 'test'),
            ('AAPL', 'balance', 2025, 4, ?, 'test'),
            ('AAPL', 'cashflow', 2025, 4, ?, 'test'),
            ('AAPL', 'cashflow', 2024, 4, ?, 'test')
        """
        ,
        [
            '{"revenue":1200,"grossProfit":720,"operatingIncome":360,"netIncome":240,"eps":2.4,"ebitda":420}',
            '{"revenue":1000,"netIncome":200,"eps":2.0}',
            '{"totalStockholdersEquity":800,"totalAssets":1600,"totalDebt":300,"cashAndCashEquivalents":50}',
            '{"freeCashFlow":180}',
            '{"freeCashFlow":150}',
        ],
    )

    report = AnalyticsEngine(AnalyticsRepository(db.conn)).asset_report("AAPL")

    assert report.valuation_depth.revenue_growth_yoy == pytest.approx(0.20)
    assert report.valuation_depth.pe_ratio == pytest.approx(15.0)
    assert report.valuation_depth.price_to_free_cash_flow == pytest.approx(20.0)
    assert report.valuation_depth.dcf_scenarios[1].scenario_name == "base"
    assert report.valuation_depth.missing_inputs == []
    assert report.forecast.expected_cagr_from_valuation is not None
    assert report.forecast.fundamental_growth_assumption == pytest.approx(0.20)
    assert report.forecast.blended_expected_cagr is not None
    assert report.ai_context.summary.startswith("AAPL has latest price")
    assert any(explanation.topic == "valuation" for explanation in report.ai_context.explanations)


def test_portfolio_report_rolls_up_holding_valuation_metrics(tmp_path):
    db = DB(str(tmp_path / "portfolio_valuation_rollup.db"))
    init_db(db)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Core')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, shares_outstanding)
        VALUES
            ('AAA', 'AAA', 'stock', 'USD', 100),
            ('BBB', 'BBB', 'stock', 'USD', 100)
        """
    )
    db.conn.execute(
        """
        INSERT INTO position(portfolio_id, asset_id, qty, book_cost, created_at, updated_at)
        VALUES
            (1, 'AAA', 1, 20, now(), now()),
            (1, 'BBB', 1, 10, now(), now())
        """
    )
    for asset_id, close, net_income, fcf in [
        ("AAA", 20.0, 100.0, 100.0),
        ("BBB", 10.0, 50.0, 50.0),
    ]:
        db.conn.execute(
            """
            INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
            VALUES
                (?, DATE '2026-01-01', ?, ?, 'test'),
                (?, DATE '2026-01-02', ?, ?, 'test')
            """,
            [asset_id, close - 1, close - 1, asset_id, close, close],
        )
        db.conn.execute(
            """
            INSERT INTO financial_statement(asset_id, statement_type, year, quarter, data_json, source)
            VALUES
                (?, 'income', 2025, 4, ?, 'test'),
                (?, 'balance', 2025, 4, ?, 'test'),
                (?, 'cashflow', 2025, 4, ?, 'test'),
                (?, 'cashflow', 2024, 4, ?, 'test')
            """,
            [
                asset_id,
                f'{{"revenue":500,"netIncome":{net_income},"eps":{net_income / 100}}}',
                asset_id,
                '{"totalStockholdersEquity":250,"totalAssets":500,"totalDebt":50}',
                asset_id,
                f'{{"freeCashFlow":{fcf}}}',
                asset_id,
                f'{{"freeCashFlow":{fcf * 0.9}}}',
            ],
        )

    report = AnalyticsEngine(AnalyticsRepository(db.conn)).portfolio_report(1)

    assert report.valuation.weighted_pe_ratio == pytest.approx(20.0)
    assert report.valuation.weighted_price_to_free_cash_flow == pytest.approx(20.0)
    assert report.valuation.weighted_expected_cagr is not None
    assert report.forecast.expected_cagr_from_valuation == pytest.approx(
        report.valuation.weighted_expected_cagr
    )
    assert report.forecast.blended_expected_cagr == pytest.approx(
        report.valuation.weighted_expected_cagr
    )
    assert len(report.valuation.position_contributions) == 2
    assert any(fact.key == "weighted_pe_ratio" for fact in report.ai_context.facts)
    assert any(explanation.topic == "portfolio_valuation" for explanation in report.ai_context.explanations)


def test_portfolio_valuation_rollup_uses_cdr_underlying_fundamentals(tmp_path):
    db = DB(str(tmp_path / "portfolio_cdr_valuation_rollup.db"))
    init_db(db)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Core')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, asset_subtype, ccy, name, shares_outstanding)
        VALUES
            ('AMD', 'AMD', 'stock', NULL, 'USD', 'Advanced Micro Devices', 100),
            ('AMD.TO', 'AMD.TO', 'stock', 'cdr', 'CAD', 'AMD Canadian Depositary Receipt', NULL)
        """
    )
    db.conn.execute(
        """
        INSERT INTO position(portfolio_id, asset_id, qty, book_cost, created_at, updated_at)
        VALUES (1, 'AMD.TO', 1, 10, now(), now())
        """
    )
    for asset_id, close in [("AMD", 20.0), ("AMD.TO", 10.0)]:
        db.conn.execute(
            """
            INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
            VALUES
                (?, DATE '2026-01-01', ?, ?, 'test'),
                (?, DATE '2026-01-02', ?, ?, 'test')
            """,
            [asset_id, close - 1, close - 1, asset_id, close, close],
        )
    db.conn.execute(
        """
        INSERT INTO financial_statement(asset_id, statement_type, year, quarter, data_json, source)
        VALUES
            ('AMD', 'income', 2025, 4, '{"revenue":500,"netIncome":100,"eps":1}', 'test'),
            ('AMD', 'balance', 2025, 4, '{"totalStockholdersEquity":250,"totalAssets":500,"totalDebt":50}', 'test'),
            ('AMD', 'cashflow', 2025, 4, '{"freeCashFlow":100}', 'test'),
            ('AMD', 'cashflow', 2024, 4, '{"freeCashFlow":90}', 'test')
        """
    )

    report = AnalyticsEngine(AnalyticsRepository(db.conn)).portfolio_report(1)

    assert report.valuation.weighted_pe_ratio == pytest.approx(20.0)
    assert report.valuation.weighted_price_to_free_cash_flow == pytest.approx(20.0)
    assert report.valuation.weighted_margin_of_safety is not None
    assert report.valuation.position_contributions[0].asset_id == "AMD.TO"
    assert report.valuation.position_contributions[0].valuation_asset_id == "AMD"
    assert report.valuation.position_contributions[0].fee_adjustment == pytest.approx(0.006)
    assert "AMD.TO: income statement" not in report.valuation.missing_inputs
    assert "AMD.TO: dividend growth history" not in report.valuation.missing_inputs


def test_cdr_aliases_use_underlying_company_for_valuation(tmp_path):
    db = DB(str(tmp_path / "portfolio_cdr_alias_valuation.db"))
    init_db(db)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Core')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name)
        VALUES
            ('CEGS.TO', 'CEGS.TO', 'stock', 'CAD', 'Constellation Energy CDR (CAD Hedged)'),
            ('NVON.NE', 'NVON.NE', 'stock', 'CAD', 'Novo Nordisk A/S Depositary Receipt'),
            ('UBER.TO', 'UBER.TO', 'stock', 'CAD', 'UBER')
        """
    )

    repo = AnalyticsRepository(db.conn)

    assert repo.valuation_asset_id("CEGS.TO") == "CEG"
    assert repo.valuation_asset_id("NVON.NE") == "NVO"
    assert repo.valuation_asset_id("UBER.TO") == "UBER"


def test_portfolio_expected_cagr_is_not_normalized_over_missing_holdings(tmp_path):
    db = DB(str(tmp_path / "portfolio_partial_expected_cagr.db"))
    init_db(db)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Core')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, shares_outstanding)
        VALUES
            ('READY', 'READY', 'stock', 'USD', 100),
            ('MISSING', 'MISSING', 'stock', 'USD', NULL)
        """
    )
    db.conn.execute(
        """
        INSERT INTO position(portfolio_id, asset_id, qty, book_cost, created_at, updated_at)
        VALUES
            (1, 'READY', 1, 10, now(), now()),
            (1, 'MISSING', 1, 10, now(), now())
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        VALUES
            ('READY', DATE '2026-01-01', 9, 9, 'test'),
            ('READY', DATE '2026-01-02', 10, 10, 'test'),
            ('MISSING', DATE '2026-01-01', 9, 9, 'test'),
            ('MISSING', DATE '2026-01-02', 10, 10, 'test')
        """
    )
    db.conn.execute(
        """
        INSERT INTO financial_statement(asset_id, statement_type, year, quarter, data_json, source)
        VALUES
            ('READY', 'income', 2025, 4, '{"revenue":500,"netIncome":100,"eps":1}', 'test'),
            ('READY', 'balance', 2025, 4, '{"totalStockholdersEquity":250,"totalAssets":500,"totalDebt":50}', 'test'),
            ('READY', 'cashflow', 2025, 4, '{"freeCashFlow":100}', 'test'),
            ('READY', 'cashflow', 2024, 4, '{"freeCashFlow":90}', 'test')
        """
    )

    report = AnalyticsEngine(AnalyticsRepository(db.conn)).portfolio_report(1)
    ready = next(item for item in report.valuation.position_contributions if item.asset_id == "READY")

    assert ready.weight == pytest.approx(0.5)
    assert report.valuation.weighted_expected_cagr == pytest.approx(
        ready.weighted_expected_cagr_contribution
    )
    assert report.valuation.weighted_expected_cagr == pytest.approx(ready.expected_cagr * 0.5)


def test_valuation_asset_id_does_not_treat_all_tsx_stocks_as_cdrs(tmp_path):
    db = DB(str(tmp_path / "tsx_common_stock.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, asset_subtype, ccy, name)
        VALUES
            ('CSU.TO', 'CSU.TO', 'stock', NULL, 'CAD', 'Constellation Software Inc.'),
            ('VISA.TO', 'VISA.TO', 'stock', 'cdr', 'CAD', 'Visa CDR')
        """
    )

    repo = AnalyticsRepository(db.conn)

    assert repo.valuation_asset_id("CSU.TO") == "CSU.TO"
    assert repo.valuation_asset_id("VISA.TO") == "V"


def test_analytics_report_payload_has_stable_public_shape(tmp_path):
    db = DB(str(tmp_path / "analytics_payload.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES ('AAPL', 'AAPL', 'stock', 'USD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        VALUES ('AAPL', DATE '2026-01-05', 100, 100, 'test')
        """
    )

    report = AnalyticsEngine(AnalyticsRepository(db.conn)).asset_report("AAPL")
    payload = analytics_report_payload(report)

    assert payload["schema_version"] == ANALYTICS_REPORT_SCHEMA_VERSION
    assert payload["report_type"] == "asset"
    assert payload["subject_id"] == "AAPL"
    assert payload["ai_context"]["subject_type"] == "asset"
    assert payload["report"]["asset_id"] == "AAPL"
    json.dumps(payload)


def test_ai_snapshot_fact_comparison_reports_metric_changes():
    previous = AIReadinessContext(
        subject_type="asset",
        subject_id="AAPL",
        summary="previous",
        facts=[
            AnalyticsFact("latest_price", "Latest price", 100.0, "currency", "market_price", 1.0),
            AnalyticsFact("pe_ratio", "P/E ratio", 20.0, "ratio", "valuation_depth", 1.0),
        ],
    )
    current = AIReadinessContext(
        subject_type="asset",
        subject_id="AAPL",
        summary="current",
        facts=[
            AnalyticsFact("latest_price", "Latest price", 110.0, "currency", "market_price", 1.0),
            AnalyticsFact("pe_ratio", "P/E ratio", 20.0, "ratio", "valuation_depth", 1.0),
            AnalyticsFact("sharpe_ratio", "Sharpe ratio", 1.2, "ratio", "risk_return", 1.0),
        ],
    )

    changes = compare_ai_snapshot_facts(previous, current)

    latest_price = next(change for change in changes if change.key == "latest_price")
    sharpe = next(change for change in changes if change.key == "sharpe_ratio")
    assert latest_price.absolute_change == pytest.approx(10.0)
    assert latest_price.relative_change == pytest.approx(0.10)
    assert sharpe.previous_value is None
    assert sharpe.current_value == pytest.approx(1.2)


def test_forecasting_projects_dividend_growth_and_simulation_bands():
    dividends = [
        (date(2025, 12, 1), 0.30),
        (date(2025, 9, 1), 0.30),
        (date(2025, 6, 1), 0.30),
        (date(2025, 3, 1), 0.30),
        (date(2024, 12, 1), 0.25),
        (date(2024, 9, 1), 0.25),
        (date(2024, 6, 1), 0.25),
        (date(2024, 3, 1), 0.25),
    ]

    assert projected_dividend_growth(dividends) == pytest.approx(0.20)

    band = simulated_forecast_band(
        start_value=100.0,
        expected_cagr=0.08,
        annualized_volatility=0.20,
        horizon_years=5,
        simulations=200,
        seed=42,
    )

    assert band is not None
    assert band.horizon_years == 5
    assert band.p10_value < band.p50_value < band.p90_value
    assert band.p10_cagr < band.p50_cagr < band.p90_cagr


def test_asset_report_includes_etf_profile_holdings_and_overlap(tmp_path):
    db = DB(str(tmp_path / "etf_analytics.db"))
    init_db(db)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Core')")
    db.conn.execute(
        """
        CREATE TABLE etf_profile (
            asset_id TEXT PRIMARY KEY,
            expense_ratio DOUBLE,
            benchmark_index_id TEXT
        )
        """
    )
    db.conn.execute(
        """
        CREATE TABLE etf_holding (
            asset_id TEXT,
            holding_symbol TEXT,
            holding_name TEXT,
            weight_pct DOUBLE,
            sector TEXT,
            country TEXT,
            currency TEXT
        )
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES
            ('VTI', 'VTI', 'etf', 'USD'),
            ('AAPL', 'AAPL', 'stock', 'USD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO position(portfolio_id, asset_id, qty, book_cost, created_at, updated_at)
        VALUES
            (1, 'VTI', 1, 100, now(), now()),
            (1, 'AAPL', 1, 150, now(), now())
        """
    )
    db.conn.execute(
        """
        INSERT INTO etf_profile(asset_id, expense_ratio, benchmark_index_id)
        VALUES ('VTI', 0.0003, 'TOTAL_US')
        """
    )
    db.conn.execute(
        """
        INSERT INTO benchmark_index(
            index_id,
            index_name,
            index_family,
            index_category,
            country_code,
            currency,
            is_core,
            is_active
        )
        VALUES ('TOTAL_US', 'Total US Market', 'CRSP', 'core_geo', 'US', 'USD', TRUE, TRUE)
        """
    )
    db.conn.execute(
        """
        INSERT INTO etf_holding(asset_id, holding_symbol, holding_name, weight_pct, sector, country, currency)
        VALUES
            ('VTI', 'AAPL', 'Apple Inc.', 55, 'Technology', 'US', 'USD'),
            ('VTI', 'RY', 'Royal Bank of Canada', 45, 'Financials', 'CA', 'CAD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO dividend_event(asset_id, ex_date, dividend_per_share, source)
        VALUES
            ('VTI', DATE '2024-12-01', 0.25, 'test'),
            ('VTI', DATE '2024-09-01', 0.25, 'test'),
            ('VTI', DATE '2024-06-01', 0.25, 'test'),
            ('VTI', DATE '2024-03-01', 0.25, 'test')
        """
    )

    start = date(2025, 1, 1)
    for i in range(6):
        db.conn.execute(
            """
            INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
            VALUES
                ('VTI', ?, ?, ?, 'test'),
                ('AAPL', ?, ?, ?, 'test')
            """,
            [
                start + timedelta(days=i),
                100.0 + (i * 2),
                100.0 + (i * 2),
                start + timedelta(days=i),
                150.0 + i,
                150.0 + i,
            ],
        )
        db.conn.execute(
            """
            INSERT INTO benchmark_index_daily_price(
                index_id,
                price_date,
                close,
                adj_close,
                source,
                source_symbol
            )
            VALUES ('TOTAL_US', ?, ?, ?, 'test', 'VTI')
            """,
            [start + timedelta(days=i), 100.0 + (i * 1.8), 100.0 + (i * 1.8)],
        )

    report = AnalyticsEngine(AnalyticsRepository(db.conn)).asset_report("VTI", portfolio_id=1)

    assert report.etf is not None
    assert report.etf.is_etf is True
    assert report.etf.expense_ratio == pytest.approx(0.0003)
    assert report.etf.benchmark_index_id == "TOTAL_US"
    assert report.etf.annual_distribution_per_share == pytest.approx(1.0)
    assert report.etf.distribution_yield == pytest.approx(1.0 / 110.0)
    assert report.etf.tracking_error is not None
    assert report.etf.holding_count == 2
    assert report.etf.top_holdings[0].holding_symbol == "AAPL"
    assert report.etf.sector_exposure == {
        "Financials": pytest.approx(0.45),
        "Technology": pytest.approx(0.55),
    }
    assert report.etf.country_exposure == {"CA": pytest.approx(0.45), "US": pytest.approx(0.55)}
    assert len(report.etf.overlap_with_portfolio) == 1
    assert report.etf.overlap_with_portfolio[0].holding_symbol == "AAPL"
    assert report.etf.missing_inputs == []


def test_etf_report_marks_missing_optional_holdings_tables(tmp_path):
    db = DB(str(tmp_path / "etf_missing.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES ('VTI', 'VTI', 'etf', 'USD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        VALUES ('VTI', DATE '2026-01-05', 100, 100, 'test')
        """
    )

    report = AnalyticsEngine(AnalyticsRepository(db.conn)).asset_report("VTI")

    assert report.etf is not None
    assert report.etf.holding_count == 0
    assert "ETF holdings" in report.etf.missing_inputs
    assert "expense ratio" in report.etf.missing_inputs


def test_portfolio_risk_decomposition_calculates_concentration_and_exposures():
    start = date(2025, 1, 1)
    positions = [
        _position("AAA", 0.60),
        _position("BBB", 0.40),
    ]
    price_history = {
        "AAA": [
            PricePoint(start + timedelta(days=i), close)
            for i, close in enumerate([100.0, 102.0, 101.0, 105.0, 106.0])
        ],
        "BBB": [
            PricePoint(start + timedelta(days=i), close)
            for i, close in enumerate([50.0, 51.0, 52.0, 51.0, 53.0])
        ],
    }

    decomposition = portfolio_risk_decomposition(
        positions=positions,
        price_history_by_asset=price_history,
        exposure_metadata={
            "AAA": {"asset_class": "Equity", "sector": "Technology", "country": "US", "currency": "USD"},
            "BBB": {"asset_class": "Fixed income", "sector": "Financials", "country": "CA", "currency": "CAD"},
        },
    )

    assert decomposition.asset_count == 2
    assert decomposition.concentration_hhi == pytest.approx(0.52)
    assert decomposition.effective_asset_count == pytest.approx(1 / 0.52)
    assert decomposition.largest_position_weight == pytest.approx(0.60)
    assert decomposition.diversification_score == pytest.approx(96.0)
    assert decomposition.portfolio_volatility is not None
    assert decomposition.average_pairwise_correlation is not None
    assert decomposition.correlation_matrix["AAA"]["AAA"] == pytest.approx(1.0)
    assert decomposition.correlation_matrix["AAA"]["BBB"] == pytest.approx(
        decomposition.correlation_matrix["BBB"]["AAA"]
    )
    assert decomposition.sector_exposure == {
        "Financials": pytest.approx(0.40),
        "Technology": pytest.approx(0.60),
    }
    assert decomposition.asset_class_exposure == {
        "Equity": pytest.approx(0.60),
        "Fixed income": pytest.approx(0.40),
    }
    assert decomposition.country_exposure == {"CA": pytest.approx(0.40), "US": pytest.approx(0.60)}
    assert decomposition.currency_exposure == {
        "CAD": pytest.approx(0.40),
        "USD": pytest.approx(0.60),
    }
    assert len(decomposition.volatility_contributions) == 2
    contribution_total = sum(
        item.portfolio_volatility_contribution or 0.0
        for item in decomposition.volatility_contributions
    )
    assert contribution_total == pytest.approx(decomposition.portfolio_volatility)


def test_portfolio_risk_decomposition_reports_missing_return_history():
    decomposition = portfolio_risk_decomposition(
        positions=[_position("AAA", 1.0)],
        price_history_by_asset={"AAA": []},
        exposure_metadata={},
    )

    assert decomposition.asset_count == 1
    assert decomposition.diversification_score == 0.0
    assert decomposition.portfolio_volatility is None
    assert "overlapping asset return history" in decomposition.missing_inputs


def test_analytics_storage_is_disabled_by_default(tmp_path):
    db = DB(str(tmp_path / "analytics_storage_disabled.db"))
    init_db(db)

    result = AnalyticsStorageService(db.conn).refresh_due(as_of_date=date(2026, 1, 5))

    assert result.skipped is True
    assert result.reason == "analytics storage disabled"
    table_count = db.conn.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_name = 'asset_analytics_snapshot'
        """
    ).fetchone()[0]
    assert table_count == 0


def test_enabled_analytics_storage_writes_daily_asset_snapshots(tmp_path):
    db = DB(str(tmp_path / "analytics_storage_enabled.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, track)
        VALUES ('AAPL', 'AAPL', 'stock', 'USD', TRUE)
        """
    )
    start = date(2025, 1, 1)
    for i in range(20):
        close = 100.0 + i
        db.conn.execute(
            """
            INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
            VALUES ('AAPL', ?, ?, ?, 'test')
            """,
            [start + timedelta(days=i), close, close],
        )

    service = AnalyticsStorageService(db.conn, enabled=True)
    first = service.refresh_due(as_of_date=date(2026, 1, 5))
    second = service.refresh_due(as_of_date=date(2026, 1, 5))

    assert first.assets_stored == 1
    assert second.assets_stored == 0
    row = db.conn.execute(
        """
        SELECT latest_price, payload_json, missing_inputs_json
        FROM asset_analytics_snapshot
        WHERE asset_id = 'AAPL'
          AND snapshot_date = DATE '2026-01-05'
        """
    ).fetchone()
    assert row[0] == pytest.approx(119.0)
    assert '"asset_id": "AAPL"' in row[1]
    assert "annual dividend" in row[2]


def test_portfolio_storage_refreshes_when_positions_change_same_day(tmp_path):
    db = DB(str(tmp_path / "analytics_storage_portfolio.db"))
    init_db(db)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Core')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES ('AAA', 'AAA', 'stock', 'USD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO position(portfolio_id, asset_id, qty, book_cost, created_at, updated_at)
        VALUES (1, 'AAA', 1, 100, now(), now())
        """
    )
    start = date(2025, 1, 1)
    for i in range(10):
        close = 100.0 + i
        db.conn.execute(
            """
            INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
            VALUES ('AAA', ?, ?, ?, 'test')
            """,
            [start + timedelta(days=i), close, close],
        )

    service = AnalyticsStorageService(db.conn, enabled=True)
    first = service.refresh_due(
        as_of_date=date(2026, 1, 5),
        asset_ids=[],
        portfolio_ids=[1],
    )
    second = service.refresh_due(
        as_of_date=date(2026, 1, 5),
        asset_ids=[],
        portfolio_ids=[1],
    )
    db.conn.execute(
        """
        UPDATE position
        SET qty = 2,
            book_cost = 200,
            updated_at = now()
        WHERE portfolio_id = 1
          AND asset_id = 'AAA'
        """
    )
    third = service.refresh_due(
        as_of_date=date(2026, 1, 5),
        asset_ids=[],
        portfolio_ids=[1],
    )

    assert first.portfolios_stored == 1
    assert second.portfolios_stored == 0
    assert third.portfolios_stored == 1
    row = db.conn.execute(
        """
        SELECT market_value
        FROM portfolio_analytics_snapshot
        WHERE portfolio_id = 1
          AND snapshot_date = DATE '2026-01-05'
        """
    ).fetchone()
    assert row[0] == pytest.approx(218.0)


def _position(asset_id: str, weight: float):
    return type(
        "PositionStub",
        (),
        {
            "asset_id": asset_id,
            "weight": weight,
        },
    )()
