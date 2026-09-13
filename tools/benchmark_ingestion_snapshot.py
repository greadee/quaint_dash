from pathlib import Path

from dashboard.db.db_conn import DB


def main() -> None:
    db = DB(str(Path("data/persistent_db.db")))
    conn = db.conn
    queries = {
        "benchmarks_by_category": """
            SELECT index_category, COUNT(*) AS benchmarks,
                   COUNT(DISTINCT p.index_id) AS with_prices,
                   COALESCE(SUM(price_count), 0) AS price_rows
            FROM benchmark_index b
            LEFT JOIN (
                SELECT index_id, COUNT(*) price_count
                FROM benchmark_index_daily_price
                GROUP BY index_id
            ) p USING(index_id)
            GROUP BY index_category
            ORDER BY index_category
        """,
        "benchmark_price_gaps": """
            SELECT b.index_id, b.index_category, b.index_name,
                   COUNT(p.price_date) AS price_rows,
                   MIN(p.price_date) AS first_date,
                   MAX(p.price_date) AS latest_date
            FROM benchmark_index b
            LEFT JOIN benchmark_index_daily_price p ON p.index_id=b.index_id
            WHERE b.is_active
            GROUP BY b.index_id, b.index_category, b.index_name
            ORDER BY b.index_category, b.index_id
        """,
        "jobs": """
            SELECT status, domain, COUNT(*)
            FROM ingestion_job
            GROUP BY status, domain
            ORDER BY status, domain
        """,
    }
    for name, sql in queries.items():
        print(f"-- {name} --")
        try:
            for row in conn.execute(sql).fetchall():
                print(row)
        except Exception as exc:
            print(type(exc).__name__, exc)


if __name__ == "__main__":
    main()
