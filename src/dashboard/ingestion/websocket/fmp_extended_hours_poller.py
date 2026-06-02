import os
from datetime import datetime, timezone
from typing import Iterable

import requests

from dashboard.ingestion.rate_limits import (
    InMemoryRateLimiter,
    RateLimitExceeded,
    RateLimitPolicy,
    default_rate_limiter,
    enforce_symbol_cap,
    env_int,
    fmp_rate_limit_policy,
    normalize_symbols,
)
from dashboard.ingestion.websocket.live_price_models import LivePriceTick


class FmpExtendedHoursClient:
    def __init__(
        self,
        api_key: str,
        rate_limiter: InMemoryRateLimiter | None = None,
        rate_limit_policy: RateLimitPolicy | None = None,
        max_symbols_per_request: int | None = None,
    ):
        self.api_key = api_key
        self.base_url = os.getenv("FMP_STABLE_BASE_URL", "https://financialmodelingprep.com/stable")
        self.rate_limiter = rate_limiter or default_rate_limiter()
        self.rate_limit_policy = rate_limit_policy or fmp_rate_limit_policy()
        self.max_symbols_per_request = (
            max_symbols_per_request
            if max_symbols_per_request is not None
            else env_int("FMP_EXTENDED_HOURS_MAX_SYMBOLS", 50)
        )

    def fetch_batch_aftermarket_quotes(
        self,
        symbols: Iterable[str],
        market_session: str,
    ) -> list[LivePriceTick]:
        symbol_names = normalize_symbols(symbols)
        if not symbol_names:
            return []

        enforce_symbol_cap("FMP extended-hours batch", symbol_names, self.max_symbols_per_request)
        symbol_list = ",".join(symbol_names)
        self.rate_limiter.acquire(self.rate_limit_policy)

        response = requests.get(
            f"{self.base_url}/batch-aftermarket-quote",
            params={"symbols": symbol_list, "apikey": self.api_key},
            timeout=15,
        )
        if getattr(response, "status_code", None) == 429:
            raise RateLimitExceeded("FMP extended-hours rate limit exceeded")
        response.raise_for_status()

        ticks: list[LivePriceTick] = []

        for item in response.json():
            symbol = item.get("symbol")
            price = item.get("price") or item.get("ask") or item.get("bid")

            if not symbol or price is None:
                continue

            ticks.append(
                LivePriceTick(
                    symbol=symbol,
                    price=float(price),
                    bid=float(item["bid"]) if item.get("bid") is not None else None,
                    ask=float(item["ask"]) if item.get("ask") is not None else None,
                    volume=float(item["volume"]) if item.get("volume") is not None else None,
                    provider="fmp",
                    market_session=market_session,
                    trade_ts_utc=datetime.now(timezone.utc).replace(tzinfo=None),
                    raw_json=item,
                )
            )

        return ticks
