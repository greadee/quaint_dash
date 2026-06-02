"""Phase 3 analytics calculations for assets, ETFs, and portfolios.

This module is intentionally calculation-first: it reads existing market,
portfolio, dividend, and financial-statement tables and reports missing inputs
instead of triggering new ingestion.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
import hashlib
import json
import math
import random
import statistics
from typing import Any


TRADING_DAYS_PER_YEAR = 252
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
    latest_price: float | None
    data_coverage: DataCoverage
    risk: RiskReturnMetrics
    relative: RelativeRiskMetrics | None
    dividend_discount: ValuationResult
    discounted_cash_flow: ValuationResult
    valuation_depth: ValuationDepthMetrics
    etf: ETFAnalytics | None
    forecast: ForecastMetrics


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
    positions: list[PositionAnalytics]
    market_value: float
    performance: PortfolioPerformanceMetrics
    risk_decomposition: PortfolioRiskDecomposition
    risk: RiskReturnMetrics | None
    relative: RelativeRiskMetrics | None
    forecast: ForecastMetrics
    missing_inputs: list[str]


@dataclass(frozen=True)
class AnalyticsRefreshResult:
    assets_stored: int = 0
    portfolios_stored: int = 0
    skipped: bool = False
    reason: str | None = None


class AnalyticsRepository:
    """Read-only access to existing analytics inputs."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def data_coverage(self) -> DataCoverage:
        return DataCoverage(
            asset_count=self._count("asset"),
            position_count=self._count("position"),
            daily_price_count=self._count("asset_quote_daily"),
            dividend_count=self._count("dividend_event"),
            split_count=self._count("split_event"),
            financial_statement_count=self._count("financial_statement"),
            benchmark_price_count=self._count("benchmark_index_daily_price"),
        )

    def price_history(
        self,
        asset_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[PricePoint]:
        where = ["asset_id = ?", "COALESCE(adj_close, close) IS NOT NULL"]
        params: list[Any] = [asset_id.upper().strip()]
        if start_date is not None:
            where.append("date >= ?")
            params.append(start_date)
        if end_date is not None:
            where.append("date <= ?")
            params.append(end_date)

        rows = self.conn.execute(
            f"""
            SELECT date, COALESCE(adj_close, close) AS close
            FROM asset_quote_daily
            WHERE {" AND ".join(where)}
            ORDER BY date
            """,
            params,
        ).fetchall()
        return [PricePoint(row[0], float(row[1])) for row in rows if row[1] and row[1] > 0]

    def benchmark_price_history(
        self,
        index_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[PricePoint]:
        if not self._table_exists("benchmark_index_daily_price"):
            return []

        where = ["index_id = ?", "COALESCE(adj_close, close) IS NOT NULL"]
        params: list[Any] = [index_id]
        if start_date is not None:
            where.append("price_date >= ?")
            params.append(start_date)
        if end_date is not None:
            where.append("price_date <= ?")
            params.append(end_date)

        rows = self.conn.execute(
            f"""
            SELECT price_date, COALESCE(adj_close, close) AS close
            FROM benchmark_index_daily_price
            WHERE {" AND ".join(where)}
            ORDER BY price_date
            """,
            params,
        ).fetchall()
        return [PricePoint(row[0], float(row[1])) for row in rows if row[1] and row[1] > 0]

    def latest_price(self, asset_id: str) -> float | None:
        row = self.conn.execute(
            """
            SELECT COALESCE(adj_close, close)
            FROM asset_quote_daily
            WHERE asset_id = ?
              AND COALESCE(adj_close, close) IS NOT NULL
            ORDER BY date DESC
            LIMIT 1
            """,
            [asset_id.upper().strip()],
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else None

    def annual_dividend_per_share(self, asset_id: str, as_of_date: date | None = None) -> float | None:
        where = ["asset_id = ?", "dividend_per_share IS NOT NULL"]
        params: list[Any] = [asset_id.upper().strip()]
        if as_of_date is not None:
            where.append("ex_date <= ?")
            params.append(as_of_date)

        rows = self.conn.execute(
            f"""
            SELECT dividend_per_share
            FROM dividend_event
            WHERE {" AND ".join(where)}
            ORDER BY ex_date DESC
            LIMIT 8
            """,
            params,
        ).fetchall()
        values = [float(row[0]) for row in rows if row[0] is not None and row[0] > 0]
        if not values:
            return None
        return sum(values[:4])

    def dividend_history(self, asset_id: str, limit: int = 12) -> list[tuple[date, float]]:
        rows = self.conn.execute(
            """
            SELECT ex_date, dividend_per_share
            FROM dividend_event
            WHERE asset_id = ?
              AND dividend_per_share IS NOT NULL
            ORDER BY ex_date DESC
            LIMIT ?
            """,
            [asset_id.upper().strip(), limit],
        ).fetchall()
        return [(row[0], float(row[1])) for row in rows if row[1] is not None and row[1] > 0]

    def shares_outstanding(self, asset_id: str) -> float | None:
        row = self.conn.execute(
            """
            SELECT shares_outstanding
            FROM asset
            WHERE asset_id = ?
            """,
            [asset_id.upper().strip()],
        ).fetchone()
        return float(row[0]) if row and row[0] is not None and row[0] > 0 else None

    def latest_free_cash_flow(self, asset_id: str) -> float | None:
        rows = self.conn.execute(
            """
            SELECT data_json
            FROM financial_statement
            WHERE asset_id = ?
              AND statement_type = 'cashflow'
            ORDER BY year DESC, quarter DESC
            LIMIT 8
            """,
            [asset_id.upper().strip()],
        ).fetchall()
        for row in rows:
            data = _json_object(row[0])
            fcf = _extract_number(data, ("freeCashFlow", "free_cash_flow", "free_cashflow"))
            if fcf is None:
                operating = _extract_number(
                    data,
                    ("operatingCashFlow", "cashFlowFromOperations", "netCashProvidedByOperatingActivities"),
                )
                capex = _extract_number(data, ("capitalExpenditure", "capital_expenditure", "capex"))
                if operating is not None and capex is not None:
                    fcf = operating - abs(capex)
            if fcf is not None and fcf > 0:
                return fcf
        return None

    def financial_statement_history(self, asset_id: str, statement_type: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT year, quarter, period_end_date, report_date, data_json
            FROM financial_statement
            WHERE asset_id = ?
              AND statement_type = ?
            ORDER BY year DESC, quarter DESC
            """,
            [asset_id.upper().strip(), statement_type],
        ).fetchall()
        return [
            {
                "year": int(row[0]),
                "quarter": int(row[1]),
                "period_end_date": row[2],
                "report_date": row[3],
                "data": _json_object(row[4]),
            }
            for row in rows
        ]

    def asset_profile(self, asset_id: str) -> dict[str, str | None]:
        row = self.conn.execute(
            """
            SELECT asset_type, asset_subtype, symbol
            FROM asset
            WHERE asset_id = ?
            """,
            [asset_id.upper().strip()],
        ).fetchone()
        if row is None:
            return {"asset_type": None, "asset_subtype": None, "symbol": None}
        return {"asset_type": row[0], "asset_subtype": row[1], "symbol": row[2]}

    def etf_profile(self, asset_id: str) -> dict[str, Any]:
        if not self._table_exists("etf_profile"):
            return {}
        row = self.conn.execute(
            """
            SELECT expense_ratio, benchmark_index_id
            FROM etf_profile
            WHERE asset_id = ?
            """,
            [asset_id.upper().strip()],
        ).fetchone()
        if row is None:
            return {}
        return {"expense_ratio": row[0], "benchmark_index_id": row[1]}

    def etf_holdings(self, asset_id: str) -> list[EtfHoldingAnalytics]:
        if not self._table_exists("etf_holding"):
            return []
        rows = self.conn.execute(
            """
            SELECT
                holding_symbol,
                holding_name,
                weight_pct,
                sector,
                country,
                currency
            FROM etf_holding
            WHERE asset_id = ?
            ORDER BY weight_pct DESC NULLS LAST, holding_symbol
            """,
            [asset_id.upper().strip()],
        ).fetchall()
        return [
            EtfHoldingAnalytics(
                holding_symbol=row[0],
                holding_name=row[1],
                weight=normalize_weight(row[2]),
                sector=row[3],
                country=row[4],
                currency=row[5],
            )
            for row in rows
        ]

    def portfolio_direct_holding_weights(self, portfolio_id: int) -> dict[str, tuple[str, float | None]]:
        rows = self.conn.execute(
            """
            SELECT
                p.asset_id,
                COALESCE(a.symbol, p.asset_id) AS symbol,
                p.qty * q.latest_price AS market_value
            FROM position p
            JOIN asset a
              ON a.asset_id = p.asset_id
            LEFT JOIN (
                SELECT asset_id, COALESCE(adj_close, close) AS latest_price
                FROM asset_quote_daily
                QUALIFY ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY date DESC) = 1
            ) q
              ON q.asset_id = p.asset_id
            WHERE p.portfolio_id = ?
              AND COALESCE(p.qty, 0) <> 0
            """,
            [portfolio_id],
        ).fetchall()
        total_value = sum(float(row[2]) for row in rows if row[2] is not None and row[2] > 0)
        result: dict[str, tuple[str, float | None]] = {}
        for row in rows:
            symbol = str(row[1]).upper()
            weight = float(row[2]) / total_value if row[2] is not None and total_value > 0 else None
            result[symbol] = (row[0], weight)
        return result

    def portfolio_positions(self, portfolio_id: int) -> list[tuple[int, str, float, float]]:
        rows = self.conn.execute(
            """
            SELECT portfolio_id, asset_id, qty, book_cost
            FROM position
            WHERE portfolio_id = ?
              AND COALESCE(qty, 0) <> 0
            ORDER BY asset_id
            """,
            [portfolio_id],
        ).fetchall()
        return [(int(row[0]), row[1], float(row[2]), float(row[3])) for row in rows]

    def portfolio_transactions(self, portfolio_id: int) -> list[tuple[Any, ...]]:
        rows = self.conn.execute(
            """
            SELECT
                txn_id,
                portfolio_id,
                time_stamp,
                txn_type,
                asset_id,
                qty,
                price,
                ccy,
                cash_amt,
                fee_amt
            FROM txn
            WHERE portfolio_id = ?
            ORDER BY time_stamp, txn_id
            """,
            [portfolio_id],
        ).fetchall()
        return rows

    def asset_exposure_metadata(self, asset_ids: list[str]) -> dict[str, dict[str, str | None]]:
        if not asset_ids:
            return {}
        placeholders = ", ".join("?" for _ in asset_ids)
        rows = self.conn.execute(
            f"""
            SELECT asset_id, sector, country, ccy
            FROM asset
            WHERE asset_id IN ({placeholders})
            """,
            asset_ids,
        ).fetchall()
        return {
            row[0]: {
                "sector": row[1],
                "country": row[2],
                "currency": row[3],
            }
            for row in rows
        }

    def tracked_asset_ids(self) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT asset_id
            FROM asset
            WHERE COALESCE(track, TRUE) = TRUE
            ORDER BY asset_id
            """
        ).fetchall()
        return [row[0] for row in rows]

    def portfolio_ids(self) -> list[int]:
        rows = self.conn.execute(
            """
            SELECT portfolio_id
            FROM portfolio
            ORDER BY portfolio_id
            """
        ).fetchall()
        return [int(row[0]) for row in rows]

    def _count(self, table_name: str) -> int:
        if not self._table_exists(table_name):
            return 0
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])

    def _table_exists(self, table_name: str) -> bool:
        row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_name = ?
            """,
            [table_name],
        ).fetchone()
        return bool(row and row[0])


class AnalyticsEngine:
    def __init__(self, repo: AnalyticsRepository) -> None:
        self.repo = repo

    def asset_report(
        self,
        asset_id: str,
        benchmark_index_id: str | None = None,
        portfolio_id: int | None = None,
        risk_free_rate: float = 0.0,
        discount_rate: float = 0.10,
        dividend_growth_rate: float = 0.03,
        terminal_growth_rate: float = 0.03,
        forecast_years: int = 5,
    ) -> AssetAnalyticsReport:
        asset_id = asset_id.upper().strip()
        prices = self.repo.price_history(asset_id)
        benchmark = (
            self.repo.benchmark_price_history(benchmark_index_id)
            if benchmark_index_id is not None
            else []
        )
        latest_price = prices[-1].close if prices else self.repo.latest_price(asset_id)

        dividend = self.repo.annual_dividend_per_share(asset_id, prices[-1].date if prices else None)
        fcf = self.repo.latest_free_cash_flow(asset_id)
        shares = self.repo.shares_outstanding(asset_id)
        fcf_per_share = fcf / shares if fcf is not None and shares else None
        valuation_depth = valuation_depth_metrics(
            income_statements=self.repo.financial_statement_history(asset_id, "income"),
            balance_sheets=self.repo.financial_statement_history(asset_id, "balance"),
            cashflow_statements=self.repo.financial_statement_history(asset_id, "cashflow"),
            market_price=latest_price,
            shares_outstanding=shares,
            annual_dividend=dividend,
            discount_rate=discount_rate,
            base_growth_rate=dividend_growth_rate,
            terminal_growth_rate=terminal_growth_rate,
            forecast_years=forecast_years,
        )
        etf = etf_analytics(
            asset_id=asset_id,
            asset_profile=self.repo.asset_profile(asset_id),
            etf_profile=self.repo.etf_profile(asset_id),
            holdings=self.repo.etf_holdings(asset_id),
            annual_distribution_per_share=dividend,
            latest_price=latest_price,
            price_history=prices,
            benchmark_price_history=self.repo.benchmark_price_history(
                benchmark_index_id or self.repo.etf_profile(asset_id).get("benchmark_index_id")
            )
            if (benchmark_index_id or self.repo.etf_profile(asset_id).get("benchmark_index_id"))
            else [],
            direct_portfolio_weights=self.repo.portfolio_direct_holding_weights(portfolio_id)
            if portfolio_id is not None
            else {},
        )
        forecast = asset_forecast_metrics(
            market_price=latest_price,
            risk= risk_return_metrics(prices, risk_free_rate=risk_free_rate),
            valuation_depth=valuation_depth,
            dividend_history=self.repo.dividend_history(asset_id),
            annual_dividend=dividend,
            forecast_years=forecast_years,
        )

        return AssetAnalyticsReport(
            asset_id=asset_id,
            latest_price=latest_price,
            data_coverage=self.repo.data_coverage(),
            risk=risk_return_metrics(prices, risk_free_rate=risk_free_rate),
            relative=relative_risk_metrics(prices, benchmark, risk_free_rate)
            if benchmark
            else None,
            dividend_discount=dividend_discount_model(
                annual_dividend=dividend,
                market_price=latest_price,
                discount_rate=discount_rate,
                growth_rate=dividend_growth_rate,
                forecast_years=forecast_years,
            ),
            discounted_cash_flow=discounted_cash_flow_model(
                cashflow_per_share=fcf_per_share,
                market_price=latest_price,
                discount_rate=discount_rate,
                growth_rate=dividend_growth_rate,
                terminal_growth_rate=terminal_growth_rate,
                forecast_years=forecast_years,
            ),
            valuation_depth=valuation_depth,
            etf=etf,
            forecast=forecast,
        )

    def portfolio_report(
        self,
        portfolio_id: int,
        benchmark_index_id: str | None = None,
        risk_free_rate: float = 0.0,
    ) -> PortfolioAnalyticsReport:
        positions = []
        missing: list[str] = []
        total_value = 0.0

        for row in self.repo.portfolio_positions(portfolio_id):
            _portfolio_id, asset_id, qty, book_cost = row
            latest_price = self.repo.latest_price(asset_id)
            market_value = qty * latest_price if latest_price is not None else None
            if market_value is None:
                missing.append(f"{asset_id}: latest price")
            else:
                total_value += market_value
            positions.append(
                PositionAnalytics(
                    portfolio_id=portfolio_id,
                    asset_id=asset_id,
                    qty=qty,
                    book_cost=book_cost,
                    latest_price=latest_price,
                    market_value=market_value,
                    weight=None,
                    unrealized_gain=market_value - book_cost if market_value is not None else None,
                )
            )

        weighted_positions = [
            PositionAnalytics(
                portfolio_id=p.portfolio_id,
                asset_id=p.asset_id,
                qty=p.qty,
                book_cost=p.book_cost,
                latest_price=p.latest_price,
                market_value=p.market_value,
                weight=p.market_value / total_value if p.market_value is not None and total_value > 0 else None,
                unrealized_gain=p.unrealized_gain,
            )
            for p in positions
        ]

        portfolio_prices = self._synthetic_portfolio_prices(weighted_positions)
        performance = portfolio_performance_metrics(
            transactions=self.repo.portfolio_transactions(portfolio_id),
            ending_market_value=total_value,
            unrealized_gain=sum(
                p.unrealized_gain for p in weighted_positions if p.unrealized_gain is not None
            )
            if weighted_positions
            else None,
        )
        risk_decomposition = portfolio_risk_decomposition(
            positions=weighted_positions,
            price_history_by_asset={
                p.asset_id: self.repo.price_history(p.asset_id)
                for p in weighted_positions
                if p.weight is not None and p.weight > 0
            },
            exposure_metadata=self.repo.asset_exposure_metadata(
                [p.asset_id for p in weighted_positions]
            ),
        )
        benchmark = (
            self.repo.benchmark_price_history(benchmark_index_id)
            if benchmark_index_id is not None
            else []
        )

        risk = risk_return_metrics(portfolio_prices, risk_free_rate) if portfolio_prices else None
        relative = (
            relative_risk_metrics(portfolio_prices, benchmark, risk_free_rate)
            if portfolio_prices and benchmark
            else None
        )
        forecast = portfolio_forecast_metrics(
            market_value=total_value,
            risk=risk,
            performance=performance,
            forecast_years=5,
        )
        if not weighted_positions:
            missing.append("portfolio positions")
        if not portfolio_prices:
            missing.append("overlapping position price history")

        return PortfolioAnalyticsReport(
            portfolio_id=portfolio_id,
            positions=weighted_positions,
            market_value=total_value,
            performance=performance,
            risk_decomposition=risk_decomposition,
            risk=risk,
            relative=relative,
            forecast=forecast,
            missing_inputs=missing,
        )

    def _synthetic_portfolio_prices(self, positions: list[PositionAnalytics]) -> list[PricePoint]:
        weighted = [p for p in positions if p.weight is not None and p.weight > 0]
        if not weighted:
            return []

        series_by_asset = {
            p.asset_id: {point.date: point.close for point in self.repo.price_history(p.asset_id)}
            for p in weighted
        }
        common_dates = set.intersection(*(set(series) for series in series_by_asset.values()))
        if not common_dates:
            return []

        sorted_dates = sorted(common_dates)
        bases = {
            asset_id: series_by_asset[asset_id][sorted_dates[0]]
            for asset_id in series_by_asset
            if series_by_asset[asset_id][sorted_dates[0]] > 0
        }
        if len(bases) != len(series_by_asset):
            return []

        points: list[PricePoint] = []
        for point_date in sorted_dates:
            normalized_value = 0.0
            for position in weighted:
                price = series_by_asset[position.asset_id][point_date]
                normalized_value += position.weight * (price / bases[position.asset_id])
            points.append(PricePoint(point_date, normalized_value))
        return points


class AnalyticsStorageService:
    """Optional persistence for the latest analytics snapshots.

    The service is inert unless ``enabled`` is true. That lets users calculate
    analytics ad hoc without storing records, while users who want an AI-ready
    cache can opt into daily and portfolio-change refreshes.
    """

    def __init__(
        self,
        conn: Any,
        enabled: bool = False,
        benchmark_index_id: str | None = None,
        risk_free_rate: float = 0.0,
    ) -> None:
        self.conn = conn
        self.enabled = enabled
        self.benchmark_index_id = benchmark_index_id
        self.risk_free_rate = risk_free_rate
        self.repo = AnalyticsRepository(conn)
        self.engine = AnalyticsEngine(self.repo)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if enabled:
            self.ensure_schema()
        else:
            if self.repo._table_exists("analytics_storage_config"):
                self.conn.execute(
                    """
                    INSERT INTO analytics_storage_config(config_key, config_value, updated_at)
                    VALUES ('enabled', 'false', now())
                    ON CONFLICT(config_key) DO UPDATE SET
                        config_value = excluded.config_value,
                        updated_at = now()
                    """
                )
            return

        self.conn.execute(
            """
            INSERT INTO analytics_storage_config(config_key, config_value, updated_at)
            VALUES ('enabled', 'true', now())
            ON CONFLICT(config_key) DO UPDATE SET
                config_value = excluded.config_value,
                updated_at = now()
            """
        )

    def refresh_due(
        self,
        as_of_date: date | None = None,
        asset_ids: list[str] | None = None,
        portfolio_ids: list[int] | None = None,
    ) -> AnalyticsRefreshResult:
        if not self.enabled:
            return AnalyticsRefreshResult(skipped=True, reason="analytics storage disabled")

        self.ensure_schema()
        as_of_date = as_of_date or date.today()
        asset_ids = asset_ids if asset_ids is not None else self.repo.tracked_asset_ids()
        portfolio_ids = portfolio_ids if portfolio_ids is not None else self.repo.portfolio_ids()

        assets_stored = 0
        for asset_id in asset_ids:
            if self._asset_due(asset_id, as_of_date):
                report = self.engine.asset_report(
                    asset_id,
                    benchmark_index_id=self.benchmark_index_id,
                    risk_free_rate=self.risk_free_rate,
                )
                self.store_asset_report(report, as_of_date)
                assets_stored += 1

        portfolios_stored = 0
        for portfolio_id in portfolio_ids:
            signature = self.portfolio_signature(portfolio_id)
            if self._portfolio_due(portfolio_id, as_of_date, signature):
                report = self.engine.portfolio_report(
                    portfolio_id,
                    benchmark_index_id=self.benchmark_index_id,
                    risk_free_rate=self.risk_free_rate,
                )
                self.store_portfolio_report(report, as_of_date, signature)
                portfolios_stored += 1

        return AnalyticsRefreshResult(
            assets_stored=assets_stored,
            portfolios_stored=portfolios_stored,
        )

    def store_asset_report(self, report: AssetAnalyticsReport, as_of_date: date) -> None:
        payload = _json_dumps(report)
        latest_missing = sorted(
            set(report.dividend_discount.missing_inputs + report.discounted_cash_flow.missing_inputs)
        )
        self.conn.execute(
            """
            INSERT INTO asset_analytics_snapshot (
                asset_id,
                snapshot_date,
                latest_price,
                cagr,
                sharpe_ratio,
                sortino_ratio,
                beta,
                alpha_annualized,
                dividend_discount_value,
                discounted_cash_flow_value,
                implied_dividend_growth,
                implied_dcf_growth,
                payload_json,
                missing_inputs_json,
                refreshed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
            ON CONFLICT(asset_id, snapshot_date) DO UPDATE SET
                latest_price = excluded.latest_price,
                cagr = excluded.cagr,
                sharpe_ratio = excluded.sharpe_ratio,
                sortino_ratio = excluded.sortino_ratio,
                beta = excluded.beta,
                alpha_annualized = excluded.alpha_annualized,
                dividend_discount_value = excluded.dividend_discount_value,
                discounted_cash_flow_value = excluded.discounted_cash_flow_value,
                implied_dividend_growth = excluded.implied_dividend_growth,
                implied_dcf_growth = excluded.implied_dcf_growth,
                payload_json = excluded.payload_json,
                missing_inputs_json = excluded.missing_inputs_json,
                refreshed_at = now()
            """,
            [
                report.asset_id,
                as_of_date,
                report.latest_price,
                report.risk.cagr,
                report.risk.sharpe_ratio,
                report.risk.sortino_ratio,
                report.relative.beta if report.relative else None,
                report.relative.alpha_annualized if report.relative else None,
                report.dividend_discount.intrinsic_value_per_share,
                report.discounted_cash_flow.intrinsic_value_per_share,
                report.dividend_discount.implied_growth_rate,
                report.discounted_cash_flow.implied_growth_rate,
                payload,
                json.dumps(latest_missing),
            ],
        )
        self._upsert_refresh_state("asset", report.asset_id, as_of_date, None)

    def store_portfolio_report(
        self,
        report: PortfolioAnalyticsReport,
        as_of_date: date,
        state_signature: str | None = None,
    ) -> None:
        signature = state_signature or self.portfolio_signature(report.portfolio_id)
        self.conn.execute(
            """
            INSERT INTO portfolio_analytics_snapshot (
                portfolio_id,
                snapshot_date,
                market_value,
                cagr,
                sharpe_ratio,
                sortino_ratio,
                beta,
                alpha_annualized,
                position_count,
                state_signature,
                payload_json,
                missing_inputs_json,
                refreshed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
            ON CONFLICT(portfolio_id, snapshot_date) DO UPDATE SET
                market_value = excluded.market_value,
                cagr = excluded.cagr,
                sharpe_ratio = excluded.sharpe_ratio,
                sortino_ratio = excluded.sortino_ratio,
                beta = excluded.beta,
                alpha_annualized = excluded.alpha_annualized,
                position_count = excluded.position_count,
                state_signature = excluded.state_signature,
                payload_json = excluded.payload_json,
                missing_inputs_json = excluded.missing_inputs_json,
                refreshed_at = now()
            """,
            [
                report.portfolio_id,
                as_of_date,
                report.market_value,
                report.risk.cagr if report.risk else None,
                report.risk.sharpe_ratio if report.risk else None,
                report.risk.sortino_ratio if report.risk else None,
                report.relative.beta if report.relative else None,
                report.relative.alpha_annualized if report.relative else None,
                len(report.positions),
                signature,
                _json_dumps(report),
                json.dumps(report.missing_inputs),
            ],
        )
        self._upsert_refresh_state("portfolio", str(report.portfolio_id), as_of_date, signature)

    def portfolio_signature(self, portfolio_id: int) -> str:
        rows = self.conn.execute(
            """
            SELECT
                p.asset_id,
                p.qty,
                p.book_cost,
                p.updated_at,
                MAX(q.date) AS latest_price_date
            FROM position p
            LEFT JOIN asset_quote_daily q
              ON q.asset_id = p.asset_id
            WHERE p.portfolio_id = ?
            GROUP BY p.asset_id, p.qty, p.book_cost, p.updated_at
            ORDER BY p.asset_id
            """,
            [portfolio_id],
        ).fetchall()
        encoded = json.dumps([_json_ready(row) for row in rows], sort_keys=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def ensure_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analytics_storage_config (
                config_key TEXT PRIMARY KEY,
                config_value TEXT NOT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT now()
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS asset_analytics_snapshot (
                asset_id TEXT NOT NULL,
                snapshot_date DATE NOT NULL,
                latest_price DOUBLE,
                cagr DOUBLE,
                sharpe_ratio DOUBLE,
                sortino_ratio DOUBLE,
                beta DOUBLE,
                alpha_annualized DOUBLE,
                dividend_discount_value DOUBLE,
                discounted_cash_flow_value DOUBLE,
                implied_dividend_growth DOUBLE,
                implied_dcf_growth DOUBLE,
                payload_json TEXT NOT NULL,
                missing_inputs_json TEXT,
                refreshed_at TIMESTAMP NOT NULL DEFAULT now(),
                PRIMARY KEY(asset_id, snapshot_date)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS portfolio_analytics_snapshot (
                portfolio_id BIGINT NOT NULL,
                snapshot_date DATE NOT NULL,
                market_value DOUBLE,
                cagr DOUBLE,
                sharpe_ratio DOUBLE,
                sortino_ratio DOUBLE,
                beta DOUBLE,
                alpha_annualized DOUBLE,
                position_count INTEGER NOT NULL DEFAULT 0,
                state_signature TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                missing_inputs_json TEXT,
                refreshed_at TIMESTAMP NOT NULL DEFAULT now(),
                PRIMARY KEY(portfolio_id, snapshot_date)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analytics_refresh_state (
                subject_type TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                last_snapshot_date DATE,
                last_refreshed_at TIMESTAMP,
                state_signature TEXT,
                PRIMARY KEY(subject_type, subject_id)
            )
            """
        )

    def _asset_due(self, asset_id: str, as_of_date: date) -> bool:
        row = self.conn.execute(
            """
            SELECT last_snapshot_date
            FROM analytics_refresh_state
            WHERE subject_type = 'asset'
              AND subject_id = ?
            """,
            [asset_id],
        ).fetchone()
        return row is None or row[0] is None or row[0] < as_of_date

    def _portfolio_due(self, portfolio_id: int, as_of_date: date, signature: str) -> bool:
        row = self.conn.execute(
            """
            SELECT last_snapshot_date, state_signature
            FROM analytics_refresh_state
            WHERE subject_type = 'portfolio'
              AND subject_id = ?
            """,
            [str(portfolio_id)],
        ).fetchone()
        return (
            row is None
            or row[0] is None
            or row[0] < as_of_date
            or row[1] != signature
        )

    def _upsert_refresh_state(
        self,
        subject_type: str,
        subject_id: str,
        snapshot_date: date,
        state_signature: str | None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO analytics_refresh_state (
                subject_type,
                subject_id,
                last_snapshot_date,
                last_refreshed_at,
                state_signature
            )
            VALUES (?, ?, ?, now(), ?)
            ON CONFLICT(subject_type, subject_id) DO UPDATE SET
                last_snapshot_date = excluded.last_snapshot_date,
                last_refreshed_at = now(),
                state_signature = excluded.state_signature
            """,
            [subject_type, subject_id, snapshot_date, state_signature],
        )


def risk_return_metrics(
    prices: list[PricePoint],
    risk_free_rate: float = 0.0,
) -> RiskReturnMetrics:
    clean = [p for p in prices if p.close > 0]
    returns = simple_returns([p.close for p in clean])
    start_date = clean[0].date if clean else None
    end_date = clean[-1].date if clean else None
    cumulative = clean[-1].close / clean[0].close - 1.0 if len(clean) >= 2 else None
    years = _years_between(start_date, end_date)
    cagr_value = cagr(clean[0].close, clean[-1].close, years) if years else None
    vol = annualized_volatility(returns)
    downside = downside_deviation(returns, risk_free_rate / TRADING_DAYS_PER_YEAR)
    excess_cagr = cagr_value - risk_free_rate if cagr_value is not None else None
    sharpe = ratio(excess_cagr, vol)
    sortino = ratio(excess_cagr, downside)
    drawdown = max_drawdown([p.close for p in clean])

    return RiskReturnMetrics(
        start_date=start_date,
        end_date=end_date,
        observations=len(clean),
        cumulative_return=cumulative,
        cagr=cagr_value,
        annualized_volatility=vol,
        downside_deviation=downside,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown=drawdown,
        best_daily_return=max(returns) if returns else None,
        worst_daily_return=min(returns) if returns else None,
    )


def relative_risk_metrics(
    asset_prices: list[PricePoint],
    benchmark_prices: list[PricePoint],
    risk_free_rate: float = 0.0,
) -> RelativeRiskMetrics:
    asset_by_date = {p.date: p.close for p in asset_prices if p.close > 0}
    benchmark_by_date = {p.date: p.close for p in benchmark_prices if p.close > 0}
    dates = sorted(set(asset_by_date).intersection(benchmark_by_date))
    if len(dates) < 3:
        return RelativeRiskMetrics(0, None, None, None, None, None)

    asset_returns = simple_returns([asset_by_date[d] for d in dates])
    benchmark_returns = simple_returns([benchmark_by_date[d] for d in dates])
    beta_value = beta(asset_returns, benchmark_returns)
    corr = correlation(asset_returns, benchmark_returns)

    asset_years = _years_between(dates[0], dates[-1])
    asset_cagr = cagr(asset_by_date[dates[0]], asset_by_date[dates[-1]], asset_years) if asset_years else None
    benchmark_cagr = (
        cagr(benchmark_by_date[dates[0]], benchmark_by_date[dates[-1]], asset_years)
        if asset_years
        else None
    )
    alpha = None
    if asset_cagr is not None and benchmark_cagr is not None and beta_value is not None:
        alpha = asset_cagr - (risk_free_rate + beta_value * (benchmark_cagr - risk_free_rate))

    return RelativeRiskMetrics(
        observations=len(asset_returns),
        beta=beta_value,
        alpha_annualized=alpha,
        correlation=corr,
        r_squared=corr * corr if corr is not None else None,
        excess_cagr=asset_cagr - benchmark_cagr
        if asset_cagr is not None and benchmark_cagr is not None
        else None,
    )


def portfolio_performance_metrics(
    transactions: list[tuple[Any, ...]],
    ending_market_value: float,
    unrealized_gain: float | None,
) -> PortfolioPerformanceMetrics:
    if not transactions:
        return PortfolioPerformanceMetrics(
            start_date=None,
            end_date=None,
            beginning_market_value=0.0,
            ending_market_value=ending_market_value,
            net_contributions=0.0,
            net_withdrawals=0.0,
            net_external_cash_flow=0.0,
            dividend_income=0.0,
            realized_gain=None,
            unrealized_gain=unrealized_gain,
            total_gain=unrealized_gain,
            modified_dietz_return=None,
            money_weighted_return=None,
            missing_inputs=["portfolio transactions"],
        )

    start_date = _txn_date(transactions[0])
    end_date = date.today()
    contributions = 0.0
    withdrawals = 0.0
    dividend_income = 0.0
    dated_external_flows: list[tuple[date, float]] = []
    investor_cash_flows: list[tuple[date, float]] = []

    for txn in transactions:
        txn_type = str(txn[3]).lower()
        txn_date = _txn_date(txn)
        amount = _txn_cash_value(txn)
        if txn_type == "contribution" and amount is not None:
            value = abs(amount)
            contributions += value
            dated_external_flows.append((txn_date, value))
            investor_cash_flows.append((txn_date, -value))
        elif txn_type == "withdrawal" and amount is not None:
            value = abs(amount)
            withdrawals += value
            dated_external_flows.append((txn_date, -value))
            investor_cash_flows.append((txn_date, value))
        elif txn_type == "dividend":
            dividend_income += max(0.0, (amount or 0.0) - _txn_fee(txn))

    realized_gain, realized_missing = average_cost_realized_gain(transactions)
    total_gain = None
    if realized_gain is not None or unrealized_gain is not None:
        total_gain = (realized_gain or 0.0) + (unrealized_gain or 0.0) + dividend_income

    external_flow = contributions - withdrawals
    dietz = modified_dietz_return(
        beginning_market_value=0.0,
        ending_market_value=ending_market_value,
        external_flows=dated_external_flows,
        start_date=start_date,
        end_date=end_date,
    )
    if ending_market_value > 0:
        investor_cash_flows.append((end_date, ending_market_value))
    mwr = money_weighted_return(investor_cash_flows)

    missing = []
    if realized_missing:
        missing.extend(realized_missing)
    if not dated_external_flows and ending_market_value > 0:
        missing.append("external cash flows")

    return PortfolioPerformanceMetrics(
        start_date=start_date,
        end_date=end_date,
        beginning_market_value=0.0,
        ending_market_value=ending_market_value,
        net_contributions=contributions,
        net_withdrawals=withdrawals,
        net_external_cash_flow=external_flow,
        dividend_income=dividend_income,
        realized_gain=realized_gain,
        unrealized_gain=unrealized_gain,
        total_gain=total_gain,
        modified_dietz_return=dietz,
        money_weighted_return=mwr,
        missing_inputs=missing,
    )


def average_cost_realized_gain(transactions: list[tuple[Any, ...]]) -> tuple[float | None, list[str]]:
    lots: dict[str, dict[str, float]] = {}
    realized = 0.0
    saw_sell = False
    missing: list[str] = []

    for txn in transactions:
        txn_type = str(txn[3]).lower()
        asset_id = txn[4]
        if asset_id is None or txn_type not in {"buy", "sell"}:
            continue

        qty = abs(float(txn[5] or 0.0))
        price = float(txn[6] or 0.0)
        fee = _txn_fee(txn)
        if qty <= 0 or price <= 0:
            missing.append(f"{asset_id}: {txn_type} quantity or price")
            continue

        lot = lots.setdefault(asset_id, {"qty": 0.0, "cost": 0.0})
        if txn_type == "buy":
            lot["qty"] += qty
            lot["cost"] += qty * price + fee
            continue

        saw_sell = True
        if lot["qty"] <= 0:
            missing.append(f"{asset_id}: sell without tracked cost basis")
            continue

        sell_qty = min(qty, lot["qty"])
        average_cost = lot["cost"] / lot["qty"]
        basis = average_cost * sell_qty
        proceeds = sell_qty * price - fee
        realized += proceeds - basis
        lot["qty"] -= sell_qty
        lot["cost"] -= basis

        if qty > sell_qty:
            missing.append(f"{asset_id}: partial sell without enough tracked cost basis")

    return (realized if saw_sell else 0.0), sorted(set(missing))


def modified_dietz_return(
    beginning_market_value: float,
    ending_market_value: float,
    external_flows: list[tuple[date, float]],
    start_date: date | None,
    end_date: date | None,
) -> float | None:
    if start_date is None or end_date is None:
        return None
    total_days = max(1, (end_date - start_date).days)
    weighted_flows = 0.0
    total_flows = 0.0
    for flow_date, amount in external_flows:
        days_remaining = max(0, (end_date - flow_date).days)
        weight = days_remaining / total_days
        weighted_flows += amount * weight
        total_flows += amount

    denominator = beginning_market_value + weighted_flows
    if denominator == 0:
        return None
    return (ending_market_value - beginning_market_value - total_flows) / denominator


def money_weighted_return(cash_flows: list[tuple[date, float]]) -> float | None:
    if len(cash_flows) < 2:
        return None

    values = [amount for _flow_date, amount in cash_flows]
    if not any(value < 0 for value in values) or not any(value > 0 for value in values):
        return None

    start_date = min(flow_date for flow_date, _amount in cash_flows)

    def npv(rate: float) -> float:
        total = 0.0
        for flow_date, amount in cash_flows:
            years = max(0.0, (flow_date - start_date).days / 365.25)
            total += amount / ((1 + rate) ** years)
        return total

    low = -0.999
    high = 10.0
    low_value = npv(low)
    high_value = npv(high)
    if low_value * high_value > 0:
        return None

    for _ in range(100):
        mid = (low + high) / 2
        mid_value = npv(mid)
        if abs(mid_value) < 1e-8:
            return mid
        if low_value * mid_value <= 0:
            high = mid
            high_value = mid_value
        else:
            low = mid
            low_value = mid_value
    return (low + high) / 2


def portfolio_risk_decomposition(
    positions: list[PositionAnalytics],
    price_history_by_asset: dict[str, list[PricePoint]],
    exposure_metadata: dict[str, dict[str, str | None]] | None = None,
) -> PortfolioRiskDecomposition:
    weighted_positions = [p for p in positions if p.weight is not None and p.weight > 0]
    weights = {p.asset_id: float(p.weight or 0.0) for p in weighted_positions}
    asset_ids = [p.asset_id for p in weighted_positions]
    missing: list[str] = []

    hhi = sum(weight * weight for weight in weights.values()) if weights else None
    effective_count = 1 / hhi if hhi and hhi > 0 else None
    largest_weight = max(weights.values()) if weights else None
    diversification = diversification_score(weights)

    aligned_returns = aligned_asset_returns(price_history_by_asset, asset_ids)
    if len(aligned_returns) < 2 and asset_ids:
        missing.append("overlapping asset return history")

    returns_by_asset = {
        asset_id: [row[asset_id] for row in aligned_returns]
        for asset_id in asset_ids
        if aligned_returns and asset_id in aligned_returns[0]
    }
    correlation_mat = correlation_matrix(returns_by_asset)
    average_corr = average_pairwise_correlation(correlation_mat)
    portfolio_vol = portfolio_annualized_volatility(returns_by_asset, weights)
    contributions = portfolio_volatility_contributions(
        returns_by_asset=returns_by_asset,
        weights=weights,
        portfolio_volatility=portfolio_vol,
    )
    exposure_metadata = exposure_metadata or {}

    return PortfolioRiskDecomposition(
        asset_count=len(asset_ids),
        effective_asset_count=effective_count,
        concentration_hhi=hhi,
        largest_position_weight=largest_weight,
        diversification_score=diversification,
        portfolio_volatility=portfolio_vol,
        average_pairwise_correlation=average_corr,
        correlation_matrix=correlation_mat,
        volatility_contributions=contributions,
        sector_exposure=dimension_exposure(weights, exposure_metadata, "sector"),
        country_exposure=dimension_exposure(weights, exposure_metadata, "country"),
        currency_exposure=dimension_exposure(weights, exposure_metadata, "currency"),
        missing_inputs=missing,
    )


def diversification_score(weights: dict[str, float]) -> float | None:
    if not weights:
        return None
    if len(weights) == 1:
        return 0.0
    hhi = sum(weight * weight for weight in weights.values())
    minimum_hhi = 1 / len(weights)
    if hhi <= minimum_hhi:
        return 100.0
    return max(0.0, min(100.0, 100.0 * (1.0 - hhi) / (1.0 - minimum_hhi)))


def aligned_asset_returns(
    price_history_by_asset: dict[str, list[PricePoint]],
    asset_ids: list[str],
) -> list[dict[str, float]]:
    if not asset_ids:
        return []
    prices_by_asset = {
        asset_id: {point.date: point.close for point in price_history_by_asset.get(asset_id, [])}
        for asset_id in asset_ids
    }
    if any(not prices for prices in prices_by_asset.values()):
        return []
    common_dates = sorted(set.intersection(*(set(prices) for prices in prices_by_asset.values())))
    rows: list[dict[str, float]] = []
    for previous_date, current_date in zip(common_dates, common_dates[1:]):
        row: dict[str, float] = {}
        valid = True
        for asset_id in asset_ids:
            previous_price = prices_by_asset[asset_id][previous_date]
            current_price = prices_by_asset[asset_id][current_date]
            if previous_price <= 0 or current_price <= 0:
                valid = False
                break
            row[asset_id] = current_price / previous_price - 1.0
        if valid:
            rows.append(row)
    return rows


def correlation_matrix(
    returns_by_asset: dict[str, list[float]],
) -> dict[str, dict[str, float | None]]:
    asset_ids = sorted(returns_by_asset)
    matrix: dict[str, dict[str, float | None]] = {}
    for left in asset_ids:
        matrix[left] = {}
        for right in asset_ids:
            if left == right:
                matrix[left][right] = 1.0 if len(returns_by_asset[left]) >= 2 else None
            else:
                matrix[left][right] = correlation(returns_by_asset[left], returns_by_asset[right])
    return matrix


def average_pairwise_correlation(matrix: dict[str, dict[str, float | None]]) -> float | None:
    values: list[float] = []
    asset_ids = sorted(matrix)
    for i, left in enumerate(asset_ids):
        for right in asset_ids[i + 1 :]:
            value = matrix[left][right]
            if value is not None:
                values.append(value)
    if not values:
        return None
    return sum(values) / len(values)


def portfolio_annualized_volatility(
    returns_by_asset: dict[str, list[float]],
    weights: dict[str, float],
) -> float | None:
    portfolio_returns = portfolio_returns_from_components(returns_by_asset, weights)
    return annualized_volatility(portfolio_returns)


def portfolio_returns_from_components(
    returns_by_asset: dict[str, list[float]],
    weights: dict[str, float],
) -> list[float]:
    if not returns_by_asset:
        return []
    lengths = {len(values) for values in returns_by_asset.values()}
    if len(lengths) != 1:
        return []
    count = lengths.pop()
    rows = []
    for idx in range(count):
        rows.append(
            sum(weights.get(asset_id, 0.0) * returns[idx] for asset_id, returns in returns_by_asset.items())
        )
    return rows


def portfolio_volatility_contributions(
    returns_by_asset: dict[str, list[float]],
    weights: dict[str, float],
    portfolio_volatility: float | None,
) -> list[AssetRiskContribution]:
    asset_ids = sorted(weights)
    if not asset_ids:
        return []
    if portfolio_volatility is None or portfolio_volatility <= 0 or not returns_by_asset:
        return [
            AssetRiskContribution(
                asset_id=asset_id,
                weight=weights[asset_id],
                annualized_volatility=annualized_volatility(returns_by_asset.get(asset_id, [])),
                portfolio_volatility_contribution=None,
                percent_of_portfolio_volatility=None,
            )
            for asset_id in asset_ids
        ]

    portfolio_returns = portfolio_returns_from_components(returns_by_asset, weights)
    portfolio_daily_volatility = statistics.stdev(portfolio_returns)
    if portfolio_daily_volatility == 0:
        return []

    contributions: list[AssetRiskContribution] = []
    for asset_id in asset_ids:
        asset_returns = returns_by_asset.get(asset_id, [])
        covariance = sample_covariance(asset_returns, portfolio_returns)
        marginal_contribution = covariance / portfolio_daily_volatility
        annualized_contribution = (
            weights[asset_id] * marginal_contribution * math.sqrt(TRADING_DAYS_PER_YEAR)
        )
        percent = annualized_contribution / portfolio_volatility if portfolio_volatility else None
        contributions.append(
            AssetRiskContribution(
                asset_id=asset_id,
                weight=weights[asset_id],
                annualized_volatility=annualized_volatility(asset_returns),
                portfolio_volatility_contribution=annualized_contribution,
                percent_of_portfolio_volatility=percent,
            )
        )
    return contributions


def sample_covariance(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / (len(xs) - 1)


def dimension_exposure(
    weights: dict[str, float],
    exposure_metadata: dict[str, dict[str, str | None]],
    dimension: str,
) -> dict[str, float]:
    exposure: dict[str, float] = {}
    for asset_id, weight in weights.items():
        value = exposure_metadata.get(asset_id, {}).get(dimension) or "Unknown"
        exposure[value] = exposure.get(value, 0.0) + weight
    return dict(sorted(exposure.items()))


def valuation_depth_metrics(
    income_statements: list[dict[str, Any]],
    balance_sheets: list[dict[str, Any]],
    cashflow_statements: list[dict[str, Any]],
    market_price: float | None,
    shares_outstanding: float | None,
    annual_dividend: float | None,
    discount_rate: float,
    base_growth_rate: float,
    terminal_growth_rate: float,
    forecast_years: int = 5,
) -> ValuationDepthMetrics:
    latest_income = _latest_statement_data(income_statements)
    previous_income = _previous_statement_data(income_statements)
    latest_balance = _latest_statement_data(balance_sheets)
    latest_cashflow = _latest_statement_data(cashflow_statements)
    previous_cashflow = _previous_statement_data(cashflow_statements)

    revenue = _extract_number(latest_income, REVENUE_ALIASES)
    previous_revenue = _extract_number(previous_income, REVENUE_ALIASES)
    gross_profit = _extract_number(latest_income, GROSS_PROFIT_ALIASES)
    operating_income = _extract_number(latest_income, OPERATING_INCOME_ALIASES)
    net_income = _extract_number(latest_income, NET_INCOME_ALIASES)
    eps = _extract_number(latest_income, EPS_ALIASES)
    previous_eps = _extract_number(previous_income, EPS_ALIASES)
    ebitda = _extract_number(latest_income, EBITDA_ALIASES)

    total_equity = _extract_number(latest_balance, EQUITY_ALIASES)
    total_assets = _extract_number(latest_balance, ASSETS_ALIASES)
    total_debt = _extract_number(latest_balance, DEBT_ALIASES)
    cash = _extract_number(latest_balance, CASH_ALIASES)

    fcf = _free_cash_flow_from_statement(latest_cashflow)
    previous_fcf = _free_cash_flow_from_statement(previous_cashflow)
    fcf_per_share = fcf / shares_outstanding if fcf is not None and shares_outstanding else None
    book_value_per_share = (
        total_equity / shares_outstanding
        if total_equity is not None and shares_outstanding
        else None
    )
    revenue_per_share = revenue / shares_outstanding if revenue is not None and shares_outstanding else None
    enterprise_value = None
    if market_price is not None and shares_outstanding:
        enterprise_value = market_price * shares_outstanding + (total_debt or 0.0) - (cash or 0.0)

    missing = valuation_missing_inputs(
        latest_income=latest_income,
        latest_balance=latest_balance,
        latest_cashflow=latest_cashflow,
        shares_outstanding=shares_outstanding,
        market_price=market_price,
        fcf=fcf,
    )

    return ValuationDepthMetrics(
        revenue_growth_yoy=growth_rate(revenue, previous_revenue),
        eps_growth_yoy=growth_rate(eps, previous_eps),
        free_cash_flow_growth_yoy=growth_rate(fcf, previous_fcf),
        gross_margin=safe_div(gross_profit, revenue),
        operating_margin=safe_div(operating_income, revenue),
        net_margin=safe_div(net_income, revenue),
        return_on_equity=safe_div(net_income, total_equity),
        return_on_assets=safe_div(net_income, total_assets),
        debt_to_equity=safe_div(total_debt, total_equity),
        net_debt_to_ebitda=safe_div((total_debt or 0.0) - (cash or 0.0), ebitda)
        if total_debt is not None or cash is not None
        else None,
        payout_ratio=safe_div(annual_dividend, eps),
        pe_ratio=safe_div(market_price, eps),
        price_to_book=safe_div(market_price, book_value_per_share),
        price_to_sales=safe_div(market_price, revenue_per_share),
        price_to_free_cash_flow=safe_div(market_price, fcf_per_share),
        ev_to_ebitda=safe_div(enterprise_value, ebitda),
        dcf_scenarios=dcf_scenarios(
            cashflow_per_share=fcf_per_share,
            market_price=market_price,
            discount_rate=discount_rate,
            base_growth_rate=base_growth_rate,
            terminal_growth_rate=terminal_growth_rate,
            forecast_years=forecast_years,
        ),
        missing_inputs=missing,
    )


def dcf_scenarios(
    cashflow_per_share: float | None,
    market_price: float | None,
    discount_rate: float,
    base_growth_rate: float,
    terminal_growth_rate: float,
    forecast_years: int = 5,
) -> list[DcfScenario]:
    scenario_inputs = [
        ("bear", max(-0.20, base_growth_rate - 0.05), discount_rate + 0.02, terminal_growth_rate),
        ("base", base_growth_rate, discount_rate, terminal_growth_rate),
        ("bull", base_growth_rate + 0.05, max(0.001, discount_rate - 0.01), terminal_growth_rate),
    ]
    scenarios: list[DcfScenario] = []
    for name, growth, scenario_discount, scenario_terminal in scenario_inputs:
        intrinsic = None
        margin = None
        if (
            cashflow_per_share is not None
            and cashflow_per_share > 0
            and scenario_discount > scenario_terminal
        ):
            intrinsic = dcf_value_per_share(
                cashflow_per_share=cashflow_per_share,
                discount_rate=scenario_discount,
                growth_rate=growth,
                terminal_growth_rate=scenario_terminal,
                forecast_years=forecast_years,
            )
            if market_price is not None and market_price > 0:
                margin = intrinsic / market_price - 1.0
        scenarios.append(
            DcfScenario(
                scenario_name=name,
                growth_rate=growth,
                discount_rate=scenario_discount,
                terminal_growth_rate=scenario_terminal,
                intrinsic_value_per_share=intrinsic,
                margin_of_safety=margin,
                implied_growth_rate=implied_dcf_growth_rate(
                    market_price=market_price,
                    cashflow_per_share=cashflow_per_share,
                    discount_rate=scenario_discount,
                    terminal_growth_rate=scenario_terminal,
                    forecast_years=forecast_years,
                ),
            )
        )
    return scenarios


def valuation_missing_inputs(
    latest_income: dict[str, Any],
    latest_balance: dict[str, Any],
    latest_cashflow: dict[str, Any],
    shares_outstanding: float | None,
    market_price: float | None,
    fcf: float | None,
) -> list[str]:
    missing: list[str] = []
    if not latest_income:
        missing.append("income statement")
    if not latest_balance:
        missing.append("balance sheet")
    if not latest_cashflow:
        missing.append("cash flow statement")
    if shares_outstanding is None:
        missing.append("shares outstanding")
    if market_price is None:
        missing.append("market price")
    if fcf is None:
        missing.append("free cash flow")
    return missing


def etf_analytics(
    asset_id: str,
    asset_profile: dict[str, str | None],
    etf_profile: dict[str, Any],
    holdings: list[EtfHoldingAnalytics],
    annual_distribution_per_share: float | None,
    latest_price: float | None,
    price_history: list[PricePoint],
    benchmark_price_history: list[PricePoint],
    direct_portfolio_weights: dict[str, tuple[str, float | None]],
) -> ETFAnalytics | None:
    asset_type = (asset_profile.get("asset_type") or "").lower()
    asset_subtype = (asset_profile.get("asset_subtype") or "").lower()
    is_etf = asset_type == "etf" or asset_subtype == "etf" or bool(etf_profile or holdings)
    if not is_etf:
        return None

    expense_ratio = (
        float(etf_profile["expense_ratio"])
        if etf_profile.get("expense_ratio") is not None
        else None
    )
    benchmark_index_id = etf_profile.get("benchmark_index_id")
    distribution_yield = safe_div(annual_distribution_per_share, latest_price)
    tracking = tracking_error(price_history, benchmark_price_history)
    missing: list[str] = []
    if expense_ratio is None:
        missing.append("expense ratio")
    if not holdings:
        missing.append("ETF holdings")
    if annual_distribution_per_share is None:
        missing.append("distribution history")
    if tracking is None:
        missing.append("benchmark price history")

    return ETFAnalytics(
        is_etf=True,
        expense_ratio=expense_ratio,
        benchmark_index_id=benchmark_index_id,
        annual_distribution_per_share=annual_distribution_per_share,
        distribution_yield=distribution_yield,
        tracking_error=tracking,
        holding_count=len(holdings),
        top_holdings=holdings[:10],
        overlap_with_portfolio=etf_portfolio_overlap(holdings, direct_portfolio_weights, asset_id),
        sector_exposure=holding_dimension_exposure(holdings, "sector"),
        country_exposure=holding_dimension_exposure(holdings, "country"),
        currency_exposure=holding_dimension_exposure(holdings, "currency"),
        missing_inputs=missing,
    )


def tracking_error(asset_prices: list[PricePoint], benchmark_prices: list[PricePoint]) -> float | None:
    asset_by_date = {point.date: point.close for point in asset_prices if point.close > 0}
    benchmark_by_date = {point.date: point.close for point in benchmark_prices if point.close > 0}
    dates = sorted(set(asset_by_date).intersection(benchmark_by_date))
    if len(dates) < 3:
        return None
    asset_returns = simple_returns([asset_by_date[day] for day in dates])
    benchmark_returns = simple_returns([benchmark_by_date[day] for day in dates])
    if len(asset_returns) != len(benchmark_returns) or len(asset_returns) < 2:
        return None
    active_returns = [
        asset_return - benchmark_return
        for asset_return, benchmark_return in zip(asset_returns, benchmark_returns)
    ]
    return annualized_volatility(active_returns)


def etf_portfolio_overlap(
    holdings: list[EtfHoldingAnalytics],
    direct_portfolio_weights: dict[str, tuple[str, float | None]],
    etf_asset_id: str,
) -> list[EtfOverlapAnalytics]:
    overlaps: list[EtfOverlapAnalytics] = []
    etf_asset_id = etf_asset_id.upper()
    for holding in holdings:
        symbol = holding.holding_symbol.upper()
        direct = direct_portfolio_weights.get(symbol)
        if direct is None:
            continue
        direct_asset_id, direct_weight = direct
        if direct_asset_id.upper() == etf_asset_id:
            continue
        overlaps.append(
            EtfOverlapAnalytics(
                holding_symbol=symbol,
                direct_asset_id=direct_asset_id,
                etf_weight=holding.weight,
                direct_portfolio_weight=direct_weight,
            )
        )
    return overlaps


def holding_dimension_exposure(
    holdings: list[EtfHoldingAnalytics],
    dimension: str,
) -> dict[str, float]:
    exposure: dict[str, float] = {}
    for holding in holdings:
        weight = holding.weight
        if weight is None:
            continue
        value = getattr(holding, dimension) or "Unknown"
        exposure[value] = exposure.get(value, 0.0) + weight
    return dict(sorted(exposure.items()))


def normalize_weight(value: Any) -> float | None:
    if value is None:
        return None
    weight = float(value)
    if weight > 1.0:
        return weight / 100.0
    return weight


def asset_forecast_metrics(
    market_price: float | None,
    risk: RiskReturnMetrics,
    valuation_depth: ValuationDepthMetrics,
    dividend_history: list[tuple[date, float]],
    annual_dividend: float | None,
    forecast_years: int = 5,
) -> ForecastMetrics:
    base_scenario = next(
        (scenario for scenario in valuation_depth.dcf_scenarios if scenario.scenario_name == "base"),
        None,
    )
    intrinsic = base_scenario.intrinsic_value_per_share if base_scenario else None
    dividend_yield = safe_div(annual_dividend, market_price)
    valuation_cagr = expected_cagr_from_valuation(
        market_price=market_price,
        intrinsic_value=intrinsic,
        income_yield=dividend_yield,
        horizon_years=forecast_years,
    )
    dividend_growth = projected_dividend_growth(dividend_history)
    fundamental_growth = fundamental_growth_assumption(valuation_depth)
    blended = blended_expected_cagr(
        valuation_cagr=valuation_cagr,
        fundamental_growth=fundamental_growth,
        historical_cagr=risk.cagr,
        income_yield=dividend_yield,
    )
    simulation = simulated_forecast_band(
        start_value=market_price,
        expected_cagr=blended,
        annualized_volatility=risk.annualized_volatility,
        horizon_years=forecast_years,
        seed=17,
    )
    missing = forecast_missing_inputs(
        valuation_cagr=valuation_cagr,
        dividend_growth=dividend_growth,
        fundamental_growth=fundamental_growth,
        simulation=simulation,
    )

    return ForecastMetrics(
        horizon_years=forecast_years,
        expected_cagr_from_valuation=valuation_cagr,
        dividend_growth_projection=dividend_growth,
        fundamental_growth_assumption=fundamental_growth,
        blended_expected_cagr=blended,
        simulation=simulation,
        missing_inputs=missing,
    )


def portfolio_forecast_metrics(
    market_value: float,
    risk: RiskReturnMetrics | None,
    performance: PortfolioPerformanceMetrics,
    forecast_years: int = 5,
) -> ForecastMetrics:
    expected = risk.cagr if risk and risk.cagr is not None else performance.money_weighted_return
    simulation = simulated_forecast_band(
        start_value=market_value if market_value > 0 else None,
        expected_cagr=expected,
        annualized_volatility=risk.annualized_volatility if risk else None,
        horizon_years=forecast_years,
        seed=23,
    )
    missing = []
    if expected is None:
        missing.append("expected return assumption")
    if risk is None or risk.annualized_volatility is None:
        missing.append("portfolio volatility")
    if simulation is None:
        missing.append("simulation inputs")

    return ForecastMetrics(
        horizon_years=forecast_years,
        expected_cagr_from_valuation=None,
        dividend_growth_projection=None,
        fundamental_growth_assumption=None,
        blended_expected_cagr=expected,
        simulation=simulation,
        missing_inputs=missing,
    )


def expected_cagr_from_valuation(
    market_price: float | None,
    intrinsic_value: float | None,
    income_yield: float | None,
    horizon_years: int,
) -> float | None:
    value_cagr = cagr(market_price, intrinsic_value, horizon_years)
    if value_cagr is None:
        return income_yield
    return value_cagr + (income_yield or 0.0)


def projected_dividend_growth(dividend_history: list[tuple[date, float]]) -> float | None:
    if len(dividend_history) < 8:
        return None
    recent = sum(value for _date, value in dividend_history[:4])
    previous = sum(value for _date, value in dividend_history[4:8])
    return growth_rate(recent, previous)


def fundamental_growth_assumption(valuation_depth: ValuationDepthMetrics) -> float | None:
    values = [
        valuation_depth.revenue_growth_yoy,
        valuation_depth.eps_growth_yoy,
        valuation_depth.free_cash_flow_growth_yoy,
    ]
    available = [value for value in values if value is not None]
    if not available:
        return None
    return max(-0.25, min(0.35, sum(available) / len(available)))


def blended_expected_cagr(
    valuation_cagr: float | None,
    fundamental_growth: float | None,
    historical_cagr: float | None,
    income_yield: float | None,
) -> float | None:
    weighted_values: list[tuple[float, float]] = []
    if valuation_cagr is not None:
        weighted_values.append((valuation_cagr, 0.45))
    if fundamental_growth is not None:
        weighted_values.append((fundamental_growth + (income_yield or 0.0), 0.35))
    if historical_cagr is not None:
        weighted_values.append((historical_cagr, 0.20))
    if not weighted_values:
        return None
    total_weight = sum(weight for _value, weight in weighted_values)
    blended = sum(value * weight for value, weight in weighted_values) / total_weight
    return clamp(blended, -0.50, 0.75)


def simulated_forecast_band(
    start_value: float | None,
    expected_cagr: float | None,
    annualized_volatility: float | None,
    horizon_years: int,
    simulations: int = 500,
    seed: int = 0,
) -> ForecastBand | None:
    if (
        start_value is None
        or start_value <= 0
        or expected_cagr is None
        or annualized_volatility is None
        or horizon_years <= 0
    ):
        return None

    rng = random.Random(seed)
    terminal_values = []
    annual_drift = expected_cagr - 0.5 * (annualized_volatility ** 2)
    for _ in range(simulations):
        shock = rng.gauss(0.0, 1.0)
        terminal = start_value * math.exp(
            annual_drift * horizon_years
            + annualized_volatility * math.sqrt(horizon_years) * shock
        )
        terminal_values.append(terminal)

    terminal_values.sort()
    expected_value = sum(terminal_values) / len(terminal_values)
    p10 = percentile(terminal_values, 0.10)
    p50 = percentile(terminal_values, 0.50)
    p90 = percentile(terminal_values, 0.90)
    return ForecastBand(
        horizon_years=horizon_years,
        expected_value=expected_value,
        p10_value=p10,
        p50_value=p50,
        p90_value=p90,
        expected_cagr=cagr(start_value, expected_value, horizon_years),
        p10_cagr=cagr(start_value, p10, horizon_years),
        p50_cagr=cagr(start_value, p50, horizon_years),
        p90_cagr=cagr(start_value, p90, horizon_years),
    )


def percentile(sorted_values: list[float], quantile: float) -> float | None:
    if not sorted_values:
        return None
    idx = min(len(sorted_values) - 1, max(0, round((len(sorted_values) - 1) * quantile)))
    return sorted_values[idx]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def forecast_missing_inputs(
    valuation_cagr: float | None,
    dividend_growth: float | None,
    fundamental_growth: float | None,
    simulation: ForecastBand | None,
) -> list[str]:
    missing: list[str] = []
    if valuation_cagr is None:
        missing.append("valuation CAGR")
    if dividend_growth is None:
        missing.append("dividend growth history")
    if fundamental_growth is None:
        missing.append("fundamental growth history")
    if simulation is None:
        missing.append("simulation inputs")
    return missing


def dividend_discount_model(
    annual_dividend: float | None,
    market_price: float | None,
    discount_rate: float,
    growth_rate: float,
    forecast_years: int = 5,
) -> ValuationResult:
    missing = []
    if annual_dividend is None:
        missing.append("annual dividend")
    if market_price is None:
        missing.append("market price")
    if discount_rate <= growth_rate:
        missing.append("discount rate above growth rate")

    intrinsic = None
    if not missing:
        intrinsic = annual_dividend * (1 + growth_rate) / (discount_rate - growth_rate)

    return _valuation_result(
        method="dividend_discount",
        intrinsic=intrinsic,
        market_price=market_price,
        forecast_years=forecast_years,
        missing=missing,
        inputs={
            "annual_dividend": annual_dividend,
            "discount_rate": discount_rate,
            "growth_rate": growth_rate,
        },
        implied_growth=implied_perpetual_growth(
            cashflow=annual_dividend,
            market_price=market_price,
            discount_rate=discount_rate,
        ),
    )


def discounted_cash_flow_model(
    cashflow_per_share: float | None,
    market_price: float | None,
    discount_rate: float,
    growth_rate: float,
    terminal_growth_rate: float,
    forecast_years: int = 5,
) -> ValuationResult:
    missing = []
    if cashflow_per_share is None:
        missing.append("cash flow per share")
    if market_price is None:
        missing.append("market price")
    if discount_rate <= terminal_growth_rate:
        missing.append("discount rate above terminal growth rate")

    intrinsic = None
    if not missing:
        intrinsic = dcf_value_per_share(
            cashflow_per_share=cashflow_per_share,
            discount_rate=discount_rate,
            growth_rate=growth_rate,
            terminal_growth_rate=terminal_growth_rate,
            forecast_years=forecast_years,
        )

    return _valuation_result(
        method="discounted_cash_flow",
        intrinsic=intrinsic,
        market_price=market_price,
        forecast_years=forecast_years,
        missing=missing,
        inputs={
            "cashflow_per_share": cashflow_per_share,
            "discount_rate": discount_rate,
            "growth_rate": growth_rate,
            "terminal_growth_rate": terminal_growth_rate,
            "forecast_years": forecast_years,
        },
        implied_growth=implied_dcf_growth_rate(
            market_price=market_price,
            cashflow_per_share=cashflow_per_share,
            discount_rate=discount_rate,
            terminal_growth_rate=terminal_growth_rate,
            forecast_years=forecast_years,
        ),
    )


def dcf_value_per_share(
    cashflow_per_share: float,
    discount_rate: float,
    growth_rate: float,
    terminal_growth_rate: float,
    forecast_years: int = 5,
) -> float:
    present_value = 0.0
    cashflow = cashflow_per_share
    for year in range(1, forecast_years + 1):
        cashflow *= 1 + growth_rate
        present_value += cashflow / ((1 + discount_rate) ** year)

    terminal_cashflow = cashflow * (1 + terminal_growth_rate)
    terminal_value = terminal_cashflow / (discount_rate - terminal_growth_rate)
    present_value += terminal_value / ((1 + discount_rate) ** forecast_years)
    return present_value


def implied_dcf_growth_rate(
    market_price: float | None,
    cashflow_per_share: float | None,
    discount_rate: float,
    terminal_growth_rate: float,
    forecast_years: int = 5,
    low: float = -0.50,
    high: float = 0.50,
) -> float | None:
    if (
        market_price is None
        or market_price <= 0
        or cashflow_per_share is None
        or cashflow_per_share <= 0
        or discount_rate <= terminal_growth_rate
    ):
        return None

    def value_at(growth: float) -> float:
        return dcf_value_per_share(
            cashflow_per_share=cashflow_per_share,
            discount_rate=discount_rate,
            growth_rate=growth,
            terminal_growth_rate=terminal_growth_rate,
            forecast_years=forecast_years,
        )

    if value_at(low) > market_price or value_at(high) < market_price:
        return None

    for _ in range(80):
        mid = (low + high) / 2
        if value_at(mid) < market_price:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def implied_perpetual_growth(
    cashflow: float | None,
    market_price: float | None,
    discount_rate: float,
) -> float | None:
    if cashflow is None or cashflow <= 0 or market_price is None or market_price <= 0:
        return None
    # Gordon growth: price = cashflow * (1 + g) / (r - g)
    return (market_price * discount_rate - cashflow) / (market_price + cashflow)


def simple_returns(closes: list[float]) -> list[float]:
    return [
        closes[i] / closes[i - 1] - 1.0
        for i in range(1, len(closes))
        if closes[i - 1] > 0 and closes[i] > 0
    ]


def annualized_volatility(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    return statistics.stdev(returns) * math.sqrt(TRADING_DAYS_PER_YEAR)


def downside_deviation(
    returns: list[float],
    minimum_acceptable_daily_return: float = 0.0,
) -> float | None:
    downside = [
        min(0.0, ret - minimum_acceptable_daily_return)
        for ret in returns
    ]
    if len(downside) < 2 or all(ret == 0 for ret in downside):
        return None
    mean_square = sum(ret * ret for ret in downside) / len(downside)
    return math.sqrt(mean_square) * math.sqrt(TRADING_DAYS_PER_YEAR)


def max_drawdown(closes: list[float]) -> float | None:
    if len(closes) < 2:
        return None
    peak = closes[0]
    worst = 0.0
    for close in closes:
        peak = max(peak, close)
        if peak > 0:
            worst = min(worst, close / peak - 1.0)
    return worst


def cagr(
    start_value: float | None,
    end_value: float | None,
    years: float | None,
) -> float | None:
    if (
        start_value is None
        or end_value is None
        or start_value <= 0
        or end_value <= 0
        or years is None
        or years <= 0
    ):
        return None
    return (end_value / start_value) ** (1 / years) - 1.0


def beta(asset_returns: list[float], benchmark_returns: list[float]) -> float | None:
    if len(asset_returns) != len(benchmark_returns) or len(asset_returns) < 2:
        return None
    mean_asset = statistics.mean(asset_returns)
    mean_benchmark = statistics.mean(benchmark_returns)
    covariance = sum(
        (asset - mean_asset) * (benchmark - mean_benchmark)
        for asset, benchmark in zip(asset_returns, benchmark_returns)
    )
    benchmark_variance = sum((benchmark - mean_benchmark) ** 2 for benchmark in benchmark_returns)
    if benchmark_variance == 0:
        return None
    return covariance / benchmark_variance


def correlation(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denom_x = sum((x - mean_x) ** 2 for x in xs)
    denom_y = sum((y - mean_y) ** 2 for y in ys)
    denominator = math.sqrt(denom_x * denom_y)
    if denominator == 0:
        return None
    return numerator / denominator


def ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _valuation_result(
    method: str,
    intrinsic: float | None,
    market_price: float | None,
    forecast_years: int,
    missing: list[str],
    inputs: dict[str, float | int | str | None],
    implied_growth: float | None,
) -> ValuationResult:
    margin = None
    expected = None
    if intrinsic is not None and market_price is not None and market_price > 0:
        margin = intrinsic / market_price - 1.0
        expected = cagr(market_price, intrinsic, forecast_years)

    return ValuationResult(
        method=method,
        intrinsic_value_per_share=intrinsic,
        market_price=market_price,
        margin_of_safety=margin,
        expected_cagr=expected,
        implied_growth_rate=implied_growth,
        inputs_used=inputs,
        missing_inputs=missing,
    )


def _years_between(start_date: date | None, end_date: date | None) -> float | None:
    if start_date is None or end_date is None:
        return None
    days = (end_date - start_date).days
    if days <= 0:
        return None
    return days / 365.25


def growth_rate(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return current / previous - 1.0


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _latest_statement_data(statements: list[dict[str, Any]]) -> dict[str, Any]:
    return statements[0]["data"] if statements else {}


def _previous_statement_data(statements: list[dict[str, Any]]) -> dict[str, Any]:
    return statements[1]["data"] if len(statements) > 1 else {}


def _free_cash_flow_from_statement(data: dict[str, Any]) -> float | None:
    fcf = _extract_number(data, FREE_CASH_FLOW_ALIASES)
    if fcf is not None:
        return fcf
    operating = _extract_number(data, OPERATING_CASH_FLOW_ALIASES)
    capex = _extract_number(data, CAPEX_ALIASES)
    if operating is None or capex is None:
        return None
    return operating - abs(capex)


def _txn_date(txn: tuple[Any, ...]) -> date:
    stamp = txn[2]
    if isinstance(stamp, datetime):
        return stamp.date()
    if isinstance(stamp, date):
        return stamp
    return datetime.fromisoformat(str(stamp)).date()


def _txn_cash_value(txn: tuple[Any, ...]) -> float | None:
    cash_amt = txn[8]
    if cash_amt is not None:
        return float(cash_amt)
    qty = txn[5]
    price = txn[6]
    if qty is None or price is None:
        return None
    return abs(float(qty)) * float(price)


def _txn_fee(txn: tuple[Any, ...]) -> float:
    return float(txn[9] or 0.0)


def _json_object(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _extract_number(data: dict[str, Any], aliases: tuple[str, ...]) -> float | None:
    for alias in aliases:
        value = data.get(alias)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.replace(",", ""))
            except ValueError:
                pass
    return None


def _json_dumps(value: Any) -> str:
    return json.dumps(_json_ready(asdict(value)), sort_keys=True)


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
