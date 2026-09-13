from datetime import date

import pandas as pd

from dashboard.ingestion.corporate_calendar.provider_yahoo_fundamentals import (
    YahooFundamentalsProvider,
)
from dashboard.ingestion.rate_limits import InMemoryRateLimiter, RateLimitPolicy


def test_yahoo_fundamentals_provider_maps_quarterly_statement_values(monkeypatch):
    period = pd.Timestamp("2026-06-30")

    class FakeTicker:
        def get_income_stmt(self, *, freq):
            assert freq == "quarterly"
            return pd.DataFrame({period: {"TotalRevenue": 100.0, "NetIncome": 12.0}})

        def get_balance_sheet(self, *, freq):
            assert freq == "quarterly"
            return pd.DataFrame({period: {"TotalAssets": 250.0, "TotalDebt": 40.0}})

        def get_cash_flow(self, *, freq):
            assert freq == "quarterly"
            return pd.DataFrame({period: {"FreeCashFlow": 18.0}})

    monkeypatch.setattr(
        "dashboard.ingestion.corporate_calendar.provider_yahoo_fundamentals.yf.Ticker",
        lambda symbol: FakeTicker(),
    )
    provider = YahooFundamentalsProvider(
        rate_limiter=InMemoryRateLimiter(),
        rate_limit_policy=RateLimitPolicy("test-yahoo-fundamentals", calls=10),
    )

    rows = provider.fetch_quarterly_statements("U.UN.TO")

    assert [(row.statement_type, row.period_end_date) for row in rows] == [
        ("income", date(2026, 6, 30)),
        ("balance", date(2026, 6, 30)),
        ("cashflow", date(2026, 6, 30)),
    ]
    assert rows[0].data_json == {"revenue": 100.0, "netIncome": 12.0}
    assert all(row.source == "yfinance_fundamentals_backup" for row in rows)
