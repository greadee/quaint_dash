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
    unrealized_return_percent: float | None = None
    total_gain: float | None = None
    total_return_percent: float | None = None
    total_gain_source: str = "unrealized"
    projected_value: float | None = None
    projected_value_low: float | None = None
    projected_value_high: float | None = None
    projected_horizon_years: int | None = None
    as_of: datetime | None = None
    source: str = "quaint_dash.duckdb"
    display_currency: str | None = None
    market_value_native: float | None = None
    book_cost_native: float | None = None
    fx_missing: list[str] = Field(default_factory=list)


class PositionSummary(BaseModel):
    asset_id: str
    symbol: str
    name: str | None
    asset_type: str | None
    allocation_class: str = "Other"
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
    native_market_value: float | None = None
    base_market_value: float | None = None
    native_book_cost: float | None = None
    base_book_cost: float | None = None
    fx_rate: float | None = None
    fx_source: str | None = None
    fx_as_of: datetime | None = None
    price_timestamp: datetime | None = None
    price_source: str | None = None
    price_session: str | None = None
    stale_price: bool = False
    stale_reason: str | None = None
    sector_exposure: dict[str, float] = Field(default_factory=dict)
    industry_exposure: dict[str, float] = Field(default_factory=dict)
    country_exposure: dict[str, float] = Field(default_factory=dict)
    currency_exposure: dict[str, float] = Field(default_factory=dict)
    data_status: str = "available"


class PortfolioMetricValue(BaseModel):
    value: float | None = None
    reason: str | None = None
    coverage: float | None = None
    source: str = "quaint_dash.duckdb"
    as_of: date | datetime | None = None


class PortfolioPerformancePoint(BaseModel):
    date: date
    portfolio_value: float | None = None
    portfolio_return_index: float | None = None
    benchmark_return_index: float | None = None


class PortfolioPerformanceResponse(BaseModel):
    portfolio_id: int
    benchmark: str | None = None
    base_currency: str
    start_date: date | None = None
    end_date: date | None = None
    range: str
    methodology: str
    calendar_alignment: str
    normalized_initial_value: float
    actual_twr_cagr: float | None = None
    historical_cumulative_return: float | None = None
    benchmark_cagr: float | None = None
    excess_cagr: float | None = None
    observation_count: int
    coverage: float | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    points: list[PortfolioPerformancePoint] = Field(default_factory=list)
    as_of: datetime
    source: str = "quaint_dash.analytics"


class PortfolioRiskResponse(BaseModel):
    portfolio_id: int
    benchmark: str | None = None
    risk_free_rate: float
    risk_free_rate_source: str
    risk_free_rate_date: date | None = None
    lookback: str
    return_frequency: str
    annualized_return: float | None = None
    annualized_volatility: float | None = None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    beta: float | None = None
    alpha: float | None = None
    correlation: float | None = None
    maximum_drawdown: float | None = None
    downside_deviation: float | None = None
    observation_count: int
    effective_number_of_holdings: float | None = None
    largest_position: float | None = None
    hhi: float | None = None
    weight_balance_score: float | None = None
    sector_concentration: dict[str, float] = Field(default_factory=dict)
    geographic_concentration: dict[str, float] = Field(default_factory=dict)
    currency_concentration: dict[str, float] = Field(default_factory=dict)
    average_pairwise_correlation: float | None = None
    risk_contribution_concentration: float | None = None
    asset_class_concentration: dict[str, float] = Field(default_factory=dict)
    missing_inputs: list[str] = Field(default_factory=list)
    as_of: datetime


class PortfolioFundamentalHolding(BaseModel):
    asset_id: str
    symbol: str
    market_value: float | None = None
    weight: float | None = None
    expected_cagr: float | None = None
    expected_cagr_contribution: float | None = None
    pe_ratio: float | None = None
    price_to_free_cash_flow: float | None = None
    revenue_growth: float | None = None
    eps_growth: float | None = None
    free_cash_flow_growth: float | None = None
    operating_margin: float | None = None
    free_cash_flow_margin: float | None = None
    dividend_yield: float | None = None
    margin_of_safety: float | None = None
    coverage_status: str
    missing_inputs: list[str] = Field(default_factory=list)


