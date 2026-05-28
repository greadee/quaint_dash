from datetime import date

from dashboard.ingestion.indices.index_ingestion_service import BenchmarkIndexIngestionService
from dashboard.ingestion.indices.sector_industry_index_universe import SECTOR_INDICES

from tests.ingestion_benchmarks.benchmark_fakes import FakeDailyPriceProvider

def test_non_core_daily_price_refresh_ingests_sector_industry_and_theme_rows(conn):
    provider = FakeDailyPriceProvider(closes=[100.0, 101.0])

    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={
            "yfinance": provider,
            "fmp": provider,
        },
    )

    service.seed_sector_industry_universe()

    inserted = service.ingest_non_core_daily_prices(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
    )

    expected_index_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM benchmark_index
        WHERE index_category IN ('sector', 'industry', 'theme');
        """
    ).fetchone()[0]

    stored_index_count = conn.execute(
        """
        SELECT COUNT(DISTINCT index_id)
        FROM benchmark_index_daily_price;
        """
    ).fetchone()[0]

    assert inserted == expected_index_count * 2
    assert stored_index_count == expected_index_count


def test_sector_daily_price_refresh_only_ingests_sector_rows(conn):
    provider = FakeDailyPriceProvider(closes=[100.0, 101.0])

    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={
            "yfinance": provider,
            "fmp": provider,
        },
    )

    service.seed_sector_industry_universe()

    inserted = service.ingest_daily_prices_for_category(
        index_category="sector",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
    )

    stored_ids = conn.execute(
        """
        SELECT DISTINCT index_id
        FROM benchmark_index_daily_price
        ORDER BY index_id;
        """
    ).fetchall()

    assert inserted == len(SECTOR_INDICES) * 2
    assert len(stored_ids) == len(SECTOR_INDICES)


def test_non_core_price_rows_are_marked_proxy(conn):
    provider = FakeDailyPriceProvider(closes=[100.0, 101.0])

    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={
            "yfinance": provider,
            "fmp": provider,
        },
    )

    service.seed_sector_industry_universe()

    service.ingest_daily_prices_for_category(
        index_category="sector",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
    )

    non_proxy_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM benchmark_index_daily_price
        WHERE is_proxy = FALSE;
        """
    ).fetchone()[0]

    assert non_proxy_count == 0