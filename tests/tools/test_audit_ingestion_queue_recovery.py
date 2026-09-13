from datetime import datetime, timedelta

import duckdb

from tools.audit_ingestion_queue_recovery import (
    apply_queue_recovery,
    build_queue_recovery_audit,
)


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
            lease_owner TEXT,
            leased_at TIMESTAMP,
            lease_expires_at TIMESTAMP,
            max_attempts INTEGER DEFAULT 3,
            terminal_reason TEXT,
            completed_at TIMESTAMP,
            superseded_by_job_id BIGINT,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
        """
    )
    old = datetime.now() - timedelta(hours=4)
    conn.executemany(
        """
        INSERT INTO ingestion_job(
            job_id, asset_id, domain, job_type, dataset, status, priority,
            requested_start_date, requested_end_date, attempt_count,
            error_message, created_at, updated_at
        )
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
        "proposed_unique_changes": 5,
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


def test_queue_recovery_apply_moves_every_proposed_job_once():
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
            lease_owner TEXT,
            leased_at TIMESTAMP,
            lease_expires_at TIMESTAMP,
            max_attempts INTEGER DEFAULT 3,
            terminal_reason TEXT,
            completed_at TIMESTAMP,
            superseded_by_job_id BIGINT,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
        """
    )
    old = datetime.now() - timedelta(hours=4)
    conn.executemany(
        """
        INSERT INTO ingestion_job(
            job_id, asset_id, domain, job_type, dataset, status, priority,
            attempt_count, error_message, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    result = apply_queue_recovery(conn, stale_hours=2)
    rows = conn.execute(
        """
        SELECT job_id, status, superseded_by_job_id
        FROM ingestion_job
        ORDER BY job_id
        """
    ).fetchall()
    after = build_queue_recovery_audit(conn, stale_hours=2)

    assert result["changed_total"] == 5
    assert rows == [
        (1, "superseded", 2),
        (2, "done", None),
        (3, "unsupported", None),
        (4, "pending", None),
        (5, "dead_letter", None),
        (6, "superseded", 7),
        (7, "pending", None),
    ]
    assert after["totals"]["legacy_failed"] == 0
    assert after["totals"]["duplicate_active_groups"] == 0
    assert after["totals"]["proposed_unique_changes"] == 0
