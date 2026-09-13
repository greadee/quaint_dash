"""S9 release drill against an isolated DuckDB database.

The drill intentionally exercises only an existing, bounded recovery action. It
does not contact providers or alter the application's calculation and storage
contracts.
"""

from dashboard.api.app import create_app
from dashboard.db.db_conn import DB
from fastapi.testclient import TestClient


def test_failed_job_is_safely_reported_and_bounded_retry_recovers_it(tmp_path):
    db_path = tmp_path / "s9-release-drill.db"
    app = create_app(db_path)
    db = DB(db_path)
    raw_error = "temporary provider reset token=release-drill-secret"
    db.conn.execute(
        "INSERT INTO asset(asset_id, symbol, asset_type, ccy) VALUES ('S9', 'S9', 'stock', 'USD')"
    )
    db.conn.execute(
        """
        INSERT INTO ingestion_job(
            job_id, asset_id, domain, job_type, dataset, status, priority,
            attempt_count, error_message, created_at
        )
        VALUES (9001, 'S9', 'market', 'refresh', 'price_daily', 'failed', 10,
                1, ?, TIMESTAMP '2026-09-11 12:00:00')
        """,
        [raw_error],
    )
    db.conn.close()

    with TestClient(app) as client:
        before = client.get("/api/v1/ingestion/queue/status")
        recovery = client.post(
            "/api/v1/ingestion/retry-failed",
            json={"domain": "market", "max_jobs": 1},
        )
        after = client.get("/api/v1/ingestion/queue/status")
        jobs = client.get("/api/v1/ingestion/jobs?domain=market")

    assert before.status_code == 200
    assert before.json()["failed_count"] == 1
    assert before.json()["failed_groups"] == [
        {
            "provider": "unknown",
            "error_category": "unexpected",
            "count": 1,
            "safe_message": "The job failed; details require local review.",
            "guidance": "Review local diagnostics before retrying; stored error payloads are not displayed here.",
        }
    ]
    assert "release-drill-secret" not in before.text

    assert recovery.status_code == 200
    assert recovery.json() == {"status": "ok", "result": {"retried_jobs": 1}}
    assert after.status_code == 200
    assert after.json()["failed_count"] == 0
    assert after.json()["pending_count"] == 1
    assert jobs.json()[0]["status"] == "pending"
    assert jobs.json()[0]["attempt_count"] == 1

    db = DB(db_path)
    persisted = db.conn.execute(
        "SELECT status, attempt_count, error_message FROM ingestion_job WHERE job_id = 9001"
    ).fetchone()
    db.conn.close()
    assert persisted == ("pending", 1, None)
