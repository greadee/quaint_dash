from __future__ import annotations

from datetime import date, timedelta

import pytest

from dashboard.analytics import (
    AnalyticsEngine,
    AnalyticsRepository,
    AnalyticsStorageService,
    PricePoint,
    discounted_cash_flow_model,
    dividend_discount_model,
    implied_dcf_growth_rate,
    money_weighted_return,
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
    assert report.performance.ending_market_value == pytest.approx(report.market_value)
    assert report.missing_inputs == []


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
