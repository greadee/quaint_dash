"""Background ingestion scheduler and worker for the API server."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from dashboard.api.services import CommandApiService, PortfolioApiService
from dashboard.db.db_conn import DB

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionBackgroundConfig:
    enabled: bool = True
    schedule_interval_seconds: int = 900
    run_interval_seconds: int = 30
    max_jobs_per_tick: int = 10
    max_run_batches_per_tick: int = 6
    max_assets_per_schedule: int = 50
    years: int = 10
    prices_only: bool = False

    @classmethod
    def from_env(cls) -> "IngestionBackgroundConfig":
        return cls(
            enabled=_truthy_env("INGESTION_BACKGROUND_ENABLED", default=False),
            schedule_interval_seconds=_int_env("INGESTION_BACKGROUND_SCHEDULE_INTERVAL_SECONDS", 900),
            run_interval_seconds=_int_env("INGESTION_BACKGROUND_RUN_INTERVAL_SECONDS", 30),
            max_jobs_per_tick=_int_env("INGESTION_BACKGROUND_MAX_JOBS_PER_TICK", 10),
            max_run_batches_per_tick=_int_env("INGESTION_BACKGROUND_MAX_RUN_BATCHES_PER_TICK", 6),
            max_assets_per_schedule=_int_env("INGESTION_BACKGROUND_MAX_ASSETS_PER_SCHEDULE", 50),
            years=_int_env("INGESTION_BACKGROUND_YEARS", 10),
            prices_only=_truthy_env("INGESTION_BACKGROUND_PRICES_ONLY", default=False),
        )


class IngestionBackgroundWorker:
    def __init__(self, db_path: Path, write_lock: Lock, config: IngestionBackgroundConfig) -> None:
        self.db_path = Path(db_path)
        self.write_lock = write_lock
        self.config = config
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self._enabled = config.enabled
        self._running = False
        self.last_schedule_at: datetime | None = None
        self.last_schedule_count: int | None = None
        self.last_run_at: datetime | None = None
        self.last_completed_count: int | None = None
        self.last_pending_count: int | None = None
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
        self._task = asyncio.create_task(self._run_loop(), name="ingestion-background-worker")
        self._running = True

    def enable(self) -> None:
        """Enable routine ingestion controls for this API process."""
        self._enabled = True

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

    async def disable(self) -> None:
        """Disable routine ingestion for this API process and stop the loop."""
        self._enabled = False
        await self.stop()

    async def tick(self) -> dict[str, int]:
        """Run one bounded schedule-and-work cycle immediately."""
        scheduled = await self.tick_schedule()
        completed = await self.tick_run()
        return {"scheduled_jobs": scheduled, "completed_jobs": completed}

    async def _run_loop(self) -> None:
        next_schedule_delay = 0.0
        try:
            while self._stop_event is not None and not self._stop_event.is_set():
                if next_schedule_delay <= 0:
                    await self.tick_schedule()
                    next_schedule_delay = float(self.config.schedule_interval_seconds)
                await self.tick_run()
                delay = min(float(self.config.run_interval_seconds), next_schedule_delay)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                except TimeoutError:
                    pass
                next_schedule_delay -= delay
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error = str(exc)
            LOGGER.exception("Ingestion background worker stopped unexpectedly")
        finally:
            self._running = False

    async def tick_schedule(self) -> int:
        try:
            count = await asyncio.to_thread(self._schedule_once)
        except Exception as exc:
            self.last_error = str(exc)
            LOGGER.warning("Ingestion background scheduling failed: %s", exc)
            return 0
        self.last_schedule_at = _now()
        self.last_schedule_count = count
        self.last_error = None
        LOGGER.info("Ingestion background scheduler queued %s job(s).", count)
        return count

    async def tick_run(self) -> int:
        try:
            count = await asyncio.to_thread(self._run_once)
        except Exception as exc:
            self.last_error = str(exc)
            LOGGER.warning("Ingestion background runner failed: %s", exc)
            return 0
        self.last_run_at = _now()
        self.last_completed_count = count
        self.last_error = None
        LOGGER.info("Ingestion background runner completed %s job(s).", count)
        return count

    def _schedule_once(self) -> int:
        with self.write_lock:
            db = DB(self.db_path)
            try:
                count = CommandApiService(db.conn).schedule_due_routine_ingestion_jobs(
                    max_assets=self.config.max_assets_per_schedule,
                    years=self.config.years,
                    prices_only=self.config.prices_only,
                )
                try:
                    PortfolioApiService(db.conn).stock_rankings(
                        factor="aggregate",
                        universe="tracked",
                        direction="buy",
                        timeframe="monthly",
                        include_retail_sentiment=False,
                        limit=self.config.max_assets_per_schedule,
                        offset=0,
                    )
                except Exception as exc:
                    LOGGER.debug("Ingestion background ranking warm-up skipped: %s", exc)
                return count
            finally:
                db.conn.close()

    def _run_once(self) -> int:
        with self.write_lock:
            db = DB(self.db_path)
            try:
                service = CommandApiService(db.conn)
                total = 0
                for _ in range(self.config.max_run_batches_per_tick):
                    completed = service.run_ingestion_jobs(
                        domain="all",
                        max_jobs=self.config.max_jobs_per_tick,
                    )
                    total += completed
                    if completed < self.config.max_jobs_per_tick:
                        break
                self.last_pending_count = _pending_job_count(db.conn)
                return total
            finally:
                db.conn.close()

    def status(self) -> dict:
        return {
            "enabled": self._enabled,
            "running": self.running,
            "last_schedule_at": self.last_schedule_at,
            "last_schedule_count": self.last_schedule_count,
            "last_run_at": self.last_run_at,
            "last_completed_count": self.last_completed_count,
            "last_pending_count": self.last_pending_count,
            "last_error": self.last_error,
            "schedule_interval_seconds": self.config.schedule_interval_seconds,
            "run_interval_seconds": self.config.run_interval_seconds,
            "max_jobs_per_tick": self.config.max_jobs_per_tick,
            "max_run_batches_per_tick": self.config.max_run_batches_per_tick,
            "max_assets_per_schedule": self.config.max_assets_per_schedule,
            "years": self.config.years,
            "prices_only": self.config.prices_only,
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
    parsed = int(value)
    return max(parsed, 1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pending_job_count(conn) -> int:
    try:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM ingestion_job
            WHERE status IN ('pending', 'running')
            """
        ).fetchone()
    except Exception as exc:
        LOGGER.debug("Ingestion background pending-count skipped: %s", exc)
        return 0
    return int(row[0])


def _running_under_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ
