"""Contracts between command services and the production database schema."""

from dashboard.analytics import AnalyticsRepository
from dashboard.brokers.repository import BrokerSyncRepository
from dashboard.db.db_conn import DB, init_db
from dashboard.models.storage import DashboardManager


def test_production_schema_contains_command_service_tables(tmp_path):
    db = DB(tmp_path / "schema_contract.db")
    init_db(db)

    tables = {
        row[0]
        for row in db.conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main'
            """
        ).fetchall()
    }

    assert {
        "asset",
        "portfolio",
        "position",
        "txn",
        "asset_quote_daily",
        "broker_storage_config",
        "current_asset_price",
        "live_price_tick",
        "live_price_provider_health",
        "candidate_run",
        "candidate_review",
        "candidate_evidence",
    } <= tables


def test_command_services_query_the_production_schema(tmp_path):
    db = DB(tmp_path / "service_contract.db")
    init_db(db)
    manager = DashboardManager(db)

    assert AnalyticsRepository(db.conn).data_coverage().asset_count == 0
    assert BrokerSyncRepository(db.conn).raw_payload_storage_enabled() is True
    assert manager.get_current_live_prices() == []
    assert manager.get_live_price_for_asset("AAPL") is None
