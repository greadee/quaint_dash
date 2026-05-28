from datetime import date

from dashboard.ingestion.indices.index_ingestion_service import BenchmarkIndexIngestionService
from dashboard.ingestion.indices.index_models import IndexConstituent

from tests.fixture_index import FakeConstituentProvider, insert_test_index, insert_test_symbol


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