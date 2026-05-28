from datetime import datetime, timezone

from dashboard.ingestion.websocket.session_classifier import MarketSessionClassifier


def _insert_us_trading_day(conn):
    conn.execute(
        """
        INSERT INTO trading_calendar(
            market_code,
            session_date,
            is_open,
            open_time_utc,
            close_time_utc
        )
        VALUES (
            'US',
            DATE '2026-05-27',
            TRUE,
            TIMESTAMP '2026-05-27 13:30:00',
            TIMESTAMP '2026-05-27 20:00:00'
        )
        """
    )


def test_regular_session_is_detected(conn):
    _insert_us_trading_day(conn)

    classifier = MarketSessionClassifier(conn)

    now_utc = datetime(2026, 5, 27, 14, 0, 0, tzinfo=timezone.utc)

    assert classifier.classify_us_session(now_utc) == "regular"


def test_pre_market_session_is_detected(conn):
    _insert_us_trading_day(conn)

    classifier = MarketSessionClassifier(conn)

    # 12:00 UTC = 08:00 ET
    now_utc = datetime(2026, 5, 27, 12, 0, 0, tzinfo=timezone.utc)

    assert classifier.classify_us_session(now_utc) == "pre"


def test_after_hours_session_is_detected(conn):
    _insert_us_trading_day(conn)

    classifier = MarketSessionClassifier(conn)

    # 21:30 UTC = 17:30 ET
    now_utc = datetime(2026, 5, 27, 21, 30, 0, tzinfo=timezone.utc)

    assert classifier.classify_us_session(now_utc) == "after"


def test_closed_session_is_detected_after_extended_hours(conn):
    _insert_us_trading_day(conn)

    classifier = MarketSessionClassifier(conn)

    # 02:30 UTC on May 28 = 22:30 ET on May 27
    now_utc = datetime(2026, 5, 28, 2, 30, 0, tzinfo=timezone.utc)

    assert classifier.classify_us_session(now_utc) == "closed"


def test_missing_calendar_day_is_closed(conn):
    classifier = MarketSessionClassifier(conn)

    now_utc = datetime(2026, 5, 30, 14, 0, 0, tzinfo=timezone.utc)

    assert classifier.classify_us_session(now_utc) == "closed"