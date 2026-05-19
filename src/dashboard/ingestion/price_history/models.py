"""
dataclasses for Domain A market ingestion
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(slots=True)
class PriceDailyRow:
    asset_id: str
    price_date: date
    open_price: Optional[float]
    high_price: Optional[float]
    low_price: Optional[float]
    close_price: Optional[float]
    adj_close_price: Optional[float]
    volume: Optional[int]
    source: str = "fmp"


@dataclass(slots=True)
class DividendEventRow:
    asset_id: str
    ex_date: date
    payment_date: Optional[date]
    record_date: Optional[date]
    declaration_date: Optional[date]
    dividend_per_share: Optional[float]
    currency: Optional[str]
    source: str = "fmp"


@dataclass(slots=True)
class SplitEventRow:
    asset_id: str
    ex_date: date
    split_from: Optional[int]
    split_to: Optional[int]
    source: str = "fmp"


@dataclass(slots=True)
class IngestionJob:
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