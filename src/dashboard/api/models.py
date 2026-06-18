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


class AssetSearchResult(BaseModel):
    asset_id: str
    symbol: str
    name: str | None
    asset_type: str | None
    sector: str | None
    industry: str | None
    country: str | None
    currency: str
    latest_price: float | None = None


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


class HoldingSignalComponent(BaseModel):
    name: str
    metric: str
    value: float | None = None
    contribution: float | None = None
    detail: str


class HoldingSignalResponse(BaseModel):
    asset_id: str
    symbol: str
    name: str | None
    currency: str
    market_value: float | None
    weight: float | None
    latest_price: float | None
    timeframe: str
    return_value: float | None
    signal_score: float
    signal_strength: float
    action: str
    confidence: float
    data_points: int
    components: list[HoldingSignalComponent]


class HoldingSignalsResponse(BaseModel):
    timeframe: str
    methodology: str
    items: list[HoldingSignalResponse]


class StockRankingComponent(BaseModel):
    name: str
    metric: str
    value: float | None = None
    score: float | None = None
    available: bool
    detail: str


class StockRankingItem(BaseModel):
    asset_id: str
    symbol: str
    name: str | None
    exchange_code: str | None = None
    currency: str
    latest_price: float | None = None
    market_value: float | None = None
    is_tracked: bool = False
    is_held: bool = False
    is_watchlisted: bool = False
    score: float
    score_strength: float
    action: str
    confidence: float
    data_status: str
    latest_data_date: date | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    components: list[StockRankingComponent] = Field(default_factory=list)


class StockRankingsResponse(BaseModel):
    factor: str
    universe: str
    direction: str
    as_of_date: date
    methodology: str
    total: int
    data_complete_count: int
    items: list[StockRankingItem]


class StockRankingSnapshotRefreshRequest(BaseModel):
    factor: str = Field(
        default="aggregate",
        pattern="^(aggregate|share_price_momentum|news_sentiment|retail_sentiment|earnings_momentum|institutional_buying)$",
    )
    universe: str = Field(default="tracked", pattern="^(tracked|all)$")
    limit: int = Field(default=100, ge=1, le=500)


class StockRankingSnapshotRefreshResponse(BaseModel):
    factor: str
    universe: str
    snapshot_date: date
    refreshed_count: int


class WatchlistAssetResponse(BaseModel):
    asset_id: str
    symbol: str
    is_watchlisted: bool


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


class BenchmarkSymbol(BaseModel):
    provider: str
    provider_symbol: str
    symbol_purpose: str
    is_primary: bool
    is_proxy: bool


class BenchmarkSyncState(BaseModel):
    job_type: str
    last_success_at: datetime | None = None
    last_attempt_at: datetime | None = None
    last_success_date: date | None = None
    last_error: str | None = None
    updated_at: datetime | None = None


class BenchmarkIndexSummary(BaseModel):
    index_id: str
    index_name: str
    index_family: str
    index_category: str
    region: str | None = None
    country_code: str | None = None
    currency: str
    is_core: bool
    is_active: bool
    notes: str | None = None
    latest_metric_date: date | None = None
    latest_close: float | None = None
    return_1d: float | None = None
    return_21d: float | None = None
    return_252d: float | None = None
    volatility_252d_ann: float | None = None
    latest_composition_date: date | None = None
    constituent_count: int | None = None
    composition_quality: str | None = None
    daily_price_last_success_at: datetime | None = None
    composition_last_success_at: datetime | None = None
    last_error: str | None = None


class BenchmarkAvailablePriceRange(BaseModel):
    first_price_date: date | None = None
    last_price_date: date | None = None


class BenchmarkAvailableMetricRange(BaseModel):
    first_metric_date: date | None = None
    last_metric_date: date | None = None


class BenchmarkIndexDetail(BenchmarkIndexSummary):
    symbols: list[BenchmarkSymbol] = Field(default_factory=list)
    sync_state: dict[str, BenchmarkSyncState] = Field(default_factory=dict)
    available_snapshot_dates: list[date] = Field(default_factory=list)
    available_price_range: BenchmarkAvailablePriceRange
    available_metric_range: BenchmarkAvailableMetricRange


class BenchmarkReadinessRequirement(BaseModel):
    key: str
    label: str
    ready: bool
    detail: str
    row_count: int = 0
    latest_date: date | None = None


class BenchmarkReadinessItem(BaseModel):
    index_id: str
    index_name: str
    index_category: str
    ready: bool
    missing: list[str] = Field(default_factory=list)
    requirements: list[BenchmarkReadinessRequirement] = Field(default_factory=list)


