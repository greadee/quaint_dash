from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class IndexSymbol:
    index_id: str
    provider: str
    provider_symbol: str
    symbol_purpose: str
    is_primary: bool
    is_proxy: bool


@dataclass(frozen=True)
class IndexDailyBar:
    index_id: str
    price_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float
    adj_close: float | None
    volume: float | None
    source: str
    source_symbol: str
    is_proxy: bool


@dataclass(frozen=True)
class IndexIntradayBar:
    index_id: str
    interval: str
    bar_start_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    source: str
    source_symbol: str
    is_proxy: bool


@dataclass(frozen=True)
class IndexConstituent:
    index_id: str
    constituent_symbol: str
    constituent_name: str | None
    exchange_code: str | None
    country_code: str | None
    currency: str | None
    sector: str | None
    industry: str | None
    weight_pct: float | None
    market_cap: float | None
    source: str
    is_proxy: bool


@dataclass(frozen=True)
class IndexCompositionSnapshot:
    index_id: str
    snapshot_date: date
    source: str
    source_symbol: str | None
    source_type: str
    is_proxy: bool
    constituent_count: int
    total_weight_pct: float | None
    data_quality: str
    notes: str | None