class PortfolioFundamentalsResponse(BaseModel):
    portfolio_id: int
    base_currency: str
    horizon_years: int
    weighted_expected_cagr: PortfolioMetricValue
    pe_ratio: PortfolioMetricValue
    price_to_free_cash_flow: PortfolioMetricValue
    revenue_growth: PortfolioMetricValue
    eps_growth: PortfolioMetricValue
    free_cash_flow_growth: PortfolioMetricValue
    operating_margin: PortfolioMetricValue
    free_cash_flow_margin: PortfolioMetricValue
    dividend_yield: PortfolioMetricValue
    margin_of_safety: PortfolioMetricValue
    holdings: list[PortfolioFundamentalHolding]
    missing_inputs: list[str] = Field(default_factory=list)
    as_of: datetime


class OptimizationConstraints(BaseModel):
    min_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    max_weight: float = Field(default=0.15, gt=0.0, le=1.0)
    min_holding_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    max_sector_exposure: float | None = Field(default=None, gt=0.0, le=1.0)
    max_country_exposure: float | None = Field(default=None, gt=0.0, le=1.0)
    max_currency_exposure: float | None = Field(default=None, gt=0.0, le=1.0)
    volatility_ceiling: float | None = Field(default=None, gt=0.0)
    max_turnover: float | None = Field(default=None, ge=0.0, le=2.0)
    min_holdings: int | None = Field(default=None, ge=1)
    max_holdings: int | None = Field(default=None, ge=1)
    locked_assets: list[str] = Field(default_factory=list)
    excluded_assets: list[str] = Field(default_factory=list)
    cash_weight: float = Field(default=0.0, ge=0.0, le=1.0)


class OptimizationPreviewRequest(BaseModel):
    objective: str = Field(pattern="^(max_expected_cagr|max_risk_adjusted_return)$")
    lookback_days: int = Field(default=756, ge=60, le=3650)
    return_frequency: str = Field(default="daily", pattern="^daily$")
    risk_free_rate: float = Field(default=0.0, ge=-0.05, le=0.25)
    horizon_years: int = Field(default=5, ge=3, le=10)
    constraints: OptimizationConstraints = Field(default_factory=OptimizationConstraints)


class OptimizationMetricSet(BaseModel):
    expected_cagr: float | None = None
    expected_volatility: float | None = None
    expected_sharpe: float | None = None
    beta: float | None = None
    concentration_hhi: float | None = None


class OptimizationPreviewResponse(BaseModel):
    portfolio_id: int
    objective: str
    status: str
    solver_message: str
    current_weights: dict[str, float]
    optimized_weights: dict[str, float]
    weight_deltas: dict[str, float]
    before: OptimizationMetricSet
    after: OptimizationMetricSet
    sector_exposure_before: dict[str, float] = Field(default_factory=dict)
    sector_exposure_after: dict[str, float] = Field(default_factory=dict)
    estimated_turnover: float | None = None
    binding_constraints: list[str] = Field(default_factory=list)
    excluded_assets: list[str] = Field(default_factory=list)
    input_coverage: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    calculation_timestamp: datetime


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
    timeframe: str
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
    timeframe: str = Field(default="monthly", pattern="^(daily|weekly|monthly|yearly)$")
    limit: int = Field(default=100, ge=1, le=500)


class StockRankingSnapshotRefreshResponse(BaseModel):
    factor: str
    universe: str
    snapshot_date: date
    refreshed_count: int


class SignalEvidenceItem(BaseModel):
    label: str
    metric: str
    value: float | None = None
    score: float | None = None
    detail: str
    source: str
    as_of: date | datetime | None = None


class SignalPortfolioImpact(BaseModel):
    portfolio_id: int
    portfolio_name: str
    weight: float | None
    market_value: float | None
    currency: str
    concentration_note: str


class SignalUserState(BaseModel):
    reviewed_at: datetime | None = None
    muted_until: datetime | None = None
    dismissed_until: datetime | None = None
    note: str | None = None
    alert_rule_id: int | None = None


class SignalSummaryMetric(BaseModel):
    key: str
    label: str
    value: int
    filter_params: dict[str, str]


class SignalHistoryPoint(BaseModel):
    date: date
    strength: float
    confidence: float
    raw_value: float
    action: str


class SignalLifecycleEvent(BaseModel):
    status: str
    timestamp: datetime | date | None
    label: str
    detail: str


class SignalEfficacyMetadata(BaseModel):
    label: str
    sample_size: int
    prior_occurrences: int | None = None
    median_forward_return: float | None = None
    median_excess_return: float | None = None
    hit_rate: float | None = None
    max_adverse_excursion: float | None = None
    benchmark: str | None = None
    methodology_version: str
    warning: str | None = None