class BenchmarkReadinessResponse(BaseModel):
    items: list[BenchmarkReadinessItem]
    total: int
    ready_count: int


class BenchmarkPricePoint(BaseModel):
    date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float
    adj_close: float | None = None
    volume: float | None = None
    source: str
    source_symbol: str
    is_proxy: bool


class BenchmarkDailyMetric(BaseModel):
    metric_date: date
    return_1d: float | None = None
    return_5d: float | None = None
    return_21d: float | None = None
    return_63d: float | None = None
    return_126d: float | None = None
    return_252d: float | None = None
    return_ytd: float | None = None
    volatility_21d_ann: float | None = None
    volatility_63d_ann: float | None = None
    volatility_252d_ann: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    drawdown_from_52w_high: float | None = None


class BenchmarkConstituent(BaseModel):
    index_id: str
    snapshot_date: date
    source: str
    constituent_symbol: str
    constituent_name: str | None = None
    exchange_code: str | None = None
    country_code: str | None = None
    currency: str | None = None
    sector: str | None = None
    industry: str | None = None
    weight_pct: float | None = None
    market_cap: float | None = None
    is_proxy: bool


class BenchmarkExposure(BaseModel):
    index_id: str
    snapshot_date: date
    dimension_type: str
    dimension_value: str
    weight_pct: float
    source: str
    source_type: str
    is_proxy: bool


class BenchmarkDefaultResponse(BaseModel):
    subject_type: str
    subject_id: str
    benchmark_index_id: str | None = None
    reason: str
    fallback_used: bool


class BenchmarkAssociation(BaseModel):
    role: str
    benchmark_index_id: str
    index_name: str
    index_category: str
    reason: str
    confidence: float


class AssetBenchmarkAssociationResponse(BaseModel):
    asset: AssetSearchResult
    associations: list[BenchmarkAssociation] = Field(default_factory=list)


class BenchmarkSeedRequest(BaseModel):
    scope: str = Field(default="core", pattern="^(core|non_core|all)$")


class BenchmarkRefreshRequest(BaseModel):
    job_type: str = Field(pattern="^(daily_price|intraday_price|composition|metrics|relative_metrics)$")
    lookback_days: int = Field(default=10, ge=1, le=3650)
    interval: str = Field(default="5min", min_length=1, max_length=16)
    comparison_index_id: str = Field(default="SP500", min_length=1, max_length=64)


class BenchmarkBulkRefreshRequest(BenchmarkRefreshRequest):
    category: str = Field(pattern="^(core_geo|sector|industry|theme|non_core|all)$")


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


class IngestionRequirementStatus(BaseModel):
    key: str
    label: str
    ready: bool
    detail: str
    row_count: int = 0
    latest_date: date | None = None
    open_jobs: int = 0
    last_error: str | None = None


class StockRankingReadinessItem(BaseModel):
    asset_id: str
    symbol: str
    name: str | None = None
    universe: str
    ready: bool
    complete_factor_count: int
    total_factor_count: int
    missing: list[str] = Field(default_factory=list)
    requirements: list[IngestionRequirementStatus] = Field(default_factory=list)


class StockRankingReadinessResponse(BaseModel):
    universe: str
    items: list[StockRankingReadinessItem]
    total: int
    ready_count: int


class IngestionAssetReadiness(BaseModel):
    asset_id: str
    symbol: str
    asset_type: str | None = None
    ready: bool
    missing: list[str] = Field(default_factory=list)
    requirements: list[IngestionRequirementStatus] = Field(default_factory=list)


class IngestionReadinessResponse(BaseModel):
    items: list[IngestionAssetReadiness]
    total: int
    ready_count: int


class IngestionScheduleRequest(BaseModel):
    pipeline: str = "all"
    asset_id: str | None = None
    max_assets: int = Field(default=25, ge=1, le=100)
    years: int = Field(default=10, ge=1, le=30)
    prices_only: bool = False
    ranking_factor: str = Field(
        default="aggregate",
        pattern="^(aggregate|share_price_momentum|news_sentiment|retail_sentiment|earnings_momentum|institutional_buying)$",
    )
    ranking_universe: str = Field(default="tracked", pattern="^(tracked|all)$")
    missing_only: bool = False
    stale_only: bool = False


class IngestionRunRequest(BaseModel):
    domain: str = "all"
    max_jobs: int = Field(default=1, ge=1, le=25)


class IngestionRetryFailedRequest(BaseModel):
    domain: str | None = None
    max_jobs: int = Field(default=25, ge=1, le=100)
