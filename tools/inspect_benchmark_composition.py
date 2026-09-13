from pathlib import Path

from dashboard.db.db_conn import DB


def main() -> None:
    conn = DB(str(Path("data/persistent_db.db"))).conn
    for index_id in ["DEV_INTL", "NDX100", "SEC_TECH", "IND_SEMICONDUCTORS"]:
        print(f"-- {index_id} constituents --")
        rows = conn.execute(
            """
            SELECT constituent_symbol, constituent_name, country_code, currency, sector, industry, weight_pct, source
            FROM benchmark_index_constituent
            WHERE index_id = ?
            ORDER BY snapshot_date DESC, weight_pct DESC NULLS LAST
            LIMIT 10
            """,
            [index_id],
        ).fetchall()
        for row in rows:
            print(row)
        exposures = conn.execute(
            """
            SELECT dimension_type, dimension_value, weight_pct, source
            FROM benchmark_index_exposure_snapshot
            WHERE index_id = ?
            ORDER BY dimension_type, weight_pct DESC
            LIMIT 20
            """,
            [index_id],
        ).fetchall()
        print("exposures", exposures)


if __name__ == "__main__":
    main()
