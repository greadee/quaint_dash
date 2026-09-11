"""Yahoo Finance fallback for quarterly financial statements."""

from __future__ import annotations

from datetime import date
import math
from typing import Any

import yfinance as yf

from dashboard.ingestion.corporate_calendar.models import FinancialStatementRow
from dashboard.ingestion.price_history.provider_yahoo import yahoo_symbol_for_asset_id
from dashboard.ingestion.rate_limits import (
    InMemoryRateLimiter,
    RateLimitPolicy,
    default_rate_limiter,
    yfinance_rate_limit_policy,
)


_STATEMENTS = {
    "income": (
        "get_income_stmt",
        {
            "revenue": ("TotalRevenue", "OperatingRevenue"),
            "grossProfit": ("GrossProfit",),
            "operatingIncome": ("OperatingIncome",),
            "netIncome": ("NetIncome", "NetIncomeCommonStockholders"),
            "eps": ("DilutedEPS", "BasicEPS"),
            "ebitda": ("EBITDA", "NormalizedEBITDA"),
            "weightedAverageShsOutDil": (
                "DilutedAverageShares",
                "BasicAverageShares",
            ),
        },
    ),
    "balance": (
        "get_balance_sheet",
        {
            "totalDebt": ("TotalDebt",),
            "totalStockholdersEquity": (
                "StockholdersEquity",
                "TotalEquityGrossMinorityInterest",
            ),
            "totalAssets": ("TotalAssets",),
            "cashAndCashEquivalents": (
                "CashCashEquivalentsAndShortTermInvestments",
                "CashAndCashEquivalents",
            ),
        },
    ),
    "cashflow": (
        "get_cash_flow",
        {
            "freeCashFlow": ("FreeCashFlow",),
            "operatingCashFlow": (
                "OperatingCashFlow",
                "TotalCashFromOperatingActivities",
            ),
            "capitalExpenditure": ("CapitalExpenditure",),
        },
    ),
}


class YahooFundamentalsProvider:
    """Fetch provider-reported statement values when FMP is unavailable."""

    source = "yfinance_fundamentals_backup"

    def __init__(
        self,
        rate_limiter: InMemoryRateLimiter | None = None,
        rate_limit_policy: RateLimitPolicy | None = None,
    ) -> None:
        self.rate_limiter = rate_limiter or default_rate_limiter()
        self.rate_limit_policy = rate_limit_policy or yfinance_rate_limit_policy(
            provider="yfinance_fundamentals"
        )

    def fetch_quarterly_statements(
        self,
        asset_id: str,
        limit: int = 16,
    ) -> list[FinancialStatementRow]:
        ticker = yf.Ticker(yahoo_symbol_for_asset_id(asset_id))
        rows: list[FinancialStatementRow] = []
        successful_requests = 0
        errors: list[Exception] = []

        for statement_type, (method_name, field_map) in _STATEMENTS.items():
            try:
                self.rate_limiter.acquire(self.rate_limit_policy)
                frame = getattr(ticker, method_name)(freq="quarterly")
                successful_requests += 1
            except Exception as exc:
                errors.append(exc)
                continue
            if frame is None or frame.empty:
                continue

            for period in list(frame.columns)[: max(1, int(limit))]:
                period_end = _to_date(period)
                if period_end is None:
                    continue
                values = frame[period]
                payload = {
                    output_name: value
                    for output_name, aliases in field_map.items()
                    if (value := _first_value(values, aliases)) is not None
                }
                if not payload:
                    continue
                rows.append(
                    FinancialStatementRow(
                        asset_id=asset_id.upper(),
                        statement_type=statement_type,
                        fiscal_year=period_end.year,
                        fiscal_quarter=((period_end.month - 1) // 3) + 1,
                        period_end_date=period_end,
                        report_date=None,
                        data_json=payload,
                        source=self.source,
                    )
                )

        if successful_requests == 0:
            detail = str(errors[-1]) if errors else "no statement response"
            raise RuntimeError(f"Yahoo fundamentals unavailable for {asset_id}: {detail}")
        return rows


def _first_value(values: Any, aliases: tuple[str, ...]) -> float | None:
    for alias in aliases:
        try:
            raw = values.get(alias)
        except AttributeError:
            raw = None
        parsed = _to_float(raw)
        if parsed is not None:
            return parsed
    return None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


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
