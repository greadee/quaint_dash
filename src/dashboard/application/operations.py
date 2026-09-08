"""Operations/Data Quality application use cases."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
import re
from typing import Any, Mapping, Protocol


class QueueStatusSource(Protocol):
    """Read existing queue state without claiming or scheduling jobs."""

    def status_groups(self) -> Iterable[Mapping[str, Any]]: ...


def _queue_failure(error: str, terminal_reason: str) -> tuple[str, str, str, str]:
    """Return allowlisted labels only; never echo provider payloads or secrets."""
    signature = f"{error} {terminal_reason}".lower()
    providers = [name for name in ("fmp", "yfinance", "reddit", "finnhub", "snaptrade")
                 if re.search(rf"\b{name}\b", signature)]
    if re.search(r"\bx (?:provider|api)\b|x_bearer_token|twitter", signature):
        providers.append("x")
    provider = providers[0] if len(providers) == 1 else "multiple" if providers else "unknown"
    if any(item in signature for item in ("rate limit", "call budget", "too many requests")) or re.search(r"\b(?:http(?: error)?|status(?: code)?)[ :]+429\b", signature):
        return provider, "provider_rate_limit", "Provider request limit reached.", "Check provider limits before choosing a bounded retry."
    if any(item in signature for item in ("missing credential", "provider missing", "api key", "api_key", "bearer_token", "not configured")) or re.search(r"\b(?:http(?: error)?|status(?: code)?)[ :]+40[123]\b", signature):
        return provider, "provider_configuration", "Provider access or configuration needs attention.", "Check credentials and subscription access before retrying."
    if any(item in signature for item in ("could not set lock", "used by another process", "database is locked", "conflicting lock")):
        return provider, "database_lock", "The local database could not be accessed.", "Check that one app process owns the database, then refresh this status."
    if "binder error" in signature or "referenced table" in signature:
        return provider, "scheduler_query", "A scheduling query failed.", "Apply the scheduler repair before requesting more work."
    if any(item in signature for item in ("retry budget", "attempt budget", "max attempts")):
        return provider, "retry_exhausted", "The job exhausted its retry budget.", "Review the underlying failure before creating replacement work."
    return provider, "unexpected", "The job failed; details require local review.", "Review local diagnostics before retrying; stored error payloads are not displayed here."


def safe_ingestion_job(job: Mapping[str, Any]) -> dict[str, Any]:
    """Keep stored diagnostics private while preserving the job response shape."""
    result = dict(job)
    for key in ("error_message", "terminal_reason"):
        if result.get(key):
            result[key] = _queue_failure(str(job.get("error_message") or ""),
                                         str(job.get("terminal_reason") or ""))[2]
    return result


def _affected_product(domain: str, dataset: str) -> str:
    """Describe existing queue scope using fixed display labels only."""
    if domain == "sentiment":
        return "Retail sentiment" if dataset in {"reddit", "x", "sentiment_daily"} else "News and sentiment"
    return {
        "market": "Prices and market history",
        "fundamentals": "Fundamentals and valuation inputs",
        "corporate_calendar": "Earnings and financial statements",
        "corporate": "Earnings and financial statements",
        "benchmark": "Benchmark data",
        "benchmarks": "Benchmark data",
        "analytics": "Analytical inputs",
    }.get(domain, "Other data products")


def _utc(timestamp: datetime) -> datetime:
    # The queue persists UTC as naive TIMESTAMP values. Never use host timezone.
    return timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp.astimezone(timezone.utc)


class OperationsQueueQueries:
    """Produce a read-only UTC snapshot; a failed read remains a failed read."""

    def __init__(self, source: QueueStatusSource, *, clock: Callable[[], datetime] | None = None) -> None:
        self._source = source
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def queue_status(self) -> dict[str, Any]:
        observed_at = _utc(self._clock())
        counts: Counter[str] = Counter()
        failures: dict[str, Counter[tuple[str, str, str, str]]] = {
            "dead_letter": Counter(), "failed": Counter(),
        }
        affected_products: set[str] = set()
        oldest: datetime | None = None
        for group in self._source.status_groups():
            state = str(group["status"])
            counts[state] += int(group["count"])
            if state in {"pending", "running"}:
                timestamp = _utc(group["oldest_created_at"])
                oldest = timestamp if oldest is None else min(oldest, timestamp)
            if state in {"pending", "running", "dead_letter", "failed"}:
                affected_products.add(_affected_product(str(group["domain"]), str(group["dataset"])))
            if state in failures:
                failures[state][_queue_failure(str(group["error_message"] or ""), str(group["terminal_reason"] or ""))] += int(group["count"])

        def failure_groups(state: str) -> list[dict[str, Any]]:
            return [
                {"provider": provider, "error_category": category, "count": count,
                 "safe_message": message, "guidance": guidance}
                for (provider, category, message, guidance), count in sorted(failures[state].items())
            ]

        return {
            "observed_at": observed_at,
            "pending_count": counts["pending"],
            "running_count": counts["running"],
            "dead_letter_count": counts["dead_letter"],
            "failed_count": counts["failed"],
            "oldest_backlog_at": oldest,
            "oldest_backlog_age_seconds": max(0.0, (observed_at - oldest).total_seconds()) if oldest else None,
            "dead_letter_groups": failure_groups("dead_letter"),
            "failed_groups": failure_groups("failed"),
            "affected_data_products": sorted(affected_products),
        }


class WorkerStatusSource(Protocol):
    """Minimal interface for workers that expose process-local status."""

    def status(self) -> Mapping[str, Any]:
        """Return the worker's current status snapshot."""


