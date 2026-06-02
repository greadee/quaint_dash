from __future__ import annotations

from datetime import date, timedelta

import pytest

from dashboard.analytics import (
    AnalyticsEngine,
    AnalyticsRepository,
    PricePoint,
    discounted_cash_flow_model,
    dividend_discount_model,
    implied_dcf_growth_rate,
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
    assert len(report.positions) == 2
    assert sum(p.weight for p in report.positions if p.weight is not None) == pytest.approx(1.0)
    assert report.risk is not None
    assert report.risk.observations == 10
    assert report.missing_inputs == []
