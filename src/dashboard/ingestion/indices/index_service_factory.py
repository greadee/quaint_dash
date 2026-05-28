from dashboard.ingestion.indices.fmp_index_provider import FMPIndexProvider
from dashboard.ingestion.indices.index_ingestion_service import BenchmarkIndexIngestionService
from dashboard.ingestion.indices.index_scheduler import BenchmarkIndexScheduler
from dashboard.ingestion.indices.yfinance_index_provider import YFinanceIndexProvider


def create_index_provider_registry():
    fmp_provider = FMPIndexProvider()

    return {
        "yfinance": YFinanceIndexProvider(),
        "fmp": fmp_provider,

        # Backward compatibility for earlier core proxy rows if any used
        # provider="etf_proxy".
        "etf_proxy": fmp_provider,
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