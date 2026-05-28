from datetime import datetime, time
from zoneinfo import ZoneInfo


class MarketSessionClassifier:
    def __init__(self, conn):
        self.conn = conn

    def classify_us_session(self, now_utc: datetime) -> str:
        eastern = now_utc.astimezone(ZoneInfo("America/New_York"))
        session_date = eastern.date()
        local_time = eastern.time()

        row = self.conn.execute(
            """
            SELECT is_open, open_time_utc, close_time_utc
            FROM trading_calendar
            WHERE market_code = 'US'
              AND session_date = ?
            """,
            [session_date],
        ).fetchone()

        if row is None or not row[0]:
            return "closed"

        _, open_time_utc, close_time_utc = row

        if open_time_utc <= now_utc.replace(tzinfo=None) <= close_time_utc:
            return "regular"

        if time(4, 0) <= local_time < time(9, 30):
            return "pre"

        if time(16, 0) <= local_time <= time(20, 0):
            return "after"

        return "closed"