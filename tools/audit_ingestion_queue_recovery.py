"""Build a read-only reconciliation ledger for the ingestion job queue."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any

import duckdb

from dashboard.ingestion.job_policy import (
    MAX_INGESTION_JOB_ATTEMPTS,
    is_permanent_ingestion_failure,
)

DEFAULT_DATABASE = Path("data/persistent_db.db")


def build_queue_recovery_audit(
    conn: duckdb.DuckDBPyConnection,
    *,
    stale_hours: int = 2,
    sample_limit: int = 20,
) -> dict[str, Any]:
    """Return a bounded, non-mutating recovery plan for every queue state."""
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
    jobs = [dict(zip(columns, row, strict=True)) for row in rows]
    newest_success: dict[tuple[str, str, str], int] = {}
    active_by_work_key: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for job in jobs:
        coverage_key = _coverage_key(job)
        if job["status"] == "done":
            newest_success[coverage_key] = max(
                newest_success.get(coverage_key, 0),
                int(job["job_id"]),
            )
        if job["status"] in {"pending", "running"}:
            active_by_work_key[_work_key(job)].append(job)

    stale_before = datetime.now() - timedelta(hours=stale_hours)
    actions: dict[str, list[int]] = defaultdict(list)
    for job in jobs:
        job_id = int(job["job_id"])
        attempts = int(job["attempt_count"])
        status = str(job["status"])
        newer_success = newest_success.get(_coverage_key(job), 0) > job_id

        if status == "running" and _older_than(job["updated_at"], stale_before):
            action = (
                "requeue_expired_running"
                if attempts < MAX_INGESTION_JOB_ATTEMPTS
                else "dead_letter_expired_running"
            )
            actions[action].append(job_id)
        elif status == "pending" and attempts >= MAX_INGESTION_JOB_ATTEMPTS:
            actions["dead_letter_exhausted_pending"].append(job_id)
        elif status == "failed":
            if newer_success:
                actions["supersede_failed"].append(job_id)
            elif is_permanent_ingestion_failure(job["error_message"]):
                actions["mark_unsupported"].append(job_id)
            elif attempts < MAX_INGESTION_JOB_ATTEMPTS:
                actions["requeue_failed"].append(job_id)
            else:
                actions["dead_letter_failed"].append(job_id)

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
        duplicate_groups.append(
            {
                "work_key": _json_ready(key),
                "keep_job_id": int(ordered[0]["job_id"]),
                "supersede_job_ids": [int(item["job_id"]) for item in ordered[1:]],
            }
        )
    duplicate_groups.sort(key=lambda item: item["keep_job_id"])

    status_counts = Counter(str(job["status"]) for job in jobs)
    domain_status_counts = Counter(
        (str(job["domain"]), str(job["status"])) for job in jobs
    )
    dataset_status_counts = Counter(
        (str(job["domain"]), str(job["dataset"]), str(job["status"])) for job in jobs
    )
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "read_only",
        "policy": {
            "max_attempts": MAX_INGESTION_JOB_ATTEMPTS,
            "stale_running_hours": stale_hours,
        },
        "totals": {
            "jobs": len(jobs),
            "active": sum(status_counts.get(item, 0) for item in ("pending", "running")),
            "legacy_failed": status_counts.get("failed", 0),
            "duplicate_active_groups": len(duplicate_groups),
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
                "sample_job_ids": job_ids[:sample_limit],
            }
            for action, job_ids in sorted(actions.items())
        },
        "duplicate_active_work": duplicate_groups[:sample_limit],
        "accounted_job_count": len(jobs),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit ingestion jobs and produce a read-only recovery ledger."
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--stale-hours", type=int, default=2)
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    database = args.database.resolve()
    conn = duckdb.connect(str(database), read_only=True)
    try:
        report = build_queue_recovery_audit(
            conn,
            stale_hours=max(1, args.stale_hours),
            sample_limit=max(0, args.sample_limit),
        )
    finally:
        conn.close()
    report["database"] = str(database)
    rendered = json.dumps(report, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


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


def _older_than(value: Any, threshold: datetime) -> bool:
    return isinstance(value, datetime) and value.replace(tzinfo=None) < threshold


def _json_ready(value: tuple[Any, ...]) -> list[Any]:
    return [
        item.isoformat() if hasattr(item, "isoformat") else item
        for item in value
    ]


if __name__ == "__main__":
    main()
