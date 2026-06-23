"""Pure analytics calculations, forecasting, valuation, and AI context."""
# ruff: noqa: F403, F405

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
import hashlib
import json
import math
import random
import statistics
from typing import Any

from .models import *


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
    asset_cagr = (
        cagr(asset_by_date[dates[0]], asset_by_date[dates[-1]], asset_years)
        if asset_years
        else None
    )
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


def average_cost_realized_gain(
    transactions: list[tuple[Any, ...]],
) -> tuple[float | None, list[str]]:
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
        asset_class_exposure=dimension_exposure(weights, exposure_metadata, "asset_class"),
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
            sum(
                weights.get(asset_id, 0.0) * returns[idx]
                for asset_id, returns in returns_by_asset.items()
            )
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


def allocation_class(
    *,
    asset_id: str | None = None,
    symbol: str | None = None,
    name: str | None = None,
    asset_type: str | None = None,
    asset_subtype: str | None = None,
    sector: str | None = None,
    industry: str | None = None,
) -> str:
    """Normalize held instruments into portfolio allocation classes."""
    text = " ".join(
        str(value or "")
        for value in (asset_id, symbol, name, asset_type, asset_subtype, sector, industry)
    ).lower()
    symbol_key = str(symbol or asset_id or "").upper().strip()
    asset_type_key = str(asset_type or "").lower().strip()
    asset_subtype_key = str(asset_subtype or "").lower().strip()

    if asset_type_key == "cash" or asset_subtype_key == "cash":
        return "Cash"
    if symbol_key in {"CASH.TO", "PSA.TO", "CSAV.TO", "HISA.TO"}:
        return "Money market"
    if any(term in text for term in ("money market", "high interest savings", "cash etf")):
        return "Money market"
    if asset_subtype_key in {"money_market", "money market"}:
        return "Money market"
    if any(term in text for term in ("bond", "fixed income", "treasury", "government bill", "t-bill", "tbill")):
        return "Fixed income"
    if asset_type_key in {"bond", "fixed_income", "fixed income"} or asset_subtype_key in {"bond", "fixed_income", "fixed income"}:
        return "Fixed income"
    if asset_subtype_key == "cdr" or "canadian depositary receipt" in text or "canadian depository receipt" in text:
        return "CDR"
    if asset_type_key in {"etf", "fund", "mutual_fund", "mutual fund"}:
        return "ETF"
    if asset_type_key in {"stock", "equity", "adr"}:
        return "Stock"
    return asset_type_key.replace("_", " ").title() if asset_type_key else "Other"


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
    revenue_per_share = (
        revenue / shares_outstanding if revenue is not None and shares_outstanding else None
    )
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


