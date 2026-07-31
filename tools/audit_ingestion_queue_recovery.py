"""Audit and safely reconcile the ingestion job queue."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
import json
from pathlib import Path
from typing import Any

import duckdb

from dashboard.ingestion.job_policy import (
    MAX_INGESTION_JOB_ATTEMPTS,
    is_permanent_ingestion_failure,
)

DEFAULT_DATABASE = Path("data/persistent_db.db")
ACTIVE_STATUSES = {"pending", "running"}


def build_queue_recovery_audit(
    conn: duckdb.DuckDBPyConnection,
    *,
    stale_hours: int = 2,
    sample_limit: int = 20,
) -> dict[str, Any]:
    """Return a bounded, non-mutating recovery plan for every queue state."""
    jobs = _load_jobs(conn)
    actions, duplicate_groups = _build_recovery_actions(
        conn,
        jobs,
        stale_hours=stale_hours,
    )
    status_counts = Counter(str(job["status"]) for job in jobs)
    domain_status_counts = Counter(
        (str(job["domain"]), str(job["status"])) for job in jobs
    )
    dataset_status_counts = Counter(
        (str(job["domain"]), str(job["dataset"]), str(job["status"])) for job in jobs
    )
    affected_ids = {
        job_id
        for job_ids in actions.values()
        for job_id in job_ids
    }
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "read_only",
        "policy": {
            "max_attempts": MAX_INGESTION_JOB_ATTEMPTS,
            "stale_running_hours": stale_hours,
        },
        "totals": {
            "jobs": len(jobs),
            "active": sum(status_counts.get(item, 0) for item in ACTIVE_STATUSES),
            "legacy_failed": status_counts.get("failed", 0),
            "duplicate_active_groups": len(duplicate_groups),
            "proposed_unique_changes": len(affected_ids),
        },
        "status_counts": dict(sorted(status_counts.items())),
        "domain_status_counts": [
            {"domain": domain, "status": status, "count": count}
            for (domain, status), count in sorted(domain_status_counts.items())
        ],
        "dataset_status_counts": [
            {
                "domain": domain,
                "dataset": dataset,
                "status": status,
                "count": count,
            }
            for (domain, dataset, status), count in sorted(dataset_status_counts.items())
        ],
        "proposed_actions": {
            action: {
                "count": len(job_ids),
                "sample_job_ids": sorted(job_ids)[:sample_limit],
            }
            for action, job_ids in sorted(actions.items())
        },
        "duplicate_active_work": duplicate_groups[:sample_limit],
        "accounted_job_count": len(jobs),
    }


def apply_queue_recovery(
    conn: duckdb.DuckDBPyConnection,
    *,
    stale_hours: int = 2,
) -> dict[str, Any]:
    """Apply the deterministic recovery plan in one transaction."""
    required_columns = {
        "lease_owner",
        "leased_at",
        "lease_expires_at",
        "max_attempts",
        "terminal_reason",
        "completed_at",
        "superseded_by_job_id",
    }
    missing = required_columns - _table_columns(conn, "ingestion_job")
    if missing:
        raise RuntimeError(
            "Run init_db before recovery; missing ingestion columns: "
            + ", ".join(sorted(missing))
        )

    jobs = _load_jobs(conn)
    actions, duplicate_groups = _build_recovery_actions(
        conn,
        jobs,
        stale_hours=stale_hours,
    )
    duplicate_superseded = {
        int(job_id): int(group["keep_job_id"])
        for group in duplicate_groups
        for job_id in group["supersede_job_ids"]
    }
    newest_success = _newest_success_by_coverage(jobs)

    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute("DROP INDEX IF EXISTS ingestion_job_pending_idx")
        changed: dict[str, int] = {}
        changed["superseded"] = _set_terminal_status(
            conn,
            sorted(
                set(actions.get("supersede_active", []))
                | set(actions.get("supersede_failed", []))
                | set(actions.get("supersede_duplicate", []))
            ),
            status="superseded",
            reason="covered by newer successful or retained work",
            superseded_by={
                **{
                    job_id: newest_success.get(
                        _coverage_key(_job_by_id(jobs, job_id))
                    )
                    for job_id in (
                        set(actions.get("supersede_active", []))
                        | set(actions.get("supersede_failed", []))
                    )
                },
                **duplicate_superseded,
            },
        )
        changed["unsupported"] = _set_terminal_status(
            conn,
            sorted(
                set(actions.get("mark_unsupported", []))
                | set(actions.get("mark_unsupported_active", []))
            ),
            status="unsupported",
            reason="provider or subscription cannot supply this dataset",
        )
        changed["dead_letter"] = _set_terminal_status(
            conn,
            sorted(
                set(actions.get("dead_letter_expired_running", []))
                | set(actions.get("dead_letter_exhausted_pending", []))
                | set(actions.get("dead_letter_failed", []))
            ),
            status="dead_letter",
            reason="ingestion retry budget exhausted",
        )
        changed["requeued"] = _set_pending(
            conn,
            sorted(
                set(actions.get("requeue_expired_running", []))
                | set(actions.get("requeue_failed", []))
            ),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    return {
        "changed": changed,
        "changed_total": sum(changed.values()),
        "before_jobs": len(jobs),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit or reconcile ingestion jobs with a verified backup."
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--stale-hours", type=int, default=2)
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--expected-jobs", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    database = args.database.resolve()
    stale_hours = max(0, args.stale_hours)
    sample_limit = max(0, args.sample_limit)

    if args.apply:
        _verify_apply_guard(
            database=database,
            backup=args.backup,
            expected_jobs=args.expected_jobs,
        )
        conn = duckdb.connect(str(database))
        try:
            before = build_queue_recovery_audit(
                conn,
                stale_hours=stale_hours,
                sample_limit=sample_limit,
            )
            result = apply_queue_recovery(conn, stale_hours=stale_hours)
            after = build_queue_recovery_audit(
                conn,
                stale_hours=stale_hours,
                sample_limit=sample_limit,
            )
        finally:
            conn.close()
        report = {
            "mode": "applied",
            "database": str(database),
            "backup": str(args.backup.resolve()),
            "before": before,
            "result": result,
            "after": after,
        }
    else:
        conn = duckdb.connect(str(database), read_only=True)
        try:
            report = build_queue_recovery_audit(
                conn,
                stale_hours=stale_hours,
                sample_limit=sample_limit,
            )
        finally:
            conn.close()
        report["database"] = str(database)

    rendered = json.dumps(report, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


def _load_jobs(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            job_id,
            asset_id,
            domain,
            job_type,
            dataset,
            status,
            priority,
            requested_start_date,
            requested_end_date,
            COALESCE(attempt_count, 0),
            error_message,
            created_at,
            updated_at
        FROM ingestion_job
        ORDER BY job_id
        """
    ).fetchall()
    columns = [
        "job_id",
        "asset_id",
        "domain",
        "job_type",
        "dataset",
        "status",
        "priority",
        "requested_start_date",
        "requested_end_date",
        "attempt_count",
        "error_message",
        "created_at",
        "updated_at",
    ]
    return [dict(zip(columns, row, strict=True)) for row in rows]


