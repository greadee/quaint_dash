"""
Yahoo Finance provider wrapper for Domain A historical OHLCV,
dividend, and split backfill.
"""

from __future__ import annotations

from datetime import date, timedelta
from fractions import Fraction
from typing import Optional

import yfinance as yf

from dashboard.ingestion.rate_limits import (
    InMemoryRateLimiter,
    RateLimitPolicy,
    default_rate_limiter,
    yfinance_rate_limit_policy,
)
from dashboard.ingestion.price_history.models import (
    PriceDailyRow,
    DividendEventRow,
    SplitEventRow,
)

class YahooPriceProvider:
    """
    Provider for historical OHLCV, dividends, and splits using yfinance.

    This is intended for Domain A backfill/reconciliation, not fundamentals.
    """

    source = "yfinance"

    def __init__(
        self,
        rate_limiter: InMemoryRateLimiter | None = None,
        rate_limit_policy: RateLimitPolicy | None = None,
    ) -> None:
        self.rate_limiter = rate_limiter or default_rate_limiter()
        self.rate_limit_policy = rate_limit_policy or yfinance_rate_limit_policy()
        self._history_cache = {}

    def _download_history(self, asset_id: str, start_date: date, end_date: date):
        """
        yfinance treats end as exclusive, so add one day.
        """
        cache_key = (asset_id.upper(), start_date, end_date)
        if cache_key in self._history_cache:
            return self._history_cache[cache_key]

        self.rate_limiter.acquire(self.rate_limit_policy)
        ticker = yf.Ticker(asset_id)

        history = ticker.history(
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            auto_adjust=False,
            actions=True,
        )
        self._history_cache[cache_key] = history
        return history

    @staticmethod
    def _to_float(value) -> Optional[float]:
        if value is None:
            return None
        try:
            if value != value:  # NaN check
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value) -> Optional[int]:
        if value is None:
            return None
        try:
            if value != value:  # NaN check
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _index_to_date(index_value) -> date:
        """
        yfinance returns a DatetimeIndex. Convert each index row to date.
        """
        return index_value.date()

    @staticmethod
    def _split_ratio_to_from_to(ratio: float) -> tuple[Optional[int], Optional[int]]:
        """
        yfinance reports Stock Splits as a ratio.

        Examples:
            2.0  -> 1-for-2 split represented as split_from=1, split_to=2
            0.25 -> 4-for-1 reverse split represented as split_from=4, split_to=1
        """
        if ratio is None or ratio == 0:
            return None, None

        frac = Fraction(float(ratio)).limit_denominator(100)

        if frac.numerator <= 0 or frac.denominator <= 0:
            return None, None

        return frac.denominator, frac.numerator

    def fetch_price_daily(
        self,
        asset_id: str,
        start_date: date,
        end_date: date,
    ) -> list[PriceDailyRow]:
        hist = self._download_history(asset_id, start_date, end_date)

        rows: list[PriceDailyRow] = []

        if hist is None or hist.empty:
            return rows

        for idx, item in hist.iterrows():
            rows.append(
                PriceDailyRow(
                    asset_id=asset_id,
                    price_date=self._index_to_date(idx),
                    open_price=self._to_float(item.get("Open")),
                    high_price=self._to_float(item.get("High")),
                    low_price=self._to_float(item.get("Low")),
                    close_price=self._to_float(item.get("Close")),
                    adj_close_price=self._to_float(item.get("Adj Close")),
                    volume=self._to_int(item.get("Volume")),
                    source=self.source,
                )
            )

        return rows

    def fetch_dividends(
        self,
        asset_id: str,
        start_date: date,
        end_date: date,
    ) -> list[DividendEventRow]:
        hist = self._download_history(asset_id, start_date, end_date)

        rows: list[DividendEventRow] = []

        if hist is None or hist.empty or "Dividends" not in hist.columns:
            return rows

        dividend_rows = hist[hist["Dividends"] > 0]

        for idx, item in dividend_rows.iterrows():
            rows.append(
                DividendEventRow(
                    asset_id=asset_id,
                    ex_date=self._index_to_date(idx),
                    payment_date=None,
                    record_date=None,
                    declaration_date=None,
                    dividend_per_share=self._to_float(item.get("Dividends")),
                    currency=None,
                    source=self.source,
                )
            )

        return rows

    def fetch_splits(
        self,
        asset_id: str,
        start_date: date,
        end_date: date,
    ) -> list[SplitEventRow]:
        hist = self._download_history(asset_id, start_date, end_date)

        rows: list[SplitEventRow] = []

        if hist is None or hist.empty or "Stock Splits" not in hist.columns:
            return rows

        split_rows = hist[hist["Stock Splits"] > 0]

        for idx, item in split_rows.iterrows():
            ratio = self._to_float(item.get("Stock Splits"))
            split_from, split_to = self._split_ratio_to_from_to(ratio)

            rows.append(
                SplitEventRow(
                    asset_id=asset_id,
                    ex_date=self._index_to_date(idx),
                    split_from=split_from,
                    split_to=split_to,
                    source=self.source,
                )
            )

        return rows
