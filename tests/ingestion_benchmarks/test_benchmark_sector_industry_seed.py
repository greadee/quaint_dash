from dashboard.ingestion.indices.core_index_universe import CORE_INDICES
from dashboard.ingestion.indices.index_ingestion_service import BenchmarkIndexIngestionService
from dashboard.ingestion.indices.sector_industry_index_universe import (
    INDUSTRY_AND_THEME_INDICES,
    NON_CORE_BENCHMARK_INDICES,
    SECTOR_INDICES,
)


def test_sector_industry_seed_inserts_expected_non_core_indices(conn):
    service = BenchmarkIndexIngestionService(conn, provider_registry={})

    inserted = service.seed_sector_industry_universe()

    rows = conn.execute(
        """
        SELECT index_id
        FROM benchmark_index
        WHERE index_category IN ('sector', 'industry', 'theme')
        ORDER BY index_id;
        """
    ).fetchall()

    actual_ids = {row[0] for row in rows}
    expected_ids = {item["index_id"] for item in NON_CORE_BENCHMARK_INDICES}

    assert inserted == len(NON_CORE_BENCHMARK_INDICES)
    assert actual_ids == expected_ids


def test_sector_industry_seed_is_idempotent(conn):
    service = BenchmarkIndexIngestionService(conn, provider_registry={})

    service.seed_sector_industry_universe()
    service.seed_sector_industry_universe()

    index_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM benchmark_index
        WHERE index_category IN ('sector', 'industry', 'theme');
        """
    ).fetchone()[0]

    expected_symbol_count = sum(
        len(item.get("symbols", [])) for item in NON_CORE_BENCHMARK_INDICES
    )

    symbol_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM benchmark_index_symbol
        WHERE index_id IN (
            SELECT index_id
            FROM benchmark_index
            WHERE index_category IN ('sector', 'industry', 'theme')
        );
        """
    ).fetchone()[0]

    assert index_count == len(NON_CORE_BENCHMARK_INDICES)
    assert symbol_count == expected_symbol_count


def test_all_universe_seed_inserts_core_and_non_core_indices(conn):
    service = BenchmarkIndexIngestionService(conn, provider_registry={})

    inserted = service.seed_all_universes()

    index_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM benchmark_index;
        """
    ).fetchone()[0]

    assert inserted == len(CORE_INDICES) + len(NON_CORE_BENCHMARK_INDICES)
    assert index_count == len(CORE_INDICES) + len(NON_CORE_BENCHMARK_INDICES)


def test_sector_universe_has_all_11_sector_benchmarks():
    assert len(SECTOR_INDICES) == 11


def test_industry_theme_universe_is_not_empty():
    assert len(INDUSTRY_AND_THEME_INDICES) > 0