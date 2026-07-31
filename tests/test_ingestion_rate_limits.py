from __future__ import annotations

import json
import urllib.error
from datetime import date

import pandas as pd
import pytest

from dashboard.ingestion.corporate_calendar.provider_fmp import FmpCorporateCalendarProvider
from dashboard.ingestion.corporate_calendar.provider_fmp import FmpEntitlementError
from dashboard.ingestion.indices.fmp_index_provider import FMPIndexProvider
from dashboard.ingestion.indices.yfinance_index_provider import YFinanceIndexProvider
from dashboard.ingestion.price_history.provider_yahoo import YahooPriceProvider
from dashboard.ingestion.rate_limits import (
    InMemoryRateLimiter,
    RateLimitExceeded,
    RateLimitPolicy,
)
from dashboard.ingestion.websocket.finnhub_stream import FinnhubWebSocketClient
from dashboard.ingestion.websocket.fmp_extended_hours_poller import FmpExtendedHoursClient


class FakeLimiter:
    def __init__(self) -> None:
        self.calls = []

    def acquire(self, policy) -> None:
        self.calls.append(policy)


class FakeUrlResponse:
    def __init__(self, payload, status: int = 200) -> None:
        self.status = status
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_rate_limiter_waits_for_window_without_counting_pending_attempts():
    now = 0.0
    sleeps = []

    def clock():
        return now

    def sleeper(seconds: float):
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    limiter = InMemoryRateLimiter(clock=clock, sleeper=sleeper)
    policy = RateLimitPolicy(provider="test", calls=1, period_seconds=10)

    limiter.acquire(policy)
    limiter.acquire(policy)

    assert sleeps == [10.0]


def test_rate_limiter_raises_when_run_budget_is_exhausted():
    limiter = InMemoryRateLimiter(clock=lambda: 1.0, sleeper=lambda _: None)
    policy = RateLimitPolicy(provider="test", calls=10, max_calls_per_run=1)

    limiter.acquire(policy)

    with pytest.raises(RateLimitExceeded, match="budget exhausted"):
        limiter.acquire(policy)


def test_rate_limiter_reset_starts_a_new_run_without_clearing_window():
    now = 0.0
    sleeps = []

    def clock():
        return now

    def sleeper(seconds: float):
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    limiter = InMemoryRateLimiter(clock=clock, sleeper=sleeper)
    policy = RateLimitPolicy(
        provider="test",
        calls=1,
        period_seconds=10,
        max_calls_per_run=1,
    )

    limiter.acquire(policy)
    limiter.reset_run_counts()
    limiter.acquire(policy)

    assert sleeps == [10.0]


def test_fmp_corporate_provider_uses_limiter_and_detects_429(monkeypatch):
    limiter = FakeLimiter()
    provider = FmpCorporateCalendarProvider(
        api_key="key",
        base_url="https://example.test",
        rate_limiter=limiter,
        rate_limit_policy=RateLimitPolicy(provider="fmp-test"),
    )

    def fail_429(*args, **kwargs):
        raise urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", fail_429)

    with pytest.raises(RateLimitExceeded):
        provider._get_json("earnings", {"symbol": "AAPL"})

    assert len(limiter.calls) == 1


def test_fmp_corporate_provider_detects_entitlement_402(monkeypatch):
    provider = FmpCorporateCalendarProvider(
        api_key="key",
        base_url="https://example.test",
        rate_limiter=FakeLimiter(),
        rate_limit_policy=RateLimitPolicy(provider="fmp-test"),
    )

    def fail_402(*args, **kwargs):
        raise urllib.error.HTTPError("url", 402, "Payment Required", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", fail_402)

    with pytest.raises(FmpEntitlementError):
        provider._get_json("income-statement", {"symbol": "AAPL"})


def test_fmp_corporate_provider_treats_limit_payload_as_budget_failure(monkeypatch):
    provider = FmpCorporateCalendarProvider(
        api_key="key",
        base_url="https://example.test",
        rate_limiter=FakeLimiter(),
        rate_limit_policy=RateLimitPolicy(provider="fmp-test"),
    )

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: FakeUrlResponse({"Error Message": "rate limit exceeded"}),
    )

    with pytest.raises(RateLimitExceeded):
        provider._get_json("earnings", {"symbol": "AAPL"})


def test_yahoo_price_provider_caches_history_downloads(monkeypatch):
    calls = []
    frame = pd.DataFrame(
        {
            "Open": [1.0],
            "High": [2.0],
            "Low": [0.5],
            "Close": [1.5],
            "Adj Close": [1.4],
            "Volume": [100],
            "Dividends": [0.1],
            "Stock Splits": [0.0],
        },
        index=pd.to_datetime(["2024-01-02"]),
    )

    class FakeTicker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def history(self, **kwargs):
            calls.append((self.symbol, kwargs))
            return frame

    monkeypatch.setattr("yfinance.Ticker", FakeTicker)

    provider = YahooPriceProvider(
        rate_limiter=FakeLimiter(),
        rate_limit_policy=RateLimitPolicy(provider="yf-test"),
    )
    provider.fetch_price_daily("AAPL", date(2024, 1, 1), date(2024, 1, 3))
    provider.fetch_dividends("AAPL", date(2024, 1, 1), date(2024, 1, 3))

    assert len(calls) == 1


