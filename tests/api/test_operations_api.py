import asyncio
from datetime import date, timedelta
from threading import Lock

from fastapi.testclient import TestClient

from dashboard.api.ingestion_background import IngestionBackgroundConfig, IngestionBackgroundWorker
from dashboard.api.app import create_app
from dashboard.api.services import CommandApiService
from dashboard.brokers.models import BrokerAccount, BrokerConnection, BrokerPosition
from dashboard.brokers.repository import BrokerSyncRepository
from dashboard.brokers.secrets import LocalSecretCipher
from dashboard.db.db_conn import DB


def test_broker_lists_redacted_connections_and_accounts(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    repo = BrokerSyncRepository(db.conn)
    repo.upsert_connection(
        BrokerConnection(
            provider="snaptrade",
            provider_connection_id="conn-1",
            institution_name="Test Bank",
            status="active",
            raw_payload={"secret": "must-not-leak"},
        )
    )
    repo.upsert_account(
        BrokerAccount(
            provider="snaptrade",
            provider_account_id="acct-1",
            provider_connection_id="conn-1",
            account_name="Investing",
            account_type="margin",
            currency="CAD",
            balance=1000,
            raw_payload={"secret": "must-not-leak"},
        )
    )
    db.conn.close()

    with TestClient(app) as client:
        connections = client.get("/api/v1/brokers/connections")
        accounts = client.get("/api/v1/brokers/accounts")

    assert connections.status_code == 200
    assert connections.json()[0]["institution_name"] == "Test Bank"
    assert "raw_payload" not in connections.text
    assert accounts.json()[0]["provider_account_id"] == "acct-1"
    assert "secret" not in accounts.text


def test_broker_accounts_use_synced_positions_when_balance_is_unavailable(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    repo = BrokerSyncRepository(db.conn)
    repo.upsert_account(
        BrokerAccount(
            provider="snaptrade",
            provider_account_id="acct-1",
            provider_connection_id="conn-1",
            account_name="TFSA",
            account_type="registered",
            currency=None,
            balance=None,
            raw_payload={"balance": {"total": {"amount": 0.0, "currency": "CAD"}}},
        )
    )
    repo.upsert_position_snapshot(
        BrokerPosition(
            provider="snaptrade",
            provider_account_id="acct-1",
            provider_position_id="pos-1",
            symbol="AAPL",
            description="Apple Inc.",
            quantity=2,
            market_value=500.0,
            currency="CAD",
            as_of_date=date(2026, 1, 5),
        )
    )
    repo.upsert_position_snapshot(
        BrokerPosition(
            provider="snaptrade",
            provider_account_id="acct-1",
            provider_position_id="pos-2",
            symbol="MSFT",
            description="Microsoft",
            quantity=1,
            market_value=250.0,
            currency="CAD",
            as_of_date=date(2026, 1, 5),
        )
    )
    db.conn.close()

    with TestClient(app) as client:
        accounts = client.get("/api/v1/brokers/accounts")

    assert accounts.status_code == 200
    account = accounts.json()[0]
    assert account["balance"] == 750.0
    assert account["currency"] == "CAD"


def test_broker_accounts_hide_closed_and_archived_provider_accounts(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    repo = BrokerSyncRepository(db.conn)
    for account_id, status in [
        ("acct-open", "open"),
        ("acct-closed", "closed"),
        ("acct-archived", "archived"),
    ]:
        repo.upsert_account(
            BrokerAccount(
                provider="snaptrade",
                provider_account_id=account_id,
                provider_connection_id="conn-1",
                account_name=account_id,
                account_type="registered",
                currency="CAD",
                balance=100.0,
                raw_payload={"status": status},
            )
        )
    db.conn.close()

    with TestClient(app) as client:
        accounts = client.get("/api/v1/brokers/accounts")

    assert accounts.status_code == 200
    assert [account["provider_account_id"] for account in accounts.json()] == ["acct-open"]


def test_mapping_broker_account_projects_positions_into_portfolio(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Broker')")
    repo = BrokerSyncRepository(db.conn)
    repo.upsert_account(
        BrokerAccount(
            provider="snaptrade",
            provider_account_id="acct-1",
            provider_connection_id="conn-1",
            account_name="TFSA",
            account_type="registered",
            currency="CAD",
            balance=None,
        )
    )
    repo.upsert_position_snapshot(
        BrokerPosition(
            provider="snaptrade",
            provider_account_id="acct-1",
            provider_position_id="pos-1",
            symbol="{'SYMBOL': 'AAPL', 'DESCRIPTION': 'Apple Inc.', 'CURRENCY': {'CODE': 'USD'}}",
            description=None,
            quantity=3,
            market_value=450.0,
            currency="{'CODE': 'USD'}",
            as_of_date=date(2026, 1, 5),
        )
    )
    db.conn.close()

    with TestClient(app) as client:
        mapping = client.post("/api/v1/brokers/accounts/acct-1/mapping", json={"portfolio_id": 1})
        positions = client.get("/api/v1/portfolios/1/positions")

    assert mapping.status_code == 200
    assert mapping.json()["result"]["upserted_positions"] == 1
    assert positions.json()[0]["asset_id"] == "AAPL"
    assert positions.json()[0]["name"] == "Apple Inc."
    assert positions.json()[0]["currency"] == "USD"
    assert positions.json()[0]["quantity"] == 3
    assert positions.json()[0]["book_cost"] == 450


def test_fhsa_broker_account_uses_cash_plus_current_snapshot_holdings(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'FHSA')")
    repo = BrokerSyncRepository(db.conn)
    repo.upsert_account(
        BrokerAccount(
            provider="snaptrade",
            provider_account_id="fhsa-1",
            provider_connection_id="conn-1",
            account_name="FHSA",
            account_type="registered",
            currency="CAD",
            balance=None,
            raw_payload={
                "type": "FHSA",
                "cash": {"amount": 15.41, "currency": "CAD"},
                "balance": {"total": {"amount": 2595.09, "currency": "CAD"}},
            },
        )
    )
    for symbol, shares, value in [
        ("CAGE", 90.3772, 2067.83),
        ("CLSA", 29.0, 511.85),
        ("OLD", 0.0, 0.0),
    ]:
        repo.upsert_position_snapshot(
            BrokerPosition(
                provider="snaptrade",
                provider_account_id="fhsa-1",
                provider_position_id=f"pos-{symbol}",
                symbol=symbol,
                description=symbol,
                quantity=shares,
                market_value=value,
                currency="CAD",
                as_of_date=date(2026, 6, 18),
            )
        )
    db.conn.close()

    with TestClient(app) as client:
        accounts = client.get("/api/v1/brokers/accounts")
        mapping = client.post("/api/v1/brokers/accounts/fhsa-1/mapping", json={"portfolio_id": 1})
        positions = client.get("/api/v1/portfolios/1/positions")

    assert accounts.status_code == 200
    account = accounts.json()[0]
    assert account["account_name"] == "FHSA"
    assert account["cash_balance"] == 15.41
    assert account["holdings_value"] == 2579.68
    assert abs(account["total_value"] - 2595.09) <= 0.01
    assert abs(account["balance"] - 2595.09) <= 0.01
    assert account["position_count"] == 2
    assert account["latest_position_date"] == "2026-06-18"

    assert mapping.status_code == 200
    assert mapping.json()["result"]["upserted_positions"] == 2
    mapped = positions.json()
    assert [item["asset_id"] for item in mapped] == ["CAGE", "CLSA"]
    mapped_value = sum(item["market_value"] for item in mapped)
    assert abs(mapped_value - 2579.68) / 2579.68 <= 0.001


def test_can_save_existing_snaptrade_user_without_returning_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("QUAINT_BROKER_SECRET_KEY", "local-test-secret")
    db_path = tmp_path / "api.db"
    app = create_app(db_path)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/brokers/snaptrade/existing-user",
            json={
                "user_key": "local-user",
                "provider_user_id": "snaptrade-user",
                "user_secret": "snaptrade-secret",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "provider": "snaptrade",
        "user_key": "local-user",
        "provider_user_id": "snaptrade-user",
        "status": "active",
    }
    assert "snaptrade-secret" not in response.text

    db = DB(db_path)
    stored = BrokerSyncRepository(db.conn).get_broker_user(
        "snaptrade",
        "local-user",
        LocalSecretCipher("local-test-secret"),
    )
    assert stored is not None
    assert stored.user_secret == "snaptrade-secret"


def test_ingestion_job_list_and_bounded_empty_run(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute(
        "INSERT INTO asset(asset_id, symbol, asset_type, ccy) VALUES ('AAPL', 'AAPL', 'stock', 'USD')"
    )
    db.conn.execute(
        """
        INSERT INTO ingestion_job(
            job_id, asset_id, domain, job_type, dataset, status, priority
        )
        VALUES (1, 'AAPL', 'market', 'refresh', 'daily_prices', 'pending', 10)
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        jobs = client.get("/api/v1/ingestion/jobs?status=pending&domain=market")
        invalid = client.post("/api/v1/ingestion/run", json={"domain": "all", "max_jobs": 0})

    assert jobs.status_code == 200
    assert jobs.json()[0]["dataset"] == "daily_prices"
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"


def test_ingestion_background_status_defaults_disabled(tmp_path):
    app = create_app(tmp_path / "api.db")

    with TestClient(app) as client:
        response = client.get("/api/v1/ingestion/background/status")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "running": False,
        "last_schedule_at": None,
        "last_schedule_count": None,
        "last_run_at": None,
        "last_completed_count": None,
        "last_error": None,
        "schedule_interval_seconds": 3600,
        "run_interval_seconds": 300,
        "max_jobs_per_tick": 2,
        "max_assets_per_schedule": 25,
        "years": 10,
        "prices_only": False,
    }


def test_ingestion_background_disabled_state_does_not_schedule_or_run(tmp_path, monkeypatch):
    calls: list[str] = []

    def fail_schedule(self, *args, **kwargs):
        calls.append("schedule")
        raise AssertionError("disabled worker should not schedule")

    def fail_run(self, *args, **kwargs):
        calls.append("run")
        raise AssertionError("disabled worker should not run")

    monkeypatch.setattr(CommandApiService, "schedule_due_routine_ingestion_jobs", fail_schedule)
    monkeypatch.setattr(CommandApiService, "run_ingestion_jobs", fail_run)

    worker = IngestionBackgroundWorker(
        tmp_path / "api.db",
        Lock(),
        IngestionBackgroundConfig(enabled=False),
    )
    worker.start()

    assert worker.status()["running"] is False
    assert calls == []


def test_ingestion_background_start_stop_endpoints_toggle_worker(tmp_path, monkeypatch):
    async def idle_loop(self):
        if self._stop_event is not None:
            await self._stop_event.wait()

    monkeypatch.setattr(IngestionBackgroundWorker, "_run_loop", idle_loop)
    app = create_app(tmp_path / "api.db")

    with TestClient(app) as client:
        initial = client.get("/api/v1/ingestion/background/status")
        started = client.post("/api/v1/ingestion/background/start")
        running = client.get("/api/v1/ingestion/background/status")
        stopped = client.post("/api/v1/ingestion/background/stop")

    assert initial.json()["enabled"] is False
    assert initial.json()["running"] is False
    assert started.status_code == 200
    assert started.json()["result"]["enabled"] is True
    assert running.json()["enabled"] is True
    assert running.json()["running"] is True
    assert stopped.status_code == 200
    assert stopped.json()["result"]["enabled"] is False
    assert stopped.json()["result"]["running"] is False


def test_ingestion_background_enabled_tick_uses_capped_schedule_and_run(tmp_path, monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake_schedule(self, **kwargs):
        calls.append(("schedule", kwargs))
        return 4

    def fake_run(self, **kwargs):
        calls.append(("run", kwargs))
        return 2

    monkeypatch.setattr(CommandApiService, "schedule_due_routine_ingestion_jobs", fake_schedule)
    monkeypatch.setattr(CommandApiService, "run_ingestion_jobs", fake_run)

    worker = IngestionBackgroundWorker(
        tmp_path / "api.db",
        Lock(),
        IngestionBackgroundConfig(
            enabled=True,
            max_assets_per_schedule=7,
            years=3,
            prices_only=True,
            max_jobs_per_tick=2,
        ),
    )

    assert asyncio.run(worker.tick_schedule()) == 4
    assert asyncio.run(worker.tick_run()) == 2

    assert calls == [
        (
            "schedule",
            {"max_assets": 7, "years": 3, "prices_only": True},
        ),
        ("run", {"domain": "all", "max_jobs": 2}),
    ]
    status = worker.status()
    assert status["last_schedule_count"] == 4
    assert status["last_completed_count"] == 2
    assert status["last_error"] is None


def test_ingestion_background_tick_endpoint_runs_one_bounded_cycle(tmp_path, monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake_schedule(self, **kwargs):
        calls.append(("schedule", kwargs))
        return 3

    def fake_run(self, **kwargs):
        calls.append(("run", kwargs))
        return 2

    monkeypatch.setattr(CommandApiService, "schedule_due_routine_ingestion_jobs", fake_schedule)
    monkeypatch.setattr(CommandApiService, "run_ingestion_jobs", fake_run)
    app = create_app(tmp_path / "api.db")

    with TestClient(app) as client:
        response = client.post("/api/v1/ingestion/background/tick")
        status = client.get("/api/v1/ingestion/background/status")

    assert response.status_code == 200
    assert response.json()["result"] == {"scheduled_jobs": 3, "completed_jobs": 2}
    assert calls == [
        (
            "schedule",
            {"max_assets": 25, "years": 10, "prices_only": False},
        ),
        ("run", {"domain": "all", "max_jobs": 2}),
    ]
    assert status.json()["last_schedule_count"] == 3
    assert status.json()["last_completed_count"] == 2


def test_ingestion_background_errors_are_captured(tmp_path, monkeypatch):
    def fail_schedule(self, **kwargs):
        raise RuntimeError("provider missing")

    monkeypatch.setattr(CommandApiService, "schedule_due_routine_ingestion_jobs", fail_schedule)

    worker = IngestionBackgroundWorker(
        tmp_path / "api.db",
        Lock(),
        IngestionBackgroundConfig(enabled=True),
    )

    assert asyncio.run(worker.tick_schedule()) == 0
    assert worker.status()["last_error"] == "provider missing"


def test_ingestion_readiness_reports_portfolio_ticker_metric_inputs(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    start = date(2025, 1, 1)

    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Core')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, shares_outstanding)
        VALUES
            ('AAPL', 'AAPL', 'stock', 'USD', 1000000),
            ('MSFT', 'MSFT', 'stock', 'USD', NULL)
        """
    )
    db.conn.execute(
        """
        INSERT INTO portfolio_ticker(portfolio_id, asset_id, is_active, source)
        VALUES
            (1, 'AAPL', TRUE, 'position'),
            (1, 'MSFT', TRUE, 'position')
        """
    )
    for index in range(252):
        price_date = start + timedelta(days=index)
        db.conn.execute(
            """
            INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
            VALUES ('AAPL', ?, 100, 100, 'test')
            """,
            [price_date],
        )
    db.conn.execute(
        """
        INSERT INTO asset_sync_state(
            asset_id, domain, dataset, backfill_status, last_successful_date, last_successful_at
        )
        VALUES
            ('AAPL', 'market', 'dividends', 'done', DATE '2026-01-01', now()),
            ('AAPL', 'market', 'splits', 'done', DATE '2026-01-01', now())
        """
    )
    for statement_type in ["income", "balance", "cashflow"]:
        db.conn.execute(
            """
            INSERT INTO financial_statement(
                asset_id, statement_type, year, quarter, period_end_date, report_date, data_json, source
            )
            VALUES ('AAPL', ?, 2026, 1, DATE '2026-03-31', DATE '2026-04-15', '{}', 'test')
            """,
            [statement_type],
        )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/ingestion/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["ready_count"] == 1

    by_asset = {item["asset_id"]: item for item in payload["items"]}
    assert by_asset["AAPL"]["ready"] is True
    assert by_asset["AAPL"]["missing"] == []
    assert by_asset["MSFT"]["ready"] is False
    assert "Projection price history" in by_asset["MSFT"]["missing"]
    assert "Cash flow statements" not in by_asset["MSFT"]["missing"]


def test_ingestion_readiness_treats_successful_financial_statement_sync_as_checked(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    start = date(2025, 1, 1)

    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Core')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, shares_outstanding)
        VALUES ('AAPL', 'AAPL', 'stock', 'USD', 1000000)
        """
    )
    db.conn.execute(
        """
        INSERT INTO portfolio_ticker(portfolio_id, asset_id, is_active, source)
        VALUES (1, 'AAPL', TRUE, 'position')
        """
    )
    for index in range(252):
        price_date = start + timedelta(days=index)
        db.conn.execute(
            """
            INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
            VALUES ('AAPL', ?, 100, 100, 'test')
            """,
            [price_date],
        )
    db.conn.execute(
        """
        INSERT INTO asset_sync_state(
            asset_id, domain, dataset, backfill_status, last_successful_date, last_successful_at
        )
        VALUES
            ('AAPL', 'market', 'dividends', 'done', DATE '2026-01-01', now()),
            ('AAPL', 'market', 'splits', 'done', DATE '2026-01-01', now()),
            ('AAPL', 'corporate', 'financial_statements', 'done', DATE '2026-01-01', now())
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/ingestion/readiness")

    assert response.status_code == 200
    item = response.json()["items"][0]
    by_requirement = {requirement["key"]: requirement for requirement in item["requirements"]}
    assert item["ready"] is True
    assert item["missing"] == []
    assert by_requirement["income_statements"]["ready"] is True
    assert by_requirement["income_statements"]["detail"] == "coverage checked; no statements returned"


def test_stock_ranking_readiness_reports_factor_gaps(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Core')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name, track)
        VALUES ('AAPL', 'AAPL', 'stock', 'USD', 'Apple Inc.', TRUE)
        """
    )
    db.conn.execute(
        """
        INSERT INTO portfolio_ticker(portfolio_id, asset_id, is_active, source)
        VALUES (1, 'AAPL', TRUE, 'position')
        """
    )
    for index in range(70):
        db.conn.execute(
            """
            INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
            VALUES ('AAPL', DATE '2026-01-01' + CAST(? AS INTEGER), ?, ?, 'test')
            """,
            [index, 100 + index, 100 + index],
        )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/ingestion/ranking-readiness?universe=tracked&limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["ready_count"] == 1
    item = payload["items"][0]
    by_requirement = {requirement["key"]: requirement for requirement in item["requirements"]}
    assert by_requirement["share_price_momentum"]["ready"] is True
    assert by_requirement["news_sentiment"]["ready"] is True
    assert by_requirement["retail_sentiment"]["ready"] is True
    assert by_requirement["earnings_momentum"]["ready"] is True
    assert by_requirement["institutional_buying"]["ready"] is True
    assert item["missing"] == []


def test_ranking_schedule_queues_missing_catalog_stock_inputs(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute(
        """
        INSERT INTO stock_catalog(asset_id, symbol, exchange_code, ccy, name)
        VALUES ('CATONLY', 'CATONLY', 'NASDAQ', 'USD', 'Catalog Only')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ingestion/schedule",
            json={
                "pipeline": "ranking",
                "asset_id": "CATONLY",
                "ranking_factor": "news_sentiment",
                "ranking_universe": "all",
                "missing_only": True,
                "max_assets": 1,
                "years": 3,
                "prices_only": False,
            },
        )

    assert response.status_code == 200
    assert response.json()["result"] == {"scheduled_jobs": 2}

    db = DB(db_path)
    asset = db.conn.execute(
        "SELECT asset_id, symbol, track FROM asset WHERE asset_id = 'CATONLY'"
    ).fetchone()
    jobs = db.conn.execute(
        """
        SELECT job_type, dataset, status
        FROM ingestion_job
        WHERE asset_id = 'CATONLY'
        ORDER BY job_type
        """
    ).fetchall()
    db.conn.close()
    assert asset == ("CATONLY", "CATONLY", False)
    assert jobs == [
        ("news_rss_refresh", "news", "pending"),
        ("sentiment_daily_aggregate", "sentiment_daily", "pending"),
    ]


def test_retry_failed_ingestion_jobs_requeues_bounded_failures(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute(
        "INSERT INTO asset(asset_id, symbol, asset_type, ccy) VALUES ('AAPL', 'AAPL', 'stock', 'USD')"
    )
    db.conn.execute(
        """
        INSERT INTO ingestion_job(
            job_id, asset_id, domain, job_type, dataset, status, priority, error_message
        )
        VALUES
            (1, 'AAPL', 'market', 'refresh', 'dividends', 'failed', 10, 'old failure'),
            (2, 'AAPL', 'market', 'refresh', 'splits', 'failed', 10, 'old failure')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        retry = client.post(
            "/api/v1/ingestion/retry-failed",
            json={"domain": "market", "max_jobs": 1},
        )
        jobs = client.get("/api/v1/ingestion/jobs?domain=market")

    assert retry.status_code == 200
    assert retry.json()["result"] == {"retried_jobs": 1}
    statuses = {row["job_id"]: row["status"] for row in jobs.json()}
    assert statuses == {1: "pending", 2: "failed"}


def test_clear_ingestion_history_removes_jobs_and_sync_state(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute(
        "INSERT INTO asset(asset_id, symbol, asset_type, ccy) VALUES ('AAPL', 'AAPL', 'stock', 'USD')"
    )
    db.conn.execute(
        """
        INSERT INTO ingestion_job(
            job_id, asset_id, domain, job_type, dataset, status, priority
        )
        VALUES (1, 'AAPL', 'market', 'refresh', 'price_daily', 'done', 10)
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_sync_state(asset_id, domain, dataset, last_successful_at)
        VALUES ('AAPL', 'market', 'price_daily', now())
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        cleared = client.delete("/api/v1/ingestion/jobs")
        jobs = client.get("/api/v1/ingestion/jobs")

    db = DB(db_path)
    state_count = db.conn.execute("SELECT COUNT(*) FROM asset_sync_state").fetchone()[0]
    asset_count = db.conn.execute("SELECT COUNT(*) FROM asset").fetchone()[0]
    db.conn.close()

    assert cleared.status_code == 200
    assert cleared.json()["result"] == {"deleted_jobs": 1, "deleted_sync_states": 1}
    assert jobs.json() == []
    assert state_count == 0
    assert asset_count == 1
