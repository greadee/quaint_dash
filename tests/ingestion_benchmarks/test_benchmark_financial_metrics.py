from __future__ import annotations

import json
from datetime import date, datetime

import duckdb
import pytest

from dashboard.ingestion.indices.benchmark_financial_metrics import BenchmarkFinancialMetricService
from tests.fixtures.fixture_index import create_benchmark_index_tables


@pytest.fixture()
def financial_metric_conn():
    conn = duckdb.connect(":memory:")
    create_benchmark_index_tables(conn)
    conn.execute(
        """
        CREATE TABLE asset (
            asset_id TEXT PRIMARY KEY,
            symbol TEXT,
            asset_type TEXT,
            sector TEXT,
            mkt_cap DOUBLE,
            shares_outstanding DOUBLE
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE asset_quote_daily (
            asset_id TEXT NOT NULL,
            date DATE NOT NULL,
            close DOUBLE,
            adj_close DOUBLE
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE financial_statement (
            asset_id TEXT NOT NULL,
            statement_type TEXT NOT NULL,
            year INTEGER NOT NULL,
            quarter INTEGER NOT NULL,
            period_end_date DATE,
            data_json JSON,
            source TEXT NOT NULL,
            PRIMARY KEY(asset_id, statement_type, year, quarter)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE earnings_calendar_event (
            asset_id TEXT NOT NULL,
            earnings_date DATE NOT NULL,
            eps_estimated DOUBLE,
            revenue_estimated DOUBLE,
            as_of_ts TIMESTAMP
        );
        """
    )
    yield conn
    conn.close()


def test_sector_financial_metrics_store_medians_without_fabricating_missing_values(financial_metric_conn):
    conn = financial_metric_conn
    _insert_sector_index(conn, "SEC_TECH")
    _insert_asset(conn, "AAA", sector="Technology", market_cap=1000)
    _insert_asset(conn, "BBB", sector="Information Technology", market_cap=500)
    _insert_asset(conn, "CCC", sector="Technology", market_cap=750)
    _insert_price(conn, "AAA", 100)
    _insert_price(conn, "BBB", 50)
    _insert_price(conn, "CCC", 20)
    _insert_income(
        conn,
        "AAA",
        year=2025,
        quarter=4,
        payload={
            "eps": 5,
            "epsNonGaap": 5.5,
            "revenue": 200,
            "grossProfit": 120,
            "operatingIncome": 70,
            "netIncome": 50,
            "ebitda": 80,
        },
    )
    _insert_income(conn, "AAA", year=2024, quarter=4, payload={"eps": 4, "revenue": 160})
    _insert_balance(conn, "AAA", {"totalDebt": 100, "cashAndCashEquivalents": 25})
    _insert_cashflow(conn, "AAA", {"freeCashFlow": 40})
    _insert_estimate(conn, "AAA", eps=6)
    _insert_income(
        conn,
        "BBB",
        year=2025,
        quarter=4,
        payload={
            "eps": 2,
            "nonGaapEPS": 2.2,
            "revenue": 100,
            "grossProfit": 40,
            "operatingIncome": 20,
            "netIncome": 12,
            "ebitda": 30,
        },
    )
    _insert_income(conn, "BBB", year=2024, quarter=4, payload={"eps": 1, "revenue": 80})
    _insert_balance(conn, "BBB", {"totalDebt": 20, "cashAndShortTermInvestments": 5})
    _insert_cashflow(conn, "BBB", {"operatingCashFlow": 20, "capitalExpenditure": -4})
    _insert_estimate(conn, "BBB", eps=2.5)

    count = BenchmarkFinancialMetricService(conn).compute_sector_benchmark(
        "SEC_TECH",
        date(2026, 6, 20),
    )

    assert count == 1
    row = conn.execute(
        """
        SELECT
            peer_count,
            covered_peer_count,
            eps_median,
            non_gaap_eps_median,
            pe_median,
            forward_pe_median,
            peg_median,
            price_to_sales_median,
            free_cash_flow_yield_median,
            data_quality
        FROM benchmark_index_financial_metric
        WHERE index_id = 'SEC_TECH';
        """
    ).fetchone()
    assert row[0] == 3
    assert row[1] == 2
    assert row[2] == pytest.approx(3.5)
    assert row[3] == pytest.approx(3.85)
    assert row[4] == pytest.approx(22.5)
    assert row[5] == pytest.approx((100 / 6 + 50 / 2.5) / 2)
    assert row[6] == pytest.approx((0.8 + 0.25) / 2)
    assert row[7] == pytest.approx(5.0)
    assert row[8] == pytest.approx((0.04 + 0.032) / 2)
    assert row[9] == "partial"


