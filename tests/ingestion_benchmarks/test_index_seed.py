from dashboard.ingestion.indices.core_index_universe import CORE_INDICES
from dashboard.ingestion.indices.index_ingestion_service import BenchmarkIndexIngestionService


def test_core_index_seed_inserts_expected_indices(conn):
    service = BenchmarkIndexIngestionService(conn, provider_registry={})

    inserted = service.seed_core_universe()

    expected_ids = {item["index_id"] for item in CORE_INDICES}

    rows = conn.execute(
        """
        SELECT index_id
        FROM benchmark_index
        ORDER BY index_id;
        """
    ).fetchall()

    actual_ids = {row[0] for row in rows}

    assert inserted == len(CORE_INDICES)
    assert actual_ids == expected_ids


def test_core_index_seed_is_idempotent(conn):
    service = BenchmarkIndexIngestionService(conn, provider_registry={})

    service.seed_core_universe()
    service.seed_core_universe()

    index_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM benchmark_index;
        """
    ).fetchone()[0]

    expected_symbol_count = sum(len(item.get("symbols", [])) for item in CORE_INDICES)

    symbol_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM benchmark_index_symbol;
        """
    ).fetchone()[0]

    assert index_count == len(CORE_INDICES)
    assert symbol_count == expected_symbol_count