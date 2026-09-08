"""S1 regressions for import isolation and the single-process DuckDB boundary."""

import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import AsyncMock, Mock

import duckdb
import pytest

from dashboard.db.db_conn import DB, DatabaseConnectionPool, connect_database


def test_importing_api_never_opens_default_database(tmp_path):
    environment = dict(os.environ, DASHBOARD_DB_PATH=str(tmp_path / "must-not-exist.db"))
    result = subprocess.run(
        [sys.executable, "-c", (
            "from unittest.mock import patch; "
            "import dashboard.db.db_conn as db; "
            "guard = patch.object(db, 'connect_database', side_effect=AssertionError('DB opened')); "
            "guard.start(); import dashboard.api.app"
        )],
        env=environment, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "must-not-exist.db").exists()


def test_deferred_app_initializes_at_startup_and_releases_database(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from dashboard.api.app import create_app

    for name in (
        "INGESTION_BACKGROUND_ENABLED", "MARKET_FRESHNESS_ENABLED",
        "DATA_READINESS_WORKER_ENABLED", "BROKER_SYNC_BACKGROUND_ENABLED",
        "BROKER_SYNC_ON_STARTUP", "BROKER_SYNC_ON_SERVER_STARTUP",
    ):
        monkeypatch.setenv(name, "false")
    path = tmp_path / "deferred.db"
    app = create_app(path, initialize_on_startup=True)
    assert not path.exists()
    with TestClient(app) as client:
        assert client.get("/api/v1/health").json()["database"] == "connected"
        assert path.exists()
    assert app.state.db_connection_pool is None
    # A separate process can acquire the database only after the pool is closed.
    result = subprocess.run(
        [sys.executable, "-c", (
            "import sys; from dashboard.db.db_conn import connect_database; "
            "c=connect_database(sys.argv[1]); "
            "assert c.execute('select count(*) from portfolio').fetchone()==(0,); c.close()"
        ), str(path)], capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_second_process_fails_with_actionable_message_without_changing_data(tmp_path):
    path = tmp_path / "owned.db"
    connection = connect_database(path)
    try:
        connection.execute("CREATE TABLE sentinel(value INTEGER)")
        connection.execute("INSERT INTO sentinel VALUES (42)")
        result = subprocess.run(
            [sys.executable, "-c", "\n".join([
                "import sys",
                "from dashboard.db.db_conn import connect_database, DatabaseInUseError",
                "try:",
                "    connect_database(sys.argv[1])",
                "except DatabaseInUseError as exc:",
                "    print(str(exc))",
                "else:",
                "    raise AssertionError('second process unexpectedly opened writer DB')",
            ]), str(path)], capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert "Use the running app" in result.stdout
        assert str(path) not in result.stdout
        assert connection.execute("SELECT * FROM sentinel").fetchall() == [(42,)]
    finally:
        connection.close()


def test_partial_pool_failure_closes_all_opened_connections(monkeypatch):
    first, second = Mock(), Mock()
    monkeypatch.setattr(
        "dashboard.db.db_conn.connect_database",
        Mock(side_effect=[first, second, RuntimeError("pool setup failed")]),
    )
    with pytest.raises(RuntimeError, match="pool setup failed"):
        DatabaseConnectionPool(Path("unused.db"), 4)
    first.close.assert_called_once_with()
    second.close.assert_called_once_with()


def test_connection_setup_failure_releases_database(monkeypatch):
    connection = Mock()
    connection.execute.side_effect = RuntimeError("configuration failed")
    monkeypatch.setattr(duckdb, "connect", Mock(return_value=connection))
    with pytest.raises(RuntimeError, match="configuration failed"):
        connect_database("unused.db")
    connection.close.assert_called_once_with()


def test_schema_initialization_failure_closes_connection(tmp_path, monkeypatch):
    from dashboard.api.app import create_app

    db = Mock(spec=DB)
    db.conn = Mock()
    monkeypatch.setattr("dashboard.api.app.DB", Mock(return_value=db))
    monkeypatch.setattr("dashboard.api.app.init_db", Mock(side_effect=RuntimeError("schema")))
    with pytest.raises(RuntimeError, match="schema"):
        create_app(tmp_path / "unused.db")
    db.conn.close.assert_called_once_with()


def test_non_lock_io_error_is_not_misreported(monkeypatch):
    monkeypatch.setattr(duckdb, "connect", Mock(side_effect=duckdb.IOException("disk failure")))
    with pytest.raises(duckdb.IOException, match="disk failure"):
        connect_database("unused.db")


def test_start_failure_stops_started_workers_and_closes_pool(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from dashboard.api.app import create_app

    app = create_app(tmp_path / "startup-failure.db")
    pool = Mock()
    monkeypatch.setattr("dashboard.api.app.DatabaseConnectionPool", Mock(return_value=pool))
    monkeypatch.setattr("dashboard.api.app._run_startup_broker_sync_if_enabled", Mock())
    worker = app.state.ingestion_background_worker
    market = app.state.market_freshness_worker
    monkeypatch.setattr(worker, "start", Mock())
    monkeypatch.setattr(worker, "stop", AsyncMock())
    monkeypatch.setattr(market, "start", Mock(side_effect=RuntimeError("startup failed")))
    monkeypatch.setattr(market, "stop", AsyncMock())
    with pytest.raises(RuntimeError, match="startup failed"):
        with TestClient(app):
            pass
    worker.stop.assert_awaited_once()
    market.stop.assert_awaited_once()
    pool.close.assert_called_once_with()
    assert app.state.db_connection_pool is None


def test_stop_failure_still_closes_pool_and_other_workers(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from dashboard.api.app import create_app

    app = create_app(tmp_path / "stop-failure.db")
    pool = Mock()
    monkeypatch.setattr("dashboard.api.app.DatabaseConnectionPool", Mock(return_value=pool))
    monkeypatch.setattr("dashboard.api.app._run_startup_broker_sync_if_enabled", Mock())
    workers = (
        app.state.ingestion_background_worker, app.state.market_freshness_worker,
        app.state.data_readiness_worker, app.state.broker_background_worker,
    )
    for worker in workers:
        monkeypatch.setattr(worker, "start", Mock())
        monkeypatch.setattr(worker, "stop", AsyncMock())
    workers[-1].stop.side_effect = RuntimeError("stop failed")
    with pytest.raises(RuntimeError, match="stop failed"):
        with TestClient(app):
            pass
    for worker in workers:
        worker.stop.assert_awaited_once()
    pool.close.assert_called_once_with()
    assert app.state.db_connection_pool is None
