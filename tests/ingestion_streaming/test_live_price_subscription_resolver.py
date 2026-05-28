from dashboard.ingestion.websocket.live_price_subscriptions import LivePriceSubscriptionResolver


def _symbols(subscriptions):
    return [item.symbol for item in subscriptions]


def test_portfolio_tickers_are_included_by_default(seeded_assets):
    resolver = LivePriceSubscriptionResolver(seeded_assets)

    subscriptions = resolver.resolve()

    assert _symbols(subscriptions) == ["AAPL", "MSFT"]


def test_watchlist_tickers_are_excluded_by_default(seeded_assets):
    resolver = LivePriceSubscriptionResolver(seeded_assets)

    subscriptions = resolver.resolve()

    assert "NVDA" not in _symbols(subscriptions)


def test_watchlist_tickers_are_included_when_enabled(seeded_assets):
    resolver = LivePriceSubscriptionResolver(seeded_assets)

    subscriptions = resolver.resolve(include_watchlist=True)

    assert _symbols(subscriptions) == ["AAPL", "MSFT", "NVDA"]


def test_duplicate_symbols_across_portfolio_and_watchlist_stream_once(seeded_assets):
    resolver = LivePriceSubscriptionResolver(seeded_assets)

    subscriptions = resolver.resolve(include_watchlist=True)
    symbols = _symbols(subscriptions)

    assert symbols.count("AAPL") == 1


def test_zero_quantity_portfolio_positions_are_not_streamed(seeded_assets):
    resolver = LivePriceSubscriptionResolver(seeded_assets)

    subscriptions = resolver.resolve(include_watchlist=True)

    assert "CASH" not in _symbols(subscriptions)