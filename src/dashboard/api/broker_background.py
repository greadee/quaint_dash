"""Periodic broker refresh worker for the API server."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import os
from pathlib import Path
from threading import Lock

from dashboard.api.worker_errors import classify_worker_error
from dashboard.application.worker_diagnostics import WorkerDiagnostics
from dashboard.db.db_conn import DB
from dashboard.models.storage import DashboardManager

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BrokerBackgroundConfig:
    enabled: bool = False
    interval_seconds: int = 3600
    min_age_hours: int = 1
    max_users: int | None = None

    @classmethod
    def from_env(cls) -> "BrokerBackgroundConfig":
        return cls(
            enabled=_truthy_env("BROKER_SYNC_BACKGROUND_ENABLED", default=False),
            interval_seconds=_int_env("BROKER_SYNC_BACKGROUND_INTERVAL_SECONDS", 3600) or 3600,
            min_age_hours=_int_env("BROKER_SYNC_MIN_AGE_HOURS", 1) or 1,
            max_users=_int_env("BROKER_SYNC_MAX_USERS"),
        )


class BrokerBackgroundWorker:
    def __init__(
        self,
        db_path: Path,
        write_lock: Lock,
        config: BrokerBackgroundConfig,
    ) -> None:
        self.db_path = db_path
        self.write_lock = write_lock
        self.config = config
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self._diagnostics = WorkerDiagnostics(
            "broker_background", classify_error=classify_worker_error,
        )

    def start(self) -> None:
        if not self.config.enabled or (self._task is not None and not self._task.done()):
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="broker-sync-background")

    async def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._diagnostics.wait_until_idle()
        self._task = None
        self._stop_event = None

    async def _run(self) -> None:
        assert self._stop_event is not None
        try:
            self._diagnostics.recover("loop")
            while not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=max(self.config.interval_seconds, 60),
                    )
                except asyncio.TimeoutError:
                    await self._diagnostics.run_phase(
                        "sync", self._sync_due, lambda _result: None, LOGGER,
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._diagnostics.fail("loop", exc)
            LOGGER.exception("Broker background worker stopped unexpectedly")

    def _sync_due(self) -> None:
        with self.write_lock:
            db = DB(self.db_path)
            try:
                manager = DashboardManager(db)
                result = manager.broker_snaptrade_sync_due(
                    max_users=self.config.max_users,
                    min_age_hours=self.config.min_age_hours,
                )
                if result.users_synced:
                    LOGGER.info(
                        "Broker background refresh synced %s user(s), saw %s account(s), %s position(s), and %s transaction(s).",
                        result.users_synced,
                        result.accounts_seen,
                        result.positions_seen,
                        result.transactions_seen,
                    )
            finally:
                db.conn.close()


def _truthy_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)