class SignalRow(BaseModel):
    signal_id: str
    definition_id: str
    asset_id: str
    ticker: str
    company_name: str | None
    exchange: str | None
    signal_name: str
    summary: str
    category: str
    direction: str
    status: str
    strength: float
    confidence: float
    portfolio_priority: float
    raw_observed_value: float | None
    normalized_value: float | None
    trigger_threshold: float | None
    lookback_period: str
    first_detected_at: datetime | date | None
    confirmation_at: datetime | date | None
    last_evaluated_at: datetime
    data_as_of: datetime | date | None
    expires_at: datetime | date | None
    resolved_at: datetime | date | None
    resolution_reason: str | None
    methodology_version: str
    source: str
    missing_data_status: str
    supporting_evidence: list[SignalEvidenceItem] = Field(default_factory=list)
    contradicting_evidence: list[SignalEvidenceItem] = Field(default_factory=list)
    affected_portfolios: list[SignalPortfolioImpact] = Field(default_factory=list)
    current_portfolio_weight: float | None
    historical_efficacy: SignalEfficacyMetadata
    related_signal_ids: list[str] = Field(default_factory=list)
    reviewed: bool = False
    muted: bool = False


class SignalsSummaryResponse(BaseModel):
    items: list[SignalRow]
    total: int
    limit: int
    offset: int
    metrics: list[SignalSummaryMetric]
    needs_attention: list[SignalRow]
    top_opportunities: list[SignalRow]
    generated_at: datetime
    data_as_of: datetime | date | None
    last_successful_computation_at: datetime | date | None
    partial_provider_failures: list[str] = Field(default_factory=list)
    stale_cached_results: bool = False
    model_version: str
    methodology: str


class SignalDetailResponse(SignalRow):
    lifecycle: list[SignalLifecycleEvent] = Field(default_factory=list)
    strength_history: list[SignalHistoryPoint] = Field(default_factory=list)
    related_news: list[NewsItemResponse] = Field(default_factory=list)
    methodology: str
    links: dict[str, str]
    user_state: SignalUserState


class SignalUserStateRequest(BaseModel):
    reviewed: bool | None = None
    muted_until: datetime | None = None
    dismissed_until: datetime | None = None
    note: str | None = Field(default=None, max_length=2000)


class SignalAlertRuleRequest(BaseModel):
    condition: str = Field(default="status_active", max_length=80)
    threshold: float | None = None
    channel: str = Field(default="in_app", max_length=40)


class SignalAlertRuleResponse(BaseModel):
    alert_rule_id: int
    signal_id: str
    definition_id: str
    asset_id: str
    condition: str
    threshold: float | None
    channel: str
    is_active: bool


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
    forward_eps: float | None = None
    forward_revenue: float | None = None
    pe_ratio: float | None = None
    forward_pe: float | None = None
    price_to_sales: float | None = None
    free_cash_flow: float | None = None
    free_cash_flow_yield: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    cash: float | None = None
    total_debt: float | None = None
    net_debt: float | None = None
    net_debt_to_ebitda: float | None = None
    current_ratio: float | None = None
    debt_to_equity: float | None = None
    shares_outstanding: float | None = None
    dividend_yield: float | None = None
    buyback_yield: float | None = None
    stock_based_compensation: float | None = None
    acquisition_intensity: float | None = None
    reinvestment_rate: float | None = None
    roic: float | None = None
    roic_on_reinvestment: float | None = None
    customer_concentration: float | None = None
    revenue_concentration: float | None = None
    latest_period_end: date | None = None
    estimate_as_of: datetime | None = None


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
    asset_type: str | None = None
    exchange_code: str | None = None
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


class SectorComparisonValues(BaseModel):
    pe_ratio: float | None = None
    price_to_sales: float | None = None
    market_cap: float | None = None
    beta: float | None = None
    return_1d: float | None = None
    return_21d: float | None = None
    return_252d: float | None = None


class SectorComparisonContext(BaseModel):
    sector: str
    median: SectorComparisonValues
    left_diff_to_median: SectorComparisonValues
    right_diff_to_median: SectorComparisonValues | None = None
    benchmark: BenchmarkComparisonProfile | None = None


class ComparisonResponse(BaseModel):
    left: ComparisonAssetProfile
    right: ComparisonAssetProfile | None = None
    benchmark: BenchmarkComparisonProfile | None = None
    sector_context: SectorComparisonContext | None = None
    insights: list[str] = Field(default_factory=list)


class ComparisonHistoryPoint(BaseModel):
    date: date
    value: float | None = None
    close: float | None = None
    cumulative_return: float | None = None


