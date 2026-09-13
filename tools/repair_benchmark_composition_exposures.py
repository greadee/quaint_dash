from __future__ import annotations

from datetime import date
from pathlib import Path
from time import monotonic

from dashboard.api.services import BenchmarkApiService
from dashboard.db.db_conn import DB, init_db
from dashboard.ingestion.indices.index_service_factory import create_index_ingestion_service


def main() -> None:
    started = monotonic()
    db = DB(str(Path("data/persistent_db.db")))
    init_db(db)
    conn = db.conn
    service = create_index_ingestion_service(conn)
    api = BenchmarkApiService(conn)
    service.seed_all_universes()
    index_ids = [
        str(row[0])
        for row in conn.execute(
            """
            SELECT index_id
            FROM benchmark_index
            WHERE is_active
              AND index_category IN ('core_geo', 'sector', 'industry', 'theme')
            ORDER BY index_category, index_id
            """
        ).fetchall()
    ]
    failures: list[tuple[str, str]] = []
    total = 0
    today = date.today()
    for index_id in index_ids:
        try:
            count = service.ingest_composition(index_id, today)
            total += count
            print(index_id, "composition", count)
        except Exception as exc:
            failures.append((index_id, str(exc)))
            print(index_id, "composition failed", exc)
    conn.commit()
    print("\n== readiness ==")
    for category in ("core_geo", "sector", "industry", "theme"):
        result = api.readiness(category=category)
        print(category, result.ready_count, "/", result.total)
        for item in result.items:
            if item.missing:
                print("missing", item.index_id, item.missing)
    print("\n== exposure counts ==")
    for row in conn.execute(
        """
        SELECT b.index_category, b.index_id, COUNT(e.dimension_type) AS exposure_rows
        FROM benchmark_index b
        LEFT JOIN benchmark_index_exposure_snapshot e ON e.index_id = b.index_id
        WHERE b.is_active
          AND b.index_category IN ('core_geo', 'sector', 'industry', 'theme')
        GROUP BY b.index_category, b.index_id
        ORDER BY b.index_category, b.index_id
        """
    ).fetchall():
        print(row)
    print("\n== totals ==")
    print("composition_rows", total)
    print("failures", len(failures))
    for failure in failures:
        print(failure)
    print(f"elapsed_seconds: {monotonic() - started:.1f}")
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
