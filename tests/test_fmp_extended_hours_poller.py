from dashboard.ingestion.websocket.fmp_extended_hours_poller import FmpExtendedHoursClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.raise_for_status_called = False

    def raise_for_status(self):
        self.raise_for_status_called = True

    def json(self):
        return self.payload


def test_fmp_aftermarket_payload_becomes_live_price_tick(monkeypatch):
    captured = {}

    payload = [
        {
            "symbol": "AAPL",
            "price": 190.12,
            "bid": 190.10,
            "ask": 190.15,
            "volume": 1500,
        }
    ]

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return FakeResponse(payload)

    monkeypatch.setattr(
        "dashboard.ingestion.websocket.fmp_extended_hours_poller.requests.get",
        fake_get,
    )

    client = FmpExtendedHoursClient(api_key="fake-key")

    ticks = client.fetch_batch_aftermarket_quotes(
        symbols=["AAPL"],
        market_session="after",
    )

    assert captured["url"].endswith("/batch-aftermarket-quote")
    assert captured["params"]["symbols"] == "AAPL"
    assert captured["params"]["apikey"] == "fake-key"
    assert captured["timeout"] == 15

    assert len(ticks) == 1

    tick = ticks[0]

    assert tick.symbol == "AAPL"
    assert tick.price == 190.12
    assert tick.bid == 190.10
    assert tick.ask == 190.15
    assert tick.volume == 1500
    assert tick.provider == "fmp"
    assert tick.market_session == "after"
    assert tick.raw_json["symbol"] == "AAPL"


def test_fmp_aftermarket_payload_uses_ask_when_price_is_missing(monkeypatch):
    payload = [
        {
            "symbol": "MSFT",
            "bid": 429.90,
            "ask": 430.10,
            "volume": 200,
        }
    ]

    def fake_get(url, params, timeout):
        return FakeResponse(payload)

    monkeypatch.setattr(
        "dashboard.ingestion.websocket.fmp_extended_hours_poller.requests.get",
        fake_get,
    )

    client = FmpExtendedHoursClient(api_key="fake-key")

    ticks = client.fetch_batch_aftermarket_quotes(
        symbols=["MSFT"],
        market_session="pre",
    )

    assert len(ticks) == 1
    assert ticks[0].symbol == "MSFT"
    assert ticks[0].price == 430.10
    assert ticks[0].market_session == "pre"


def test_fmp_aftermarket_payload_skips_rows_without_symbol_or_price(monkeypatch):
    payload = [
        {
            "symbol": None,
            "price": 100.00,
        },
        {
            "symbol": "BAD",
            "price": None,
            "bid": None,
            "ask": None,
        },
        {
            "symbol": "AAPL",
            "price": 190.12,
        },
    ]

    def fake_get(url, params, timeout):
        return FakeResponse(payload)

    monkeypatch.setattr(
        "dashboard.ingestion.websocket.fmp_extended_hours_poller.requests.get",
        fake_get,
    )

    client = FmpExtendedHoursClient(api_key="fake-key")

    ticks = client.fetch_batch_aftermarket_quotes(
        symbols=["AAPL", "BAD"],
        market_session="after",
    )

    assert len(ticks) == 1
    assert ticks[0].symbol == "AAPL"