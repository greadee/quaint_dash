from dataclasses import dataclass


@dataclass(frozen=True)
class StreamSubscription:
    asset_id: str
    symbol: str
    exchange_code: str | None
    source_scope: str


class LivePriceSubscriptionResolver:
    def __init__(self, conn):
        self.conn = conn

    def resolve(
        self,
        include_portfolios: bool = True,
        include_watchlist: bool = False,
    ) -> list[StreamSubscription]:
        subscriptions: dict[str, StreamSubscription] = {}

        if include_portfolios:
            rows = self.conn.execute(
                """
                SELECT DISTINCT a.asset_id, a.symbol, a.exchange_code
                FROM position p
                JOIN asset a ON a.asset_id = p.asset_id
                WHERE p.quantity <> 0
                """
            ).fetchall()

            for asset_id, symbol, exchange_code in rows:
                subscriptions[symbol] = StreamSubscription(
                    asset_id=asset_id,
                    symbol=symbol,
                    exchange_code=exchange_code,
                    source_scope="portfolio",
                )

        if include_watchlist:
            rows = self.conn.execute(
                """
                SELECT DISTINCT a.asset_id, a.symbol, a.exchange_code
                FROM watchlist_asset wa
                JOIN asset a ON a.asset_id = wa.asset_id
                WHERE wa.is_active = TRUE
                """
            ).fetchall()

            for asset_id, symbol, exchange_code in rows:
                subscriptions.setdefault(
                    symbol,
                    StreamSubscription(
                        asset_id=asset_id,
                        symbol=symbol,
                        exchange_code=exchange_code,
                        source_scope="watchlist",
                    ),
                )

        return sorted(subscriptions.values(), key=lambda item: item.symbol)