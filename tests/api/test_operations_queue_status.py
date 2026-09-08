from datetime import datetime, timedelta, timezone

import duckdb
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from dashboard.api.dependencies import get_connection
from dashboard.api.routes import router
from dashboard.application.operations import OperationsQueueQueries
from dashboard.db.operations import OperationsQueueRepository


@pytest.fixture
def queue_connection():
    """Only synthetic queue rows; no app startup, workers, or provider access."""
    with duckdb.connect(":memory:") as connection:
        connection.execute("""
            CREATE TABLE ingestion_job (
                job_id BIGINT, asset_id TEXT DEFAULT 'TEST', domain TEXT DEFAULT 'market',
                job_type TEXT DEFAULT 'refresh', dataset TEXT DEFAULT 'price_daily',
                status TEXT, priority INTEGER DEFAULT 0, requested_start_date DATE,
                requested_end_date DATE, attempt_count INTEGER DEFAULT 0,
                error_message TEXT, terminal_reason TEXT,
                created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP DEFAULT current_timestamp
            )
        """)
        yield connection


def queue_client(connection):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_connection] = lambda: connection
    return TestClient(app)


def test_queue_status_counts_whole_backlog_and_reads_without_mutation(queue_connection):
    queue_connection.execute("""
        INSERT INTO ingestion_job (job_id, status, created_at)
        SELECT range, 'pending', TIMESTAMP '2026-09-01 12:00:00' FROM range(701)
    """)
    queue_connection.execute("""
        INSERT INTO ingestion_job (job_id, status, created_at) VALUES
            (702, 'running', '2026-09-02 12:00:00'),
            (703, 'done', '2020-01-01'),
            (704, 'superseded', '2020-01-01')
    """)
    before = queue_connection.execute("SELECT * FROM ingestion_job ORDER BY job_id").fetchall()
    observed_at = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
    status = OperationsQueueQueries(
        OperationsQueueRepository(queue_connection), clock=lambda: observed_at,
    ).queue_status()

    assert status["pending_count"] == 701
    assert status["running_count"] == 1
    assert status["dead_letter_count"] == status["failed_count"] == 0
    assert status["oldest_backlog_at"] == datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
    assert status["oldest_backlog_age_seconds"] == 6 * 86400
    assert status["affected_data_products"] == ["Prices and market history"]
    with queue_client(queue_connection) as client:
        response = client.get("/api/v1/ingestion/queue/status")
    assert response.status_code == 200
    assert response.json()["pending_count"] == 701
    assert response.json()["oldest_backlog_at"].endswith("Z")
    assert response.json()["observed_at"].endswith("Z")
    assert queue_connection.execute("SELECT * FROM ingestion_job ORDER BY job_id").fetchall() == before


def test_queue_failures_group_safe_messages_without_leaking_payloads(queue_connection):
    queue_connection.executemany("""
        INSERT INTO ingestion_job
            (job_id, status, domain, dataset, error_message, terminal_reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?, '2026-01-01')
    """, [
        (1, "dead_letter", "corporate", "financial_statements", "FMP rate limit exceeded token=secret-one", "max attempts",),
        (2, "dead_letter", "corporate", "financial_statements", "FMP HTTP error 429 https://private.test/key", None,),
        (3, "failed", "sentiment", "x", "X provider requires X_BEARER_TOKEN=secret-two", None,),
        (4, "dead_letter", "PRIVATE_DOMAIN", "PRIVATE_DATASET", "raw stack traceback password=secret-three", None,),
    ])
    with queue_client(queue_connection) as client:
        response = client.get("/api/v1/ingestion/queue/status")
    payload = response.json()
    assert response.status_code == 200
    assert payload["dead_letter_count"] == 3
    assert payload["failed_count"] == 1
    assert payload["oldest_backlog_at"] is None
    assert payload["oldest_backlog_age_seconds"] is None
    assert [(group["provider"], group["error_category"], group["count"]) for group in payload["dead_letter_groups"]] == [
        ("fmp", "provider_rate_limit", 2), ("unknown", "unexpected", 1),
    ]
    assert payload["failed_groups"][0]["provider"] == "x"
    assert payload["failed_groups"][0]["error_category"] == "provider_configuration"
    assert payload["affected_data_products"] == [
        "Earnings and financial statements", "Other data products", "Retail sentiment",
    ]
    for private in ("secret-", "private.test", "PRIVATE_", "traceback", "X_BEARER_TOKEN"):
        assert private not in response.text


def test_empty_queue_is_zero_without_inventing_age(queue_connection):
    with queue_client(queue_connection) as client:
        response = client.get("/api/v1/ingestion/queue/status")
    payload = response.json()
    assert response.status_code == 200
    assert [payload[field] for field in ("pending_count", "running_count", "failed_count", "dead_letter_count")] == [0] * 4
    assert payload["oldest_backlog_age_seconds"] is None
    assert payload["dead_letter_groups"] == payload["failed_groups"] == payload["affected_data_products"] == []


def test_failed_queue_read_returns_unavailable_not_zero(queue_connection, monkeypatch, caplog):
    def fail_read(self):
        raise RuntimeError("private database path and token=keep-in-logs")

    monkeypatch.setattr(OperationsQueueRepository, "status_groups", fail_read)
    with queue_client(queue_connection) as client:
        response = client.get("/api/v1/ingestion/queue/status")
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Queue diagnostics are unavailable. Check local database access and refresh status.",
    }
    assert "pending_count" not in response.text
    assert "keep-in-logs" not in response.text
    assert "keep-in-logs" in caplog.text


def test_job_list_redacts_display_errors_and_preserves_stored_errors(queue_connection):
    raw_error = "FMP HTTP error 402 key=private-key https://private.test/account"
    queue_connection.execute("""
        INSERT INTO ingestion_job (job_id, status, error_message, created_at)
        VALUES (1, 'failed', ?, '2026-09-01')
    """, [raw_error])
    with queue_client(queue_connection) as client:
        response = client.get("/api/v1/ingestion/jobs")
    assert response.status_code == 200
    assert response.json()[0]["error_message"] == "Provider access or configuration needs attention."
    assert response.json()[0]["status"] == "failed"
    assert "private" not in response.text
    assert queue_connection.execute("SELECT error_message FROM ingestion_job").fetchone()[0] == raw_error


@pytest.mark.parametrize("offset_hours", [None, -6, 9])
def test_queue_clock_and_timestamp_are_normalized_to_utc(offset_hours):
    class Source:
        def status_groups(self):
            return [{
                "status": "pending", "domain": "market", "dataset": "price_daily", "count": 1,
                "oldest_created_at": datetime(2026, 9, 7, 12),
                "error_message": None, "terminal_reason": None,
            }]

    clock = datetime(2026, 9, 7, 13)
    if offset_hours is not None:
        clock = clock.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=offset_hours)))
    status = OperationsQueueQueries(Source(), clock=lambda: clock).queue_status()
    assert status["oldest_backlog_age_seconds"] == 3600
    assert status["observed_at"].utcoffset() == timedelta(0)


def test_future_created_at_does_not_produce_negative_backlog_age(queue_connection):
    queue_connection.execute("""
        INSERT INTO ingestion_job (job_id, status, created_at)
        VALUES (1, 'pending', '2026-09-08')
    """)
    status = OperationsQueueQueries(
        OperationsQueueRepository(queue_connection), clock=lambda: datetime(2026, 9, 7),
    ).queue_status()
    assert status["oldest_backlog_age_seconds"] == 0
