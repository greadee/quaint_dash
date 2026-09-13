"""Analytics data models and public report schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

TRADING_DAYS_PER_YEAR = 252
ANALYTICS_REPORT_SCHEMA_VERSION = "phase3.analytics.v1"
REVENUE_ALIASES = ("revenue", "totalRevenue", "total_revenue")
GROSS_PROFIT_ALIASES = ("grossProfit", "gross_profit")
OPERATING_INCOME_ALIASES = ("operatingIncome", "operating_income")
NET_INCOME_ALIASES = ("netIncome", "net_income")
EPS_ALIASES = ("eps", "epsDiluted", "dilutedEPS", "dilutedEps")
EBITDA_ALIASES = ("ebitda", "EBITDA")
EQUITY_ALIASES = ("totalStockholdersEquity", "totalShareholderEquity", "total_equity")
ASSETS_ALIASES = ("totalAssets", "total_assets")
DEBT_ALIASES = ("totalDebt", "shortLongTermDebtTotal", "total_debt")
CASH_ALIASES = ("cashAndCashEquivalents", "cashAndShortTermInvestments", "cash")
FREE_CASH_FLOW_ALIASES = ("freeCashFlow", "free_cash_flow", "free_cashflow")
OPERATING_CASH_FLOW_ALIASES = (
    "operatingCashFlow",
    "cashFlowFromOperations",
    "netCashProvidedByOperatingActivities",
)
CAPEX_ALIASES = ("capitalExpenditure", "capital_expenditure", "capex")
DEFAULT_BENCHMARK_BY_COUNTRY = {
    "US": "SP500",
    "USA": "SP500",
    "UNITED STATES": "SP500",
    "CA": "TSXCOMP",
    "CAN": "TSXCOMP",
    "CANADA": "TSXCOMP",
    "GB": "FTSE100",
    "UK": "FTSE100",
    "UNITED KINGDOM": "FTSE100",
    "JP": "NIKKEI225",
    "JAPAN": "NIKKEI225",
}
DEFAULT_BENCHMARK_BY_CURRENCY = {
    "USD": "SP500",
    "CAD": "TSXCOMP",
    "GBP": "FTSE100",
    "JPY": "NIKKEI225",
}


@dataclass(frozen=True)
class PricePoint:
    date: date
    close: float


@dataclass(frozen=True)
class DataCoverage:
    asset_count: int
    position_count: int
    daily_price_count: int
    dividend_count: int
    split_count: int
    financial_statement_count: int
    benchmark_price_count: int


@dataclass(frozen=True)
class RiskReturnMetrics:
    start_date: date | None
    end_date: date | None
    observations: int
    cumulative_return: float | None
    cagr: float | None
    annualized_volatility: float | None
    downside_deviation: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None
    max_drawdown: float | None
    best_daily_return: float | None
    worst_daily_return: float | None


@dataclass(frozen=True)
class RelativeRiskMetrics:
    observations: int
    beta: float | None
    alpha_annualized: float | None
    correlation: float | None
    r_squared: float | None
    excess_cagr: float | None


@dataclass(frozen=True)
class PortfolioPerformanceMetrics:
    start_date: date | None
    end_date: date | None
    beginning_market_value: float
    ending_market_value: float
    net_contributions: float
    net_withdrawals: float
    net_external_cash_flow: float
    dividend_income: float
    realized_gain: float | None
    unrealized_gain: float | None
    total_gain: float | None
    modified_dietz_return: float | None
    money_weighted_return: float | None
    missing_inputs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AssetRiskContribution:
    asset_id: str
    weight: float
    annualized_volatility: float | None
    portfolio_volatility_contribution: float | None
    percent_of_portfolio_volatility: float | None


@dataclass(frozen=True)
class PortfolioRiskDecomposition:
    asset_count: int
    effective_asset_count: float | None
    concentration_hhi: float | None
    largest_position_weight: float | None
    diversification_score: float | None
    portfolio_volatility: float | None
    average_pairwise_correlation: float | None
    correlation_matrix: dict[str, dict[str, float | None]] = field(default_factory=dict)
    volatility_contributions: list[AssetRiskContribution] = field(default_factory=list)
    asset_class_exposure: dict[str, float] = field(default_factory=dict)
    sector_exposure: dict[str, float] = field(default_factory=dict)
    country_exposure: dict[str, float] = field(default_factory=dict)
    currency_exposure: dict[str, float] = field(default_factory=dict)
    missing_inputs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DcfScenario:
    scenario_name: str
    growth_rate: float
    discount_rate: float
    terminal_growth_rate: float
    intrinsic_value_per_share: float | None
    margin_of_safety: float | None
    implied_growth_rate: float | None


@dataclass(frozen=True)
class ValuationDepthMetrics:
    revenue_growth_yoy: float | None
    eps_growth_yoy: float | None
    free_cash_flow_growth_yoy: float | None
    gross_margin: float | None
    operating_margin: float | None
    net_margin: float | None
    return_on_equity: float | None
    return_on_assets: float | None
    debt_to_equity: float | None
    net_debt_to_ebitda: float | None
    payout_ratio: float | None
    pe_ratio: float | None
    price_to_book: float | None
    price_to_sales: float | None
    price_to_free_cash_flow: float | None
    ev_to_ebitda: float | None
    dcf_scenarios: list[DcfScenario] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EtfHoldingAnalytics:
    holding_symbol: str
    holding_name: str | None
    weight: float | None
    sector: str | None
    country: str | None
    currency: str | None


@dataclass(frozen=True)
class EtfOverlapAnalytics:
    holding_symbol: str
    direct_asset_id: str
    etf_weight: float | None
    direct_portfolio_weight: float | None


@dataclass(frozen=True)
class ETFAnalytics:
    is_etf: bool
    expense_ratio: float | None
    benchmark_index_id: str | None
    annual_distribution_per_share: float | None
    distribution_yield: float | None
    tracking_error: float | None
    holding_count: int
    top_holdings: list[EtfHoldingAnalytics] = field(default_factory=list)
    overlap_with_portfolio: list[EtfOverlapAnalytics] = field(default_factory=list)
    sector_exposure: dict[str, float] = field(default_factory=dict)
    country_exposure: dict[str, float] = field(default_factory=dict)
    currency_exposure: dict[str, float] = field(default_factory=dict)
    missing_inputs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ForecastBand:
    horizon_years: int
    expected_value: float | None
    p10_value: float | None
    p50_value: float | None
    p90_value: float | None
    expected_cagr: float | None
    p10_cagr: float | None
    p50_cagr: float | None
    p90_cagr: float | None


@dataclass(frozen=True)
class ForecastMetrics:
    horizon_years: int
    expected_cagr_from_valuation: float | None
    dividend_growth_projection: float | None
    fundamental_growth_assumption: float | None
    blended_expected_cagr: float | None
    simulation: ForecastBand | None
    missing_inputs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PositionValuationContribution:
    asset_id: str
    valuation_asset_id: str | None
    valuation_source: str
    allocation_class: str | None
    fcf_metrics_applicable: bool
    fee_adjustment: float | None
    weight: float | None
    margin_of_safety: float | None
    pe_ratio: float | None
    price_to_free_cash_flow: float | None
    dividend_yield: float | None
    expected_cagr: float | None
    weighted_expected_cagr_contribution: float | None


@dataclass(frozen=True)
class PortfolioValuationRollup:
    weighted_margin_of_safety: float | None
    weighted_pe_ratio: float | None
    weighted_price_to_free_cash_flow: float | None
    weighted_dividend_yield: float | None
    weighted_expected_cagr: float | None
    undervalued_weight: float
    overvalued_weight: float
    fair_value_weight: float
    position_contributions: list[PositionValuationContribution] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AnalyticsFact:
    key: str
    label: str
    value: float | int | str | bool | None
    unit: str | None
    source: str
    confidence: float


@dataclass(frozen=True)
class AnalyticsExplanation:
    topic: str
    summary: str
    evidence: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AnalyticsAnomaly:
    severity: str
    metric: str
    message: str
    value: float | int | str | bool | None = None


@dataclass(frozen=True)
class SnapshotMetricChange:
    key: str
    previous_value: float | int | str | bool | None
    current_value: float | int | str | bool | None
    absolute_change: float | None
    relative_change: float | None


@dataclass(frozen=True)
class AIReadinessContext:
    subject_type: str
    subject_id: str
    summary: str
    facts: list[AnalyticsFact] = field(default_factory=list)
    explanations: list[AnalyticsExplanation] = field(default_factory=list)
    anomalies: list[AnalyticsAnomaly] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    snapshot_hash: str | None = None


@dataclass(frozen=True)
class ValuationResult:
    method: str
    intrinsic_value_per_share: float | None
    market_price: float | None
    margin_of_safety: float | None
    expected_cagr: float | None
    implied_growth_rate: float | None
    inputs_used: dict[str, float | int | str | None] = field(default_factory=dict)
    missing_inputs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AssetAnalyticsReport:
    asset_id: str
    benchmark_index_id: str | None
    latest_price: float | None
    data_coverage: DataCoverage
    risk: RiskReturnMetrics
    relative: RelativeRiskMetrics | None
    dividend_discount: ValuationResult
    discounted_cash_flow: ValuationResult
    valuation_depth: ValuationDepthMetrics
    etf: ETFAnalytics | None
    forecast: ForecastMetrics
    ai_context: AIReadinessContext


@dataclass(frozen=True)
class PositionAnalytics:
    portfolio_id: int
    asset_id: str
    qty: float
    book_cost: float
    latest_price: float | None
    market_value: float | None
    weight: float | None
    unrealized_gain: float | None


@dataclass(frozen=True)
class PortfolioAnalyticsReport:
    portfolio_id: int
    benchmark_index_id: str | None
    positions: list[PositionAnalytics]
    market_value: float
    performance: PortfolioPerformanceMetrics
    risk_decomposition: PortfolioRiskDecomposition
    valuation: PortfolioValuationRollup
    risk: RiskReturnMetrics | None
    relative: RelativeRiskMetrics | None
    forecast: ForecastMetrics
    missing_inputs: list[str]
    ai_context: AIReadinessContext


@dataclass(frozen=True)
class AnalyticsRefreshResult:
    assets_stored: int = 0
    portfolios_stored: int = 0
    skipped: bool = False
    reason: str | None = None
