from pathlib import Path

from dashboard.api.services import BenchmarkApiService
from dashboard.db.db_conn import DB


def main() -> None:
    conn = DB(str(Path("data/persistent_db.db"))).conn
    api = BenchmarkApiService(conn)
    print("== readiness ==")
    for category in ("core_geo", "sector", "industry", "theme"):
        result = api.readiness(category=category)
        print(category, result.ready_count, "/", result.total)
        for item in result.items:
            if item.missing:
                print("missing", item.index_id, item.missing)
    print("\n== coverage ==")
    for row in conn.execute(
        """
        SELECT
          b.index_category,
          COUNT(*) AS benchmarks,
          COUNT(*) FILTER (WHERE COALESCE(p.price_rows, 0) > 0) AS with_prices,
          MIN(p.first_date) AS earliest_history,
          MAX(p.latest_date) AS latest_price,
          COUNT(*) FILTER (WHERE COALESCE(m.metric_rows, 0) > 0) AS with_metrics,
          COUNT(*) FILTER (WHERE b.index_id = 'SP500' OR COALESCE(r.relative_rows, 0) > 0) AS with_relative_or_baseline,
          COUNT(*) FILTER (WHERE COALESCE(c.constituent_rows, 0) > 0) AS with_constituents,
          COUNT(*) FILTER (WHERE COALESCE(e.exposure_rows, 0) > 0) AS with_exposures
        FROM benchmark_index b
        LEFT JOIN (
          SELECT index_id, COUNT(*) AS price_rows, MIN(price_date) AS first_date, MAX(price_date) AS latest_date
          FROM benchmark_index_daily_price GROUP BY index_id
        ) p ON p.index_id = b.index_id
        LEFT JOIN (
          SELECT index_id, COUNT(*) AS metric_rows
          FROM benchmark_index_daily_metric GROUP BY index_id
        ) m ON m.index_id = b.index_id
        LEFT JOIN (
          SELECT index_id, COUNT(*) AS relative_rows
          FROM benchmark_index_relative_metric GROUP BY index_id
        ) r ON r.index_id = b.index_id
        LEFT JOIN (
          SELECT index_id, COUNT(*) AS constituent_rows
          FROM benchmark_index_constituent GROUP BY index_id
        ) c ON c.index_id = b.index_id
        LEFT JOIN (
          SELECT index_id, COUNT(*) AS exposure_rows
          FROM benchmark_index_exposure_snapshot GROUP BY index_id
        ) e ON e.index_id = b.index_id
        WHERE b.is_active
          AND b.index_category IN ('core_geo', 'sector', 'industry', 'theme')
        GROUP BY b.index_category
        ORDER BY b.index_category
        """
    ).fetchall():
        print(row)
    print("\n== queue ==")
    for row in conn.execute(
        """
        SELECT status, domain, COUNT(*)
        FROM ingestion_job
        GROUP BY status, domain
        ORDER BY status, domain
        """
    ).fetchall():
        print(row)
    print("\n== failed jobs ==")
    for row in conn.execute(
        """
        SELECT domain, dataset, job_type, asset_id, error_message
        FROM ingestion_job
        WHERE status = 'failed'
        ORDER BY domain, dataset, job_type, asset_id
        LIMIT 25
        """
    ).fetchall():
        print(row)


if __name__ == "__main__":
    main()
