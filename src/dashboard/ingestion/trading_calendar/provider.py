from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas_market_calendars as mcal


MARKET_CONFIG = {
    "US": {
        "exchange_code": "XNYS",
        "calendar_name": "NYSE",
        "timezone": "America/New_York",
    },
    "CAN": {
        "exchange_code": "XTSE",
        "calendar_name": "TSX",
        "timezone": "America/Toronto",
    },
}


@dataclass
class TradingCalendarDay:
    market_code: str
    exchange_code: str
    session_date: date
    is_open: bool
    is_half_day: bool
    open_time_utc: Any | None
    close_time_utc: Any | None
    open_time_local: str | None
    close_time_local: str | None
    timezone: str
    holiday_name: str | None
    source: str
    source_version: str | None


class TradingCalendarProvider:
    """
    Builds exchange trading calendars locally with pandas_market_calendars.
    """

    source = "pandas_market_calendars"

    def build_days(
        self,
        market_code: str,
        start_date: date,
        end_date: date,
    ) -> list[TradingCalendarDay]:
        market_code = market_code.upper().strip()

        if market_code not in MARKET_CONFIG:
            raise ValueError(f"Unsupported market_code: {market_code}")

        cfg = MARKET_CONFIG[market_code]
        cal = mcal.get_calendar(cfg["calendar_name"])

        schedule = cal.schedule(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )

        early_closes = mcal.early_closes(schedule)

        open_by_date = {
            idx.date(): row
            for idx, row in schedule.iterrows()
        }

        half_days = {idx.date() for idx in early_closes.index}

        days: list[TradingCalendarDay] = []
        current = start_date

        while current <= end_date:
            row = open_by_date.get(current)

            if row is None:
                days.append(
                    TradingCalendarDay(
                        market_code=market_code,
                        exchange_code=cfg["exchange_code"],
                        session_date=current,
                        is_open=False,
                        is_half_day=False,
                        open_time_utc=None,
                        close_time_utc=None,
                        open_time_local=None,
                        close_time_local=None,
                        timezone=cfg["timezone"],
                        holiday_name=None,
                        source=self.source,
                        source_version=None,
                    )
                )
            else:
                market_open = row["market_open"]
                market_close = row["market_close"]

                days.append(
                    TradingCalendarDay(
                        market_code=market_code,
                        exchange_code=cfg["exchange_code"],
                        session_date=current,
                        is_open=True,
                        is_half_day=current in half_days,
                        open_time_utc=market_open.to_pydatetime(),
                        close_time_utc=market_close.to_pydatetime(),
                        open_time_local=str(market_open.tz_convert(cfg["timezone"]).time()),
                        close_time_local=str(market_close.tz_convert(cfg["timezone"]).time()),
                        timezone=cfg["timezone"],
                        holiday_name=None,
                        source=self.source,
                        source_version=None,
                    )
                )

            current += timedelta(days=1)

        return days