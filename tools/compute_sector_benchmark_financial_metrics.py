from __future__ import annotations

from pathlib import Path

from dashboard.db.db_conn import DB, init_db
from dashboard.ingestion.indices.benchmark_financial_metrics import BenchmarkFinancialMetricService
from dashboard.ingestion.indices.index_service_factory import create_index_ingestion_service


DB_PATH = Path("data/persistent_db.db")


def main() -> None:
    db = DB(str(DB_PATH))
    init_db(db)

    index_service = create_index_ingestion_service(db.conn)
    index_service.seed_sector_industry_universe()

    service = BenchmarkFinancialMetricService(db.conn)
    computed = service.compute_sector_financial_metrics()
    print(f"computed sector benchmark financial metric snapshots: {computed}")

    rows = db.conn.execute(
        """
        SELECT
            b.index_id,
            b.index_name,
            m.peer_count,
            m.covered_peer_count,
            m.pe_median,
            m.non_gaap_eps_median,
            m.peg_median,
            m.data_quality,
            m.metric_date
        FROM benchmark_index b
        LEFT JOIN benchmark_index_financial_metric m
          ON m.index_id = b.index_id
         AND m.source = 'computed_from_company_fundamentals'
        WHERE b.index_category = 'sector'
          AND b.is_active
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY b.index_id
            ORDER BY m.metric_date DESC NULLS LAST
        ) = 1
        ORDER BY b.index_id;
        """
    ).fetchall()
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
