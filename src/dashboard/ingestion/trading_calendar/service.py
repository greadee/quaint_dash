from dataclasses import dataclass
from datetime import date

from dashboard.db import queries as qry
from dashboard.ingestion.trading_calendar.provider import (
    MARKET_CONFIG,
    TradingCalendarProvider,
    TradingCalendarDay,
)


@dataclass
class TradingCalendarIngestionService:
    conn: object
    provider: TradingCalendarProvider | None = None

    def __post_init__(self):
        if self.provider is None:
            self.provider = TradingCalendarProvider()

    def refresh_market(
        self,
        market_code: str,
        start_date: date,
        end_date: date,
    ) -> int:
        market_code = market_code.upper().strip()

        if market_code not in MARKET_CONFIG:
            raise ValueError(f"Unsupported market_code: {market_code}")

        cfg = MARKET_CONFIG[market_code]

        self.conn.execute(
            qry.MARK_TRADING_CALENDAR_SYNC_RUNNING,
            [market_code, cfg["exchange_code"], self.provider.source],
        )

        try:
            days = self.provider.build_days(market_code, start_date, end_date)

            for day in days:
                self._upsert_day(day)

            self.conn.execute(
                qry.MARK_TRADING_CALENDAR_SYNC_SUCCESS,
                [start_date, end_date, market_code],
            )

            return len(days)

        except Exception as exc:
            self.conn.execute(
                qry.MARK_TRADING_CALENDAR_SYNC_FAILED,
                [str(exc), market_code],
            )
            raise

    def refresh_all(
        self,
        start_date: date,
        end_date: date,
    ) -> int:
        total = 0
        for market_code in MARKET_CONFIG:
            total += self.refresh_market(market_code, start_date, end_date)
        return total

    def is_market_open_day(self, market_code: str, session_date: date) -> bool:
        row = self.conn.execute(
            qry.IS_MARKET_OPEN_DAY,
            [market_code.upper().strip(), session_date],
        ).fetchone()

        if row is None:
            return False

        return bool(row[0])

    def _upsert_day(self, day: TradingCalendarDay) -> None:
        self.conn.execute(
            qry.UPSERT_TRADING_CALENDAR_DAY,
            [
                day.market_code,
                day.exchange_code,
                day.session_date,
                day.is_open,
                day.is_half_day,
                day.open_time_utc,
                day.close_time_utc,
                day.open_time_local,
                day.close_time_local,
                day.timezone,
                day.holiday_name,
                day.source,
                day.source_version,
            ],
        )