def test_sector_financial_metrics_record_unavailable_when_no_peer_data(financial_metric_conn):
    conn = financial_metric_conn
    _insert_sector_index(conn, "SEC_UTILITIES")

    count = BenchmarkFinancialMetricService(conn).compute_sector_benchmark(
        "SEC_UTILITIES",
        date(2026, 6, 20),
    )

    assert count == 1
    row = conn.execute(
        """
        SELECT peer_count, covered_peer_count, pe_median, non_gaap_eps_median, data_quality
        FROM benchmark_index_financial_metric
        WHERE index_id = 'SEC_UTILITIES';
        """
    ).fetchone()
    assert row == (0, 0, None, None, "unavailable")


def _insert_sector_index(conn, index_id: str) -> None:
    conn.execute(
        """
        INSERT INTO benchmark_index (
            index_id,
            index_name,
            index_family,
            index_category,
            region,
            country_code,
            currency,
            is_core,
            is_active
        )
        VALUES (?, ?, 'Select Sector SPDR', 'sector', 'United States', 'US', 'USD', FALSE, TRUE);
        """,
        [index_id, index_id],
    )


def _insert_asset(conn, asset_id: str, *, sector: str, market_cap: float) -> None:
    conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, sector, mkt_cap, shares_outstanding)
        VALUES (?, ?, 'stock', ?, ?, 100);
        """,
        [asset_id, asset_id, sector, market_cap],
    )


def _insert_price(conn, asset_id: str, close: float) -> None:
    conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close)
        VALUES (?, DATE '2026-06-19', ?, ?);
        """,
        [asset_id, close, close],
    )


def _insert_income(conn, asset_id: str, *, year: int, quarter: int, payload: dict) -> None:
    conn.execute(
        """
        INSERT INTO financial_statement(asset_id, statement_type, year, quarter, period_end_date, data_json, source)
        VALUES (?, 'income', ?, ?, ?, ?, 'test');
        """,
        [asset_id, year, quarter, date(year, 12, 31), json.dumps(payload)],
    )


def _insert_balance(conn, asset_id: str, payload: dict) -> None:
    conn.execute(
        """
        INSERT INTO financial_statement(asset_id, statement_type, year, quarter, period_end_date, data_json, source)
        VALUES (?, 'balance', 2025, 4, DATE '2025-12-31', ?, 'test');
        """,
        [asset_id, json.dumps(payload)],
    )


def _insert_cashflow(conn, asset_id: str, payload: dict) -> None:
    conn.execute(
        """
        INSERT INTO financial_statement(asset_id, statement_type, year, quarter, period_end_date, data_json, source)
        VALUES (?, 'cashflow', 2025, 4, DATE '2025-12-31', ?, 'test');
        """,
        [asset_id, json.dumps(payload)],
    )


def _insert_estimate(conn, asset_id: str, eps: float) -> None:
    conn.execute(
        """
        INSERT INTO earnings_calendar_event(asset_id, earnings_date, eps_estimated, revenue_estimated, as_of_ts)
        VALUES (?, DATE '2026-02-01', ?, NULL, ?);
        """,
        [asset_id, eps, datetime(2026, 1, 15, 12, 0, 0)],
    )
