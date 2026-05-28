from __future__ import annotations

from datetime import date, datetime, timezone

import duckdb
import pytest

from dashboard.ingestion.indices.index_models import (
    IndexConstituent,
    IndexDailyBar,
    IndexIntradayBar,
)


BENCHMARK_INDEX_TEST_SCHEMA = """
CREATE TABLE benchmark_index (
    index_id TEXT PRIMARY KEY,
    index_name TEXT NOT NULL,
    index_family TEXT NOT NULL,
    index_category TEXT NOT NULL,
    region TEXT,
    country_code TEXT,
    currency TEXT NOT NULL,
    is_core BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE benchmark_index_symbol (
    index_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_symbol TEXT NOT NULL,
    symbol_purpose TEXT NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    is_proxy BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (index_id, provider, provider_symbol, symbol_purpose)
);

CREATE TABLE benchmark_index_daily_price (
    index_id TEXT NOT NULL,
    price_date DATE NOT NULL,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE NOT NULL,
    adj_close DOUBLE,
    volume DOUBLE,
    previous_close DOUBLE,
    price_return_1d DOUBLE,
    total_return_1d DOUBLE,
    source TEXT NOT NULL,
    source_symbol TEXT NOT NULL,
    is_proxy BOOLEAN NOT NULL DEFAULT FALSE,
    fetched_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (index_id, price_date)
);

CREATE TABLE benchmark_index_intraday_price (
    index_id TEXT NOT NULL,
    interval TEXT NOT NULL,
    bar_start_utc TIMESTAMP NOT NULL,
    open DOUBLE NOT NULL,
    high DOUBLE NOT NULL,
    low DOUBLE NOT NULL,
    close DOUBLE NOT NULL,
    volume DOUBLE,
    source TEXT NOT NULL,
    source_symbol TEXT NOT NULL,
    is_proxy BOOLEAN NOT NULL DEFAULT FALSE,
    fetched_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (index_id, interval, bar_start_utc)
);

CREATE TABLE benchmark_index_composition_snapshot (
    index_id TEXT NOT NULL,
    snapshot_date DATE NOT NULL,
    source TEXT NOT NULL,
    source_symbol TEXT,
    source_type TEXT NOT NULL,
    is_proxy BOOLEAN NOT NULL DEFAULT FALSE,
    constituent_count INTEGER,
    total_weight_pct DOUBLE,
    data_quality TEXT NOT NULL DEFAULT 'unknown',
    notes TEXT,
    fetched_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (index_id, snapshot_date, source)
);

CREATE TABLE benchmark_index_constituent (
    index_id TEXT NOT NULL,
    snapshot_date DATE NOT NULL,
    source TEXT NOT NULL,
    constituent_symbol TEXT NOT NULL,
    constituent_name TEXT,
    exchange_code TEXT,
    country_code TEXT,
    currency TEXT,
    sector TEXT,
    industry TEXT,
    weight_pct DOUBLE,
    market_cap DOUBLE,
    is_proxy BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (
        index_id,
        snapshot_date,
        source,
        constituent_symbol
    )
);

CREATE TABLE benchmark_index_exposure_snapshot (
    index_id TEXT NOT NULL,
    snapshot_date DATE NOT NULL,
    dimension_type TEXT NOT NULL,
    dimension_value TEXT NOT NULL,
    weight_pct DOUBLE NOT NULL,
    source TEXT NOT NULL,
    source_type TEXT NOT NULL,
    is_proxy BOOLEAN NOT NULL DEFAULT FALSE,
    fetched_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (
        index_id,
        snapshot_date,
        dimension_type,
        dimension_value,
        source
    )
);

CREATE TABLE benchmark_index_daily_metric (
    index_id TEXT NOT NULL,
    metric_date DATE NOT NULL,
    return_1d DOUBLE,
    return_5d DOUBLE,
    return_21d DOUBLE,
    return_63d DOUBLE,
    return_126d DOUBLE,
    return_252d DOUBLE,
    return_ytd DOUBLE,
    volatility_21d_ann DOUBLE,
    volatility_63d_ann DOUBLE,
    volatility_252d_ann DOUBLE,
    sma_50 DOUBLE,
    sma_200 DOUBLE,
    high_52w DOUBLE,
    low_52w DOUBLE,
    drawdown_from_52w_high DOUBLE,
    source TEXT NOT NULL DEFAULT 'computed',
    computed_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (index_id, metric_date)
);

CREATE TABLE benchmark_index_relative_metric (
    index_id TEXT NOT NULL,
    comparison_index_id TEXT NOT NULL,
    metric_date DATE NOT NULL,
    correlation_252d DOUBLE,
    beta_252d DOUBLE,
    excess_return_252d DOUBLE,
    source TEXT NOT NULL DEFAULT 'computed',
    computed_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (index_id, comparison_index_id, metric_date)
);

CREATE TABLE benchmark_index_sync_state (
    index_id TEXT NOT NULL,
    job_type TEXT NOT NULL,
    last_success_at TIMESTAMP,
    last_attempt_at TIMESTAMP,
    last_success_date DATE,
    last_error TEXT,
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (index_id, job_type)
);
"""


@pytest.fixture()
def conn():
    connection = duckdb.connect(":memory:")
    connection.execute(BENCHMARK_INDEX_TEST_SCHEMA)
    yield connection
    connection.close()


