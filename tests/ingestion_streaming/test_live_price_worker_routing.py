from dashboard.ingestion.websocket.live_price_worker import LivePriceWorker


def test_regular_session_routes_to_finnhub(seeded_assets, monkeypatch):
    worker = LivePriceWorker(seeded_assets)

    calls = []

    monkeypatch.setattr(
        worker.session_classifier,
        "classify_us_session",
        lambda now_utc: "regular",
    )

    def fake_finnhub(symbols, symbol_to_asset_id):
        calls.append(("finnhub", symbols, symbol_to_asset_id))

    def fake_fmp(symbols, symbol_to_asset_id, session):
        calls.append(("fmp", symbols, symbol_to_asset_id, session))

    monkeypatch.setattr(worker, "_run_finnhub", fake_finnhub)
    monkeypatch.setattr(worker, "_run_fmp_extended", fake_fmp)

    result = worker.run_once(
        include_watchlist=False,
        enable_extended_hours=True,
    )

    assert result == 1
    assert len(calls) == 1
    assert calls[0][0] == "finnhub"
    assert calls[0][1] == ["AAPL", "MSFT"]
    assert calls[0][2] == {
        "AAPL": "AAPL",
        "MSFT": "MSFT",
    }


def test_pre_market_routes_to_fmp_when_extended_hours_enabled(seeded_assets, monkeypatch):
    worker = LivePriceWorker(seeded_assets)

    calls = []

    monkeypatch.setattr(
        worker.session_classifier,
        "classify_us_session",
        lambda now_utc: "pre",
    )

    monkeypatch.setattr(
        worker,
        "_run_finnhub",
        lambda symbols, symbol_to_asset_id: calls.append(("finnhub", symbols)),
    )

    monkeypatch.setattr(
        worker,
        "_run_fmp_extended",
        lambda symbols, symbol_to_asset_id, session: calls.append(
            ("fmp", symbols, session)
        ),
    )

    result = worker.run_once(
        include_watchlist=False,
        enable_extended_hours=True,
    )

    assert result == 1
    assert calls == [
        ("fmp", ["AAPL", "MSFT"], "pre"),
    ]


def test_after_hours_routes_to_fmp_when_extended_hours_enabled(seeded_assets, monkeypatch):
    worker = LivePriceWorker(seeded_assets)

    calls = []

    monkeypatch.setattr(
        worker.session_classifier,
        "classify_us_session",
        lambda now_utc: "after",
    )

    monkeypatch.setattr(
        worker,
        "_run_finnhub",
        lambda symbols, symbol_to_asset_id: calls.append(("finnhub", symbols)),
    )

    monkeypatch.setattr(
        worker,
        "_run_fmp_extended",
        lambda symbols, symbol_to_asset_id, session: calls.append(
            ("fmp", symbols, session)
        ),
    )

    result = worker.run_once(
        include_watchlist=False,
        enable_extended_hours=True,
    )

    assert result == 1
    assert calls == [
        ("fmp", ["AAPL", "MSFT"], "after"),
    ]


def test_closed_session_does_not_call_providers(seeded_assets, monkeypatch):
    worker = LivePriceWorker(seeded_assets)

    calls = []

    monkeypatch.setattr(
        worker.session_classifier,
        "classify_us_session",
        lambda now_utc: "closed",
    )

    monkeypatch.setattr(
        worker,
        "_run_finnhub",
        lambda symbols, symbol_to_asset_id: calls.append(("finnhub", symbols)),
    )

    monkeypatch.setattr(
        worker,
        "_run_fmp_extended",
        lambda symbols, symbol_to_asset_id, session: calls.append(
            ("fmp", symbols, session)
        ),
    )

    result = worker.run_once(
        include_watchlist=False,
        enable_extended_hours=True,
    )

    assert result == 0
    assert calls == []


def test_pre_market_does_not_call_fmp_when_extended_hours_disabled(seeded_assets, monkeypatch):
    worker = LivePriceWorker(seeded_assets)

    calls = []

    monkeypatch.setattr(
        worker.session_classifier,
        "classify_us_session",
        lambda now_utc: "pre",
    )

    monkeypatch.setattr(
        worker,
        "_run_finnhub",
        lambda symbols, symbol_to_asset_id: calls.append(("finnhub", symbols)),
    )

    monkeypatch.setattr(
        worker,
        "_run_fmp_extended",
        lambda symbols, symbol_to_asset_id, session: calls.append(
            ("fmp", symbols, session)
        ),
    )

    result = worker.run_once(
        include_watchlist=False,
        enable_extended_hours=False,
    )

    assert result == 0
    assert calls == []


def test_worker_can_include_watchlist_symbols_when_enabled(seeded_assets, monkeypatch):
    worker = LivePriceWorker(seeded_assets)

    calls = []

    monkeypatch.setattr(
        worker.session_classifier,
        "classify_us_session",
        lambda now_utc: "regular",
    )

    monkeypatch.setattr(
        worker,
        "_run_finnhub",
        lambda symbols, symbol_to_asset_id: calls.append(
            ("finnhub", symbols, symbol_to_asset_id)
        ),
    )

    monkeypatch.setattr(
        worker,
        "_run_fmp_extended",
        lambda symbols, symbol_to_asset_id, session: calls.append(
            ("fmp", symbols, session)
        ),
    )

    result = worker.run_once(
        include_watchlist=True,
        enable_extended_hours=True,
    )

    assert result == 1
    assert calls[0][0] == "finnhub"
    assert calls[0][1] == ["AAPL", "MSFT", "NVDA"]
    assert calls[0][2] == {
        "AAPL": "AAPL",
        "MSFT": "MSFT",
        "NVDA": "NVDA",
    }