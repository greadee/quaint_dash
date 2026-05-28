REQUIRED_BENCHMARK_TABLES = {
    "benchmark_index",
    "benchmark_index_symbol",
    "benchmark_index_daily_price",
    "benchmark_index_intraday_price",
    "benchmark_index_composition_snapshot",
    "benchmark_index_constituent",
    "benchmark_index_exposure_snapshot",
    "benchmark_index_daily_metric",
    "benchmark_index_relative_metric",
    "benchmark_index_sync_state",
}


def test_benchmark_index_schema_has_required_tables(conn):
    rows = conn.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'main';
        """
    ).fetchall()

    table_names = {row[0] for row in rows}

    assert REQUIRED_BENCHMARK_TABLES.issubset(table_names)


def test_benchmark_index_daily_price_primary_key_deduplicates(conn):
    conn.execute(
        """
        INSERT INTO benchmark_index (
            index_id,
            index_name,
            index_family,
            index_category,
            currency
        )
        VALUES ('SP500', 'S&P 500', 'S&P', 'core_geo', 'USD');
        """
    )

    conn.execute(
        """
        INSERT INTO benchmark_index_daily_price (
            index_id,
            price_date,
            close,
            source,
            source_symbol
        )
        VALUES ('SP500', DATE '2026-01-01', 100.0, 'test', '^GSPC');
        """
    )

    conn.execute(
        """
        INSERT INTO benchmark_index_daily_price (
            index_id,
            price_date,
            close,
            source,
            source_symbol
        )
        VALUES ('SP500', DATE '2026-01-01', 101.0, 'test', '^GSPC')
        ON CONFLICT (index_id, price_date) DO UPDATE SET
            close = excluded.close;
        """
    )

    row = conn.execute(
        """
        SELECT COUNT(*), MAX(close)
        FROM benchmark_index_daily_price
        WHERE index_id = 'SP500';
        """
    ).fetchone()

    assert row[0] == 1
    assert row[1] == 101.0