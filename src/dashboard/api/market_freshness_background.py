"""Background live-price freshness worker for held assets."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

from dashboard.db.db_conn import DB
from dashboard.ingestion.price_history.db.ingestion_repo import PriceHistoryIngestionRepository
from dashboard.ingestion.price_history.models import PriceDailyRow
from dashboard.ingestion.price_history.provider_yahoo import YahooPriceProvider
from dashboard.ingestion.ticker_universe import TickerSubscription
from dashboard.ingestion.websocket.live_price_models import LivePriceTick
from dashboard.ingestion.websocket.live_price_repo import LivePriceRepository
from dashboard.ingestion.websocket.live_price_subscriptions import LivePriceSubscriptionResolver

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketFreshnessConfig:
    enabled: bool = True
    poll_interval_seconds: int = 900
    include_watchlist: bool = False
    lookback_days: int = 7
    max_symbols_per_tick: int = 25

    @classmethod
    def from_env(cls) -> "MarketFreshnessConfig":
        return cls(
            enabled=_truthy_env("MARKET_FRESHNESS_ENABLED", default=False),
            poll_interval_seconds=_int_env("MARKET_FRESHNESS_POLL_INTERVAL_SECONDS", 900),
            include_watchlist=_truthy_env("MARKET_FRESHNESS_INCLUDE_WATCHLIST", default=False),
            lookback_days=_int_env("MARKET_FRESHNESS_LOOKBACK_DAYS", 7),
            max_symbols_per_tick=_int_env("MARKET_FRESHNESS_MAX_SYMBOLS_PER_TICK", 25),
        )


class MarketFreshnessWorker:
    def __init__(self, db_path: Path, write_lock: Lock, config: MarketFreshnessConfig) -> None:
        self.db_path = Path(db_path)
        self.write_lock = write_lock
        self.config = config
        self._enabled = config.enabled
        self._running = False
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self.last_poll_at: datetime | None = None
        self.last_refreshed_count: int | None = None
        self.last_subscription_count: int | None = None
        self.last_error: str | None = None

    @property
    def running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def start(self) -> None:
        if not self._enabled:
            return
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop(), name="market-freshness-worker")
        self._running = True

    def enable(self) -> None:
        self._enabled = True

    async def disable(self) -> None:
        self._enabled = False
        await self.stop()

    async def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._running = False

    async def tick(self) -> dict[str, int]:
        refreshed = await self.tick_poll()
        return {
            "refreshed_prices": refreshed,
            "subscriptions": self.last_subscription_count or 0,
        }

    async def tick_poll(self) -> int:
        try:
            count = await asyncio.to_thread(self._poll_once)
        except Exception as exc:
            self.last_error = str(exc)
            LOGGER.warning("Market freshness worker failed: %s", exc)
            return 0
        self.last_poll_at = _now()
        self.last_refreshed_count = count
        self.last_error = None
        LOGGER.info("Market freshness worker refreshed %s current price(s).", count)
        return count

    async def _run_loop(self) -> None:
        try:
            while self._stop_event is not None and not self._stop_event.is_set():
                await self.tick_poll()
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=float(self.config.poll_interval_seconds),
                    )
                except TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error = str(exc)
            LOGGER.exception("Market freshness worker stopped unexpectedly")
        finally:
            self._running = False

    def _poll_once(self) -> int:
        subscriptions = self._resolve_subscriptions()
        self.last_subscription_count = len(subscriptions)
        if not subscriptions:
            return 0
        stale_subscriptions = self._filter_stale_subscriptions(subscriptions)
        if not stale_subscriptions:
            return 0

        provider = YahooPriceProvider()
        today = date.today()
        start = today - timedelta(days=max(self.config.lookback_days, 1))
        refreshed: list[LivePriceTick] = []
        daily_rows: list[PriceDailyRow] = []
        stored_fallbacks = self._stored_price_fallbacks(stale_subscriptions)
        for item in stale_subscriptions[: self.config.max_symbols_per_tick]:
            try:
                rows = provider.fetch_price_daily(item.symbol, start, today)
            except Exception as exc:
                LOGGER.warning(
                    "Market price refresh failed for %s: %s",
                    item.symbol,
                    exc,
                )
                rows = []
            daily_rows.extend(
                PriceDailyRow(
                    asset_id=item.asset_id,
                    price_date=row.price_date,
                    open_price=row.open_price,
                    high_price=row.high_price,
                    low_price=row.low_price,
                    close_price=row.close_price,
                    adj_close_price=row.adj_close_price,
                    volume=row.volume,
                    source=row.source,
                )
                for row in rows
            )
            latest = next((row for row in reversed(rows) if row.close_price is not None or row.adj_close_price is not None), None)
            if latest is None:
                fallback = stored_fallbacks.get(item.asset_id)
                if fallback is not None:
                    fallback_date, fallback_price, fallback_volume = fallback
                    refreshed.append(
                        LivePriceTick(
                            asset_id=item.asset_id,
                            symbol=item.symbol,
                            price=fallback_price,
                            volume=fallback_volume,
                            provider="stored_close_fallback",
                            market_session="previous_close",
                            trade_ts_utc=datetime.combine(
                                fallback_date,
                                datetime.min.time(),
                            ),
                            raw_json={
                                "source": "market_freshness_worker",
                                "fallback_reason": "live provider returned no rows",
                            },
                        )
                    )
                continue
            price = latest.close_price if latest.close_price is not None else latest.adj_close_price
            if price is None:
                continue
            refreshed.append(
                LivePriceTick(
                    asset_id=item.asset_id,
                    symbol=item.symbol,
                    price=float(price),
                    volume=float(latest.volume) if latest.volume is not None else None,
                    provider="yfinance",
                    market_session="regular",
                    trade_ts_utc=datetime.combine(
                        latest.price_date,
                        datetime.min.time(),
                    ),
                    raw_json={"source": "market_freshness_worker"},
                )
            )

        if not refreshed:
            return 0

        with self.write_lock:
            db = DB(self.db_path)
            try:
                if daily_rows:
                    PriceHistoryIngestionRepository(db.conn).upsert_price_rows(daily_rows)
                repo = LivePriceRepository(db.conn)
                for tick in refreshed:
                    repo.save_tick(tick)
                repo.mark_provider_healthy("yfinance")
            finally:
                db.conn.close()
        return len(refreshed)

    def _stored_price_fallbacks(
        self,
        subscriptions: list[TickerSubscription],
    ) -> dict[str, tuple[date, float, float | None]]:
        asset_ids = [item.asset_id for item in subscriptions if item.asset_id]
        if not asset_ids:
            return {}
        placeholders = ", ".join("?" for _ in asset_ids)
        with self.write_lock:
            db = DB(self.db_path)
            try:
                rows = db.conn.execute(
                    f"""
                    SELECT asset_id, date, price, volume
                    FROM (
                        SELECT
                            asset_id,
                            date,
                            COALESCE(adj_close, close) AS price,
                            volume,
                            ROW_NUMBER() OVER (
                                PARTITION BY asset_id
                                ORDER BY date DESC
                            ) AS price_rank
                        FROM asset_quote_daily
                        WHERE asset_id IN ({placeholders})
                          AND COALESCE(adj_close, close) IS NOT NULL
                    ) ranked
                    WHERE price_rank = 1
                    """,
                    asset_ids,
                ).fetchall()
            finally:
                db.conn.close()
        return {
            str(asset_id): (
                price_date,
                float(price),
                float(volume) if volume is not None else None,
            )
            for asset_id, price_date, price, volume in rows
        }

    def _filter_stale_subscriptions(self, subscriptions: list[TickerSubscription]) -> list[TickerSubscription]:
        asset_ids = [item.asset_id for item in subscriptions if item.asset_id]
        if not asset_ids:
            return subscriptions
        placeholders = ", ".join("?" for _ in asset_ids)
        with self.write_lock:
            db = DB(self.db_path)
            try:
                candidate_rows = db.conn.execute(
                    f"""
                    WITH latest_daily AS (
                        SELECT
                            asset_id,
                            date,
                            COALESCE(adj_close, close) AS price,
                            ROW_NUMBER() OVER (
                                PARTITION BY asset_id
                                ORDER BY date DESC
                            ) AS price_rank
                        FROM asset_quote_daily
                        WHERE asset_id IN ({placeholders})
                          AND COALESCE(adj_close, close) IS NOT NULL
                    )
                    SELECT
                        current.asset_id,
                        current.price,
                        CAST(current.updated_at AS DATE),
                        CAST(current.trade_ts_utc AS DATE),
                        daily.date,
                        daily.price
                    FROM current_asset_price current
                    LEFT JOIN latest_daily daily
                      ON daily.asset_id = current.asset_id
                     AND daily.price_rank = 1
                    WHERE current.asset_id IN ({placeholders})
                    """,
                    [*asset_ids, *asset_ids],
                ).fetchall()
            finally:
                db.conn.close()
        today = date.today()
        fresh_asset_ids = {
            str(row[0])
            for row in candidate_rows
            if row[2] is not None
            and row[2] >= today
            and row[3] is not None
            and row[4] is not None
            and row[4] >= row[3]
            and row[1] is not None
            and row[5] is not None
            and abs(float(row[5]) - float(row[1]))
            / max(abs(float(row[1])), 0.000001)
            <= 0.005
        }
        return [item for item in subscriptions if not item.asset_id or item.asset_id not in fresh_asset_ids]

    def _resolve_subscriptions(self) -> list[TickerSubscription]:
        with self.write_lock:
            db = DB(self.db_path)
            try:
                return LivePriceSubscriptionResolver(db.conn).resolve(
                    include_portfolios=True,
                    include_watchlist=self.config.include_watchlist,
                )
            finally:
                db.conn.close()

    def status(self) -> dict:
        return {
            "enabled": self._enabled,
            "running": self.running,
            "last_poll_at": self.last_poll_at,
            "last_refreshed_count": self.last_refreshed_count,
            "last_subscription_count": self.last_subscription_count,
            "last_error": self.last_error,
            "poll_interval_seconds": self.config.poll_interval_seconds,
            "include_watchlist": self.config.include_watchlist,
            "lookback_days": self.config.lookback_days,
            "max_symbols_per_tick": self.config.max_symbols_per_tick,
        }


def _truthy_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return max(int(value), 1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _running_under_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ
