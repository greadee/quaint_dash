from datetime import date, datetime

from dashboard.ingestion.indices.core_index_universe import CORE_INDICES
from dashboard.ingestion.indices.index_ingestion_service import BenchmarkIndexIngestionService
from dashboard.ingestion.indices.index_scheduler import BenchmarkIndexScheduler

from tests.conftest import FailingIntradayProvider, FakeDailyPriceProvider


def test_scheduler_enqueues_daily_price_jobs_for_core_indices(conn):
    provider = FakeDailyPriceProvider(closes=[100.0, 101.0])

    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={
            "fake": provider,
            "yfinance": provider,
            "fmp": provider,
            "etf_proxy": provider,
        },
    )

    service.seed_core_universe()

    scheduler = BenchmarkIndexScheduler(conn, service)

    result = scheduler.run_core_daily_refresh(
        lookback_days=5,
        end_date=date(2026, 1, 3),
    )

    stored_index_count = conn.execute(
        """
        SELECT COUNT(DISTINCT index_id)
        FROM benchmark_index_daily_price;
        """
    ).fetchone()[0]

    assert result.job_type == "core_daily_refresh"
    assert result.target_count == len(CORE_INDICES)
    assert stored_index_count == len(CORE_INDICES)
    assert result.row_count >= len(CORE_INDICES)


def test_scheduler_does_not_enqueue_intraday_jobs_when_market_closed(conn):
    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={
            "fake": FailingIntradayProvider(),
            "yfinance": FailingIntradayProvider(),
            "fmp": FailingIntradayProvider(),
            "etf_proxy": FailingIntradayProvider(),
        },
    )

    service.seed_core_universe()

    scheduler = BenchmarkIndexScheduler(
        conn,
        service,
        market_is_open_fn=lambda current_time: False,
    )

    result = scheduler.run_core_intraday_refresh(
        interval="5min",
        now=datetime(2026, 1, 3, 12, 0),
    )

    stored_bar_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM benchmark_index_intraday_price;
        """
    ).fetchone()[0]

    assert result.job_type == "core_intraday_refresh"
    assert result.target_count == len(CORE_INDICES)
    assert result.row_count == 0
    assert stored_bar_count == 0