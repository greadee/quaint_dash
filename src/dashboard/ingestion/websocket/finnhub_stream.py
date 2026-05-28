import json
import time
from datetime import datetime, timezone
from typing import Callable

import websocket

from dashboard.ingestion.websocket.live_price_models import LivePriceTick


class FinnhubWebSocketClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.url = f"wss://ws.finnhub.io?token={api_key}"

    def stream(
        self,
        symbols: list[str],
        on_tick: Callable[[LivePriceTick], None],
        stop_after_one_message: bool = False,
    ) -> None:
        def on_open(ws):
            for symbol in symbols:
                ws.send(json.dumps({"type": "subscribe", "symbol": symbol}))

        def on_message(ws, message: str):
            for tick in parse_finnhub_trade_payload(message):
                on_tick(tick)

            if stop_after_one_message:
                ws.close()

            payload = json.loads(message)

            if payload.get("type") != "trade":
                return

            for item in payload.get("data", []):
                tick = LivePriceTick(
                    symbol=item["s"],
                    price=float(item["p"]),
                    volume=float(item["v"]) if item.get("v") is not None else None,
                    provider="finnhub",
                    market_session="regular",
                    trade_ts_utc=datetime.fromtimestamp(
                        item["t"] / 1000,
                        tz=timezone.utc,
                    ).replace(tzinfo=None),
                    raw_json=item,
                )
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


def parse_finnhub_trade_payload(message: str | dict) -> list[LivePriceTick]:
    """
    Parse a Finnhub websocket trade payload into LivePriceTick objects.

    This is kept as a pure helper so it can be unit tested without opening
    a real websocket connection.
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