class ComparisonHistorySeries(BaseModel):
    asset_id: str
    symbol: str
    mode: str
    currency: str
    start_date: date | None = None
    end_date: date | None = None
    observation_count: int
    source: str | None = None
    points: list[ComparisonHistoryPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ComparisonFreshness(BaseModel):
    latest_price_date: date | None = None
    latest_price_source: str | None = None
    latest_price_ingested_at: datetime | None = None
    latest_fiscal_period: date | None = None
    latest_fundamental_source: str | None = None
    latest_fundamental_ingested_at: datetime | None = None
    calculation_timestamp: datetime
    provider: str
    stale: bool = False
    stale_reason: str | None = None


class ComparisonCoverage(BaseModel):
    requested_symbols: list[str]
    resolved_symbols: list[str]
    failed_symbols: list[str] = Field(default_factory=list)
    common_start_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    benchmark: str | None = None
    currency: str
    mode: str
    calculation_version: str
    warnings: list[str] = Field(default_factory=list)


class ComparisonFxPolicy(BaseModel):
    display_currency: str
    native_currency_count: int
    historical: bool
    source: str | None = None
    rate_count: int = 0
    as_of: datetime | None = None
    missing_pairs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ComparisonWorkspaceResponse(BaseModel):
    requested_symbols: list[str]
    assets: list[ComparisonAssetProfile]
    failed_symbols: list[str] = Field(default_factory=list)
    benchmark: BenchmarkComparisonProfile | None = None
    historical_series: list[ComparisonHistorySeries] = Field(default_factory=list)
    freshness: dict[str, ComparisonFreshness] = Field(default_factory=dict)
    coverage: ComparisonCoverage
    fx_policy: ComparisonFxPolicy
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


class BenchmarkHardenRequest(BaseModel):
    lookback_days: int = Field(default=730, ge=252, le=3650)
    include_composition: bool = True
    include_relative_metrics: bool = True
    comparison_index_id: str = Field(default="SP500", min_length=1, max_length=64)


class BenchmarkBulkHardenRequest(BenchmarkHardenRequest):
    category: str = Field(default="all", pattern="^(core_geo|sector|industry|theme|non_core|all)$")


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
    user_key: str | None = Field(default=None, min_length=1, max_length=100)
    broker: str | None = None
    reconnect: str | None = None


class BrokerPortalResponse(BaseModel):
    url: str


class BrokerSyncRequest(BaseModel):
    user_key: str | None = Field(default=None, min_length=1, max_length=100)


class BrokerConnectionResponse(BaseModel):
    provider: str
    connection_id: int | None
    provider_connection_id: str
    institution_name: str
    status: str
    account_count: int = 0
    last_attempted_refresh_at: datetime | None = None
    last_successful_refresh_at: datetime | None = None
    last_error: str | None = None


class BrokerAccountResponse(BaseModel):
    provider: str
    provider_account_id: str
    provider_connection_id: str
    masked_account_number: str | None = None
    account_name: str | None
    account_type: str | None
    currency: str | None
    balance: float | None
    cash_balance: float | None = None
    holdings_value: float | None = None
    total_value: float | None = None
    position_count: int = 0
    latest_position_date: date | None = None
    portfolio_id: int | None
    portfolio_name: str | None = None
    available_transaction_count: int = 0
    imported_transaction_count: int = 0
    unsupported_transaction_count: int = 0
    latest_activity_date: date | None = None
    last_imported_at: datetime | None = None
    updated_at: datetime | None = None


class BrokerStatusResponse(BaseModel):
    provider: str = "snaptrade"
    configured: bool
    broker_profile_ready: bool
    broker_profile_status: str
    broker_profile_key: str | None = None
    raw_payload_storage_enabled: bool
    scheduled_refresh_enabled: bool
    freshness_window_hours: int
    max_users_per_run: int | None = None
    last_refresh_at: datetime | None = None
    last_successful_refresh_at: datetime | None = None
    last_scheduled_run_at: datetime | None = None
    next_eligible_refresh_at: datetime | None = None
    provider_message: str | None = None


class BrokerSyncHistoryItem(BaseModel):
    sync_run_id: int
    provider: str
    user_key: str | None = None
    connection_label: str | None = None
    trigger_type: str = "manual"
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    accounts_processed: int
    positions_stored: int
    activities_stored: int
    status: str
    error_summary: str | None = None


class BrokerImportCategoryCounts(BaseModel):
    buys: int = 0
    sells: int = 0
    dividends: int = 0
    interest: int = 0
    fees: int = 0
    taxes: int = 0
    contributions: int = 0
    withdrawals: int = 0
    reinvestments: int = 0
    transfers: int = 0
    unknown: int = 0


class BrokerImportPreviewItem(BaseModel):
    provider_transaction_id: str
    institution_name: str | None = None
    account_name: str | None = None
    masked_account_number: str | None = None
    portfolio_id: int | None = None
    portfolio_name: str | None = None
    trade_date: date
    source_type: str
    category: str
    status: str
    symbol: str | None = None
    quantity: float | None = None
    price: float | None = None
    amount: float | None = None
    currency: str | None = None
    normalization_result: str


class BrokerImportPreviewGroup(BaseModel):
    institution_name: str | None = None
    account_name: str | None = None
    masked_account_number: str | None = None
    portfolio_id: int | None = None
    portfolio_name: str | None = None
    ready_count: int = 0
    already_imported_count: int = 0
    unsupported_count: int = 0
    needs_review_count: int = 0
    unresolved_asset_count: int = 0
    failed_validation_count: int = 0
    category_counts: BrokerImportCategoryCounts = Field(default_factory=BrokerImportCategoryCounts)
    items: list[BrokerImportPreviewItem] = Field(default_factory=list)


class BrokerImportPreviewResponse(BaseModel):
    generated_at: datetime
    total_transactions: int
    ready_count: int
    already_imported_count: int
    unsupported_count: int
    needs_review_count: int
    unresolved_asset_count: int
    failed_validation_count: int
    date_start: date | None = None
    date_end: date | None = None
    groups: list[BrokerImportPreviewGroup] = Field(default_factory=list)


class BrokerReconciliationItem(BaseModel):
    institution_name: str | None = None
    account_name: str | None = None
    masked_account_number: str | None = None
    ticker: str | None = None
    asset_id: str | None = None
    broker_quantity: float | None = None
    local_quantity: float | None = None
    quantity_difference: float | None = None
    broker_market_value: float | None = None
    local_market_value: float | None = None
    value_difference: float | None = None
    currency: str | None = None
    broker_data_timestamp: date | None = None
    local_ledger_timestamp: datetime | None = None
    status: str


class BrokerReconciliationResponse(BaseModel):
    generated_at: datetime
    items: list[BrokerReconciliationItem] = Field(default_factory=list)


class BrokerStorageSettingRequest(BaseModel):
    enabled: bool


class BrokerStorageSettingResponse(BaseModel):
    raw_payload_storage_enabled: bool


class BrokerDueRefreshRequest(BaseModel):
    max_users: int | None = Field(default=None, ge=1, le=100)
    min_age_hours: int = Field(default=1, ge=1, le=168)
    force: bool = False


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
    last_pending_count: int | None = None
    last_error: str | None = None
    schedule_interval_seconds: int
    run_interval_seconds: int
    max_jobs_per_tick: int
    max_run_batches_per_tick: int
    max_assets_per_schedule: int
    years: int
    prices_only: bool


class MarketFreshnessStatusResponse(BaseModel):
    enabled: bool
    running: bool
    last_poll_at: datetime | None = None
    last_refreshed_count: int | None = None
    last_subscription_count: int | None = None
    last_error: str | None = None
    poll_interval_seconds: int
    include_watchlist: bool
    lookback_days: int
    max_symbols_per_tick: int


class DataReadinessWorkerStatusResponse(BaseModel):
    enabled: bool
    running: bool
    last_check_at: datetime | None = None
    last_target_count: int | None = None
    last_ready_count: int | None = None
    last_valuation_count: int | None = None
    last_scheduled_count: int | None = None
    last_completed_count: int | None = None
    last_pending_count: int | None = None
    last_missing: list[str] = Field(default_factory=list)
    last_error: str | None = None
    poll_interval_seconds: int
    max_assets_per_tick: int
    max_jobs_per_batch: int
    max_run_batches_per_tick: int
    years: int
    min_price_rows: int


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
    ranking_timeframe: str = Field(default="monthly", pattern="^(daily|weekly|monthly|yearly)$")
    missing_only: bool = False
    stale_only: bool = False


class IngestionRunRequest(BaseModel):
    domain: str = "all"
    max_jobs: int = Field(default=1, ge=1, le=25)


class IngestionRetryFailedRequest(BaseModel):
    domain: str | None = None
    max_jobs: int = Field(default=25, ge=1, le=100)