def test_fmp_extended_hours_rejects_oversized_symbol_batch(monkeypatch):
    def fail_request(*args, **kwargs):
        raise AssertionError("request should not be sent")

    monkeypatch.setattr("requests.get", fail_request)
    client = FmpExtendedHoursClient(
        api_key="key",
        rate_limiter=FakeLimiter(),
        rate_limit_policy=RateLimitPolicy(provider="fmp-test"),
        max_symbols_per_request=2,
    )

    with pytest.raises(RateLimitExceeded, match="symbol budget exceeded"):
        client.fetch_batch_aftermarket_quotes(["AAPL", "MSFT", "NVDA"], "post")


def test_fmp_extended_hours_dedupes_symbols_before_request(monkeypatch):
    requests_seen = []

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return []

    def fake_get(url, params, timeout):
        requests_seen.append(params["symbols"])
        return Response()

    monkeypatch.setattr("requests.get", fake_get)
    client = FmpExtendedHoursClient(
        api_key="key",
        rate_limiter=FakeLimiter(),
        rate_limit_policy=RateLimitPolicy(provider="fmp-test"),
        max_symbols_per_request=3,
    )

    client.fetch_batch_aftermarket_quotes(["aapl", "AAPL", "msft"], "post")

    assert requests_seen == ["AAPL,MSFT"]


def test_finnhub_rejects_oversized_subscription_before_connect(monkeypatch):
    def fail_import(name):
        if name == "websocket":
            raise AssertionError("websocket should not be imported")
        return __import__(name)

    monkeypatch.setattr("builtins.__import__", fail_import)
    client = FinnhubWebSocketClient(api_key="key", max_symbols=1)

    with pytest.raises(RateLimitExceeded, match="symbol budget exceeded"):
        client.stream(["AAPL", "MSFT"], on_tick=lambda tick: None)


def test_fmp_index_provider_uses_limiter_and_detects_429(monkeypatch):
    limiter = FakeLimiter()
    provider = FMPIndexProvider(
        api_key="key",
        rate_limiter=limiter,
        rate_limit_policy=RateLimitPolicy(provider="fmp-index-test"),
    )

    class Response:
        status_code = 429

        def raise_for_status(self):
            raise AssertionError("429 should be handled before raise_for_status")

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: Response())

    with pytest.raises(RateLimitExceeded):
        provider._get("https://example.test", "/path", {})

    assert len(limiter.calls) == 1


def test_fmp_index_provider_reports_entitlement_errors_without_url(monkeypatch):
    provider = FMPIndexProvider(
        api_key="secret",
        rate_limiter=FakeLimiter(),
        rate_limit_policy=RateLimitPolicy(provider="fmp-index-test"),
    )

    class Response:
        status_code = 402

        def raise_for_status(self):
            raise AssertionError("402 should be handled before raise_for_status")

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: Response())

    with pytest.raises(RuntimeError) as exc_info:
        provider._get("https://example.test", "/path", {})

    message = str(exc_info.value)
    assert "access denied" in message
    assert "secret" not in message
    assert "apikey" not in message


def test_yfinance_index_provider_uses_limiter(monkeypatch):
    limiter = FakeLimiter()
    provider = YFinanceIndexProvider(
        rate_limiter=limiter,
        rate_limit_policy=RateLimitPolicy(provider="yf-index-test"),
    )
    frame = pd.DataFrame({"Close": [1.0]}, index=pd.to_datetime(["2024-01-02"]))

    monkeypatch.setattr("yfinance.download", lambda *args, **kwargs: frame)

    provider.get_daily_prices(
        index_id="sp500",
        provider_symbol="^GSPC",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 3),
        is_proxy=False,
    )

    assert len(limiter.calls) == 1


def test_yfinance_index_provider_parses_proxy_top_holdings(monkeypatch):
    limiter = FakeLimiter()
    provider = YFinanceIndexProvider(
        rate_limiter=limiter,
        rate_limit_policy=RateLimitPolicy(provider="yf-index-test"),
    )
    holdings = pd.DataFrame(
        {
            "Name": ["Apple Inc.", "Microsoft Corp."],
            "Holding Percent": [0.06, 4.0],
            "Sector": ["Information Technology", "Information Technology"],
        },
        index=["AAPL", "MSFT"],
    )

    class FakeFundsData:
        top_holdings = holdings

    class FakeTicker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol
            self.funds_data = FakeFundsData()

    monkeypatch.setattr("yfinance.Ticker", FakeTicker)

    constituents = provider.get_constituents(
        index_id="SP500",
        provider_symbol="SPY",
        is_proxy=True,
    )

    assert len(limiter.calls) == 1
    assert [(item.constituent_symbol, item.weight_pct) for item in constituents] == [
        ("AAPL", 6.0),
        ("MSFT", 4.0),
    ]
