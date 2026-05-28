from dashboard.ingestion.indices.index_ingestion_service import BenchmarkIndexIngestionService

from tests.fixtures.fixture_index import FakeIntradayProvider, insert_test_index, insert_test_symbol


def test_intraday_price_ingestion_deduplicates_bars(conn):
    insert_test_index(conn)
    insert_test_symbol(
        conn,
        provider="fake",
        provider_symbol="^GSPC",
        symbol_purpose="price_intraday",
    )

    service = BenchmarkIndexIngestionService(
        conn,
        provider_registry={"fake": FakeIntradayProvider()},
    )

    first_count = service.ingest_intraday_prices("SP500", interval="5min")
    second_count = service.ingest_intraday_prices("SP500", interval="5min")

    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM benchmark_index_intraday_price
        WHERE index_id = 'SP500'
          AND interval = '5min';
        """
    ).fetchone()

    assert first_count == 1
    assert second_count == 1
    assert row[0] == 1