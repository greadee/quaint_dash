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


class PortfolioUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


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
    projected_value: float | None = None
    projected_value_low: float | None = None
    projected_value_high: float | None = None
    projected_horizon_years: int | None = None


class PositionSummary(BaseModel):
    asset_id: str
    symbol: str
    name: str | None
    asset_type: str | None
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    currency: str
    quantity: float
    book_cost: float
    latest_price: float | None
    market_value: float | None
    unrealized_gain: float | None
    total_return_percent: float | None = None
    weight: float | None
    broker_linked: bool = False
    broker_account_count: int = 0


class AssetHoldingSummary(PositionSummary):
    portfolio_id: int
    portfolio_name: str


class AssetActivitySummary(BaseModel):
    source: str
    provider: str | None = None
    provider_account_id: str | None = None
    provider_transaction_id: str | None = None
    transaction_id: int | None = None
    portfolio_id: int | None = None
    portfolio_name: str | None = None
    timestamp: datetime
    transaction_type: str
    asset_id: str
    symbol: str
    quantity: float | None
    price: float | None
    currency: str | None
    cash_amount: float | None


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
    is_cdr: bool = False
    underlying_asset_id: str | None = None
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


class PriceMoverResponse(BaseModel):
    asset_id: str
    symbol: str
    name: str | None
    latest_price: float | None
    previous_price: float | None
    change: float | None
    change_percent: float | None
    market_value: float | None
    weight: float | None


class NewsItemResponse(BaseModel):
    title: str
    provider: str | None
    published_at: datetime | None
    url: str | None
    asset_id: str | None
    symbol: str | None
    sentiment: str | None


class OverviewUpdatesResponse(BaseModel):
    total_market_value: float
    position_count: int
    mover_count: int
    news_count: int
    price_movers: list[PriceMoverResponse]
    news: list[NewsItemResponse]


class ComparisonReturns(BaseModel):
    return_1d: float | None = None
    return_5d: float | None = None
    return_21d: float | None = None
    return_252d: float | None = None


class ComparisonFundamentals(BaseModel):
    revenue: float | None = None
    net_income: float | None = None
    eps: float | None = None
    pe_ratio: float | None = None
    price_to_sales: float | None = None


class ValuationContext(BaseModel):
    historical_pe_average: float | None = None
    historical_pe_discount: float | None = None
    sector_pe_average: float | None = None
    sector_pe_premium: float | None = None
    industry_pe_average: float | None = None
    industry_pe_premium: float | None = None


class ComparisonAssetProfile(BaseModel):
    asset_id: str
    symbol: str
    name: str | None
    sector: str | None
    industry: str | None
    country: str | None
    currency: str
    latest_price: float | None
    market_cap: float | None
    market_beta: float | None
    returns: ComparisonReturns
    fundamentals: ComparisonFundamentals
    valuation: ValuationContext


class BenchmarkComparisonProfile(BaseModel):
    index_id: str
    name: str
    category: str
    currency: str
    return_1d: float | None = None
    return_21d: float | None = None
    return_252d: float | None = None
    volatility_252d: float | None = None


class ComparisonResponse(BaseModel):
    left: ComparisonAssetProfile
    right: ComparisonAssetProfile | None = None
    benchmark: BenchmarkComparisonProfile | None = None
    insights: list[str] = Field(default_factory=list)


class BrokerUserCreate(BaseModel):
    user_key: str = Field(min_length=1, max_length=100)


class BrokerExistingUserCreate(BaseModel):
    user_key: str = Field(min_length=1, max_length=100)
    provider_user_id: str = Field(min_length=1, max_length=100)
    user_secret: str = Field(min_length=1)


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


class IngestionBackgroundStatusResponse(BaseModel):
    enabled: bool
    running: bool
    last_schedule_at: datetime | None = None
    last_schedule_count: int | None = None
    last_run_at: datetime | None = None
    last_completed_count: int | None = None
    last_error: str | None = None
    schedule_interval_seconds: int
    run_interval_seconds: int
    max_jobs_per_tick: int
    max_assets_per_schedule: int
    years: int
    prices_only: bool


class IngestionScheduleRequest(BaseModel):
    pipeline: str = "all"
    asset_id: str | None = None
    max_assets: int = Field(default=25, ge=1, le=100)
    years: int = Field(default=10, ge=1, le=30)
    prices_only: bool = False


class IngestionRunRequest(BaseModel):
    domain: str = "all"
    max_jobs: int = Field(default=1, ge=1, le=25)


class IngestionRetryFailedRequest(BaseModel):
    domain: str | None = None
    max_jobs: int = Field(default=25, ge=1, le=100)
