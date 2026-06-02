import json
from dashboard.ingestion.websocket.live_price_models import LivePriceTick


class LivePriceRepository:
    def __init__(self, conn):
        self.conn = conn

    def insert_tick(self, tick: LivePriceTick) -> None:
        self.conn.execute(
            """
            INSERT INTO live_price_tick (
                asset_id, symbol, provider, market_session,
                price, volume, bid, ask, trade_ts_utc, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                tick.asset_id,
                tick.symbol,
                tick.provider,
                tick.market_session,
                tick.price,
                tick.volume,
                tick.bid,
                tick.ask,
                tick.trade_ts_utc,
                json.dumps(tick.raw_json or {}),
            ],
        )

    def upsert_current_price(self, tick: LivePriceTick) -> None:
        self.conn.execute(
            """
            DELETE FROM current_asset_price
            WHERE asset_id = ?
            """,
            [tick.asset_id],
        )

        self.conn.execute(
            """
            INSERT INTO current_asset_price (
                asset_id, symbol, price, volume, bid, ask,
                provider, market_session, trade_ts_utc, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                tick.asset_id,
                tick.symbol,
                tick.price,
                tick.volume,
                tick.bid,
                tick.ask,
                tick.provider,
                tick.market_session,
                tick.trade_ts_utc,
                json.dumps(tick.raw_json or {}),
            ],
        )

    def save_tick(self, tick: LivePriceTick) -> None:
        self.insert_tick(tick)
        if tick.asset_id is not None:
            self.upsert_current_price(tick)

    def mark_provider_healthy(self, provider: str) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO live_price_provider_health (
                provider, status, last_success_at, updated_at
            )
            VALUES (?, 'healthy', now(), now())
            """,
            [provider],
        )

    def mark_provider_error(self, provider: str, error_message: str) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO live_price_provider_health (
                provider, status, last_error_at, last_error_message, updated_at
            )
            VALUES (?, 'degraded', now(), ?, now())
            """,
            [provider, error_message],
        )