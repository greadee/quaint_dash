from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from time import monotonic

from dashboard.api.services import BenchmarkApiService
from dashboard.db.db_conn import DB, init_db
from dashboard.ingestion.indices.index_service_factory import create_index_ingestion_service
from dashboard.models.commands.ingestion import IngestionCommands


DB_PATH = Path("data/persistent_db.db")
CATEGORIES = ("core_geo", "sector", "industry", "theme")
COMPARISON_INDEX_ID = "SP500"
LOOKBACK_DAYS = 10_000


class QueueRunner(IngestionCommands):
    def __init__(self, conn):
        self.conn = conn


def rows(conn, sql: str, params: list[object] | None = None):
    return conn.execute(sql, params or []).fetchall()


def benchmark_ids(conn) -> list[str]:
    result = rows(
        conn,
        """
        SELECT index_id
        FROM benchmark_index
        WHERE is_active
          AND index_category IN ('core_geo', 'sector', 'industry', 'theme')
        ORDER BY
          CASE WHEN index_id = ? THEN 0 ELSE 1 END,
          CASE index_category
            WHEN 'core_geo' THEN 1
            WHEN 'sector' THEN 2
            WHEN 'industry' THEN 3
            WHEN 'theme' THEN 4
            ELSE 5
          END,
          index_id
        """,
        [COMPARISON_INDEX_ID],
    )
    return [str(row[0]) for row in result]


def readiness(conn):
    return rows(
        conn,
        """
        SELECT
          b.index_category,
          b.index_id,
          COUNT(p.price_date) AS price_rows,
          MIN(p.price_date) AS first_price_date,
          MAX(p.price_date) AS latest_price_date,
          COUNT(m.metric_date) AS metric_rows,
          MAX(m.metric_date) AS latest_metric_date,
          COUNT(r.metric_date) AS relative_metric_rows,
          MAX(r.metric_date) AS latest_relative_metric_date,
          COUNT(DISTINCT c.constituent_symbol) AS constituent_rows,
          MAX(c.snapshot_date) AS latest_composition_date
        FROM benchmark_index b
        LEFT JOIN benchmark_index_daily_price p ON p.index_id = b.index_id
        LEFT JOIN benchmark_index_daily_metric m ON m.index_id = b.index_id
        LEFT JOIN benchmark_index_relative_metric r ON r.index_id = b.index_id
        LEFT JOIN benchmark_index_constituent c ON c.index_id = b.index_id
        WHERE b.is_active
          AND b.index_category IN ('core_geo', 'sector', 'industry', 'theme')
        GROUP BY b.index_category, b.index_id
        ORDER BY b.index_category, b.index_id
        """,
    )


def print_readiness(conn, title: str) -> None:
    print(f"\n== {title} ==")
    for row in readiness(conn):
        print(row)


def queue_summary(conn) -> list[tuple]:
    return rows(
        conn,
        """
        SELECT status, domain, COUNT(*)
        FROM ingestion_job
        GROUP BY status, domain
        ORDER BY status, domain
        """,
    )


def drain_pending_queue(conn, max_total_jobs: int = 300) -> int:
    runner = QueueRunner(conn)
    completed = 0
    while completed < max_total_jobs:
        pending = rows(
            conn,
            "SELECT COUNT(*) FROM ingestion_job WHERE status = 'pending'",
        )[0][0]
        if not pending:
            break
        processed = runner.run_ingestion_jobs(domain="all", max_jobs=min(25, max_total_jobs - completed))
        if not processed:
            break
        completed += processed
        print(f"queue: processed {completed}, pending {pending}")
    return completed


def main() -> None:
    started = monotonic()
    db = DB(str(DB_PATH))
    init_db(db)
    conn = db.conn
    service = create_index_ingestion_service(conn)
    api = BenchmarkApiService(conn)
    seeded = service.seed_all_universes()
    ids = benchmark_ids(conn)
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    print(f"seeded/updated benchmark universe rows: {seeded}")
    print(f"target benchmark count: {len(ids)}")
    print(f"daily history window: {start.isoformat()} -> {end.isoformat()}")
    print_readiness(conn, "before")

    failures: list[tuple[str, str, str]] = []
    totals = {
        "daily_price_rows": 0,
        "metric_rows": 0,
        "composition_rows": 0,
        "relative_metric_rows": 0,
    }

    for index_id in ids:
        print(f"\n-- harden {index_id} --")
        try:
            daily = service.ingest_daily_prices(index_id, start, end)
            totals["daily_price_rows"] += daily
            print(f"daily prices: {daily}")
        except Exception as exc:
            failures.append((index_id, "daily_price", str(exc)))
            print(f"daily prices failed: {exc}")
            continue

        try:
            metrics = service.compute_daily_metrics(index_id)
            totals["metric_rows"] += metrics
            print(f"metrics: {metrics}")
        except Exception as exc:
            failures.append((index_id, "metrics", str(exc)))
            print(f"metrics failed: {exc}")

        try:
            composition = service.ingest_composition(index_id, end)
            totals["composition_rows"] += composition
            print(f"composition: {composition}")
        except Exception as exc:
            failures.append((index_id, "composition", str(exc)))
            print(f"composition failed: {exc}")

        if index_id.upper() != COMPARISON_INDEX_ID:
            try:
                relative = service.compute_relative_metrics(index_id, COMPARISON_INDEX_ID)
                totals["relative_metric_rows"] += relative
                print(f"relative metrics: {relative}")
            except Exception as exc:
                failures.append((index_id, "relative_metrics", str(exc)))
                print(f"relative metrics failed: {exc}")

    service.conn.commit()
    conn.commit()

    print("\n== api readiness ==")
    for category in CATEGORIES:
        try:
            result = api.readiness(category=category)
            print(category, result.ready_count, "/", result.total)
        except Exception as exc:
            print(category, "readiness failed", exc)

    print_readiness(conn, "after benchmark harden")
    print("\n== queued jobs before drain ==")
    for row in queue_summary(conn):
        print(row)
    drained = drain_pending_queue(conn)
    print(f"queue jobs processed: {drained}")
    print("\n== queued jobs after drain ==")
    for row in queue_summary(conn):
        print(row)

    missing_prices = [
        row for row in readiness(conn)
        if int(row[2] or 0) == 0
    ]
    print("\n== totals ==")
    print(totals)
    print(f"failures: {len(failures)}")
    for failure in failures:
        print(failure)
    print(f"missing price histories: {len(missing_prices)}")
    for row in missing_prices:
        print(row)
    print(f"elapsed_seconds: {monotonic() - started:.1f}")

    if missing_prices:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
