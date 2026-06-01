from dashboard.ingestion.ticker_universe import (
    TickerSubscription as StreamSubscription,
    TickerUniverseRepository,
)


class LivePriceSubscriptionResolver:
    def __init__(self, conn):
        self.ticker_universe = TickerUniverseRepository(conn)

    def resolve(
        self,
        include_portfolios: bool = True,
        include_watchlist: bool = False,
    ) -> list[StreamSubscription]:
        return self.ticker_universe.stream_subscriptions(
            include_portfolios=include_portfolios,
            include_watchlist=include_watchlist,
        )
