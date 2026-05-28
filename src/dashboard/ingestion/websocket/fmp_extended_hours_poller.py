from datetime import datetime, timezone
from typing import Iterable

import requests

from dashboard.ingestion.websocket.live_price_models import LivePriceTick


class FmpExtendedHoursClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://financialmodelingprep.com/stable"

    def fetch_batch_aftermarket_quotes(
        self,
        symbols: Iterable[str],
        market_session: str,
    ) -> list[LivePriceTick]:
        symbol_list = ",".join(symbols)
        response = requests.get(
            f"{self.base_url}/batch-aftermarket-quote",
            params={"symbols": symbol_list, "apikey": self.api_key},
            timeout=15,
        )
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