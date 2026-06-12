from datetime import date

import pytest

from dashboard.ingestion.indices.index_ingestion_service import BenchmarkIndexIngestionService
from dashboard.ingestion.indices.index_models import IndexConstituent

from tests.fixtures.fixture_index import FakeConstituentProvider, insert_test_index, insert_test_symbol


def make_constituent(
    symbol: str,
    sector: str,
    weight_pct: float,
    country_code: str = "US",
    currency: str = "USD",
):
    return IndexConstituent(
        index_id="SP500",
        constituent_symbol=symbol,
        constituent_name=symbol,
        exchange_code="XNYS",
        country_code=country_code,
        currency=currency,
        sector=sector,
        industry=None,
        weight_pct=weight_pct,
        market_cap=None,
        source="fake",
        is_proxy=False,
    )


class FailingConstituentProvider:
    provider_name = "fmp"

    def get_daily_prices(self, *args, **kwargs):
        return []

    def get_intraday_prices(self, *args, **kwargs):
        return []

    def get_constituents(self, *args, **kwargs):
        raise RuntimeError(
            "402 Client Error: Payment Required for url: "
            "https://financialmodelingprep.com/stable/etf/holdings?symbol=SPY&apikey=secret"
        )


def test_composition_snapshot_replaces_same_day_source_rows(conn):
    insert_test_index(conn)
    insert_test_symbol(
        conn,
        provider="fake",
        provider_symbol="sp500-constituent",
        symbol_purpose="constituents",
    )

    provider = FakeConstituentProvider(
        [
            make_constituent("AAPL", "Information Technology", 40.0),
            make_constituent("MSFT", "Information Technology", 30.0),
        ]
    )

    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={"fake": provider},
    )

    service.ingest_composition("SP500", snapshot_date=date(2026, 1, 31))

    provider.constituents = [
        make_constituent("NVDA", "Information Technology", 50.0),
    ]

    service.ingest_composition("SP500", snapshot_date=date(2026, 1, 31))

    rows = conn.execute(
        """
        SELECT constituent_symbol
        FROM benchmark_index_constituent
        WHERE index_id = 'SP500'
          AND snapshot_date = DATE '2026-01-31'
          AND source = 'fake'
        ORDER BY constituent_symbol;
        """
    ).fetchall()

    assert rows == [("NVDA",)]


def test_exposure_snapshot_computes_sector_weights_from_constituents(conn):
    insert_test_index(conn)
    insert_test_symbol(
        conn,
        provider="fake",
        provider_symbol="sp500-constituent",
        symbol_purpose="constituents",
    )

    provider = FakeConstituentProvider(
        [
            make_constituent("AAPL", "Information Technology", 40.0),
            make_constituent("MSFT", "Information Technology", 30.0),
            make_constituent("LLY", "Health Care", 30.0),
        ]
    )

    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={"fake": provider},
    )

    service.ingest_composition("SP500", snapshot_date=date(2026, 1, 31))

    rows = conn.execute(
        """
        SELECT dimension_value, weight_pct
        FROM benchmark_index_exposure_snapshot
        WHERE index_id = 'SP500'
          AND snapshot_date = DATE '2026-01-31'
          AND dimension_type = 'sector'
        ORDER BY dimension_value;
        """
    ).fetchall()

    assert rows == [
        ("Health Care", 30.0),
        ("Information Technology", 70.0),
    ]


def test_composition_falls_back_to_yfinance_proxy_holdings(conn):
    insert_test_index(conn)
    insert_test_symbol(
        conn,
        provider="fmp",
        provider_symbol="SPY",
        symbol_purpose="proxy_holdings",
        is_proxy=True,
    )

    provider = FakeConstituentProvider(
        [
            make_constituent("AAPL", "Information Technology", 60.0),
            make_constituent("MSFT", "Information Technology", 40.0),
        ]
    )

    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={
            "fmp": FailingConstituentProvider(),
            "yfinance": provider,
        },
    )

    count = service.ingest_composition("SP500", snapshot_date=date(2026, 1, 31))

    snapshot = conn.execute(
        """
        SELECT source, source_symbol, source_type, is_proxy, constituent_count
        FROM benchmark_index_composition_snapshot
        WHERE index_id = 'SP500'
          AND snapshot_date = DATE '2026-01-31';
        """
    ).fetchone()

    assert count == 2
    assert snapshot == ("fake", "SPY", "etf_proxy", True, 2)


def test_composition_sync_failure_redacts_provider_api_keys(conn):
    insert_test_index(conn)
    insert_test_symbol(
        conn,
        provider="fmp",
        provider_symbol="SPY",
        symbol_purpose="proxy_holdings",
        is_proxy=True,
    )

    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={"fmp": FailingConstituentProvider()},
    )

    with pytest.raises(ValueError, match="All composition providers failed"):
        service.ingest_composition("SP500", snapshot_date=date(2026, 1, 31))

    last_error = conn.execute(
        """
        SELECT last_error
        FROM benchmark_index_sync_state
        WHERE index_id = 'SP500'
          AND job_type = 'composition';
        """
    ).fetchone()[0]

    assert "secret" not in last_error
    assert "apikey=[redacted]" in last_error