def tracking_error(
    asset_prices: list[PricePoint], benchmark_prices: list[PricePoint]
) -> float | None:
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
        (
            scenario
            for scenario in valuation_depth.dcf_scenarios
            if scenario.scenario_name == "base"
        ),
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
    valuation_expected_cagr: float | None = None,
    forecast_years: int = 5,
) -> ForecastMetrics:
    expected = (
        valuation_expected_cagr
        if valuation_expected_cagr is not None
        else risk.cagr
        if risk and risk.cagr is not None
        else performance.money_weighted_return
    )
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
        expected_cagr_from_valuation=valuation_expected_cagr,
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
    annual_drift = expected_cagr - 0.5 * (annualized_volatility**2)
    for _ in range(simulations):
        shock = rng.gauss(0.0, 1.0)
        terminal = start_value * math.exp(
            annual_drift * horizon_years + annualized_volatility * math.sqrt(horizon_years) * shock
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


def asset_ai_context(
    asset_id: str,
    latest_price: float | None,
    risk: RiskReturnMetrics,
    relative: RelativeRiskMetrics | None,
    dividend_discount: ValuationResult,
    discounted_cash_flow: ValuationResult,
    valuation_depth: ValuationDepthMetrics,
    etf: ETFAnalytics | None,
    forecast: ForecastMetrics,
) -> AIReadinessContext:
    missing = sorted(
        set(
            dividend_discount.missing_inputs
            + discounted_cash_flow.missing_inputs
            + valuation_depth.missing_inputs
            + forecast.missing_inputs
            + (etf.missing_inputs if etf else [])
        )
    )
    facts = [
        _analytics_fact("latest_price", "Latest price", latest_price, "currency", "market_price"),
        _analytics_fact("cagr", "Historical CAGR", risk.cagr, "percent", "risk_return"),
        _analytics_fact(
            "annualized_volatility",
            "Annualized volatility",
            risk.annualized_volatility,
            "percent",
            "risk_return",
        ),
        _analytics_fact("sharpe_ratio", "Sharpe ratio", risk.sharpe_ratio, "ratio", "risk_return"),
        _analytics_fact(
            "sortino_ratio", "Sortino ratio", risk.sortino_ratio, "ratio", "risk_return"
        ),
        _analytics_fact(
            "max_drawdown", "Max drawdown", risk.max_drawdown, "percent", "risk_return"
        ),
        _analytics_fact(
            "beta", "Beta", relative.beta if relative else None, "ratio", "relative_risk"
        ),
        _analytics_fact(
            "alpha_annualized",
            "Annualized alpha",
            relative.alpha_annualized if relative else None,
            "percent",
            "relative_risk",
        ),
        _analytics_fact(
            "ddm_intrinsic_value",
            "DDM intrinsic value",
            dividend_discount.intrinsic_value_per_share,
            "currency",
            "dividend_discount",
        ),
        _analytics_fact(
            "dcf_intrinsic_value",
            "DCF intrinsic value",
            discounted_cash_flow.intrinsic_value_per_share,
            "currency",
            "discounted_cash_flow",
        ),
        _analytics_fact(
            "dcf_margin_of_safety",
            "DCF margin of safety",
            discounted_cash_flow.margin_of_safety,
            "percent",
            "discounted_cash_flow",
        ),
        _analytics_fact(
            "pe_ratio", "P/E ratio", valuation_depth.pe_ratio, "ratio", "valuation_depth"
        ),
        _analytics_fact(
            "price_to_free_cash_flow",
            "Price to free cash flow",
            valuation_depth.price_to_free_cash_flow,
            "ratio",
            "valuation_depth",
        ),
        _analytics_fact(
            "debt_to_equity",
            "Debt to equity",
            valuation_depth.debt_to_equity,
            "ratio",
            "valuation_depth",
        ),
        _analytics_fact(
            "blended_expected_cagr",
            "Blended expected CAGR",
            forecast.blended_expected_cagr,
            "percent",
            "forecast",
        ),
    ]
    if etf is not None:
        facts.extend(
            [
                _analytics_fact("is_etf", "Is ETF", etf.is_etf, None, "etf_profile"),
                _analytics_fact(
                    "expense_ratio", "Expense ratio", etf.expense_ratio, "percent", "etf_profile"
                ),
                _analytics_fact(
                    "distribution_yield",
                    "Distribution yield",
                    etf.distribution_yield,
                    "percent",
                    "etf_profile",
                ),
                _analytics_fact(
                    "tracking_error",
                    "Tracking error",
                    etf.tracking_error,
                    "percent",
                    "etf_profile",
                ),
                _analytics_fact(
                    "holding_count", "ETF holding count", etf.holding_count, "count", "etf_holdings"
                ),
            ]
        )

    explanations = [
        AnalyticsExplanation(
            topic="risk",
            summary=_asset_risk_summary(risk),
            evidence=_present_fact_labels(
                facts, ["cagr", "annualized_volatility", "sharpe_ratio", "max_drawdown"]
            ),
        ),
        AnalyticsExplanation(
            topic="valuation",
            summary=_asset_valuation_summary(discounted_cash_flow, valuation_depth),
            evidence=_present_fact_labels(
                facts, ["dcf_intrinsic_value", "dcf_margin_of_safety", "pe_ratio"]
            ),
        ),
        AnalyticsExplanation(
            topic="forecast",
            summary=_forecast_summary(forecast),
            evidence=_present_fact_labels(facts, ["blended_expected_cagr"]),
        ),
    ]
    if etf is not None and etf.is_etf:
        explanations.append(
            AnalyticsExplanation(
                topic="etf",
                summary=f"ETF profile covers {etf.holding_count} holdings and benchmark {etf.benchmark_index_id or 'unknown'}.",
                evidence=_present_fact_labels(
                    facts, ["expense_ratio", "distribution_yield", "tracking_error"]
                ),
            )
        )

    anomalies = asset_ai_anomalies(risk, discounted_cash_flow, valuation_depth, etf, missing)
    summary = _asset_ai_summary(asset_id, latest_price, forecast, anomalies, missing)
    snapshot_hash = _ai_snapshot_hash(facts, anomalies, missing)
    return AIReadinessContext(
        subject_type="asset",
        subject_id=asset_id,
        summary=summary,
        facts=facts,
        explanations=explanations,
        anomalies=anomalies,
        missing_inputs=missing,
        snapshot_hash=snapshot_hash,
    )


def portfolio_ai_context(
    portfolio_id: int,
    positions: list[PositionAnalytics],
    market_value: float,
    performance: PortfolioPerformanceMetrics,
    risk_decomposition: PortfolioRiskDecomposition,
    valuation: PortfolioValuationRollup,
    risk: RiskReturnMetrics | None,
    relative: RelativeRiskMetrics | None,
    forecast: ForecastMetrics,
    missing_inputs: list[str],
) -> AIReadinessContext:
    missing = sorted(
        set(
            missing_inputs
            + risk_decomposition.missing_inputs
            + valuation.missing_inputs
            + forecast.missing_inputs
        )
    )
    facts = [
        _analytics_fact(
            "market_value", "Market value", market_value, "currency", "portfolio_positions"
        ),
        _analytics_fact(
            "position_count", "Position count", len(positions), "count", "portfolio_positions"
        ),
        _analytics_fact(
            "modified_dietz_return",
            "Modified Dietz return",
            performance.modified_dietz_return,
            "percent",
            "portfolio_performance",
        ),
        _analytics_fact(
            "money_weighted_return",
            "Money-weighted return",
            performance.money_weighted_return,
            "percent",
            "portfolio_performance",
        ),
        _analytics_fact(
            "portfolio_cagr",
            "Portfolio CAGR",
            risk.cagr if risk else None,
            "percent",
            "risk_return",
        ),
        _analytics_fact(
            "portfolio_volatility",
            "Portfolio volatility",
            risk_decomposition.portfolio_volatility,
            "percent",
            "risk_decomposition",
        ),
        _analytics_fact(
            "sharpe_ratio",
            "Sharpe ratio",
            risk.sharpe_ratio if risk else None,
            "ratio",
            "risk_return",
        ),
        _analytics_fact(
            "sortino_ratio",
            "Sortino ratio",
            risk.sortino_ratio if risk else None,
            "ratio",
            "risk_return",
        ),
        _analytics_fact(
            "beta", "Beta", relative.beta if relative else None, "ratio", "relative_risk"
        ),
        _analytics_fact(
            "alpha_annualized",
            "Annualized alpha",
            relative.alpha_annualized if relative else None,
            "percent",
            "relative_risk",
        ),
        _analytics_fact(
            "concentration_hhi",
            "Concentration HHI",
            risk_decomposition.concentration_hhi,
            "ratio",
            "risk_decomposition",
        ),
        _analytics_fact(
            "largest_position_weight",
            "Largest position weight",
            risk_decomposition.largest_position_weight,
            "percent",
            "risk_decomposition",
        ),
        _analytics_fact(
            "diversification_score",
            "Diversification score",
            risk_decomposition.diversification_score,
            "score",
            "risk_decomposition",
        ),
        _analytics_fact(
            "weighted_margin_of_safety",
            "Weighted margin of safety",
            valuation.weighted_margin_of_safety,
            "percent",
            "portfolio_valuation",
        ),
        _analytics_fact(
            "weighted_pe_ratio",
            "Weighted P/E ratio",
            valuation.weighted_pe_ratio,
            "ratio",
            "portfolio_valuation",
        ),
        _analytics_fact(
            "weighted_price_to_free_cash_flow",
            "Weighted price to free cash flow",
            valuation.weighted_price_to_free_cash_flow,
            "ratio",
            "portfolio_valuation",
        ),
        _analytics_fact(
            "weighted_dividend_yield",
            "Weighted dividend yield",
            valuation.weighted_dividend_yield,
            "percent",
            "portfolio_valuation",
        ),
        _analytics_fact(
            "weighted_expected_cagr",
            "Weighted expected CAGR",
            valuation.weighted_expected_cagr,
            "percent",
            "portfolio_valuation",
        ),
        _analytics_fact(
            "overvalued_weight",
            "Overvalued weight",
            valuation.overvalued_weight,
            "percent",
            "portfolio_valuation",
        ),
        _analytics_fact(
            "blended_expected_cagr",
            "Blended expected CAGR",
            forecast.blended_expected_cagr,
            "percent",
            "forecast",
        ),
    ]
    explanations = [
        AnalyticsExplanation(
            topic="portfolio_performance",
            summary=_portfolio_performance_summary(performance, risk),
            evidence=_present_fact_labels(
                facts, ["market_value", "money_weighted_return", "portfolio_cagr"]
            ),
        ),
        AnalyticsExplanation(
            topic="portfolio_risk",
            summary=_portfolio_risk_summary(risk_decomposition),
            evidence=_present_fact_labels(
                facts,
                [
                    "portfolio_volatility",
                    "concentration_hhi",
                    "largest_position_weight",
                    "diversification_score",
                ],
            ),
        ),
        AnalyticsExplanation(
            topic="portfolio_valuation",
            summary=_portfolio_valuation_summary(valuation),
            evidence=_present_fact_labels(
                facts,
                ["weighted_margin_of_safety", "weighted_pe_ratio", "weighted_dividend_yield"],
            ),
        ),
        AnalyticsExplanation(
            topic="forecast",
            summary=_forecast_summary(forecast),
            evidence=_present_fact_labels(facts, ["blended_expected_cagr"]),
        ),
    ]
    anomalies = portfolio_ai_anomalies(risk_decomposition, risk, missing, valuation=valuation)
    summary = _portfolio_ai_summary(portfolio_id, market_value, positions, anomalies, missing)
    snapshot_hash = _ai_snapshot_hash(facts, anomalies, missing)
    return AIReadinessContext(
        subject_type="portfolio",
        subject_id=str(portfolio_id),
        summary=summary,
        facts=facts,
        explanations=explanations,
        anomalies=anomalies,
        missing_inputs=missing,
        snapshot_hash=snapshot_hash,
    )


def compare_ai_snapshot_facts(
    previous: AIReadinessContext,
    current: AIReadinessContext,
) -> list[SnapshotMetricChange]:
    previous_facts = {fact.key: fact.value for fact in previous.facts}
    current_facts = {fact.key: fact.value for fact in current.facts}
    changes = []
    for key in sorted(previous_facts.keys() | current_facts.keys()):
        previous_value = previous_facts.get(key)
        current_value = current_facts.get(key)
        if previous_value == current_value:
            continue
        absolute = None
        relative = None
        if _is_number(previous_value) and _is_number(current_value):
            absolute = float(current_value) - float(previous_value)
            relative = safe_div(absolute, float(previous_value))
        changes.append(
            SnapshotMetricChange(
                key=key,
                previous_value=previous_value,
                current_value=current_value,
                absolute_change=absolute,
                relative_change=relative,
            )
        )
    return changes


def analytics_report_payload(
    report: AssetAnalyticsReport | PortfolioAnalyticsReport,
) -> dict[str, Any]:
    if isinstance(report, AssetAnalyticsReport):
        report_type = "asset"
        subject_id = report.asset_id
    else:
        report_type = "portfolio"
        subject_id = str(report.portfolio_id)

    return {
        "schema_version": ANALYTICS_REPORT_SCHEMA_VERSION,
        "report_type": report_type,
        "subject_id": subject_id,
        "benchmark_index_id": report.benchmark_index_id,
        "ai_context": _json_ready(asdict(report.ai_context)),
        "report": _json_ready(asdict(report)),
    }


def analytics_report_json(report: AssetAnalyticsReport | PortfolioAnalyticsReport) -> str:
    return json.dumps(analytics_report_payload(report), sort_keys=True)


def asset_ai_anomalies(
    risk: RiskReturnMetrics,
    discounted_cash_flow: ValuationResult,
    valuation_depth: ValuationDepthMetrics,
    etf: ETFAnalytics | None,
    missing_inputs: list[str],
) -> list[AnalyticsAnomaly]:
    anomalies: list[AnalyticsAnomaly] = []
    if risk.annualized_volatility is not None and risk.annualized_volatility > 0.40:
        anomalies.append(
            AnalyticsAnomaly(
                "high",
                "annualized_volatility",
                "Annualized volatility is above 40%.",
                risk.annualized_volatility,
            )
        )
    if risk.max_drawdown is not None and risk.max_drawdown < -0.30:
        anomalies.append(
            AnalyticsAnomaly(
                "high", "max_drawdown", "Maximum drawdown is deeper than 30%.", risk.max_drawdown
            )
        )
    if (
        discounted_cash_flow.margin_of_safety is not None
        and discounted_cash_flow.margin_of_safety < -0.20
    ):
        anomalies.append(
            AnalyticsAnomaly(
                "medium",
                "dcf_margin_of_safety",
                "DCF estimate is more than 20% below market price.",
                discounted_cash_flow.margin_of_safety,
            )
        )
    if valuation_depth.pe_ratio is not None and valuation_depth.pe_ratio > 40:
        anomalies.append(
            AnalyticsAnomaly(
                "medium", "pe_ratio", "P/E ratio is above 40.", valuation_depth.pe_ratio
            )
        )
    if valuation_depth.debt_to_equity is not None and valuation_depth.debt_to_equity > 2:
        anomalies.append(
            AnalyticsAnomaly(
                "medium",
                "debt_to_equity",
                "Debt-to-equity is above 2.",
                valuation_depth.debt_to_equity,
            )
        )
    if etf and etf.tracking_error is not None and etf.tracking_error > 0.05:
        anomalies.append(
            AnalyticsAnomaly(
                "medium", "tracking_error", "ETF tracking error is above 5%.", etf.tracking_error
            )
        )
    if missing_inputs:
        anomalies.append(
            AnalyticsAnomaly(
                "low",
                "missing_inputs",
                "Some analytics inputs are unavailable.",
                len(missing_inputs),
            )
        )
    return anomalies


def portfolio_ai_anomalies(
    risk_decomposition: PortfolioRiskDecomposition,
    risk: RiskReturnMetrics | None,
    missing_inputs: list[str],
    valuation: PortfolioValuationRollup | None = None,
) -> list[AnalyticsAnomaly]:
    anomalies: list[AnalyticsAnomaly] = []
    largest = risk_decomposition.largest_position_weight
    hhi = risk_decomposition.concentration_hhi
    if (largest is not None and largest > 0.25) or (hhi is not None and hhi > 0.25):
        anomalies.append(
            AnalyticsAnomaly(
                "high", "concentration", "Portfolio concentration is elevated.", largest or hhi
            )
        )
    score = risk_decomposition.diversification_score
    if score is not None and score < 50:
        anomalies.append(
            AnalyticsAnomaly(
                "medium", "diversification_score", "Diversification score is below 50.", score
            )
        )
    volatility = risk_decomposition.portfolio_volatility or (
        risk.annualized_volatility if risk else None
    )
    if volatility is not None and volatility > 0.35:
        anomalies.append(
            AnalyticsAnomaly(
                "medium", "portfolio_volatility", "Portfolio volatility is above 35%.", volatility
            )
        )
    if valuation and valuation.overvalued_weight > 0.50:
        anomalies.append(
            AnalyticsAnomaly(
                "medium",
                "overvalued_weight",
                "More than half of the portfolio has negative valuation margin of safety.",
                valuation.overvalued_weight,
            )
        )
    if missing_inputs:
        anomalies.append(
            AnalyticsAnomaly(
                "low",
                "missing_inputs",
                "Some portfolio analytics inputs are unavailable.",
                len(missing_inputs),
            )
        )
    return anomalies


def _analytics_fact(
    key: str,
    label: str,
    value: float | int | str | bool | None,
    unit: str | None,
    source: str,
) -> AnalyticsFact:
    confidence = 1.0 if value is not None else 0.0
    return AnalyticsFact(
        key=key,
        label=label,
        value=value,
        unit=unit,
        source=source,
        confidence=confidence,
    )


def _present_fact_labels(facts: list[AnalyticsFact], keys: list[str]) -> list[str]:
    by_key = {fact.key: fact for fact in facts}
    return [by_key[key].label for key in keys if key in by_key and by_key[key].value is not None]


def _asset_ai_summary(
    asset_id: str,
    latest_price: float | None,
    forecast: ForecastMetrics,
    anomalies: list[AnalyticsAnomaly],
    missing_inputs: list[str],
) -> str:
    price = f"latest price {latest_price:.2f}" if latest_price is not None else "no latest price"
    expected = forecast.blended_expected_cagr
    expectation = (
        f"blended expected CAGR {expected:.2%}" if expected is not None else "no blended CAGR"
    )
    return (
        f"{asset_id} has {price}, {expectation}, "
        f"{len(anomalies)} anomaly flags, and {len(missing_inputs)} missing input groups."
    )


def _portfolio_ai_summary(
    portfolio_id: int,
    market_value: float,
    positions: list[PositionAnalytics],
    anomalies: list[AnalyticsAnomaly],
    missing_inputs: list[str],
) -> str:
    return (
        f"Portfolio {portfolio_id} has market value {market_value:.2f}, "
        f"{len(positions)} positions, {len(anomalies)} anomaly flags, "
        f"and {len(missing_inputs)} missing input groups."
    )


def _asset_risk_summary(risk: RiskReturnMetrics) -> str:
    if risk.cagr is None and risk.annualized_volatility is None:
        return "Return history is insufficient for risk-adjusted analytics."
    cagr_text = f"CAGR {risk.cagr:.2%}" if risk.cagr is not None else "CAGR unavailable"
    vol_text = (
        f"annualized volatility {risk.annualized_volatility:.2%}"
        if risk.annualized_volatility is not None
        else "volatility unavailable"
    )
    return f"Historical risk profile shows {cagr_text} with {vol_text}."


def _asset_valuation_summary(
    discounted_cash_flow: ValuationResult,
    valuation_depth: ValuationDepthMetrics,
) -> str:
    if discounted_cash_flow.margin_of_safety is not None:
        return f"DCF margin of safety is {discounted_cash_flow.margin_of_safety:.2%}."
    if valuation_depth.pe_ratio is not None:
        return f"Valuation context is available with P/E of {valuation_depth.pe_ratio:.2f}."
    return "Valuation inputs are not yet complete enough for a firm intrinsic value view."


def _portfolio_performance_summary(
    performance: PortfolioPerformanceMetrics,
    risk: RiskReturnMetrics | None,
) -> str:
    if performance.money_weighted_return is not None:
        return f"Money-weighted return is {performance.money_weighted_return:.2%}."
    if risk and risk.cagr is not None:
        return f"Synthetic portfolio CAGR is {risk.cagr:.2%}."
    return "Portfolio performance needs more cash-flow or price history."


def _portfolio_risk_summary(risk_decomposition: PortfolioRiskDecomposition) -> str:
    if risk_decomposition.largest_position_weight is None:
        return "Portfolio concentration cannot be assessed without valued positions."
    return (
        f"Largest position weight is {risk_decomposition.largest_position_weight:.2%}; "
        f"diversification score is {risk_decomposition.diversification_score or 0.0:.2f}."
    )


def _portfolio_valuation_summary(valuation: PortfolioValuationRollup) -> str:
    if valuation.weighted_margin_of_safety is not None:
        return (
            f"Weighted margin of safety is {valuation.weighted_margin_of_safety:.2%}; "
            f"overvalued weight is {valuation.overvalued_weight:.2%}."
        )
    if valuation.weighted_pe_ratio is not None:
        return f"Weighted P/E ratio is {valuation.weighted_pe_ratio:.2f}."
    return "Portfolio valuation rollup needs more holding-level fundamentals."


def _forecast_summary(forecast: ForecastMetrics) -> str:
    if forecast.blended_expected_cagr is None:
        return "Forecast inputs are incomplete."
    return f"Blended expected CAGR is {forecast.blended_expected_cagr:.2%} over {forecast.horizon_years} years."


def _ai_snapshot_hash(
    facts: list[AnalyticsFact],
    anomalies: list[AnalyticsAnomaly],
    missing_inputs: list[str],
) -> str:
    encoded = json.dumps(
        {
            "facts": _json_ready([asdict(fact) for fact in facts]),
            "anomalies": _json_ready([asdict(anomaly) for anomaly in anomalies]),
            "missing_inputs": missing_inputs,
        },
        sort_keys=True,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _normalize_code(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.upper().strip()
    return normalized or None


def _weighted_average(
    contributions: list[PositionValuationContribution],
    attr: str,
) -> float | None:
    weighted_sum = 0.0
    total_weight = 0.0
    for contribution in contributions:
        value = getattr(contribution, attr)
        weight = contribution.weight
        if value is None or weight is None:
            continue
        weighted_sum += value * weight
        total_weight += weight
    return safe_div(weighted_sum, total_weight)


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
    downside = [min(0.0, ret - minimum_acceptable_daily_return) for ret in returns]
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
