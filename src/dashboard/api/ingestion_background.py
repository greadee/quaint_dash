"""Background ingestion scheduler and worker for the API server."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from dashboard.api.services import CommandApiService
from dashboard.api.worker_errors import classify_worker_error
from dashboard.application.worker_diagnostics import WorkerDiagnostics
from dashboard.db.db_conn import DB

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionBackgroundConfig:
    enabled: bool = True
    schedule_interval_seconds: int = 1800
    run_interval_seconds: int = 60
    backlog_interval_seconds: int = 1
    max_jobs_per_tick: int = 5
    max_run_batches_per_tick: int = 1
    max_assets_per_schedule: int = 25
    years: int = 10
    prices_only: bool = False

    @classmethod
    def from_env(cls) -> "IngestionBackgroundConfig":
        return cls(
            enabled=_truthy_env("INGESTION_BACKGROUND_ENABLED", default=False),
            schedule_interval_seconds=_int_env("INGESTION_BACKGROUND_SCHEDULE_INTERVAL_SECONDS", 1800),
            run_interval_seconds=_int_env("INGESTION_BACKGROUND_RUN_INTERVAL_SECONDS", 60),
            backlog_interval_seconds=_int_env("INGESTION_BACKGROUND_BACKLOG_INTERVAL_SECONDS", 1),
            max_jobs_per_tick=_int_env("INGESTION_BACKGROUND_MAX_JOBS_PER_TICK", 5),
            max_run_batches_per_tick=_int_env("INGESTION_BACKGROUND_MAX_RUN_BATCHES_PER_TICK", 1),
            max_assets_per_schedule=_int_env("INGESTION_BACKGROUND_MAX_ASSETS_PER_SCHEDULE", 25),
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
        self._stop_generation = 0
        self.last_schedule_at: datetime | None = None
        self.last_schedule_count: int | None = None
        self.last_run_at: datetime | None = None
        self.last_completed_count: int | None = None
        self.last_pending_count: int | None = None
        self.started_at: datetime | None = None
        self.last_progress_at: datetime | None = None
        self.completed_since_start = 0
        self._diagnostics = WorkerDiagnostics(
            "ingestion_background", classify_error=classify_worker_error,
        )

    @property
    def last_error(self) -> str | None:
        return self._diagnostics.last_error

    @property
    def running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def start(self) -> None:
        if not self._enabled:
            return
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self.started_at = _now()
        self.last_progress_at = None
        self.completed_since_start = 0
        self._task = asyncio.create_task(self._run_loop(), name="ingestion-background-worker")
        self._running = True

    def enable(self) -> None:
        """Enable routine ingestion controls for this API process."""
        self._enabled = True

    async def stop(self) -> None:
        self._stop_generation += 1
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._diagnostics.wait_until_idle()
        self._running = False

    async def disable(self) -> None:
        """Disable routine ingestion for this API process and stop the loop."""
        self._enabled = False
        await self.stop()

    async def tick(self) -> dict[str, int]:
        """Run one bounded schedule-and-work cycle immediately."""
        generation = self._stop_generation
        scheduled = await self.tick_schedule()
        completed = await self.tick_run() if generation == self._stop_generation else 0
        return {"scheduled_jobs": scheduled, "completed_jobs": completed}

    async def _run_loop(self) -> None:
        next_schedule_at = 0.0
        event_loop = asyncio.get_running_loop()
        try:
            self._diagnostics.recover("loop")
            while self._stop_event is not None and not self._stop_event.is_set():
                if event_loop.time() >= next_schedule_at:
                    await self.tick_schedule()
                    next_schedule_at = event_loop.time() + float(
                        self.config.schedule_interval_seconds
                    )
                completed = await self.tick_run()
                delay = min(
                    _next_run_delay_seconds(
                        self.config,
                        completed=completed,
                        pending=self.last_pending_count,
                    ),
                    max(0.0, next_schedule_at - event_loop.time()),
                )
                if delay <= 0:
                    continue
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                except TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._diagnostics.fail("loop", exc)
            LOGGER.exception("Ingestion background worker stopped unexpectedly")
        finally:
            self._running = False

    async def tick_schedule(self) -> int:
        def succeeded(count: int) -> None:
            self.last_schedule_at = _now()
            self.last_schedule_count = count
            LOGGER.info("Ingestion background scheduler queued %s job(s).", count)

        count = await self._diagnostics.run_phase("schedule", self._schedule_once, succeeded, LOGGER)
        return count or 0

    async def tick_run(self) -> int:
        def succeeded(count: int) -> None:
            self.last_run_at = _now()
            self.last_completed_count = count
            if count > 0 and self.started_at is not None:
                self.last_progress_at = self.last_run_at
                self.completed_since_start += count
            LOGGER.info("Ingestion background runner completed %s job(s).", count)

        count = await self._diagnostics.run_phase("run", self._run_once, succeeded, LOGGER)
        return count or 0

    def _schedule_once(self) -> int:
        with self.write_lock:
            db = DB(self.db_path)
            try:
                count = CommandApiService(db.conn).schedule_due_routine_ingestion_jobs(
                    max_assets=self.config.max_assets_per_schedule,
                    years=self.config.years,
                    prices_only=self.config.prices_only,
                )
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
            **self._diagnostics.status(enabled=self._enabled),
            "enabled": self._enabled,
            "running": self.running,
            "last_schedule_at": self.last_schedule_at,
            "last_schedule_count": self.last_schedule_count,
            "last_run_at": self.last_run_at,
            "last_completed_count": self.last_completed_count,
            "last_pending_count": self.last_pending_count,
            "started_at": self.started_at,
            "last_progress_at": self.last_progress_at,
            "completed_since_start": self.completed_since_start,
            "last_error": self.last_error,
            "schedule_interval_seconds": self.config.schedule_interval_seconds,
            "run_interval_seconds": self.config.run_interval_seconds,
            "backlog_interval_seconds": self.config.backlog_interval_seconds,
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


def _next_run_delay_seconds(
    config: IngestionBackgroundConfig,
    *,
    completed: int,
    pending: int | None,
) -> float:
    """Use the short cadence only while a cycle is making backlog progress."""
    if completed > 0 and pending is not None and pending > 0:
        return float(min(config.backlog_interval_seconds, config.run_interval_seconds))
    return float(config.run_interval_seconds)


def _running_under_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ
