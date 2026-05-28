from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

from dashboard.ingestion.indices.index_models import (
    IndexConstituent,
    IndexDailyBar,
    IndexIntradayBar,
)


class FMPIndexProvider:
    """
    Financial Modeling Prep provider.

    Recommended use:
    - fallback for daily/intraday index prices
    - primary for supported constituents/composition
    """

    provider_name = "fmp"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://financialmodelingprep.com/api/v3",
        timeout_seconds: int = 20,
    ):
        load_dotenv()

        self.api_key = api_key or os.getenv("FMP_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

        if not self.api_key:
            raise ValueError("FMP_API_KEY is required for FMPIndexProvider")

    def get_daily_prices(
        self,
        index_id: str,
        provider_symbol: str,
        start_date: date,
        end_date: date,
        is_proxy: bool,
    ) -> list[IndexDailyBar]:
        payload = self._get(
            f"/historical-price-full/{provider_symbol}",
            {
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
            },
        )

        rows = payload.get("historical", [])
        bars: list[IndexDailyBar] = []

        for row in rows:
            close = self._float_or_none(row.get("close"))
            if close is None:
                continue

            bars.append(
                IndexDailyBar(
                    index_id=index_id,
                    price_date=datetime.strptime(row["date"], "%Y-%m-%d").date(),
                    open=self._float_or_none(row.get("open")),
                    high=self._float_or_none(row.get("high")),
                    low=self._float_or_none(row.get("low")),
                    close=close,
                    adj_close=self._float_or_none(row.get("adjClose")),
                    volume=self._float_or_none(row.get("volume")),
                    source=self.provider_name,
                    source_symbol=provider_symbol,
                    is_proxy=is_proxy,
                )
            )

        return sorted(bars, key=lambda bar: bar.price_date)

    def get_intraday_prices(
        self,
        index_id: str,
        provider_symbol: str,
        interval: str,
        is_proxy: bool,
    ) -> list[IndexIntradayBar]:
        fmp_interval = self._map_interval(interval)

        payload = self._get(
            f"/historical-chart/{fmp_interval}/{provider_symbol}",
            {},
        )

        if not isinstance(payload, list):
            return []

        bars: list[IndexIntradayBar] = []

        for row in payload:
            close = self._float_or_none(row.get("close"))
            open_ = self._float_or_none(row.get("open"))
            high = self._float_or_none(row.get("high"))
            low = self._float_or_none(row.get("low"))

            if close is None or open_ is None or high is None or low is None:
                continue

            bars.append(
                IndexIntradayBar(
                    index_id=index_id,
                    interval=interval,
                    bar_start_utc=self._parse_fmp_datetime(row["date"]),
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=self._float_or_none(row.get("volume")),
                    source=self.provider_name,
                    source_symbol=provider_symbol,
                    is_proxy=is_proxy,
                )
            )

        return sorted(bars, key=lambda bar: bar.bar_start_utc)

    def get_constituents(
        self,
        index_id: str,
        provider_symbol: str,
        is_proxy: bool,
    ) -> list[IndexConstituent]:
        endpoint = self._constituent_endpoint(provider_symbol)

        if endpoint is None:
            return []

        payload = self._get(endpoint, {})

        if not isinstance(payload, list):
            return []

        constituents: list[IndexConstituent] = []

        for row in payload:
            symbol = row.get("symbol") or row.get("ticker")
            if not symbol:
                continue

            constituents.append(
                IndexConstituent(
                    index_id=index_id,
                    constituent_symbol=str(symbol),
                    constituent_name=row.get("name") or row.get("companyName"),
                    exchange_code=row.get("exchange") or row.get("exchangeShortName"),
                    country_code=row.get("country"),
                    currency=row.get("currency"),
                    sector=row.get("sector"),
                    industry=row.get("subSector") or row.get("industry"),
                    weight_pct=self._weight_to_percent(row.get("weight")),
                    market_cap=self._float_or_none(row.get("marketCap")),
                    source=self.provider_name,
                    is_proxy=is_proxy,
                )
            )

        return constituents

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        params = dict(params)
        params["apikey"] = self.api_key

        response = requests.get(
            f"{self.base_url}{path}",
            params=params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def _constituent_endpoint(self, provider_symbol: str) -> str | None:
        """
        Keep this explicit because index constituent endpoint names vary by provider.
        Add mappings as you confirm them.
        """
        normalized = provider_symbol.strip().lower()

        endpoint_map = {
            "sp500-constituent": "/sp500_constituent",
            "nasdaq-constituent": "/nasdaq_constituent",
            "dowjones-constituent": "/dowjones_constituent",
        }

        return endpoint_map.get(normalized)

    def _map_interval(self, interval: str) -> str:
        allowed = {
            "1min": "1min",
            "5min": "5min",
            "15min": "15min",
            "30min": "30min",
            "60min": "1hour",
            "1hour": "1hour",
        }

        if interval not in allowed:
            raise ValueError(f"Unsupported FMP interval: {interval}")

        return allowed[interval]

    def _parse_fmp_datetime(self, value: str) -> datetime:
        # FMP timestamps are usually exchange-local strings without timezone.
        # Store as UTC-naive converted to UTC for consistency.
        # Later, if you add exchange calendars, localize by index market timezone first.
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)

    def _weight_to_percent(self, value: Any) -> float | None:
        weight = self._float_or_none(value)

        if weight is None:
            return None

        # Some providers return 0.063 for 6.3%, others return 6.3.
        if 0 <= weight <= 1:
            return weight * 100

        return weight

    def _float_or_none(self, value: Any) -> float | None:
        if value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None