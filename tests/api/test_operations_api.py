from datetime import date

from fastapi.testclient import TestClient

from dashboard.api.app import create_app
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
