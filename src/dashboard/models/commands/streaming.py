"""Live-price query and streaming commands."""


class StreamingCommands:
    def get_current_live_prices(self):
        return self.conn.execute(
            """
            SELECT
                asset_id, symbol, price, volume, bid, ask, provider,
                market_session, trade_ts_utc, updated_at
            FROM current_asset_price
            ORDER BY symbol
            """
        ).fetchall()

    def get_live_price_for_asset(self, asset_id: str):
        return self.conn.execute(
            """
            SELECT
                asset_id, symbol, price, volume, bid, ask, provider,
                market_session, trade_ts_utc, updated_at
            FROM current_asset_price
            WHERE asset_id = ?
            """,
            [asset_id],
        ).fetchone()

    def run_live_price_stream(
        self,
        include_watchlist: bool = False,
        enable_extended_hours: bool = True,
    ) -> None:
        from dashboard.ingestion.websocket.live_price_worker import LivePriceWorker

        LivePriceWorker(self.conn).run(
            include_watchlist=include_watchlist,
            enable_extended_hours=enable_extended_hours,
        )