class WorkerCommandSource(WorkerStatusSource, Protocol):
    """Minimal interface for controllable process-local workers."""

    def enable(self) -> None:
        """Enable the worker for this process."""

    async def disable(self) -> None:
        """Disable and stop the worker for this process."""

    async def tick(self) -> Mapping[str, Any]:
        """Run one bounded work cycle."""


class OperationsStatusQueries:
    """Read-only Operations status use cases.

    API routes depend on this facade instead of reaching into worker
    implementations directly. Worker command behavior remains owned by the
    existing worker classes until the command migration slice.
    """

    def __init__(
        self,
        ingestion_background_worker: WorkerStatusSource,
        market_freshness_worker: WorkerStatusSource,
        data_readiness_worker: WorkerStatusSource,
    ) -> None:
        self._ingestion_background_worker = ingestion_background_worker
        self._market_freshness_worker = market_freshness_worker
        self._data_readiness_worker = data_readiness_worker

    def ingestion_background_status(self) -> dict[str, Any]:
        return dict(self._ingestion_background_worker.status())

    def market_freshness_status(self) -> dict[str, Any]:
        return dict(self._market_freshness_worker.status())

    def data_readiness_status(self) -> dict[str, Any]:
        return dict(self._data_readiness_worker.status())


class OperationsWorkerCommands:
    """Operations worker command use cases."""

    def __init__(
        self,
        ingestion_background_worker: WorkerCommandSource,
        market_freshness_worker: WorkerCommandSource,
        data_readiness_worker: WorkerCommandSource,
    ) -> None:
        self._ingestion_background_worker = ingestion_background_worker
        self._market_freshness_worker = market_freshness_worker
        self._data_readiness_worker = data_readiness_worker

    def start_ingestion_background(self) -> dict[str, Any]:
        self._ingestion_background_worker.enable()
        return dict(self._ingestion_background_worker.status())

    async def stop_ingestion_background(self) -> dict[str, Any]:
        await self._ingestion_background_worker.disable()
        return dict(self._ingestion_background_worker.status())

    async def tick_ingestion_background(self) -> dict[str, Any]:
        return dict(await self._ingestion_background_worker.tick())

    def start_market_freshness(self) -> dict[str, Any]:
        self._market_freshness_worker.enable()
        return dict(self._market_freshness_worker.status())

    async def stop_market_freshness(self) -> dict[str, Any]:
        await self._market_freshness_worker.disable()
        return dict(self._market_freshness_worker.status())

    async def tick_market_freshness(self) -> dict[str, Any]:
        return dict(await self._market_freshness_worker.tick())

    def start_data_readiness(self) -> dict[str, Any]:
        self._data_readiness_worker.enable()
        return dict(self._data_readiness_worker.status())

    async def stop_data_readiness(self) -> dict[str, Any]:
        await self._data_readiness_worker.disable()
        return dict(self._data_readiness_worker.status())

    async def tick_data_readiness(self) -> dict[str, Any]:
        return dict(await self._data_readiness_worker.tick())
