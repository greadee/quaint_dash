from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from time import monotonic

from dashboard.api.services import BenchmarkApiService
from dashboard.db.db_conn import DB, init_db
from dashboard.ingestion.indices.index_service_factory import create_index_ingestion_service


DB_PATH = Path("data/persistent_db.db")
LOOKBACK_DAYS = 10_000
COMPARISON_INDEX_ID = "SP500"


def rows(conn, sql: str, params: list[object] | None = None):
    return conn.execute(sql, params or []).fetchall()


def active_benchmark_ids(conn) -> list[str]:
    return [
        str(row[0])
        for row in rows(
            conn,
            """
            SELECT index_id
            FROM benchmark_index
            WHERE is_active
              AND index_category IN ('core_geo', 'sector', 'industry', 'theme')
            ORDER BY index_category, index_id
            """,
        )
    ]


def price_counts(conn):
    return rows(
        conn,
        """
        SELECT
          b.index_category,
          b.index_id,
          COALESCE(p.price_rows, 0) AS price_rows,
          p.first_date,
          p.latest_date,
          COALESCE(m.metric_rows, 0) AS metric_rows,
          m.latest_metric_date,
          COALESCE(r.relative_rows, 0) AS relative_rows,
          r.latest_relative_date,
          COALESCE(c.constituent_rows, 0) AS constituent_rows,
          c.latest_composition_date
        FROM benchmark_index b
        LEFT JOIN (
          SELECT index_id, COUNT(*) AS price_rows, MIN(price_date) AS first_date, MAX(price_date) AS latest_date
          FROM benchmark_index_daily_price GROUP BY index_id
        ) p ON p.index_id = b.index_id
        LEFT JOIN (
          SELECT index_id, COUNT(*) AS metric_rows, MAX(metric_date) AS latest_metric_date
          FROM benchmark_index_daily_metric GROUP BY index_id
        ) m ON m.index_id = b.index_id
        LEFT JOIN (
          SELECT index_id, COUNT(*) AS relative_rows, MAX(metric_date) AS latest_relative_date
          FROM benchmark_index_relative_metric GROUP BY index_id
        ) r ON r.index_id = b.index_id
        LEFT JOIN (
          SELECT index_id, COUNT(DISTINCT constituent_symbol) AS constituent_rows, MAX(snapshot_date) AS latest_composition_date
          FROM benchmark_index_constituent GROUP BY index_id
        ) c ON c.index_id = b.index_id
        WHERE b.is_active
          AND b.index_category IN ('core_geo', 'sector', 'industry', 'theme')
        ORDER BY b.index_category, b.index_id
        """,
    )


def print_counts(conn, title: str) -> None:
    print(f"\n== {title} ==")
    for row in price_counts(conn):
        print(row)


def main() -> None:
    started = monotonic()
    db = DB(str(DB_PATH))
    init_db(db)
    conn = db.conn
    service = create_index_ingestion_service(conn)
    api = BenchmarkApiService(conn)
    service.seed_all_universes()
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    failures: list[tuple[str, str, str]] = []
    totals = {"daily": 0, "metrics": 0, "composition": 0, "relative": 0}

    print_counts(conn, "before repair")

    for index_id in ("SP500", "NDX100"):
        print(f"\n-- repair {index_id} --")
        try:
            daily = service.ingest_daily_prices(index_id, start, end)
            totals["daily"] += daily
            print("daily", daily)
        except Exception as exc:
            failures.append((index_id, "daily", str(exc)))
            print("daily failed", exc)
            continue
        try:
            metrics = service.compute_daily_metrics(index_id)
            totals["metrics"] += metrics
            print("metrics", metrics)
        except Exception as exc:
            failures.append((index_id, "metrics", str(exc)))
            print("metrics failed", exc)
        try:
            composition = service.ingest_composition(index_id, end)
            totals["composition"] += composition
            print("composition", composition)
        except Exception as exc:
            failures.append((index_id, "composition", str(exc)))
            print("composition failed", exc)

    print("\n-- recompute relative metrics against SP500 --")
    for index_id in active_benchmark_ids(conn):
        if index_id == COMPARISON_INDEX_ID:
            continue
        try:
            count = service.compute_relative_metrics(index_id, COMPARISON_INDEX_ID)
            totals["relative"] += count
            print(index_id, count)
        except Exception as exc:
            failures.append((index_id, "relative", str(exc)))
            print(index_id, "relative failed", exc)

    conn.commit()

    print("\n== api readiness ==")
    for category in ("core_geo", "sector", "industry", "theme"):
        result = api.readiness(category=category)
        print(category, result.ready_count, "/", result.total)
        for item in result.items:
            if item.missing:
                print("missing", item.index_id, item.missing)

    print_counts(conn, "after repair")
    print("\n== totals ==")
    print(totals)
    print("failures", len(failures))
    for failure in failures:
        print(failure)
    print(f"elapsed_seconds: {monotonic() - started:.1f}")

    missing_prices = [row for row in price_counts(conn) if int(row[2] or 0) == 0]
    if missing_prices:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
