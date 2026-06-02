"""Phase 3 analytics calculations for assets, ETFs, and portfolios.

This module is intentionally calculation-first: it reads existing market,
portfolio, dividend, and financial-statement tables and reports missing inputs
instead of triggering new ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import json
import math
import statistics
from typing import Any


TRADING_DAYS_PER_YEAR = 252


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
    risk: RiskReturnMetrics | None
    relative: RelativeRiskMetrics | None
    missing_inputs: list[str]


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
        if not weighted_positions:
            missing.append("portfolio positions")
        if not portfolio_prices:
            missing.append("overlapping position price history")

        return PortfolioAnalyticsReport(
            portfolio_id=portfolio_id,
            positions=weighted_positions,
            market_value=total_value,
            risk=risk,
            relative=relative,
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
    sharpe = ratio(cagr_value - risk_free_rate, vol)
    sortino = ratio(cagr_value - risk_free_rate, downside)
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


def cagr(start_value: float, end_value: float, years: float | None) -> float | None:
    if start_value <= 0 or end_value <= 0 or years is None or years <= 0:
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
