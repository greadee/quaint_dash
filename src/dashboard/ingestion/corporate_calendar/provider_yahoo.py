"""Yahoo Finance fallback provider for historical earnings surprises."""

from __future__ import annotations

from datetime import date
import math
from typing import Any

import yfinance as yf

from dashboard.ingestion.corporate_calendar.models import CorporateCalendarEventRow
from dashboard.ingestion.rate_limits import (
    InMemoryRateLimiter,
    RateLimitPolicy,
    default_rate_limiter,
    yfinance_rate_limit_policy,
)


class YahooEarningsProvider:
    """Fetch EPS estimates and reported EPS when the primary source is incomplete."""

    source = "yfinance_earnings_backup"

    def __init__(
        self,
        rate_limiter: InMemoryRateLimiter | None = None,
        rate_limit_policy: RateLimitPolicy | None = None,
    ) -> None:
        self.rate_limiter = rate_limiter or default_rate_limiter()
        self.rate_limit_policy = rate_limit_policy or yfinance_rate_limit_policy(
            provider="yfinance_earnings"
        )

    def fetch_earnings_for_symbol(
        self,
        asset_id: str,
        limit: int = 16,
    ) -> list[CorporateCalendarEventRow]:
        self.rate_limiter.acquire(self.rate_limit_policy)
        frame = yf.Ticker(asset_id).get_earnings_dates(
            limit=min(max(int(limit), 1), 100)
        )
        if frame is None or frame.empty:
            return []

        rows: list[CorporateCalendarEventRow] = []
        for index, item in frame.iterrows():
            earnings_date = self._to_date(index)
            if earnings_date is None:
                continue
            eps_estimated = self._to_float(item.get("EPS Estimate"))
            eps_actual = self._to_float(item.get("Reported EPS"))
            if eps_estimated is None and eps_actual is None:
                continue
            rows.append(
                CorporateCalendarEventRow(
                    asset_id=asset_id.upper(),
                    earnings_date=earnings_date,
                    fiscal_year=None,
                    fiscal_quarter=None,
                    time=None,
                    eps_estimated=eps_estimated,
                    eps_actual=eps_actual,
                    revenue_estimated=None,
                    revenue_actual=None,
                    source=self.source,
                )
            )
        return rows

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None

    @staticmethod
    def _to_date(value: Any) -> date | None:
        if value is None:
            return None
        if hasattr(value, "date"):
            parsed = value.date()
            if isinstance(parsed, date):
                return parsed
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None
