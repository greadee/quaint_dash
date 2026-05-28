from dashboard.ingestion.indices.fmp_index_provider import FMPIndexProvider
from dashboard.ingestion.indices.index_ingestion_service import BenchmarkIndexIngestionService
from dashboard.ingestion.indices.index_scheduler import BenchmarkIndexScheduler
from dashboard.ingestion.indices.yfinance_index_provider import YFinanceIndexProvider


def create_index_provider_registry():
    """
    Central place for benchmark index providers.

    Provider priority is mostly controlled by benchmark_index_symbol rows:
    - yfinance should usually be primary for prices
    - FMP should usually be fallback for prices
    - FMP should be primary for supported constituents
    """
    return {
        "yfinance": YFinanceIndexProvider(),
        "fmp": FMPIndexProvider(),
    }


def create_index_ingestion_service(conn):
    return BenchmarkIndexIngestionService(
        conn=conn,
        provider_registry=create_index_provider_registry(),
    )


def create_index_scheduler(conn):
    service = create_index_ingestion_service(conn)

    return BenchmarkIndexScheduler(
        conn=conn,
        service=service,
    )