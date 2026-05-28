from datetime import datetime

from dashboard.ingestion.websocket.live_price_models import LivePriceTick
from dashboard.ingestion.websocket.live_price_repo import LivePriceRepository


def test_current_asset_price_is_replaced_with_latest_tick(conn):
    repo = LivePriceRepository(conn)

    first_tick = LivePriceTick(
        asset_id="AAPL",
        symbol="AAPL",
        price=100.00,
        volume=10,
        provider="finnhub",
        market_session="regular",
        trade_ts_utc=datetime(2026, 1, 1, 14, 30, 0),
        raw_json={"source": "first"},
    )

    second_tick = LivePriceTick(
        asset_id="AAPL",
        symbol="AAPL",
        price=101.25,
        volume=20,
        provider="finnhub",
        market_session="regular",
        trade_ts_utc=datetime(2026, 1, 1, 14, 31, 0),
        raw_json={"source": "second"},
    )

    repo.save_tick(first_tick)
    repo.save_tick(second_tick)

    current = conn.execute(
        """
        SELECT symbol, price, volume, provider, market_session, trade_ts_utc
        FROM current_asset_price
        WHERE asset_id = 'AAPL'
        """
    ).fetchone()

    assert current == (
        "AAPL",
        101.25,
        20.0,
        "finnhub",
        "regular",
        datetime(2026, 1, 1, 14, 31, 0),
    )


def test_raw_live_price_ticks_are_inserted_for_audit_debugging(conn):
    repo = LivePriceRepository(conn)

    repo.save_tick(
        LivePriceTick(
            asset_id="AAPL",
            symbol="AAPL",
            price=100.00,
            provider="finnhub",
            market_session="regular",
            raw_json={"n": 1},
        )
    )

    repo.save_tick(
        LivePriceTick(
            asset_id="AAPL",
            symbol="AAPL",
            price=101.00,
            provider="finnhub",
            market_session="regular",
            raw_json={"n": 2},
        )
    )

    raw_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM live_price_tick
        WHERE asset_id = 'AAPL'
        """
    ).fetchone()[0]

    current_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM current_asset_price
        WHERE asset_id = 'AAPL'
        """
    ).fetchone()[0]

    assert raw_count == 2
    assert current_count == 1


def test_provider_health_can_be_marked_healthy(conn):
    repo = LivePriceRepository(conn)

    repo.mark_provider_healthy("finnhub")

    row = conn.execute(
        """
        SELECT provider, status, last_success_at, last_error_at
        FROM live_price_provider_health
        WHERE provider = 'finnhub'
        """
    ).fetchone()

    assert row[0] == "finnhub"
    assert row[1] == "healthy"
    assert row[2] is not None
    assert row[3] is None


def test_provider_health_can_record_error(conn):
    repo = LivePriceRepository(conn)

    repo.mark_provider_error("fmp", "rate limit")

    row = conn.execute(
        """
        SELECT provider, status, last_success_at, last_error_at, last_error_message
        FROM live_price_provider_health
        WHERE provider = 'fmp'
        """
    ).fetchone()

    assert row[0] == "fmp"
    assert row[1] == "degraded"
    assert row[2] is None
    assert row[3] is not None
    assert row[4] == "rate limit"