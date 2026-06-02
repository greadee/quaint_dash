from datetime import date
import pytest
from dashboard.db.db_conn import DB, init_db
from dashboard.models.storage import DashboardManager
from dashboard.ingestion.trading_calendar.service import TradingCalendarIngestionService
from dashboard.ingestion.trading_calendar.provider import TradingCalendarDay

@pytest.fixture
def manager(tmp_path):
    db_path = tmp_path / "test.db"

    db = DB(str(db_path))
    init_db(db)

    return DashboardManager(db)

class FakeTradingCalendarProvider:
    source = "fake_calendar"

    def build_days(self, market_code, start_date, end_date):
        return [
            TradingCalendarDay(
                market_code=market_code,
                exchange_code="XNYS" if market_code == "US" else "XTSE",
                session_date=date(2026, 1, 1),
                is_open=False,
                is_half_day=False,
                open_time_utc=None,
                close_time_utc=None,
                open_time_local=None,
                close_time_local=None,
                timezone="America/New_York",
                holiday_name="New Year's Day",
                source=self.source,
                source_version="test",
            ),
            TradingCalendarDay(
                market_code=market_code,
                exchange_code="XNYS" if market_code == "US" else "XTSE",
                session_date=date(2026, 1, 2),
                is_open=True,
                is_half_day=False,
                open_time_utc=None,
                close_time_utc=None,
                open_time_local="09:30:00",
                close_time_local="16:00:00",
                timezone="America/New_York",
                holiday_name=None,
                source=self.source,
                source_version="test",
            ),
        ]


def test_trading_calendar_refresh_upserts_days(manager):
    service = TradingCalendarIngestionService(
        manager.conn,
        provider=FakeTradingCalendarProvider(),
    )

    n = service.refresh_market("US", date(2026, 1, 1), date(2026, 1, 2))

    assert n == 2

    rows = manager.conn.execute("""
        SELECT session_date, is_open
        FROM trading_calendar
        WHERE market_code = 'US'
        ORDER BY session_date;
    """).fetchall()

    assert rows == [
        (date(2026, 1, 1), False),
        (date(2026, 1, 2), True),
    ]


def test_is_market_open_day_returns_false_for_closed_day(manager):
    service = TradingCalendarIngestionService(
        manager.conn,
        provider=FakeTradingCalendarProvider(),
    )

    service.refresh_market("US", date(2026, 1, 1), date(2026, 1, 2))

    assert service.is_market_open_day("US", date(2026, 1, 1)) is False
    assert service.is_market_open_day("US", date(2026, 1, 2)) is True