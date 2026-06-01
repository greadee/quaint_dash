# src/dashboard/ingestion/fundamentals/refresh_service.py

from __future__ import annotations


class ExistingStatementIngestionAdapter:
    """
    Adapter around the project's existing financial statement ingestion service.

    This keeps Phase 1 focused on subscription/scheduling/worker orchestration.
    """

    METHOD_NAMES = (
        "refresh_latest_financial_statements",
        "refresh_latest_fundamentals",
        "refresh_asset",
        "ingest_latest_for_asset",
    )

    def __init__(self, statement_ingestion_service):
        self.statement_ingestion_service = statement_ingestion_service

    def refresh_latest(self, asset_id: str) -> None:
        for method_name in self.METHOD_NAMES:
            method = getattr(self.statement_ingestion_service, method_name, None)

            if method is not None:
                method(asset_id)
                return

        raise AttributeError(
            "Existing financial statement ingestion service does not expose "
            "a supported refresh method. Add your method name to "
            "ExistingStatementIngestionAdapter.METHOD_NAMES."
        )


class FundamentalRefreshService:
    def __init__(self, statement_ingestion_service):
        self.statement_adapter = ExistingStatementIngestionAdapter(
            statement_ingestion_service
        )

    def refresh_asset(self, asset_id: str) -> None:
        """
        Refreshes latest fundamentals for one asset.

        The actual financial statement ingestion is delegated to the existing
        statement ingestion code.
        """

        self.statement_adapter.refresh_latest(asset_id)
