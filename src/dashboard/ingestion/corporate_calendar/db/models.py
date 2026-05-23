"""
dataclasses for corporate calendar ingestion
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional


@dataclass(slots=True)
class CorporateCalendarEventRow:
    asset_id: str
    earnings_date: date
    fiscal_year: Optional[int]
    fiscal_quarter: Optional[int]
    time: Optional[str]
    eps_estimated: Optional[float]
    eps_actual: Optional[float]
    revenue_estimated: Optional[float]
    revenue_actual: Optional[float]
    source: str = "fmp"


@dataclass(slots=True)
class FinancialStatementRow:
    asset_id: str
    statement_type: str
    fiscal_year: int
    fiscal_quarter: int
    period_end_date: date
    report_date: Optional[date]
    data_json: dict[str, Any]
    source: str = "fmp"


@dataclass(slots=True)
class CorporateIngestionJob:
    job_id: int
    asset_id: str
    domain: str
    job_type: str
    dataset: str
    status: str
    priority: int
    requested_start_date: Optional[date]
    requested_end_date: Optional[date]
    attempt_count: int
    error_message: Optional[str]