def insert_test_index(
    conn,
    index_id: str = "SP500",
    index_name: str = "S&P 500",
    currency: str = "USD",
    is_core: bool = True,
):
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
        VALUES (?, ?, 'TestFamily', 'core_geo', 'North America', 'US', ?, ?, TRUE)
        ON CONFLICT (index_id) DO NOTHING;
        """,
        [index_id, index_name, currency, is_core],
    )


def insert_test_symbol(
    conn,
    index_id: str = "SP500",
    provider: str = "fake",
    provider_symbol: str = "^GSPC",
    symbol_purpose: str = "price_daily",
    is_primary: bool = True,
    is_proxy: bool = False,
):
    conn.execute(
        """
        INSERT INTO benchmark_index_symbol (
            index_id,
            provider,
            provider_symbol,
            symbol_purpose,
            is_primary,
            is_proxy
        )
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        [
            index_id,
            provider,
            provider_symbol,
            symbol_purpose,
            is_primary,
            is_proxy,
        ],
    )


def insert_daily_price_rows(conn, index_id: str, start_close: float = 100.0, days: int = 260):
    insert_test_index(conn, index_id=index_id)

    for i in range(days):
        price_date = date(2025, 1, 1).fromordinal(date(2025, 1, 1).toordinal() + i)
        close = start_close + i

        previous_close = None if i == 0 else start_close + i - 1
        price_return_1d = None

        if previous_close is not None:
            price_return_1d = (close / previous_close) - 1

        conn.execute(
            """
            INSERT INTO benchmark_index_daily_price (
                index_id,
                price_date,
                open,
                high,
                low,
                close,
                adj_close,
                volume,
                previous_close,
                price_return_1d,
                total_return_1d,
                source,
                source_symbol,
                is_proxy
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'test', ?, FALSE);
            """,
            [
                index_id,
                price_date,
                close - 1,
                close + 1,
                close - 2,
                close,
                close,
                1000,
                previous_close,
                price_return_1d,
                price_return_1d,
                index_id,
            ],
        )


class FakeDailyPriceProvider:
    provider_name = "fake"

    def __init__(self, closes: list[float] | None = None):
        self.closes = closes or [100.0, 102.0]

    def get_daily_prices(
        self,
        index_id: str,
        provider_symbol: str,
        start_date: date,
        end_date: date,
        is_proxy: bool,
    ) -> list[IndexDailyBar]:
        bars = []

        for i, close in enumerate(self.closes):
            price_date = date(2026, 1, 1).fromordinal(date(2026, 1, 1).toordinal() + i)

            bars.append(
                IndexDailyBar(
                    index_id=index_id,
                    price_date=price_date,
                    open=close - 1,
                    high=close + 1,
                    low=close - 2,
                    close=close,
                    adj_close=close,
                    volume=1000 + i,
                    source=self.provider_name,
                    source_symbol=provider_symbol,
                    is_proxy=is_proxy,
                )
            )

        return bars

    def get_intraday_prices(self, *args, **kwargs):
        return []

    def get_constituents(self, *args, **kwargs):
        return []


class EmptyProvider:
    provider_name = "empty"

    def get_daily_prices(self, *args, **kwargs):
        return []

    def get_intraday_prices(self, *args, **kwargs):
        return []

    def get_constituents(self, *args, **kwargs):
        return []


class FakeIntradayProvider:
    provider_name = "fake"

    def get_daily_prices(self, *args, **kwargs):
        return []

    def get_intraday_prices(
        self,
        index_id: str,
        provider_symbol: str,
        interval: str,
        is_proxy: bool,
    ) -> list[IndexIntradayBar]:
        return [
            IndexIntradayBar(
                index_id=index_id,
                interval=interval,
                bar_start_utc=datetime(2026, 1, 2, 15, 30, tzinfo=timezone.utc),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1000,
                source=self.provider_name,
                source_symbol=provider_symbol,
                is_proxy=is_proxy,
            )
        ]

    def get_constituents(self, *args, **kwargs):
        return []


class FakeConstituentProvider:
    provider_name = "fake"

    def __init__(self, constituents: list[IndexConstituent]):
        self.constituents = constituents

    def get_daily_prices(self, *args, **kwargs):
        return []

    def get_intraday_prices(self, *args, **kwargs):
        return []

    def get_constituents(
        self,
        index_id: str,
        provider_symbol: str,
        is_proxy: bool,
    ) -> list[IndexConstituent]:
        return [
            IndexConstituent(
                index_id=index_id,
                constituent_symbol=item.constituent_symbol,
                constituent_name=item.constituent_name,
                exchange_code=item.exchange_code,
                country_code=item.country_code,
                currency=item.currency,
                sector=item.sector,
                industry=item.industry,
                weight_pct=item.weight_pct,
                market_cap=item.market_cap,
                source=self.provider_name,
                is_proxy=is_proxy,
            )
            for item in self.constituents
        ]


class FailingIntradayProvider:
    provider_name = "failing"

    def get_daily_prices(self, *args, **kwargs):
        return []

    def get_intraday_prices(self, *args, **kwargs):
        raise AssertionError("Intraday provider should not be called when market is closed")

    def get_constituents(self, *args, **kwargs):
        return []