from __future__ import annotations

from datetime import date, datetime, timezone

from dashboard.ingestion.indices.index_models import (
    IndexConstituent,
    IndexDailyBar,
    IndexIntradayBar,
)


class FakeDailyPriceProvider:
    provider_name = "fake"

    def __init__(self, closes: list[float] | None = None):
        self.closes = closes or [100.0, 101.0]

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
            price_date = date(2026, 1, 1).fromordinal(
                date(2026, 1, 1).toordinal() + i
            )

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
        raise AssertionError(
            "Intraday provider should not be called when market is closed"
        )

    def get_constituents(self, *args, **kwargs):
        return []