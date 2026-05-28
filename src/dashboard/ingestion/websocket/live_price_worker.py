
import os
import time
from datetime import datetime, timezone

from dashboard.ingestion.websocket.live_price_repo import LivePriceRepository
from dashboard.ingestion.websocket.live_price_subscriptions import LivePriceSubscriptionResolver
from dashboard.ingestion.websocket.finnhub_stream import FinnhubWebSocketClient
from dashboard.ingestion.websocket.fmp_extended_hours_poller import FmpExtendedHoursClient
from dashboard.ingestion.websocket.session_classifier import MarketSessionClassifier


class LivePriceWorker:
    def __init__(self, conn):
        self.conn = conn
        self.repo = LivePriceRepository(conn)
        self.resolver = LivePriceSubscriptionResolver(conn)
        self.session_classifier = MarketSessionClassifier(conn)

    def run(self) -> None:
        include_watchlist = os.getenv("LIVE_STREAM_WATCHLIST_ASSETS", "false").lower() == "true"
        enable_extended = os.getenv("LIVE_STREAM_EXTENDED_HOURS", "true").lower() == "true"

        subscriptions = self.resolver.resolve(
            include_portfolios=True,
            include_watchlist=include_watchlist,
        )

        if not subscriptions:
            return

        symbol_to_asset_id = {
            item.symbol: item.asset_id
            for item in subscriptions
        }

        symbols = list(symbol_to_asset_id.keys())

        while True:
            now_utc = datetime.now(timezone.utc)
            session = self.session_classifier.classify_us_session(now_utc)

            if session == "regular":
                self._run_finnhub(symbols, symbol_to_asset_id)
            elif session in {"pre", "after"} and enable_extended:
                self._run_fmp_extended(symbols, symbol_to_asset_id, session)
            else:
                time.sleep(60)

    def _run_finnhub(self, symbols: list[str], symbol_to_asset_id: dict[str, str]) -> None:
        client = FinnhubWebSocketClient(api_key=os.environ["FINNHUB_API_KEY"])

        def handle_tick(tick):
            tick = tick.__class__(
                **{
                    **tick.__dict__,
                    "asset_id": symbol_to_asset_id.get(tick.symbol),
                    "market_session": "regular",
                }
            )
            self.repo.save_tick(tick)
            self.repo.mark_provider_healthy("finnhub")

        try:
            client.stream(symbols=symbols, on_tick=handle_tick)
        except Exception as exc:
            self.repo.mark_provider_error("finnhub", str(exc))
            time.sleep(10)

    def _run_fmp_extended(
        self,
        symbols: list[str],
        symbol_to_asset_id: dict[str, str],
        session: str,
    ) -> None:
        client = FmpExtendedHoursClient(api_key=os.environ["FMP_API_KEY"])
        poll_seconds = int(os.getenv("LIVE_STREAM_FMP_EXTENDED_POLL_SECONDS", "60"))

        try:
            ticks = client.fetch_batch_aftermarket_quotes(
                symbols=symbols,
                market_session=session,
            )

            for tick in ticks:
                tick = tick.__class__(
                    **{
                        **tick.__dict__,
                        "asset_id": symbol_to_asset_id.get(tick.symbol),
                    }
                )
                self.repo.save_tick(tick)

            self.repo.mark_provider_healthy("fmp")
        except Exception as exc:
            self.repo.mark_provider_error("fmp", str(exc))

        time.sleep(poll_seconds)