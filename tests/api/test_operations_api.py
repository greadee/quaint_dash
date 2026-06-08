from fastapi.testclient import TestClient

from dashboard.api.app import create_app
from dashboard.brokers.models import BrokerAccount, BrokerConnection
from dashboard.brokers.repository import BrokerSyncRepository
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
