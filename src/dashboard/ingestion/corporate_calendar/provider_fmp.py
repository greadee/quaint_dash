"""
FMP provider wrapper for earnings calendar, earnings actuals, and financial statements.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from dotenv import load_dotenv

from dashboard.ingestion.rate_limits import (
    InMemoryRateLimiter,
    RateLimitExceeded,
    RateLimitPolicy,
    default_rate_limiter,
    fmp_rate_limit_policy,
)
from dashboard.ingestion.corporate_calendar.models import (
    CorporateCalendarEventRow,
    FinancialStatementRow,
)

load_dotenv()


class FmpEntitlementError(RuntimeError):
    """Raised when the configured FMP plan cannot access the requested endpoint."""


class FmpCorporateCalendarProvider:
    """
    FMP stable endpoint provider.
    """

    source = "fmp"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://financialmodelingprep.com/stable",
        rate_limiter: InMemoryRateLimiter | None = None,
        rate_limit_policy: RateLimitPolicy | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.rate_limiter = rate_limiter or default_rate_limiter()
        self.rate_limit_policy = rate_limit_policy or fmp_rate_limit_policy()

        if not self.api_key:
            raise RuntimeError("FMP_API_KEY not found in environment or .env file")

    def _get_json(self, path: str, params: dict[str, Any]) -> Any:
        query = dict(params)
        query["apikey"] = self.api_key

        url = f"{self.base_url}/{path.lstrip('/')}?{urllib.parse.urlencode(query)}"

        try:
            self.rate_limiter.acquire(self.rate_limit_policy)
            with urllib.request.urlopen(url, timeout=20) as response:
                status = getattr(response, "status", 200)
                if status == 429:
                    raise RateLimitExceeded("FMP rate limit exceeded")
                if status != 200:
                    raise RuntimeError(f"FMP request failed with status {status}")
                payload = response.read().decode("utf-8")

        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise RateLimitExceeded("FMP rate limit exceeded") from exc
            if exc.code == 402:
                raise FmpEntitlementError(
                    "FMP HTTP error 402: plan does not include this corporate endpoint"
                ) from exc
            raise RuntimeError(f"FMP HTTP error {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"FMP connection error: {exc.reason}") from exc

        data = json.loads(payload)

        if isinstance(data, dict) and "Error Message" in data:
            message = str(data["Error Message"])
            if "limit" in message.lower() or "rate" in message.lower():
                raise RateLimitExceeded(message)
            raise RuntimeError(message)

        return data

    def fetch_earnings_calendar(
        self,
        start_date: date,
        end_date: date,
    ) -> list[CorporateCalendarEventRow]:
        data = self._get_json(
            "earnings-calendar",
            {
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
            },
        )

        rows: list[CorporateCalendarEventRow] = []

        for item in data or []:
            symbol = item.get("symbol")
            earnings_date = self._to_date(item.get("date"))

            if not symbol or earnings_date is None:
                continue

            rows.append(
                CorporateCalendarEventRow(
                    asset_id=symbol.upper(),
                    earnings_date=earnings_date,
                    fiscal_year=self._to_int(item.get("fiscalYear") or item.get("year")),
                    fiscal_quarter=self._to_quarter(item.get("quarter")),
                    time=item.get("time") or item.get("epsTime"),
                    eps_estimated=self._to_float(item.get("epsEstimated") or item.get("epsEstimate")),
                    eps_actual=self._to_float(item.get("eps") or item.get("epsActual")),
                    revenue_estimated=self._to_float(item.get("revenueEstimated")),
                    revenue_actual=self._to_float(item.get("revenue")),
                    source=self.source,
                )
            )

        return rows

    def fetch_earnings_for_symbol(
        self,
        asset_id: str,
        limit: int = 16,
    ) -> list[CorporateCalendarEventRow]:
        data = self._get_json(
            "earnings",
            {
                "symbol": asset_id,
                "limit": limit,
            },
        )

        rows: list[CorporateCalendarEventRow] = []

        for item in data or []:
            earnings_date = self._to_date(item.get("date"))

            if earnings_date is None:
                continue

            rows.append(
                CorporateCalendarEventRow(
                    asset_id=asset_id.upper(),
                    earnings_date=earnings_date,
                    fiscal_year=self._to_int(item.get("fiscalYear") or item.get("year")),
                    fiscal_quarter=self._to_quarter(item.get("quarter")),
                    time=item.get("time") or item.get("epsTime"),
                    eps_estimated=self._to_float(item.get("epsEstimated") or item.get("epsEstimate")),
                    eps_actual=self._to_float(item.get("eps") or item.get("epsActual")),
                    revenue_estimated=self._to_float(item.get("revenueEstimated")),
                    revenue_actual=self._to_float(item.get("revenue")),
                    source=self.source,
                )
            )

        return rows

    def fetch_quarterly_statements(
        self,
        asset_id: str,
        limit: int = 16,
    ) -> list[FinancialStatementRow]:
        rows: list[FinancialStatementRow] = []

        endpoints = {
            "income": "income-statement",
            "balance": "balance-sheet-statement",
            "cashflow": "cash-flow-statement",
        }

        for statement_type, path in endpoints.items():
            data = self._get_json(
                path,
                {
                    "symbol": asset_id,
                    "period": "quarter",
                    "limit": limit,
                },
            )

            for item in data or []:
                fiscal_year = self._to_int(item.get("calendarYear") or item.get("fiscalYear"))
                fiscal_quarter = self._period_to_quarter(str(item.get("period") or "").upper())
                period_end = self._to_date(item.get("date") or item.get("fillingDate"))

                if fiscal_year is None or fiscal_quarter is None or period_end is None:
                    continue

                rows.append(
                    FinancialStatementRow(
                        asset_id=asset_id.upper(),
                        statement_type=statement_type,
                        fiscal_year=fiscal_year,
                        fiscal_quarter=fiscal_quarter,
                        period_end_date=period_end,
                        report_date=self._to_date(item.get("fillingDate") or item.get("acceptedDate")),
                        data_json=item,
                        source=self.source,
                    )
                )

        return rows

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        if value in (None, ""):
            return None

        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_date(value: Any) -> Optional[date]:
        if not value:
            return None

        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    @staticmethod
    def _period_to_quarter(period: str) -> Optional[int]:
        if period in {"Q1", "Q2", "Q3", "Q4"}:
            return int(period[1])
        if period in {"FY", "ANNUAL"}:
            return 4

        return None

    @staticmethod
    def _to_quarter(value: Any) -> Optional[int]:
        q = FmpCorporateCalendarProvider._to_int(value)

        if q in (1, 2, 3, 4):
            return q

        return None
