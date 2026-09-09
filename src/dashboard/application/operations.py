"""Operations/Data Quality application use cases."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
import re
from typing import Any, Mapping, Protocol


BLOCKED_BACKLOG_AGE_SECONDS = 60 * 60
DEAD_LETTER_CRITICAL_THRESHOLD = 1


class QueueStatusSource(Protocol):
    """Read existing queue state without claiming or scheduling jobs."""

    def status_groups(self) -> Iterable[Mapping[str, Any]]: ...


def _queue_failure(error: str, terminal_reason: str) -> tuple[str, str, str, str]:
    """Return allowlisted labels only; never echo provider payloads or secrets."""
    signature = f"{error} {terminal_reason}".lower()
    providers = [
        name
        for name in ("fmp", "yfinance", "reddit", "finnhub", "snaptrade")
        if re.search(rf"\b{name}\b", signature)
    ]
    if re.search(r"\bx (?:provider|api)\b|x_bearer_token|twitter", signature):
        providers.append("x")
    provider = providers[0] if len(providers) == 1 else "multiple" if providers else "unknown"
    if any(
        item in signature for item in ("rate limit", "call budget", "too many requests")
    ) or re.search(r"\b(?:http(?: error)?|status(?: code)?)[ :]+429\b", signature):
        return (
            provider,
            "provider_rate_limit",
            "Provider request limit reached.",
            "Check provider limits before choosing a bounded retry.",
        )
    if any(
        item in signature
        for item in (
            "missing credential",
            "provider missing",
            "api key",
            "api_key",
            "bearer_token",
            "not configured",
        )
    ) or re.search(r"\b(?:http(?: error)?|status(?: code)?)[ :]+40[123]\b", signature):
        return (
            provider,
            "provider_configuration",
            "Provider access or configuration needs attention.",
            "Check credentials and subscription access before retrying.",
        )
    if any(
        item in signature
        for item in (
            "could not set lock",
            "used by another process",
            "database is locked",
            "conflicting lock",
        )
    ):
        return (
            provider,
            "database_lock",
            "The local database could not be accessed.",
            "Check that one app process owns the database, then refresh this status.",
        )
    if "binder error" in signature or "referenced table" in signature:
        return (
            provider,
            "scheduler_query",
            "A scheduling query failed.",
            "Apply the scheduler repair before requesting more work.",
        )
    if any(item in signature for item in ("retry budget", "attempt budget", "max attempts")):
        return (
            provider,
            "retry_exhausted",
            "The job exhausted its retry budget.",
            "Review the underlying failure before creating replacement work.",
        )
    return (
        provider,
        "unexpected",
        "The job failed; details require local review.",
        "Review local diagnostics before retrying; stored error payloads are not displayed here.",
    )


def safe_ingestion_job(job: Mapping[str, Any]) -> dict[str, Any]:
    """Keep stored diagnostics private while preserving the job response shape."""
    result = dict(job)
    for key in ("error_message", "terminal_reason"):
        if result.get(key):
            result[key] = _queue_failure(
                str(job.get("error_message") or ""), str(job.get("terminal_reason") or "")
            )[2]
    return result


def _affected_product(domain: str, dataset: str) -> str:
    """Describe existing queue scope using fixed display labels only."""
    if domain == "sentiment":
        return (
            "Retail sentiment"
            if dataset in {"reddit", "x", "sentiment_daily"}
            else "News and sentiment"
        )
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
    return (
        timestamp.replace(tzinfo=timezone.utc)
        if timestamp.tzinfo is None
        else timestamp.astimezone(timezone.utc)
    )


class OperationsQueueQueries:
    """Produce a read-only UTC snapshot; a failed read remains a failed read."""

    def __init__(
        self, source: QueueStatusSource, *, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._source = source
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def queue_status(self) -> dict[str, Any]:
        observed_at = _utc(self._clock())
        counts: Counter[str] = Counter()
        failures: dict[str, Counter[tuple[str, str, str, str]]] = {
            "dead_letter": Counter(),
            "failed": Counter(),
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
                affected_products.add(
                    _affected_product(str(group["domain"]), str(group["dataset"]))
                )
            if state in failures:
                failures[state][
                    _queue_failure(
                        str(group["error_message"] or ""), str(group["terminal_reason"] or "")
                    )
                ] += int(group["count"])

        def failure_groups(state: str) -> list[dict[str, Any]]:
            return [
                {
                    "provider": provider,
                    "error_category": category,
                    "count": count,
                    "safe_message": message,
                    "guidance": guidance,
                }
                for (provider, category, message, guidance), count in sorted(
                    failures[state].items()
                )
            ]

        return {
            "observed_at": observed_at,
            "pending_count": counts["pending"],
            "running_count": counts["running"],
            "dead_letter_count": counts["dead_letter"],
            "failed_count": counts["failed"],
            "oldest_backlog_at": oldest,
            "oldest_backlog_age_seconds": max(0.0, (observed_at - oldest).total_seconds())
            if oldest
            else None,
            "dead_letter_groups": failure_groups("dead_letter"),
            "failed_groups": failure_groups("failed"),
            "affected_data_products": sorted(affected_products),
        }


def build_operations_health_summary(
    *,
    queue: Mapping[str, Any],
    workers: Iterable[Mapping[str, Any]],
    benchmark_evidence: Iterable[Mapping[str, Any]] = (),
    news_providers: Iterable[Mapping[str, Any]] = (),
    retail_providers: Iterable[Mapping[str, Any]] = (),
    signal_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine read-only diagnostics using one conservative severity policy.

    Any dead letter is critical. A backlog older than one hour is critical when
    routine ingestion is disabled. Current worker failures and failed enabled
    providers are critical. Stale essential evidence, stale providers, cached
    signals, and missing optional social credentials are warnings. Workers that
    are intentionally disabled without blocking old work are informational.
    """
    worker_rows = [dict(item) for item in workers]
    incidents: list[dict[str, Any]] = []

    def add(
        code: str,
        severity: str,
        title: str,
        detail: str,
        guidance: str,
        products: Iterable[str],
        *,
        job_status: str | None = None,
    ) -> None:
        affected = sorted(set(products))
        query = f"?incident={code}"
        if job_status:
            query += f"&status={job_status}"
        incidents.append(
            {
                "code": code,
                "severity": severity,
                "title": title,
                "detail": detail,
                "guidance": guidance,
                "affected_data_products": affected,
                "operations_url": f"/operations{query}#operations-health",
            }
        )

    pending = int(queue.get("pending_count") or 0)
    dead_letters = int(queue.get("dead_letter_count") or 0)
    failed = int(queue.get("failed_count") or 0)
    backlog_age = queue.get("oldest_backlog_age_seconds")
    queue_products = [str(item) for item in queue.get("affected_data_products") or ()]
    routine = next(
        (item for item in worker_rows if item.get("worker_name") == "ingestion_background"),
        None,
    )

    if dead_letters >= DEAD_LETTER_CRITICAL_THRESHOLD:
        add(
            "dead-letters",
            "critical",
            "Jobs have stopped retrying",
            f"{dead_letters} dead-letter job{'s' if dead_letters != 1 else ''} require cause review.",
            "Review the safe provider/error groups below before creating replacement work.",
            queue_products,
            job_status="dead_letter",
        )
    elif failed:
        add(
            "failed-jobs",
            "warning",
            "Failed jobs need review",
            f"{failed} legacy failed job{'s' if failed != 1 else ''} remain in the queue.",
            "Review the failure category before choosing a bounded retry.",
            queue_products,
            job_status="failed",
        )

    blocked_backlog = bool(
        pending
        and backlog_age is not None
        and float(backlog_age) >= BLOCKED_BACKLOG_AGE_SECONDS
        and routine
        and not bool(routine.get("enabled"))
    )
    if blocked_backlog:
        add(
            "blocked-backlog",
            "critical",
            "Old work is waiting without a routine worker",
            f"{pending} queued job{'s' if pending != 1 else ''} include work older than one hour while routine ingestion is disabled.",
            "Confirm provider access and worker intent, then use a bounded run or start the routine worker.",
            queue_products,
            job_status="pending",
        )
    elif pending:
        add(
            "active-backlog",
            "warning",
            "Data work is waiting",
            f"{pending} job{'s are' if pending != 1 else ' is'} queued.",
            "Check backlog age and worker state before requesting more work.",
            queue_products,
            job_status="pending",
        )

    for worker in worker_rows:
        failures = worker.get("current_failures") or {}
        state = str(worker.get("state") or "unknown")
        products = worker.get("affected_data_products") or ()
        label = str(worker.get("label") or worker.get("worker_name") or "Worker")
        if state in {"failed", "blocked", "misconfigured"} or failures:
            failure = next(iter(failures.values()), {}) if isinstance(failures, Mapping) else {}
            add(
                f"worker-{worker.get('worker_name', 'unknown')}",
                "critical",
                f"{label} is {state}",
                str(failure.get("safe_message") or "The worker cannot complete its current cycle."),
                str(
                    failure.get("guidance") or "Review worker diagnostics before running more work."
                ),
                products,
            )

    failure_groups = [
        *list(queue.get("dead_letter_groups") or ()),
        *list(queue.get("failed_groups") or ()),
    ]
    provider_groups: dict[tuple[str, str], Mapping[str, Any]] = {}
    for group in failure_groups:
        provider_groups[
            (
                str(group.get("provider") or "unknown"),
                str(group.get("error_category") or "unexpected"),
            )
        ] = group
    for (provider, category), group in provider_groups.items():
        if provider == "unknown":
            continue
        code = f"provider-{provider}-{category}".replace("_", "-")
        add(
            code,
            "critical"
            if category
            in {"database_lock", "scheduler_query", "provider_configuration", "provider_rate_limit"}
            else "warning",
            f"{provider.upper() if provider == 'fmp' else provider.title()} provider work is blocked",
            str(group.get("safe_message") or "Provider work needs attention."),
            str(group.get("guidance") or "Review provider access before retrying."),
            queue_products,
            job_status="dead_letter"
            if group in (queue.get("dead_letter_groups") or ())
            else "failed",
        )

    evidence_rows = [dict(item) for item in benchmark_evidence]
    stale_benchmarks = [
        item
        for item in evidence_rows
        if item.get("freshness_state") in {"stale", "blocked"}
        or item.get("action_eligibility") == "blocked"
    ]
    if stale_benchmarks:
        oldest = min(
            (str(item["observed_at"]) for item in stale_benchmarks if item.get("observed_at")),
            default=None,
        )
        detail = f"{len(stale_benchmarks)} benchmark series are stale or blocked."
        if oldest:
            detail += f" Oldest evidence is dated {oldest[:10]}."
        add(
            "stale-benchmarks",
            "warning",
            "Benchmark evidence is stale",
            detail,
            "Review benchmark freshness before using relative-performance views.",
            ("Benchmarks", "Comparison context"),
        )

    for provider in news_providers:
        if not provider.get("is_enabled"):
            continue
        state = str(provider.get("status") or "unknown")
        if state not in {"failed", "stale", "not_started"}:
            continue
        code_name = (
            re.sub(r"[^a-z0-9]+", "-", str(provider.get("provider_code") or "news").lower()).strip(
                "-"
            )
            or "news"
        )
        add(
            f"news-{code_name}",
            "critical" if state == "failed" else "warning",
            f"{str(provider.get('provider_name') or provider.get('provider_code') or 'News provider')} is {state.replace('_', ' ')}",
            "Current news coverage from this enabled provider is not available.",
            "Review provider access and last-success timing before refreshing news.",
            ("News", "Signals"),
        )

    signal_summary = signal_summary or {}
    if signal_summary.get("stale_cached_results"):
        add(
            "stale-signals",
            "warning",
            "Signal results include stale cached records",
            "The signal store contains expired or incomplete evidence.",
            "Review the Signals freshness filters and ranking readiness before scheduling new work.",
            ("Signals",),
        )

    retail_rows = [dict(item) for item in retail_providers]
    if retail_rows and not any(item.get("configured") for item in retail_rows):
        add(
            "social-credentials",
            "warning",
            "Social providers are not configured",
            "Reddit and X ingestion are unavailable; stored social outputs are not current source evidence.",
            "Configure an intended provider before scheduling social ingestion. Leave this disabled if social data is intentionally excluded.",
            ("Retail sentiment",),
        )

    disabled = [
        str(item.get("label") or item.get("worker_name"))
        for item in worker_rows
        if not item.get("enabled")
    ]
    if disabled and not blocked_backlog:
        add(
            "workers-disabled",
            "info",
            "Automatic workers are disabled",
            f"Disabled by configuration: {', '.join(disabled)}.",
            "No blocked old backlog was detected. Start workers only if automatic refresh is intended.",
            (),
        )

    severity_rank = {"info": 0, "warning": 1, "critical": 2}
    incidents.sort(key=lambda item: (-severity_rank[item["severity"]], item["code"]))
    actionable = [item for item in incidents if item["severity"] != "info"]
    overall = (
        "critical"
        if any(item["severity"] == "critical" for item in incidents)
        else "degraded"
        if actionable
        else "healthy"
    )
    headlines = {
        "critical": "Data health needs immediate attention",
        "degraded": "Data health is degraded",
        "healthy": "Data health is clear",
    }
    affected_products = sorted(
        {product for item in actionable for product in item["affected_data_products"]}
    )
    summary = (
        actionable[0]["detail"]
        if actionable
        else "No critical failures, stale essential evidence, or blocked work were detected."
    )
    return {
        "observed_at": queue["observed_at"],
        "status": overall,
        "headline": headlines[overall],
        "summary": summary,
        "incident_count": len(actionable),
        "informational_count": len(incidents) - len(actionable),
        "affected_data_products": affected_products,
        "queue": dict(queue),
        "workers": worker_rows,
        "incidents": incidents,
        "operations_url": actionable[0]["operations_url"]
        if actionable
        else "/operations#operations-health",
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