def _build_recovery_actions(
    conn: duckdb.DuckDBPyConnection,
    jobs: list[dict[str, Any]],
    *,
    stale_hours: int,
) -> tuple[dict[str, list[int]], list[dict[str, Any]]]:
    newest_success = _newest_success_by_coverage(jobs)
    successful_sync = _successful_sync_by_coverage(conn)
    permanent_failure_keys = {
        _coverage_key(job)
        for job in jobs
        if job["status"] == "failed"
        and is_permanent_ingestion_failure(job["error_message"])
    }
    stale_before = datetime.now() - timedelta(hours=stale_hours)
    actions: dict[str, list[int]] = defaultdict(list)
    already_classified: set[int] = set()

    for job in jobs:
        job_id = int(job["job_id"])
        attempts = int(job["attempt_count"])
        status = str(job["status"])
        coverage_key = _coverage_key(job)
        newer_success = newest_success.get(coverage_key, 0) > job_id
        sync_covers = _sync_covers_job(successful_sync.get(coverage_key), job)

        if status in ACTIVE_STATUSES and (newer_success or sync_covers):
            actions["supersede_active"].append(job_id)
            already_classified.add(job_id)
        elif status in ACTIVE_STATUSES and coverage_key in permanent_failure_keys:
            actions["mark_unsupported_active"].append(job_id)
            already_classified.add(job_id)
        elif status == "running" and _older_than(job["updated_at"], stale_before):
            action = (
                "requeue_expired_running"
                if attempts < MAX_INGESTION_JOB_ATTEMPTS
                else "dead_letter_expired_running"
            )
            actions[action].append(job_id)
            already_classified.add(job_id)
        elif status == "pending" and attempts >= MAX_INGESTION_JOB_ATTEMPTS:
            actions["dead_letter_exhausted_pending"].append(job_id)
            already_classified.add(job_id)
        elif status == "failed":
            if newer_success or sync_covers:
                actions["supersede_failed"].append(job_id)
            elif is_permanent_ingestion_failure(job["error_message"]):
                actions["mark_unsupported"].append(job_id)
            elif attempts < MAX_INGESTION_JOB_ATTEMPTS:
                actions["requeue_failed"].append(job_id)
            else:
                actions["dead_letter_failed"].append(job_id)
            already_classified.add(job_id)

    active_by_work_key: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for job in jobs:
        if job["status"] in ACTIVE_STATUSES and int(job["job_id"]) not in already_classified:
            active_by_work_key[_work_key(job)].append(job)

    duplicate_groups = []
    for key, group in active_by_work_key.items():
        if len(group) <= 1:
            continue
        ordered = sorted(
            group,
            key=lambda item: (
                int(item["priority"]),
                item["created_at"] or datetime.min,
                int(item["job_id"]),
            ),
            reverse=True,
        )
        superseded = [int(item["job_id"]) for item in ordered[1:]]
        actions["supersede_duplicate"].extend(superseded)
        duplicate_groups.append(
            {
                "work_key": _json_ready(key),
                "keep_job_id": int(ordered[0]["job_id"]),
                "supersede_job_ids": superseded,
            }
        )
    duplicate_groups.sort(key=lambda item: item["keep_job_id"])
    return actions, duplicate_groups


