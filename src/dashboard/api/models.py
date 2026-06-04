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


class BrokerUserCreate(BaseModel):
    user_key: str = Field(min_length=1, max_length=100)


class BrokerUserResponse(BaseModel):
    provider: str
    user_key: str
    provider_user_id: str
    status: str


class BrokerPortalRequest(BaseModel):
    user_key: str = Field(min_length=1, max_length=100)
    broker: str | None = None
    reconnect: str | None = None


class BrokerPortalResponse(BaseModel):
    url: str


class BrokerSyncRequest(BaseModel):
    user_key: str = Field(min_length=1, max_length=100)


class BrokerConnectionResponse(BaseModel):
    provider: str
    connection_id: int | None
    provider_connection_id: str
    institution_name: str
    status: str


class BrokerAccountResponse(BaseModel):
    provider: str
    provider_account_id: str
    provider_connection_id: str
    account_name: str | None
    account_type: str | None
    currency: str | None
    balance: float | None
    portfolio_id: int | None


class BrokerAccountMappingRequest(BaseModel):
    portfolio_id: int


class BrokerImportRequest(BaseModel):
    portfolio_id: int | None = None


class ActionResult(BaseModel):
    status: str = "ok"
    result: dict[str, Any] = Field(default_factory=dict)


class IngestionJobResponse(BaseModel):
    job_id: int
    asset_id: str | None
    domain: str
    job_type: str
    dataset: str
    status: str
    priority: int
    requested_start_date: date | None
    requested_end_date: date | None
    attempt_count: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class IngestionScheduleRequest(BaseModel):
    pipeline: str = "all"
    asset_id: str | None = None
    max_assets: int = Field(default=25, ge=1, le=100)
    years: int = Field(default=10, ge=1, le=30)
    prices_only: bool = False


class IngestionRunRequest(BaseModel):
    domain: str = "all"
    max_jobs: int = Field(default=1, ge=1, le=25)
