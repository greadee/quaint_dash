"""S1 failures, recovery and shutdown checks; no providers or live database."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timezone
import json
from threading import Event, Lock
from unittest.mock import Mock

import duckdb
import pytest

from dashboard.api.data_readiness_background import DataReadinessConfig, DataReadinessWorker
from dashboard.api.ingestion_background import IngestionBackgroundConfig, IngestionBackgroundWorker
from dashboard.api.market_freshness_background import MarketFreshnessConfig, MarketFreshnessWorker
from dashboard.api.worker_errors import classify_worker_error
from dashboard.application.worker_diagnostics import WorkerDiagnostics
from dashboard.db.db_conn import DatabaseInUseError, connect_database
from dashboard.ingestion.rate_limits import RateLimitExceeded
from dashboard.ingestion.ticker_universe import TickerSubscription


def ingestion_worker(tmp_path):
    return IngestionBackgroundWorker(
        tmp_path / "worker.db", Lock(), IngestionBackgroundConfig(enabled=False),
    )


def test_diagnostic_snapshot_stays_consistent_during_threaded_status_reads():
    diagnostics = WorkerDiagnostics("test")
    start = Event()

    def transition():
        assert start.wait(3)
        for _ in range(1000):
            diagnostics.fail("schedule", RuntimeError("private"))
            diagnostics.recover("schedule")

    def read():
        start.set()
        for _ in range(1000):
            status = diagnostics.status(enabled=True)
            assert bool(status["current_failures"]) == (status["state"] == "failed")
            if status["current_failures"]:
                assert status["current_failures"]["schedule"] == status["last_failure"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        mutation = executor.submit(transition)
        snapshot = executor.submit(read)
        mutation.result(timeout=10)
        snapshot.result(timeout=10)
    assert diagnostics.status(enabled=True)["failure_count"] == 1000


def fail(exc):
    def operation():
        raise exc
    return operation


def test_runner_success_does_not_erase_scheduler_failure(tmp_path, monkeypatch):
    worker = ingestion_worker(tmp_path)
    monkeypatch.setattr(worker, "_schedule_once", fail(duckdb.BinderException("raw query secret")))
    monkeypatch.setattr(worker, "_run_once", lambda: 2)

    assert asyncio.run(worker.tick()) == {"scheduled_jobs": 0, "completed_jobs": 2}
    state = worker.status()
    assert state["state"] == "failed"
    assert set(state["current_failures"]) == {"schedule"}
    assert state["current_failures"]["schedule"]["category"] == "scheduler_query"
    assert state["last_schedule_at"] is None
    assert state["last_completed_count"] == 2
    assert "secret" not in json.dumps(state, default=str)

    monkeypatch.setattr(worker, "_schedule_once", lambda: 3)
    assert asyncio.run(worker.tick_schedule()) == 3
    state = worker.status()
    assert state["current_failures"] == {}
    assert state["last_error"] is None
    assert state["state"] == "disabled"
    assert state["last_failure"]["phase"] == "schedule"
    assert state["failure_count"] == 1


@pytest.mark.parametrize(("exc", "phase", "category", "state"), [
    (DatabaseInUseError("private.db"), "run", "database_lock", "blocked"),
    (duckdb.IOException("file used by another process private.db"), "run", "database_lock", "blocked"),
    (duckdb.BinderException("secret SQL"), "schedule", "scheduler_query", "failed"),
    (duckdb.ParserException("secret SQL"), "schedule", "scheduler_query", "failed"),
    (RateLimitExceeded("private quota"), "run", "provider_rate_limit", "blocked"),
    (RuntimeError("FMP HTTP error 402 apikey=private"), "run", "provider_configuration", "misconfigured"),
    (RuntimeError("missing credentials private"), "run", "provider_configuration", "misconfigured"),
    (RuntimeError("arbitrary secret Bearer private https://private.test"), "run", "unexpected", "failed"),
])
def test_failure_classification_counts_and_redaction(exc, phase, category, state):
    diagnostics = WorkerDiagnostics("worker", classify_error=classify_worker_error)
    diagnostics.fail(phase, exc)
    diagnostics.fail(phase, exc)
    snapshot = diagnostics.status(enabled=False)
    failure = snapshot["current_failures"][phase]
    assert snapshot["state"] == state
    assert snapshot["failure_count"] == failure["count"] == 2
    assert failure["category"] == category
    assert failure["occurred_at"].tzinfo == timezone.utc
    assert failure["guidance"]
    serialized = json.dumps(snapshot, default=str)
    for secret in ("private", "secret SQL", "Bearer", "apikey"):
        assert secret not in serialized


def test_recovery_is_phase_specific_and_history_survives():
    diagnostics = WorkerDiagnostics("worker", classify_error=classify_worker_error)
    diagnostics.fail("schedule", RuntimeError("scheduling error"))
    diagnostics.fail("run", RateLimitExceeded("quota"))
    diagnostics.recover("schedule")
    assert set(diagnostics.status(enabled=True)["current_failures"]) == {"run"}
    diagnostics.recover("run")
    snapshot = diagnostics.status(enabled=True)
    assert snapshot["state"] == "idle"
    assert snapshot["last_failure"]["category"] == "provider_rate_limit"
    assert snapshot["failure_count"] == 2


@pytest.mark.parametrize(("kind", "phase"), [("market", "poll"), ("readiness", "check")])
def test_other_worker_failures_are_safe_and_recover(tmp_path, monkeypatch, kind, phase):
    if kind == "market":
        worker = MarketFreshnessWorker(tmp_path / "worker.db", Lock(), MarketFreshnessConfig(enabled=False))
        method, success = "_poll_once", 2
    else:
        worker = DataReadinessWorker(tmp_path / "worker.db", Lock(), DataReadinessConfig(enabled=False))
        method, success = "_tick_once", {"targets": 0, "ready": 0}
    monkeypatch.setattr(worker, method, fail(RateLimitExceeded("private token")))
    asyncio.run(worker.tick())
    state = worker.status()
    assert state["state"] == "blocked"
    assert state["current_failures"][phase]["category"] == "provider_rate_limit"
    assert "private token" not in json.dumps(state, default=str)
    monkeypatch.setattr(worker, method, lambda: success)
    asyncio.run(worker.tick())
    assert worker.status()["current_failures"] == {}
    assert worker.status()["failure_count"] == 1


@pytest.mark.parametrize("kind", ["ingestion", "market", "readiness"])
def test_stop_waits_for_owned_database_operation(tmp_path, monkeypatch, kind):
    started, release, closed = Event(), Event(), Event()
    if kind == "ingestion":
        worker = ingestion_worker(tmp_path)
        method, tick, result = "_run_once", worker.tick_run, 1
    elif kind == "market":
        worker = MarketFreshnessWorker(tmp_path / "worker.db", Lock(), MarketFreshnessConfig(enabled=False))
        method, tick, result = "_poll_once", worker.tick_poll, 1
    else:
        worker = DataReadinessWorker(tmp_path / "worker.db", Lock(), DataReadinessConfig(enabled=False))
        method, tick, result = "_tick_once", worker.tick, {"targets": 0, "ready": 0}

    def operation():
        connection = connect_database(tmp_path / "owned.db")
        try:
            started.set()
            assert release.wait(5)
            return result
        finally:
            connection.close()
            closed.set()

    monkeypatch.setattr(worker, method, operation)

    async def scenario():
        task = asyncio.create_task(tick())
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        stop = asyncio.create_task(worker.stop())
        try:
            await asyncio.sleep(0.02)
            assert not stop.done()
            assert not closed.is_set()
        finally:
            release.set()
        await stop
        with pytest.raises(asyncio.CancelledError):
            await task
        assert closed.is_set()
        assert worker.status()["current_failures"] == {}

    asyncio.run(scenario())


def test_stop_during_manual_schedule_does_not_begin_a_run(tmp_path, monkeypatch):
    worker = ingestion_worker(tmp_path)
    started, release = Event(), Event()
    runs = []

    def schedule():
        started.set()
        assert release.wait(5)
        return 2

    monkeypatch.setattr(worker, "_schedule_once", schedule)
    monkeypatch.setattr(worker, "_run_once", lambda: runs.append(1) or 1)

    async def scenario():
        tick = asyncio.create_task(worker.tick())
        assert await asyncio.to_thread(started.wait, 3)
        stop = asyncio.create_task(worker.stop())
        await asyncio.sleep(0)
        release.set()
        await stop
        assert await tick == {"scheduled_jobs": 2, "completed_jobs": 0}
        assert runs == []

    asyncio.run(scenario())


def test_overlapping_cycle_does_not_start_more_work(tmp_path, monkeypatch):
    worker = ingestion_worker(tmp_path)
    started, release = Event(), Event()
    calls = []

    def schedule():
        calls.append("schedule")
        started.set()
        assert release.wait(5)
        return 3

    monkeypatch.setattr(worker, "_schedule_once", schedule)
    monkeypatch.setattr(worker, "_run_once", lambda: calls.append("run") or 2)

    async def scenario():
        first = asyncio.create_task(worker.tick())
        assert await asyncio.to_thread(started.wait, 3)
        try:
            assert worker.status()["state"] == "running"
            assert await worker.tick() == {"scheduled_jobs": 0, "completed_jobs": 0}
            assert calls == ["schedule"]
        finally:
            release.set()
        assert await first == {"scheduled_jobs": 3, "completed_jobs": 2}

    asyncio.run(scenario())


def test_cancelled_stop_still_waits_for_manual_work(tmp_path, monkeypatch):
    worker = ingestion_worker(tmp_path)
    started, release, finished = Event(), Event(), Event()

    def operation():
        started.set()
        try:
            assert release.wait(5)
            return 1
        finally:
            finished.set()

    monkeypatch.setattr(worker, "_run_once", operation)

    async def scenario():
        tick = asyncio.create_task(worker.tick_run())
        assert await asyncio.to_thread(started.wait, 3)
        stop = asyncio.create_task(worker.stop())
        await asyncio.sleep(0)
        stop.cancel()
        await asyncio.sleep(0)
        stop.cancel()
        try:
            await asyncio.sleep(0.02)
            assert not stop.done()
            assert not finished.is_set()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await stop
        assert finished.is_set()
        assert await tick == 1

    asyncio.run(scenario())


def test_market_provider_failure_is_not_erased_by_a_successful_poll(tmp_path, monkeypatch):
    worker = MarketFreshnessWorker(
        tmp_path / "worker.db", Lock(), MarketFreshnessConfig(enabled=False),
    )
    subscriptions = [TickerSubscription("AAA", "AAA", None, "portfolio")]
    monkeypatch.setattr(worker, "_resolve_subscriptions", lambda: subscriptions)
    monkeypatch.setattr(worker, "_filter_stale_subscriptions", lambda items: items)
    monkeypatch.setattr(worker, "_stored_price_fallbacks", lambda items: {})
    provider = Mock()
    provider.fetch_price_daily.side_effect = RateLimitExceeded("secret provider token")
    monkeypatch.setattr(
        "dashboard.api.market_freshness_background.YahooPriceProvider", lambda: provider,
    )
    assert asyncio.run(worker.tick_poll()) == 0
    assert worker.status()["current_failures"]["provider"]["category"] == "provider_rate_limit"
    # No stale subscriptions means no provider success was observed: keep the failure.
    subscriptions.clear()
    asyncio.run(worker.tick_poll())
    assert worker.status()["state"] == "blocked"
    subscriptions.append(TickerSubscription("AAA", "AAA", None, "portfolio"))
    provider.fetch_price_daily.side_effect = None
    provider.fetch_price_daily.return_value = []
    asyncio.run(worker.tick_poll())
    assert worker.status()["current_failures"] == {}
    assert worker.status()["last_failure"]["phase"] == "provider"
