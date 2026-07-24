from datetime import datetime, timedelta

import duckdb

from tools.audit_ingestion_queue_recovery import build_queue_recovery_audit


def test_queue_recovery_audit_accounts_for_and_classifies_jobs():
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE ingestion_job (
            job_id BIGINT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            domain TEXT NOT NULL,
            job_type TEXT NOT NULL,
            dataset TEXT NOT NULL,
            status TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0,
            requested_start_date DATE,
            requested_end_date DATE,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
        """
    )
    old = datetime.now() - timedelta(hours=4)
    conn.executemany(
        """
        INSERT INTO ingestion_job
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?)
        """,
        [
            (1, "AAPL", "market", "refresh", "price", "failed", 10, 1, "timeout", old, old),
            (2, "AAPL", "market", "refresh", "price", "done", 10, 2, None, old, old),
            (3, "MSFT", "corporate", "refresh", "fundamentals", "failed", 10, 1, "HTTP error 402", old, old),
            (4, "NVDA", "market", "refresh", "price", "running", 10, 1, None, old, old),
            (5, "META", "market", "refresh", "price", "pending", 10, 3, None, old, old),
            (6, "TSLA", "market", "refresh", "price", "pending", 5, 0, None, old, old),
            (7, "TSLA", "market", "refresh", "price", "pending", 10, 0, None, old, old),
        ],
    )

    report = build_queue_recovery_audit(conn, stale_hours=2)

    assert report["totals"] == {
        "jobs": 7,
        "active": 4,
        "legacy_failed": 2,
        "duplicate_active_groups": 1,
    }
    actions = report["proposed_actions"]
    assert actions["supersede_failed"]["sample_job_ids"] == [1]
    assert actions["mark_unsupported"]["sample_job_ids"] == [3]
    assert actions["requeue_expired_running"]["sample_job_ids"] == [4]
    assert actions["dead_letter_exhausted_pending"]["sample_job_ids"] == [5]
    duplicate = report["duplicate_active_work"][0]
    assert duplicate["keep_job_id"] == 7
    assert duplicate["supersede_job_ids"] == [6]
    assert report["accounted_job_count"] == 7
