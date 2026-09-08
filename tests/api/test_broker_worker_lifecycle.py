"""Broker refresh cancellation must not outlive the API's database ownership."""

import asyncio
from threading import Event, Lock
from types import SimpleNamespace
from unittest.mock import Mock

import duckdb
import pytest

from dashboard.api.broker_background import BrokerBackgroundConfig, BrokerBackgroundWorker
from dashboard.db.db_conn import DB


def _expire_first_interval(monkeypatch, waiting_again):
    """Run one scheduled refresh immediately without changing production intervals."""
    original_wait_for = asyncio.wait_for
    first = True

    async def wait_for(awaitable, timeout):
        nonlocal first
        if first:
            first = False
            awaitable.close()
            raise asyncio.TimeoutError
        waiting_again.set()
        return await original_wait_for(awaitable, timeout)

    monkeypatch.setattr("dashboard.api.broker_background.asyncio.wait_for", wait_for)


def test_stop_waits_for_broker_refresh_and_closes_its_database(tmp_path, monkeypatch):
    async def scenario():
        started = asyncio.Event()
        release = Event()
        loop = asyncio.get_running_loop()
        opened = []
        _expire_first_interval(monkeypatch, asyncio.Event())

        def open_database(path):
            db = DB(path)
            opened.append(db)
            return db

        def sync_due(**kwargs):
            assert kwargs == {"max_users": 2, "min_age_hours": 3}
            loop.call_soon_threadsafe(started.set)
            if not release.wait(timeout=5):
                raise AssertionError("test did not release broker refresh")
            # The connection must remain usable until the owned thread returns.
            assert opened[0].conn.execute("SELECT 1").fetchone() == (1,)
            return SimpleNamespace(users_synced=0)

        monkeypatch.setattr("dashboard.api.broker_background.DB", open_database)
        monkeypatch.setattr(
            "dashboard.api.broker_background.DashboardManager",
            Mock(return_value=SimpleNamespace(broker_snaptrade_sync_due=sync_due)),
        )
        worker = BrokerBackgroundWorker(
            tmp_path / "broker.db", Lock(),
            BrokerBackgroundConfig(enabled=True, max_users=2, min_age_hours=3),
        )
        worker.start()
        try:
            await started.wait()
            stopping = asyncio.create_task(worker.stop())
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not stopping.done()
            release.set()
            await stopping
            assert worker._task is None
            assert not worker._diagnostics.active
            assert worker._diagnostics.last_error is None
            with pytest.raises(duckdb.ConnectionException, match="closed"):
                opened[0].conn.execute("SELECT 1")
        finally:
            release.set()
            await worker.stop()

    asyncio.run(scenario())


@pytest.mark.parametrize("failure_point", ["open", "manager", "sync"])
def test_broker_refresh_failure_is_contained_and_releases_connection(
    tmp_path, monkeypatch, failure_point,
):
    async def scenario():
        waiting_again = asyncio.Event()
        _expire_first_interval(monkeypatch, waiting_again)
        db = Mock()
        database_factory = Mock(return_value=db)
        manager = Mock()
        manager_factory = Mock(return_value=manager)
        failure = RuntimeError("broker test failure")
        if failure_point == "open":
            database_factory.side_effect = failure
        elif failure_point == "manager":
            manager_factory.side_effect = failure
        else:
            manager.broker_snaptrade_sync_due.side_effect = failure
        monkeypatch.setattr("dashboard.api.broker_background.DB", database_factory)
        monkeypatch.setattr("dashboard.api.broker_background.DashboardManager", manager_factory)
        worker = BrokerBackgroundWorker(
            tmp_path / "unused.db", Lock(), BrokerBackgroundConfig(enabled=True),
        )
        worker.start()
        try:
            await waiting_again.wait()
            assert worker._task is not None and not worker._task.done()
            assert worker._diagnostics.current_failures["sync"].category == "unexpected"
            assert worker._diagnostics.status(enabled=True)["failure_count"] == 1
            database_factory.assert_called_once_with(worker.db_path)
            if failure_point == "open":
                db.conn.close.assert_not_called()
                manager_factory.assert_not_called()
            else:
                db.conn.close.assert_called_once_with()
        finally:
            await worker.stop()

    asyncio.run(scenario())


def test_broker_loop_failure_does_not_break_shutdown(tmp_path, monkeypatch):
    async def scenario():
        async def failed_wait(awaitable, timeout):
            awaitable.close()
            raise RuntimeError("unexpected timer failure")

        monkeypatch.setattr("dashboard.api.broker_background.asyncio.wait_for", failed_wait)
        database_factory = Mock()
        monkeypatch.setattr("dashboard.api.broker_background.DB", database_factory)
        worker = BrokerBackgroundWorker(
            tmp_path / "unused.db", Lock(), BrokerBackgroundConfig(enabled=True),
        )
        worker.start()
        await worker._task
        assert worker._diagnostics.current_failures["loop"].category == "unexpected"
        await worker.stop()
        assert worker._task is None
        database_factory.assert_not_called()

    asyncio.run(scenario())
