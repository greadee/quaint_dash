from datetime import date, datetime

from dashboard.ingestion.indices.index_ingestion_service import BenchmarkIndexIngestionService
from dashboard.ingestion.indices.index_scheduler import BenchmarkIndexScheduler
from dashboard.ingestion.indices.sector_industry_index_universe import NON_CORE_BENCHMARK_INDICES

from tests.ingestion_benchmarks.benchmark_fakes import (
    FailingIntradayProvider,
    FakeDailyPriceProvider,
)


def test_scheduler_refreshes_non_core_daily_prices(conn):
    provider = FakeDailyPriceProvider(closes=[100.0, 101.0])

    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={
            "yfinance": provider,
            "fmp": provider,
        },
    )

    service.seed_sector_industry_universe()

    scheduler = BenchmarkIndexScheduler(conn, service)

    result = scheduler.run_non_core_daily_refresh(
        lookback_days=5,
        end_date=date(2026, 1, 3),
    )

    stored_index_count = conn.execute(
        """
        SELECT COUNT(DISTINCT index_id)
        FROM benchmark_index_daily_price;
        """
    ).fetchone()[0]

    assert result.job_type == "non_core_daily_refresh"
    assert result.target_count == len(NON_CORE_BENCHMARK_INDICES)
    assert stored_index_count == len(NON_CORE_BENCHMARK_INDICES)
    assert result.row_count == len(NON_CORE_BENCHMARK_INDICES) * 2


def test_scheduler_does_not_refresh_non_core_intraday_when_market_closed(conn):
    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={
            "yfinance": FailingIntradayProvider(),
            "fmp": FailingIntradayProvider(),
        },
    )

    service.seed_sector_industry_universe()

    scheduler = BenchmarkIndexScheduler(
        conn,
        service,
        market_is_open_fn=lambda current_time: False,
    )

    result = scheduler.run_non_core_intraday_refresh(
        interval="5min",
        now=datetime(2026, 1, 3, 12, 0),
    )

    stored_bar_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM benchmark_index_intraday_price;
        """
    ).fetchone()[0]

    assert result.job_type == "non_core_intraday_refresh"
    assert result.target_count == len(NON_CORE_BENCHMARK_INDICES)
    assert result.row_count == 0
    assert stored_bar_count == 0


def test_scheduler_can_refresh_sector_only(conn):
    provider = FakeDailyPriceProvider(closes=[100.0, 101.0])

    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={
            "yfinance": provider,
            "fmp": provider,
        },
    )

    service.seed_sector_industry_universe()

    scheduler = BenchmarkIndexScheduler(conn, service)

    result = scheduler.run_sector_daily_refresh(
        lookback_days=5,
        end_date=date(2026, 1, 3),
    )

    categories = conn.execute(
        """
        SELECT DISTINCT b.index_category
        FROM benchmark_index_daily_price p
        JOIN benchmark_index b
          ON p.index_id = b.index_id
        ORDER BY b.index_category;
        """
    ).fetchall()

    assert result.job_type == "sector_daily_refresh"
    assert categories == [("sector",)]