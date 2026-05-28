import json
from datetime import datetime, timezone

from dashboard.ingestion.websocket.finnhub_stream import parse_finnhub_trade_payload


def test_finnhub_trade_payload_becomes_live_price_tick():
    payload = {
        "type": "trade",
        "data": [
            {
                "s": "AAPL",
                "p": 191.25,
                "v": 100,
                "t": 1710000000000,
                "c": ["@"],
            }
        ],
    }

    ticks = parse_finnhub_trade_payload(json.dumps(payload))

    assert len(ticks) == 1

    tick = ticks[0]

    assert tick.symbol == "AAPL"
    assert tick.price == 191.25
    assert tick.volume == 100
    assert tick.provider == "finnhub"
    assert tick.market_session == "regular"
    assert tick.raw_json["s"] == "AAPL"

    expected_ts = datetime.fromtimestamp(
        1710000000000 / 1000,
        tz=timezone.utc,
    ).replace(tzinfo=None)

    assert tick.trade_ts_utc == expected_ts


def test_finnhub_non_trade_payload_returns_empty_list():
    payload = {
        "type": "ping",
    }

    ticks = parse_finnhub_trade_payload(payload)

    assert ticks == []


def test_finnhub_trade_payload_with_multiple_trades_returns_multiple_ticks():
    payload = {
        "type": "trade",
        "data": [
            {
                "s": "AAPL",
                "p": 191.25,
                "v": 100,
                "t": 1710000000000,
            },
            {
                "s": "MSFT",
                "p": 430.50,
                "v": 20,
                "t": 1710000001000,
            },
        ],
    }

    ticks = parse_finnhub_trade_payload(payload)

    assert len(ticks) == 2
    assert [tick.symbol for tick in ticks] == ["AAPL", "MSFT"]
    assert [tick.price for tick in ticks] == [191.25, 430.50]