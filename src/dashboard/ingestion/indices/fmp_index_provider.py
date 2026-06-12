from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

from dashboard.ingestion.rate_limits import (
    InMemoryRateLimiter,
    RateLimitExceeded,
    RateLimitPolicy,
    default_rate_limiter,
    fmp_rate_limit_policy,
)
from dashboard.ingestion.indices.index_models import (
    IndexConstituent,
    IndexDailyBar,
    IndexIntradayBar,
)


class FMPIndexProvider:
    """
    Financial Modeling Prep provider.

    Use:
    - fallback daily/intraday price source
    - primary supported index constituent source
    - primary ETF proxy holdings source
    """

    provider_name = "fmp"

    def __init__(
        self,
        api_key: str | None = None,
        v3_base_url: str = "https://financialmodelingprep.com/api/v3",
        stable_base_url: str = "https://financialmodelingprep.com/stable",
        timeout_seconds: int = 20,
        rate_limiter: InMemoryRateLimiter | None = None,
        rate_limit_policy: RateLimitPolicy | None = None,
    ):
        load_dotenv()

        self.api_key = api_key or os.getenv("FMP_API_KEY")
        self.v3_base_url = v3_base_url.rstrip("/")
        self.stable_base_url = stable_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.rate_limiter = rate_limiter or default_rate_limiter()
        self.rate_limit_policy = rate_limit_policy or fmp_rate_limit_policy()

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
        payload = self._get_v3(
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
            raw_date = row.get("date")

            if close is None or raw_date is None:
                continue

            bars.append(
                IndexDailyBar(
                    index_id=index_id,
                    price_date=datetime.strptime(raw_date, "%Y-%m-%d").date(),
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

        payload = self._get_v3(
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
            raw_date = row.get("date")

            if close is None or open_ is None or high is None or low is None or raw_date is None:
                continue

            bars.append(
                IndexIntradayBar(
                    index_id=index_id,
                    interval=interval,
                    bar_start_utc=self._parse_fmp_datetime(raw_date),
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
        constituent_endpoint = self._constituent_endpoint(provider_symbol)

        if constituent_endpoint is not None:
            payload = self._get_v3(constituent_endpoint, {})
            return self._parse_index_constituents(index_id, payload, is_proxy)

        return self._get_etf_holdings(
            index_id=index_id,
            etf_symbol=provider_symbol,
            is_proxy=True,
        )

    def _get_etf_holdings(
        self,
        index_id: str,
        etf_symbol: str,
        is_proxy: bool,
    ) -> list[IndexConstituent]:
        payload = self._get_stable(
            "/etf/holdings",
            {"symbol": etf_symbol},
        )

        if not isinstance(payload, list):
            return []

        constituents: list[IndexConstituent] = []

        for row in payload:
            symbol = (
                row.get("asset")
                or row.get("symbol")
                or row.get("holdingSymbol")
                or row.get("ticker")
            )

            if not symbol:
                continue

            constituents.append(
                IndexConstituent(
                    index_id=index_id,
                    constituent_symbol=str(symbol),
                    constituent_name=(
                        row.get("name")
                        or row.get("holdingName")
                        or row.get("companyName")
                        or row.get("assetName")
                    ),
                    exchange_code=row.get("exchange") or row.get("exchangeShortName"),
                    country_code=row.get("country") or row.get("countryCode"),
                    currency=row.get("currency"),
                    sector=row.get("sector"),
                    industry=row.get("industry") or row.get("subSector"),
                    weight_pct=self._weight_to_percent(
                        row.get("weightPercentage")
                        or row.get("weight")
                        or row.get("percentage")
                        or row.get("marketValuePercentage")
                    ),
                    market_cap=self._float_or_none(row.get("marketCap")),
                    source=self.provider_name,
                    is_proxy=is_proxy,
                )
            )

        return constituents

    def _parse_index_constituents(
        self,
        index_id: str,
        payload: Any,
        is_proxy: bool,
    ) -> list[IndexConstituent]:
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

    def _get_v3(self, path: str, params: dict[str, Any]) -> Any:
        return self._get(self.v3_base_url, path, params)

    def _get_stable(self, path: str, params: dict[str, Any]) -> Any:
        return self._get(self.stable_base_url, path, params)

    def _get(self, base_url: str, path: str, params: dict[str, Any]) -> Any:
        params = dict(params)
        params["apikey"] = self.api_key

        self.rate_limiter.acquire(self.rate_limit_policy)
        response = requests.get(
            f"{base_url}{path}",
            params=params,
            timeout=self.timeout_seconds,
        )
        if response.status_code == 429:
            raise RateLimitExceeded("FMP index rate limit exceeded")
        if response.status_code in {402, 403}:
            raise RuntimeError(
                f"FMP index endpoint access denied ({response.status_code}); "
                "the current plan does not include this benchmark data endpoint"
            )
        if response.status_code >= 400:
            raise RuntimeError(f"FMP index HTTP error {response.status_code}")
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and "Error Message" in data:
            message = str(data["Error Message"])
            if "limit" in message.lower() or "rate" in message.lower():
                raise RateLimitExceeded(message)
            raise RuntimeError(message)
        return data

    def _constituent_endpoint(self, provider_symbol: str) -> str | None:
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
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)

    def _weight_to_percent(self, value: Any) -> float | None:
        weight = self._float_or_none(value)

        if weight is None:
            return None

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
