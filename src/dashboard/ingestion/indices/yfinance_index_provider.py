from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
import yfinance as yf

from dashboard.ingestion.indices.index_models import (
    IndexConstituent,
    IndexDailyBar,
    IndexIntradayBar,
)


class YFinanceIndexProvider:
    """
    yfinance provider.

    Use this primarily for price bars because it avoids burning FMP API calls.
    Composition is intentionally unsupported here because yfinance is not a
    reliable source of benchmark index constituents.
    """

    provider_name = "yfinance"

    def get_daily_prices(
        self,
        index_id: str,
        provider_symbol: str,
        start_date: date,
        end_date: date,
        is_proxy: bool,
    ) -> list[IndexDailyBar]:
        df = yf.download(
            provider_symbol,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )

        if df is None or df.empty:
            return []

        df = self._flatten_yfinance_columns(df)
        bars: list[IndexDailyBar] = []

        for raw_index, row in df.iterrows():
            close = self._float_or_none(row.get("Close"))
            if close is None:
                continue

            price_date = self._to_date(raw_index)

            bars.append(
                IndexDailyBar(
                    index_id=index_id,
                    price_date=price_date,
                    open=self._float_or_none(row.get("Open")),
                    high=self._float_or_none(row.get("High")),
                    low=self._float_or_none(row.get("Low")),
                    close=close,
                    adj_close=self._float_or_none(row.get("Adj Close")),
                    volume=self._float_or_none(row.get("Volume")),
                    source=self.provider_name,
                    source_symbol=provider_symbol,
                    is_proxy=is_proxy,
                )
            )

        return bars

    def get_intraday_prices(
        self,
        index_id: str,
        provider_symbol: str,
        interval: str,
        is_proxy: bool,
    ) -> list[IndexIntradayBar]:
        yf_interval = self._map_interval(interval)

        df = yf.download(
            provider_symbol,
            period="5d",
            interval=yf_interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )

        if df is None or df.empty:
            return []

        df = self._flatten_yfinance_columns(df)
        bars: list[IndexIntradayBar] = []

        for raw_index, row in df.iterrows():
            close = self._float_or_none(row.get("Close"))
            open_ = self._float_or_none(row.get("Open"))
            high = self._float_or_none(row.get("High"))
            low = self._float_or_none(row.get("Low"))

            if close is None or open_ is None or high is None or low is None:
                continue

            bars.append(
                IndexIntradayBar(
                    index_id=index_id,
                    interval=interval,
                    bar_start_utc=self._to_utc_datetime(raw_index),
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=self._float_or_none(row.get("Volume")),
                    source=self.provider_name,
                    source_symbol=provider_symbol,
                    is_proxy=is_proxy,
                )
            )

        return bars

    def get_constituents(
        self,
        index_id: str,
        provider_symbol: str,
        is_proxy: bool,
    ) -> list[IndexConstituent]:
        return []

    def _flatten_yfinance_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        yfinance sometimes returns a multi-index column frame even for one symbol.
        Convert it back to normal OHLCV columns.
        """
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]
        return df

    def _map_interval(self, interval: str) -> str:
        allowed = {
            "1min": "1m",
            "2min": "2m",
            "5min": "5m",
            "15min": "15m",
            "30min": "30m",
            "60min": "60m",
            "1hour": "60m",
        }

        if interval not in allowed:
            raise ValueError(f"Unsupported yfinance interval: {interval}")

        return allowed[interval]

    def _to_date(self, value: Any) -> date:
        if hasattr(value, "date"):
            return value.date()
        return datetime.fromisoformat(str(value)).date()

    def _to_utc_datetime(self, value: Any) -> datetime:
        ts = pd.Timestamp(value)

        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")

        return ts.to_pydatetime()

    def _float_or_none(self, value: Any) -> float | None:
        if value is None:
            return None

        try:
            if pd.isna(value):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None