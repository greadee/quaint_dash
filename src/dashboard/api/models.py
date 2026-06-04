"""Public API request and response models."""

from datetime import date, datetime
from typing import Generic, TypeVar
from typing import Any

from pydantic import BaseModel, Field

T = TypeVar("T")


class HealthResponse(BaseModel):
    status: str
    api_version: str
    database: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    base_ccy: str = Field(default="CAD", min_length=3, max_length=3)


class PortfolioSummary(BaseModel):
    portfolio_id: int
    name: str
    base_ccy: str
    created_at: datetime
    updated_at: datetime
    position_count: int
    market_value: float
    book_cost: float
    unrealized_gain: float | None


class PositionSummary(BaseModel):
    asset_id: str
    symbol: str
    name: str | None
    asset_type: str | None
    currency: str
    quantity: float
    book_cost: float
    latest_price: float | None
    market_value: float | None
    unrealized_gain: float | None
    weight: float | None


class TransactionSummary(BaseModel):
    transaction_id: int
    portfolio_id: int
    timestamp: datetime
    transaction_type: str
    asset_id: str | None
    quantity: float | None
    price: float | None
    currency: str | None
    cash_amount: float | None
    fee_amount: float | None
    batch_id: int


class AssetDetail(BaseModel):
    asset_id: str
    symbol: str
    exchange_code: str | None
    asset_type: str | None
    asset_subtype: str | None
    currency: str
    name: str | None
    description: str | None
    sector: str | None
    industry: str | None
    country: str | None
    region: str | None
    size: str | None
    market_cap: float | None
    shares_outstanding: float | None
    market_beta: float | None
    latest_price: float | None


class PricePointResponse(BaseModel):
    date: date
    close: float
