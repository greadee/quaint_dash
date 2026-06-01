from __future__ import annotations

import pytest

from dashboard.ingestion.fundamentals.refresh_service import (
    ExistingStatementIngestionAdapter,
    FundamentalRefreshService,
)


class StatementServiceWithPreferredMethod:
    def __init__(self):
        self.calls = []

    def refresh_latest_financial_statements(self, asset_id):
        self.calls.append(("refresh_latest_financial_statements", asset_id))

    def refresh_asset(self, asset_id):
        self.calls.append(("refresh_asset", asset_id))


class StatementServiceWithFallbackMethod:
    def __init__(self):
        self.calls = []

    def ingest_latest_for_asset(self, asset_id):
        self.calls.append(("ingest_latest_for_asset", asset_id))


class UnsupportedStatementService:
    pass


def test_existing_statement_adapter_uses_first_supported_method():
    statement_service = StatementServiceWithPreferredMethod()
    adapter = ExistingStatementIngestionAdapter(statement_service)

    adapter.refresh_latest("AAPL")

    assert statement_service.calls == [("refresh_latest_financial_statements", "AAPL")]


def test_existing_statement_adapter_uses_later_supported_method_when_needed():
    statement_service = StatementServiceWithFallbackMethod()
    adapter = ExistingStatementIngestionAdapter(statement_service)

    adapter.refresh_latest("MSFT")

    assert statement_service.calls == [("ingest_latest_for_asset", "MSFT")]


def test_existing_statement_adapter_raises_clear_error_when_service_is_unsupported():
    adapter = ExistingStatementIngestionAdapter(UnsupportedStatementService())

    with pytest.raises(AttributeError, match="does not expose a supported refresh method"):
        adapter.refresh_latest("AAPL")


def test_fundamental_refresh_service_delegates_to_adapter():
    statement_service = StatementServiceWithFallbackMethod()
    service = FundamentalRefreshService(statement_service)

    service.refresh_asset("BN.TO")

    assert statement_service.calls == [("ingest_latest_for_asset", "BN.TO")]