def _newest_success_by_coverage(
    jobs: list[dict[str, Any]],
) -> dict[tuple[str, str, str], int]:
    newest: dict[tuple[str, str, str], int] = {}
    for job in jobs:
        if job["status"] != "done":
            continue
        key = _coverage_key(job)
        newest[key] = max(newest.get(key, 0), int(job["job_id"]))
    return newest


def _successful_sync_by_coverage(
    conn: duckdb.DuckDBPyConnection,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    if "asset_sync_state" not in _table_names(conn):
        return {}
    rows = conn.execute(
        """
        SELECT
            asset_id,
            domain,
            dataset,
            backfill_status,
            last_successful_date,
            last_attempted_at,
            last_successful_at
        FROM asset_sync_state
        WHERE backfill_status = 'done'
           OR last_successful_date IS NOT NULL
           OR last_successful_at IS NOT NULL
        """
    ).fetchall()
    return {
        (str(row[0]), str(row[1]), str(row[2])): {
            "backfill_status": row[3],
            "last_successful_date": row[4],
            "last_attempted_at": row[5],
            "last_successful_at": row[6],
        }
        for row in rows
    }


def _sync_covers_job(sync: dict[str, Any] | None, job: dict[str, Any]) -> bool:
    if not sync:
        return False
    successful_at = sync.get("last_successful_at")
    updated_at = job.get("updated_at")
    if (
        isinstance(successful_at, datetime)
        and isinstance(updated_at, datetime)
        and successful_at >= updated_at
    ):
        return True
    successful_date = sync.get("last_successful_date")
    requested_end = job.get("requested_end_date")
    return (
        isinstance(successful_date, date)
        and isinstance(requested_end, date)
        and successful_date >= requested_end
    )


def _set_terminal_status(
    conn: duckdb.DuckDBPyConnection,
    job_ids: list[int],
    *,
    status: str,
    reason: str,
    superseded_by: dict[int, int | None] | None = None,
) -> int:
    if not job_ids:
        return 0
    superseded_by = superseded_by or {}
    changed = 0
    for job_id in job_ids:
        row = conn.execute(
            """
            UPDATE ingestion_job
            SET
                status = ?,
                terminal_reason = ?,
                superseded_by_job_id = ?,
                lease_owner = NULL,
                leased_at = NULL,
                lease_expires_at = NULL,
                completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = ?
              AND status IN ('pending', 'running', 'failed')
            RETURNING job_id
            """,
            [status, reason, superseded_by.get(job_id), job_id],
        ).fetchone()
        changed += int(row is not None)
    return changed


def _set_pending(conn: duckdb.DuckDBPyConnection, job_ids: list[int]) -> int:
    if not job_ids:
        return 0
    changed = 0
    for job_id in job_ids:
        row = conn.execute(
            """
            UPDATE ingestion_job
            SET
                status = 'pending',
                error_message = NULL,
                terminal_reason = 'recovered for bounded retry',
                lease_owner = NULL,
                leased_at = NULL,
                lease_expires_at = NULL,
                completed_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = ?
              AND status IN ('running', 'failed')
            RETURNING job_id
            """,
            [job_id],
        ).fetchone()
        changed += int(row is not None)
    return changed


def _verify_apply_guard(
    *,
    database: Path,
    backup: Path | None,
    expected_jobs: int | None,
) -> None:
    if backup is None or expected_jobs is None:
        raise SystemExit("--apply requires --backup and --expected-jobs")
    backup_path = backup.resolve()
    if not backup_path.is_file():
        raise SystemExit(f"Backup does not exist: {backup_path}")
    backup_conn = duckdb.connect(str(backup_path), read_only=True)
    try:
        backup_jobs = int(
            backup_conn.execute("SELECT COUNT(*) FROM ingestion_job").fetchone()[0]
        )
    finally:
        backup_conn.close()
    if backup_jobs != expected_jobs:
        raise SystemExit(
            f"Backup job count {backup_jobs} does not match expected {expected_jobs}"
        )
    live_conn = duckdb.connect(str(database), read_only=True)
    try:
        live_jobs = int(
            live_conn.execute("SELECT COUNT(*) FROM ingestion_job").fetchone()[0]
        )
    finally:
        live_conn.close()
    if live_jobs != expected_jobs:
        raise SystemExit(
            f"Live job count {live_jobs} does not match expected {expected_jobs}"
        )


def _coverage_key(job: dict[str, Any]) -> tuple[str, str, str]:
    return (str(job["asset_id"]), str(job["domain"]), str(job["dataset"]))


def _work_key(job: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(job["asset_id"]),
        str(job["domain"]),
        str(job["job_type"]),
        str(job["dataset"]),
        job["requested_start_date"],
        job["requested_end_date"],
    )


def _job_by_id(jobs: list[dict[str, Any]], job_id: int) -> dict[str, Any]:
    return next(job for job in jobs if int(job["job_id"]) == job_id)


def _older_than(value: Any, threshold: datetime) -> bool:
    return isinstance(value, datetime) and value.replace(tzinfo=None) < threshold


def _json_ready(value: tuple[Any, ...]) -> list[Any]:
    return [item.isoformat() if hasattr(item, "isoformat") else item for item in value]


def _table_names(conn: duckdb.DuckDBPyConnection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    }


def _table_columns(conn: duckdb.DuckDBPyConnection, table_name: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    }


if __name__ == "__main__":
    main()
