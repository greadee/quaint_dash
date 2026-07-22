"""Asset and portfolio analytics report orchestration."""
# ruff: noqa: F403, F405

from __future__ import annotations

from .calculations import *
from .calculations import _weighted_average
from .models import *
from .repository import AnalyticsRepository


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
        benchmark_index_id = benchmark_index_id or self.repo.default_benchmark_for_asset(asset_id)
        prices = self.repo.price_history(asset_id)
        benchmark = (
            self.repo.benchmark_price_history(benchmark_index_id)
            if benchmark_index_id is not None
            else []
        )
        latest_price = prices[-1].close if prices else self.repo.latest_price(asset_id)

        dividend = self.repo.annual_dividend_per_share(
            asset_id, prices[-1].date if prices else None
        )
        fcf = self.repo.latest_free_cash_flow(asset_id)
        shares = self.repo.shares_outstanding(asset_id)
        fcf_per_share = fcf / shares if fcf is not None and shares else None
        risk = risk_return_metrics(prices, risk_free_rate=risk_free_rate)
        relative = relative_risk_metrics(prices, benchmark, risk_free_rate) if benchmark else None
        dividend_discount = dividend_discount_model(
            annual_dividend=dividend,
            market_price=latest_price,
            discount_rate=discount_rate,
            growth_rate=dividend_growth_rate,
            forecast_years=forecast_years,
        )
        discounted_cash_flow = discounted_cash_flow_model(
            cashflow_per_share=fcf_per_share,
            market_price=latest_price,
            discount_rate=discount_rate,
            growth_rate=dividend_growth_rate,
            terminal_growth_rate=terminal_growth_rate,
            forecast_years=forecast_years,
        )
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
            risk=risk,
            valuation_depth=valuation_depth,
            dividend_history=self.repo.dividend_history(asset_id),
            annual_dividend=dividend,
            forecast_years=forecast_years,
        )
        ai_context = asset_ai_context(
            asset_id=asset_id,
            latest_price=latest_price,
            risk=risk,
            relative=relative,
            dividend_discount=dividend_discount,
            discounted_cash_flow=discounted_cash_flow,
            valuation_depth=valuation_depth,
            etf=etf,
            forecast=forecast,
        )

        return AssetAnalyticsReport(
            asset_id=asset_id,
            benchmark_index_id=benchmark_index_id,
            latest_price=latest_price,
            data_coverage=self.repo.data_coverage(),
            risk=risk,
            relative=relative,
            dividend_discount=dividend_discount,
            discounted_cash_flow=discounted_cash_flow,
            valuation_depth=valuation_depth,
            etf=etf,
            forecast=forecast,
            ai_context=ai_context,
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
                weight=p.market_value / total_value
                if p.market_value is not None and total_value > 0
                else None,
                unrealized_gain=p.unrealized_gain,
            )
            for p in positions
        ]
        benchmark_index_id = benchmark_index_id or self.repo.default_benchmark_for_portfolio(
            weighted_positions
        )

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
        valuation = self._portfolio_valuation_rollup(weighted_positions)
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
            valuation_expected_cagr=valuation.weighted_expected_cagr,
            forecast_years=5,
        )
        if not weighted_positions:
            missing.append("portfolio positions")
        if not portfolio_prices:
            missing.append("overlapping position price history")
        ai_context = portfolio_ai_context(
            portfolio_id=portfolio_id,
            positions=weighted_positions,
            market_value=total_value,
            performance=performance,
            risk_decomposition=risk_decomposition,
            valuation=valuation,
            risk=risk,
            relative=relative,
            forecast=forecast,
            missing_inputs=missing,
        )

        return PortfolioAnalyticsReport(
            portfolio_id=portfolio_id,
            benchmark_index_id=benchmark_index_id,
            positions=weighted_positions,
            market_value=total_value,
            performance=performance,
            risk_decomposition=risk_decomposition,
            valuation=valuation,
            risk=risk,
            relative=relative,
            forecast=forecast,
            missing_inputs=missing,
            ai_context=ai_context,
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

    def _portfolio_valuation_rollup(
        self,
        positions: list[PositionAnalytics],
        discount_rate: float = 0.10,
        growth_rate: float = 0.03,
        terminal_growth_rate: float = 0.03,
        forecast_years: int = 5,
    ) -> PortfolioValuationRollup:
        contributions: list[PositionValuationContribution] = []
        missing: list[str] = []

        for position in positions:
            if position.weight is None or position.weight <= 0:
                continue
            asset_id = position.asset_id
            valuation_asset_id = self.repo.valuation_asset_id(asset_id)
            profile = self.repo.asset_profile(asset_id)
            asset_class = allocation_class(
                asset_id=asset_id,
                symbol=profile.get("symbol"),
                name=profile.get("name"),
                asset_type=profile.get("asset_type"),
                asset_subtype=profile.get("asset_subtype"),
                sector=profile.get("sector"),
                industry=profile.get("industry"),
            )
            company_valuation_applicable = asset_class in {"Stock", "CDR"}
            fcf_metrics_applicable = company_valuation_applicable and not _fcf_metrics_not_applicable(
                self.repo.asset_profile(valuation_asset_id)
            )
            latest_price = (
                self.repo.latest_price(valuation_asset_id) or position.latest_price
                if valuation_asset_id != asset_id
                else position.latest_price
            )
            annual_dividend = self.repo.annual_dividend_per_share(valuation_asset_id)
            dividend_yield = safe_div(annual_dividend, latest_price)
            shares = self.repo.shares_outstanding(valuation_asset_id)
            fcf = self.repo.latest_free_cash_flow(valuation_asset_id)
            fcf_per_share = fcf / shares if fcf is not None and shares else None
            dcf = discounted_cash_flow_model(
                cashflow_per_share=fcf_per_share,
                market_price=latest_price,
                discount_rate=discount_rate,
                growth_rate=growth_rate,
                terminal_growth_rate=terminal_growth_rate,
                forecast_years=forecast_years,
            )
            valuation_depth = valuation_depth_metrics(
                income_statements=self.repo.financial_statement_history(
                    valuation_asset_id, "income"
                ),
                balance_sheets=self.repo.financial_statement_history(
                    valuation_asset_id, "balance"
                ),
                cashflow_statements=self.repo.financial_statement_history(
                    valuation_asset_id, "cashflow"
                ),
                market_price=latest_price,
                shares_outstanding=shares,
                annual_dividend=annual_dividend,
                discount_rate=discount_rate,
                base_growth_rate=growth_rate,
                terminal_growth_rate=terminal_growth_rate,
                forecast_years=forecast_years,
            )
            risk = risk_return_metrics(self.repo.price_history(valuation_asset_id))
            forecast = asset_forecast_metrics(
                market_price=latest_price,
                risk=risk,
                valuation_depth=valuation_depth,
                dividend_history=self.repo.dividend_history(valuation_asset_id),
                annual_dividend=annual_dividend,
                forecast_years=forecast_years,
            )
            fee_adjustment = self.repo.wrapper_fee_adjustment(asset_id)
            has_forward_projection = (
                forecast.expected_cagr_from_valuation is not None
                or forecast.fundamental_growth_assumption is not None
            )
            if has_forward_projection:
                expected = (
                    forecast.blended_expected_cagr - fee_adjustment
                    if forecast.blended_expected_cagr is not None and fee_adjustment is not None
                    else forecast.blended_expected_cagr
                )
            else:
                expected = None
            valuation_source = (
                f"underlying company fundamentals: {valuation_asset_id}"
                if valuation_asset_id != asset_id
                else "held security fundamentals"
            )
            contributions.append(
                PositionValuationContribution(
                    asset_id=asset_id,
                    valuation_asset_id=valuation_asset_id,
                    valuation_source=valuation_source,
                    allocation_class=asset_class,
                    fcf_metrics_applicable=fcf_metrics_applicable,
                    fee_adjustment=fee_adjustment,
                    weight=position.weight,
                    margin_of_safety=dcf.margin_of_safety if fcf_metrics_applicable else None,
                    pe_ratio=valuation_depth.pe_ratio if company_valuation_applicable else None,
                    price_to_free_cash_flow=valuation_depth.price_to_free_cash_flow
                    if fcf_metrics_applicable
                    else None,
                    dividend_yield=dividend_yield,
                    expected_cagr=expected,
                    weighted_expected_cagr_contribution=position.weight * expected
                    if expected is not None
                    else None,
                )
            )
            if fcf_metrics_applicable and dcf.margin_of_safety is None:
                missing.extend(f"{asset_id}: {item}" for item in dcf.missing_inputs)
            if company_valuation_applicable and valuation_depth.pe_ratio is None:
                missing.extend(
                    f"{asset_id}: {item}"
                    for item in valuation_depth.missing_inputs
                    if item in {"income statement", "shares outstanding", "market price"}
                )
            if fcf_metrics_applicable and valuation_depth.price_to_free_cash_flow is None:
                missing.extend(
                    f"{asset_id}: {item}"
                    for item in valuation_depth.missing_inputs
                    if item
                    in {
                        "cash flow statement",
                        "free cash flow",
                        "shares outstanding",
                        "market price",
                    }
                )
            if not has_forward_projection:
                missing.extend(f"{asset_id}: {item}" for item in forecast.missing_inputs)
                missing.append(f"{asset_id}: forward valuation or fundamental projection")

        undervalued_weight = sum(
            item.weight or 0.0
            for item in contributions
            if item.margin_of_safety is not None and item.margin_of_safety >= 0.10
        )
        overvalued_weight = sum(
            item.weight or 0.0
            for item in contributions
            if item.margin_of_safety is not None and item.margin_of_safety <= -0.10
        )
        fair_value_weight = sum(
            item.weight or 0.0
            for item in contributions
            if item.margin_of_safety is not None and -0.10 < item.margin_of_safety < 0.10
        )

        return PortfolioValuationRollup(
            weighted_margin_of_safety=_weighted_average(contributions, "margin_of_safety"),
            weighted_pe_ratio=_weighted_average(contributions, "pe_ratio"),
            weighted_price_to_free_cash_flow=_weighted_average(
                contributions, "price_to_free_cash_flow"
            ),
            weighted_dividend_yield=_weighted_average(contributions, "dividend_yield"),
            weighted_expected_cagr=sum(
                item.weight * item.expected_cagr
                for item in contributions
                if item.weight is not None and item.expected_cagr is not None
            )
            if any(item.expected_cagr is not None for item in contributions)
            else None,
            undervalued_weight=undervalued_weight,
            overvalued_weight=overvalued_weight,
            fair_value_weight=fair_value_weight,
            position_contributions=contributions,
            missing_inputs=sorted(set(missing)),
        )


def _fcf_metrics_not_applicable(profile: dict[str, str | None]) -> bool:
    sector = str(profile.get("sector") or "").lower()
    industry = str(profile.get("industry") or "").lower()
    return (
        "asset management" in industry
        or "bank" in industry
        or "insurance" in industry
        or sector in {"banks", "insurance"}
    )
