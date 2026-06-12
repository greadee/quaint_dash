from datetime import date

from dashboard.ingestion.indices.index_ingestion_service import BenchmarkIndexIngestionService

from tests.fixtures.fixture_index import (
    EmptyProvider,
    FakeDailyPriceProvider,
    insert_test_index,
    insert_test_symbol,
)


class FailingDailyPriceProvider:
    provider_name = "etf_proxy"

    def get_daily_prices(self, *args, **kwargs):
        raise RuntimeError(
            "403 Client Error: Forbidden for url: "
            "https://financialmodelingprep.com/api/v3/historical-price-full/IEFA?apikey=secret"
        )

    def get_intraday_prices(self, *args, **kwargs):
        return []

    def get_constituents(self, *args, **kwargs):
        return []


def test_daily_price_ingestion_upserts_bars(conn):
    insert_test_index(conn)
    insert_test_symbol(conn, provider="fake", provider_symbol="^GSPC")

    provider = FakeDailyPriceProvider(closes=[100.0, 102.0])

    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={"fake": provider},
    )

    inserted = service.ingest_daily_prices(
        index_id="SP500",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
    )

    assert inserted == 2

    provider.closes = [100.0, 105.0]

    service.ingest_daily_prices(
        index_id="SP500",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
    )

    row = conn.execute(
        """
        SELECT COUNT(*), MAX(close)
        FROM benchmark_index_daily_price
        WHERE index_id = 'SP500';
        """
    ).fetchone()

    assert row[0] == 2
    assert row[1] == 105.0


def test_daily_price_ingestion_computes_1d_return(conn):
    insert_test_index(conn)
    insert_test_symbol(conn, provider="fake", provider_symbol="^GSPC")

    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={"fake": FakeDailyPriceProvider(closes=[100.0, 102.0])},
    )

    service.ingest_daily_prices(
        index_id="SP500",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
    )

    row = conn.execute(
        """
        SELECT previous_close, price_return_1d
        FROM benchmark_index_daily_price
        WHERE index_id = 'SP500'
          AND price_date = DATE '2026-01-02';
        """
    ).fetchone()

    assert row[0] == 100.0
    assert round(row[1], 4) == 0.0200


def test_provider_fallback_marks_proxy_rows_correctly(conn):
    insert_test_index(conn)

    insert_test_symbol(
        conn,
        provider="empty",
        provider_symbol="^MISSING",
        symbol_purpose="price_daily",
        is_primary=True,
        is_proxy=False,
    )

    insert_test_symbol(
        conn,
        provider="proxy",
        provider_symbol="SPY",
        symbol_purpose="proxy_price",
        is_primary=False,
        is_proxy=True,
    )

    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={
            "empty": EmptyProvider(),
            "proxy": FakeDailyPriceProvider(closes=[100.0, 101.0]),
        },
    )

    service.ingest_daily_prices(
        index_id="SP500",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
    )

    row = conn.execute(
        """
        SELECT source_symbol, is_proxy
        FROM benchmark_index_daily_price
        WHERE index_id = 'SP500'
        ORDER BY price_date
        LIMIT 1;
        """
    ).fetchone()

    assert row[0] == "SPY"
    assert row[1] is True


def test_proxy_price_falls_back_to_yfinance_symbol(conn):
    insert_test_index(conn, index_id="DEV_INTL")
    insert_test_symbol(
        conn,
        index_id="DEV_INTL",
        provider="etf_proxy",
        provider_symbol="IEFA",
        symbol_purpose="proxy_price",
        is_primary=True,
        is_proxy=True,
    )

    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={
            "etf_proxy": FailingDailyPriceProvider(),
            "yfinance": FakeDailyPriceProvider(closes=[70.0, 71.0]),
        },
    )

    inserted = service.ingest_daily_prices(
        index_id="DEV_INTL",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
    )

    row = conn.execute(
        """
        SELECT source_symbol, is_proxy
        FROM benchmark_index_daily_price
        WHERE index_id = 'DEV_INTL'
        ORDER BY price_date
        LIMIT 1;
        """
    ).fetchone()

    assert inserted == 2
    assert row == ("IEFA", True)
