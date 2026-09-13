"""Process-local, display-safe diagnostics for bounded background work.

Exception text is used only to recognize a small set of known failure signatures.
Every message and recovery hint returned to callers comes from the fixed catalog
below. The original exception belongs in server logs, never in this read model.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Callable, TypeVar

T = TypeVar("T")


async def _join_owned_task(task: asyncio.Task[T]) -> T:
    """Defer cancellation until an owned operation has finished its cleanup."""
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    if cancelled:
        raise asyncio.CancelledError
    return task.result()

_FAILURES = {
    "database_lock": (
        "blocked",
        "The database is currently owned by another process.",
        "Stop the other database writer before starting one bounded cycle. Do not repeatedly retry.",
    ),
    "scheduler_query": (
        "failed",
        "The scheduler could not execute its database query.",
        "Review the server diagnostics and repair the scheduler query before running another cycle.",
    ),
    "provider_rate_limit": (
        "blocked",
        "A data provider's request limit has been reached.",
        "Wait for the provider's quota window to reset and check its plan limits before retrying.",
    ),
    "provider_configuration": (
        "misconfigured",
        "A required data provider is not configured or the requested access is unavailable.",
        "Check the provider credentials and subscription access before starting another cycle.",
    ),
    "unexpected": (
        "failed",
        "The worker could not complete this phase.",
        "Review the server diagnostics for this worker and timestamp before running another cycle.",
    ),
}


@dataclass(frozen=True)
class WorkerFailure:
    worker_name: str
    phase: str
    category: str
    safe_message: str
    guidance: str
    occurred_at: datetime
    count: int


class WorkerDiagnostics:
    """Track phase recovery independently and retain the most recent failure.

    Counts and history last for this worker instance; no job records are changed.
    Mutations run on the owning event loop, including completion callbacks. A
    lock keeps synchronous API status reads consistent with phase transitions.
    """

    def __init__(
        self,
        worker_name: str,
        *,
        classify_error: Callable[[Exception, str], str] | None = None,
    ) -> None:
        self.worker_name = worker_name
        self._classify_error = classify_error or (lambda exc, phase: "unexpected")
        self.current_failures: dict[str, WorkerFailure] = {}
        self.last_failure: WorkerFailure | None = None
        self._phase_counts: dict[str, int] = {}
        self._active_task: asyncio.Task | None = None
        self._status_lock = RLock()

    @property
    def active(self) -> bool:
        return self._active_task is not None and not self._active_task.done()

    def fail(self, phase: str, exc: Exception) -> None:
        with self._status_lock:
            self._record_failure(phase, exc)

    def _record_failure(self, phase: str, exc: Exception) -> None:
        category = self._classify_error(exc, phase)
        if category not in _FAILURES:
            category = "unexpected"
        _, message, guidance = _FAILURES[category]
        count = self._phase_counts.get(phase, 0) + 1
        self._phase_counts[phase] = count
        failure = WorkerFailure(
            self.worker_name, phase, category, message, guidance, datetime.now(timezone.utc), count,
        )
        self.current_failures[phase] = failure
        self.last_failure = failure

    def recover(self, phase: str) -> None:
        with self._status_lock:
            self.current_failures.pop(phase, None)

    def _primary_failure(self) -> WorkerFailure | None:
        priority = {"failed": 3, "misconfigured": 2, "blocked": 1}
        return max(
            self.current_failures.values(),
            key=lambda failure: (priority[_FAILURES[failure.category][0]], failure.occurred_at),
            default=None,
        )

    @property
    def last_error(self) -> str | None:
        with self._status_lock:
            failure = self._primary_failure()
            return failure.safe_message if failure else None

    def status(self, *, enabled: bool) -> dict:
        with self._status_lock:
            return self._status_snapshot(enabled=enabled)

    def _status_snapshot(self, *, enabled: bool) -> dict:
        failure = self._primary_failure()
        if failure is not None:
            state = _FAILURES[failure.category][0]
        elif self.active:
            state = "running"
        else:
            state = "idle" if enabled else "disabled"
        return {
            "worker_name": self.worker_name,
            "state": state,
            "current_failures": {phase: asdict(item) for phase, item in self.current_failures.items()},
            "last_failure": asdict(self.last_failure) if self.last_failure else None,
            "failure_count": sum(self._phase_counts.values()),
        }

    async def run_phase(
        self,
        phase: str,
        operation: Callable[[], T],
        on_success: Callable[[T], None],
        logger: logging.Logger,
    ) -> T | None:
        """Skip overlapping work and finish an owned thread before cancellation.

        Cancelling an asyncio waiter does not cancel ``to_thread``. Shielding and
        joining the actual operation keeps shutdown from closing database owners
        while work is still using them. Completion state is recorded even when
        the original HTTP caller or background loop has been cancelled.
        """
        if self.active:
            return None

        async def execute() -> T | None:
            try:
                result = await asyncio.to_thread(operation)
                on_success(result)
            except Exception as exc:
                self.fail(phase, exc)
                logger.exception("%s %s phase failed", self.worker_name, phase)
                return None
            self.recover(phase)
            return result

        task = asyncio.create_task(execute(), name=f"{self.worker_name}-{phase}")
        self._active_task = task
        return await _join_owned_task(task)

    async def wait_until_idle(self) -> None:
        if self.active:
            await _join_owned_task(self._active_task)
