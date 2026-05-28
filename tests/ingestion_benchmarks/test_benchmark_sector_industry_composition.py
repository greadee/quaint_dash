from datetime import date

from dashboard.ingestion.indices.index_ingestion_service import BenchmarkIndexIngestionService
from dashboard.ingestion.indices.index_models import IndexConstituent

from tests.ingestion_benchmarks.benchmark_fakes import FakeConstituentProvider

def make_proxy_constituent(
    index_id: str,
    symbol: str,
    sector: str,
    industry: str,
    weight_pct: float,
    country_code: str = "US",
    currency: str = "USD",
):
    return IndexConstituent(
        index_id=index_id,
        constituent_symbol=symbol,
        constituent_name=symbol,
        exchange_code="XNYS",
        country_code=country_code,
        currency=currency,
        sector=sector,
        industry=industry,
        weight_pct=weight_pct,
        market_cap=None,
        source="fake",
        is_proxy=True,
    )


def test_non_core_composition_ingests_proxy_holdings(conn):
    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={
            "fmp": FakeConstituentProvider(
                [
                    make_proxy_constituent(
                        "SEC_TECH",
                        "AAPL",
                        "Information Technology",
                        "Consumer Electronics",
                        40.0,
                    ),
                    make_proxy_constituent(
                        "SEC_TECH",
                        "MSFT",
                        "Information Technology",
                        "Software",
                        60.0,
                    ),
                ]
            )
        },
    )

    service.seed_sector_industry_universe()

    count = service.ingest_composition(
        index_id="SEC_TECH",
        snapshot_date=date(2026, 1, 31),
    )

    snapshot = conn.execute(
        """
        SELECT source_type, is_proxy, constituent_count, data_quality
        FROM benchmark_index_composition_snapshot
        WHERE index_id = 'SEC_TECH'
          AND snapshot_date = DATE '2026-01-31';
        """
    ).fetchone()

    assert count == 2
    assert snapshot[0] == "etf_proxy"
    assert snapshot[1] is True
    assert snapshot[2] == 2
    assert snapshot[3] == "proxy"


def test_non_core_composition_generates_industry_exposure(conn):
    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={
            "fmp": FakeConstituentProvider(
                [
                    make_proxy_constituent(
                        "SEC_TECH",
                        "AAPL",
                        "Information Technology",
                        "Consumer Electronics",
                        40.0,
                    ),
                    make_proxy_constituent(
                        "SEC_TECH",
                        "MSFT",
                        "Information Technology",
                        "Software",
                        60.0,
                    ),
                ]
            )
        },
    )

    service.seed_sector_industry_universe()

    service.ingest_composition(
        index_id="SEC_TECH",
        snapshot_date=date(2026, 1, 31),
    )

    rows = conn.execute(
        """
        SELECT dimension_value, weight_pct
        FROM benchmark_index_exposure_snapshot
        WHERE index_id = 'SEC_TECH'
          AND snapshot_date = DATE '2026-01-31'
          AND dimension_type = 'industry'
        ORDER BY dimension_value;
        """
    ).fetchall()

    assert rows == [
        ("Consumer Electronics", 40.0),
        ("Software", 60.0),
    ]