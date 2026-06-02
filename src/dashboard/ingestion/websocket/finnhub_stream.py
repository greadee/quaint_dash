from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Callable

from dashboard.ingestion.rate_limits import enforce_symbol_cap, env_int, normalize_symbols
from dashboard.ingestion.websocket.live_price_models import LivePriceTick


def parse_finnhub_trade_payload(message: str | dict) -> list[LivePriceTick]:
    """
    Parse a Finnhub websocket trade payload into LivePriceTick objects.

    This stays dependency-free so parser tests do not require websocket-client.
    """
    payload = json.loads(message) if isinstance(message, str) else message

    if payload.get("type") != "trade":
        return []

    ticks: list[LivePriceTick] = []

    for item in payload.get("data", []):
        timestamp_ms = item.get("t")
        trade_ts_utc = None

        if timestamp_ms is not None:
            trade_ts_utc = datetime.fromtimestamp(
                timestamp_ms / 1000,
                tz=timezone.utc,
            ).replace(tzinfo=None)

        ticks.append(
            LivePriceTick(
                symbol=item["s"],
                price=float(item["p"]),
                volume=float(item["v"]) if item.get("v") is not None else None,
                provider="finnhub",
                market_session="regular",
                trade_ts_utc=trade_ts_utc,
                raw_json=item,
            )
        )

    return ticks


class FinnhubWebSocketClient:
    def __init__(self, api_key: str, max_symbols: int | None = None):
        self.api_key = api_key
        self.url = os.getenv("FINNHUB_WEBSOCKET_URL", f"wss://ws.finnhub.io?token={api_key}")
        self.max_symbols = (
            max_symbols
            if max_symbols is not None
            else env_int("FINNHUB_WEBSOCKET_MAX_SYMBOLS", 50)
        )

    def stream(
        self,
        symbols: list[str],
        on_tick: Callable[[LivePriceTick], None],
        stop_after_one_message: bool = False,
    ) -> None:
        """
        Start Finnhub websocket streaming.

        websocket-client is imported lazily so unit tests that only test the
        parser do not need to import the websocket package during collection.
        """
        symbols = normalize_symbols(symbols)
        if not symbols:
            return
        enforce_symbol_cap("Finnhub websocket", symbols, self.max_symbols)

        try:
            import websocket
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency: websocket-client. "
                "Install it with `pip install websocket-client`."
            ) from exc

        def on_open(ws):
            for symbol in symbols:
                ws.send(json.dumps({"type": "subscribe", "symbol": symbol}))

        def on_message(ws, message: str):
            for tick in parse_finnhub_trade_payload(message):
                on_tick(tick)

            if stop_after_one_message:
                ws.close()

        ws = websocket.WebSocketApp(
            self.url,
            on_open=on_open,
            on_message=on_message,
        )

        while True:
            ws.run_forever(ping_interval=30, ping_timeout=10)
            time.sleep(5)
