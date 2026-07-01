"""Business Strength analyzer and scoring engine."""

from __future__ import annotations

import statistics
from datetime import date, datetime
from typing import Any

from dashboard.analytics.repository import AnalyticsRepository
from dashboard.api.services import AssetApiService, _first_number, _float_or_none, _json_dict, _ratio_like
from dashboard.services.business_strength.explanations import category_explanation, metric_explanation
from dashboard.services.business_strength.models import (
    CATEGORY_LABELS,
    METHODOLOGY_VERSION,
    BusinessStrengthScorecard,
    CategoryScore,
    MetricInput,
    MetricScore,
    StandardizedBusinessStrengthInput,
)
from dashboard.services.business_strength.normalization import combined_score
from dashboard.services.business_strength.persistence import BusinessStrengthRepository
from dashboard.services.business_strength.templates import BusinessStrengthTemplateRegistry


class BusinessStrengthAnalyzer:
    """Build, score, and persist deterministic Business Strength scorecards."""

    def __init__(self, conn) -> None:
        self.conn = conn
        self.registry = BusinessStrengthTemplateRegistry()
        self.repo = BusinessStrengthRepository(conn, self.registry)

    def latest_or_run(self, asset_id: str, *, force: bool = False) -> BusinessStrengthScorecard:
        if not force:
            existing = self.repo.latest(asset_id)
            if existing is not None:
                return existing
        return self.run(asset_id)

    def run(self, asset_id: str) -> BusinessStrengthScorecard:
        asset = AssetApiService(self.conn).get_asset(asset_id)
        fundamental_asset_id = AnalyticsRepository(self.conn).valuation_asset_id(asset.asset_id)
        template, source, classification_confidence = self.registry.classify(asset.symbol, asset.sector, asset.industry, asset.name)
        self.repo.upsert_methodology()
        template_id = self.repo.upsert_template(template)
        self.repo.upsert_classification(asset.asset_id, template, source, classification_confidence)
        standardized = self._load_inputs(asset, fundamental_asset_id, template.template_code)
        scorecard = self._score(standardized, template)
        run_id = self.repo.persist(scorecard, template_id)
        scorecard.analysis_run_id = run_id
        return scorecard

    def compare(self, symbols: list[str]) -> dict[str, Any]:
        scorecards = []
        failed = []
        for symbol in symbols[:8]:
            try:
                scorecards.append(self.latest_or_run(symbol))
            except LookupError:
                failed.append(symbol)
        template_codes = {item.template_code for item in scorecards}
        common_metric_codes = set.intersection(
            *[set(metric.metric_code for category in item.category_scores for metric in category.metrics) for item in scorecards]
        ) if scorecards else set()
        return {
            "methodology_version": METHODOLOGY_VERSION,
            "assets": scorecards,
            "failed_symbols": failed,
            "mixed_templates": len(template_codes) > 1,
            "common_metric_codes": sorted(common_metric_codes),
            "warning": "Category scores are comparable; underlying template-specific metrics may differ." if len(template_codes) > 1 else None,
        }

    def _load_inputs(self, asset, fundamental_asset_id: str, template_code: str) -> StandardizedBusinessStrengthInput:
        statements = {
            kind: self._statement_rows(fundamental_asset_id, kind)
            for kind in ("income", "balance", "cashflow")
        }
        latest_income = statements["income"][0][0] if statements["income"] else {}
        latest_balance = statements["balance"][0][0] if statements["balance"] else {}
        latest_cashflow = statements["cashflow"][0][0] if statements["cashflow"] else {}
        source_as_of = max((row[2] for rows in statements.values() for row in rows if row[2]), default=None)
        peer_ids = self._peer_ids(asset.sector, asset.industry, template_code, fundamental_asset_id)
        peer_metrics = self._peer_metric_values(peer_ids)
        revenue_values = [_first_number(row[0], "revenue", "totalRevenue") for row in statements["income"]]
        net_income_values = [_first_number(row[0], "netIncome", "net_income", "netIncomeCommonStockholders") for row in statements["income"]]
        margin_values = [self._margin(row[0], "operatingIncome", "operating_income") for row in statements["income"]]
        shares_values = [_first_number(row[0], "weightedAverageShsOutDil", "weightedAverageSharesDiluted", "sharesOutstanding") for row in statements["income"]]
        revenue = _first_number(latest_income, "revenue", "totalRevenue")
        gross_profit = _first_number(latest_income, "grossProfit", "gross_profit")
        operating_income = _first_number(latest_income, "operatingIncome", "operating_income")
        net_income = _first_number(latest_income, "netIncome", "net_income", "netIncomeCommonStockholders")
        ebitda = _first_number(latest_income, "ebitda", "EBITDA")
        rd = _first_number(latest_income, "researchAndDevelopmentExpenses", "researchAndDevelopment")
        fcf = _first_number(latest_cashflow, "freeCashFlow", "free_cash_flow")
        ocf = _first_number(latest_cashflow, "operatingCashFlow", "netCashProvidedByOperatingActivities")
        capex = _first_number(latest_cashflow, "capitalExpenditure", "capital_expenditure")
        if fcf is None and ocf is not None and capex is not None:
            fcf = ocf + capex
        cash = _first_number(latest_balance, "cashAndCashEquivalents", "cashAndShortTermInvestments", "cash")
        debt = _first_number(latest_balance, "totalDebt", "debt")
        equity = _first_number(latest_balance, "totalStockholdersEquity", "totalEquity")
        assets = _first_number(latest_balance, "totalAssets")
        current_assets = _first_number(latest_balance, "totalCurrentAssets")
        current_liabilities = _first_number(latest_balance, "totalCurrentLiabilities")
        tax_rate = _first_number(latest_income, "effectiveTaxRate", "taxRate")
        tax_rate = tax_rate if tax_rate is not None and 0 <= tax_rate <= 1 else 0.21
        invested_capital = debt + equity - cash if debt is not None and equity is not None and cash is not None else None
        nopat = operating_income * (1 - tax_rate) if operating_income is not None else None
        metrics = {
            "revenue_cagr_3y": self._input("revenue_cagr_3y", self._cagr(revenue_values[:4]), source_as_of),
            "revenue_growth_consistency": self._input("revenue_growth_consistency", self._consistency_score(revenue_values), source_as_of),
            "gross_margin": self._input("gross_margin", gross_profit / revenue if gross_profit is not None and revenue else None, source_as_of, peer_metrics.get("gross_margin")),
            "operating_margin": self._input("operating_margin", operating_income / revenue if operating_income is not None and revenue else None, source_as_of, peer_metrics.get("operating_margin"), margin_values),
            "net_margin": self._input("net_margin", net_income / revenue if net_income is not None and revenue else None, source_as_of, peer_metrics.get("net_margin")),
            "free_cash_flow_margin": self._input("free_cash_flow_margin", fcf / revenue if fcf is not None and revenue else None, source_as_of),
            "revenue_volatility": self._input("revenue_volatility", self._relative_stdev(revenue_values), source_as_of),
            "net_debt_to_ebitda": self._input("net_debt_to_ebitda", (debt - cash) / ebitda if debt is not None and cash is not None and ebitda else None, source_as_of),
            "current_ratio": self._input("current_ratio", current_assets / current_liabilities if current_assets is not None and current_liabilities else None, source_as_of),
            "free_cash_flow_conversion": self._input("free_cash_flow_conversion", fcf / net_income if fcf is not None and net_income else None, source_as_of),
            "roic": self._input("roic", nopat / invested_capital if nopat is not None and invested_capital and invested_capital > 0 else None, source_as_of, peer_metrics.get("roic")),
            "roe": self._input("roe", net_income / equity if net_income is not None and equity else None, source_as_of),
            "asset_turnover": self._input("asset_turnover", revenue / assets if revenue is not None and assets else None, source_as_of),
            "share_count_cagr_3y": self._input("share_count_cagr_3y", self._cagr(shares_values[:4]), source_as_of),
            "buyback_yield_net_sbc": self._input("buyback_yield_net_sbc", self._buyback_net_sbc(latest_cashflow, asset.market_cap), source_as_of),
            "earnings_volatility": self._input("earnings_volatility", self._relative_stdev(net_income_values), source_as_of),
            "fundamental_drawdown": self._input("fundamental_drawdown", self._drawdown(net_income_values), source_as_of),
            "customer_concentration": self._input("customer_concentration", _ratio_like(_first_number(latest_income, "customerConcentration", "topCustomerRevenuePercent")), source_as_of),
            "revenue_concentration": self._input("revenue_concentration", _ratio_like(_first_number(latest_income, "revenueConcentration", "topSegmentRevenuePercent")), source_as_of),
            "margin_stability": self._input("margin_stability", self._stability_score(margin_values), source_as_of),
            "gross_margin_premium": self._input("gross_margin_premium", self._premium(gross_profit / revenue if gross_profit is not None and revenue else None, peer_metrics.get("gross_margin", [])), source_as_of),
            "rd_intensity": self._input("rd_intensity", rd / revenue if rd is not None and revenue else None, source_as_of),
            "inventory_intensity": self._input("inventory_intensity", _first_number(latest_balance, "inventory") / revenue if revenue and _first_number(latest_balance, "inventory") is not None else None, source_as_of),
            "rule_of_40": self._input("rule_of_40", self._rule_of_40(revenue_values[:4], fcf, revenue), source_as_of),
            "sbc_to_revenue": self._input("sbc_to_revenue", _first_number(latest_cashflow, "stockBasedCompensation", "shareBasedCompensation") / revenue if revenue and _first_number(latest_cashflow, "stockBasedCompensation", "shareBasedCompensation") is not None else None, source_as_of),
            "debt_to_equity": self._input("debt_to_equity", debt / equity if debt is not None and equity else None, source_as_of),
        }
        return StandardizedBusinessStrengthInput(
            asset_id=asset.asset_id,
            symbol=asset.symbol,
            name=asset.name,
            sector=asset.sector,
            industry=asset.industry,
            fundamental_asset_id=fundamental_asset_id,
            analysis_date=date.today(),
            source_data_as_of=source_as_of,
            metrics=metrics,
            peer_group=peer_ids,
        )

    def _score(self, inputs: StandardizedBusinessStrengthInput, template) -> BusinessStrengthScorecard:
        categories: list[CategoryScore] = []
        missing: list[str] = []
        stale: list[str] = []
        estimated: list[str] = []
        for category, weight in template.category_weights.items():
            metric_scores = []
            for definition in [m for m in template.metrics if m.category == category]:
                metric_input = inputs.metrics.get(definition.code)
                status = metric_input.status if metric_input else "unknown"
                value = metric_input.value if metric_input else None
                if status == "unknown" and not definition.required:
                    status = "not_applicable"
                if status == "unknown" and definition.required:
                    missing.append(definition.label)
                if status == "estimated":
                    estimated.append(definition.label)
                if status == "stale":
                    stale.append(definition.label)
                score = peer = hist = None
                if value is not None and status not in {"unknown", "not_applicable", "conflicting"}:
                    score, peer, hist = combined_score(
                        value,
                        low=definition.absolute_min,
                        high=definition.absolute_max,
                        direction=definition.direction,
                        peer_values=metric_input.peer_values,
                        historical_values=metric_input.historical_values,
                        normalization=definition.normalization,
                    )
                confidence = self._metric_confidence(status, value, bool(metric_input and metric_input.peer_values), bool(metric_input and metric_input.historical_values))
                metric_scores.append(MetricScore(
                    category_code=category,
                    metric_code=definition.code,
                    label=definition.label,
                    raw_value=value,
                    normalized_value=score,
                    metric_score=score,
                    metric_weight=definition.weight,
                    contribution=score * definition.weight if score is not None else None,
                    unit=definition.unit,
                    direction=definition.direction,
                    value_status=status,
                    source=metric_input.source if metric_input else definition.source,
                    source_timestamp=metric_input.source_timestamp if metric_input else None,
                    peer_percentile=peer,
                    historical_percentile=hist,
                    confidence=confidence,
                    explanation=metric_explanation(definition.label, value, score, status),
                ))
            usable = [m for m in metric_scores if m.metric_score is not None]
            applicable = [m for m in metric_scores if m.value_status != "not_applicable"]
            total_weight = sum(m.metric_weight for m in usable)
            raw_score = sum((m.metric_score or 0) * m.metric_weight for m in usable) / total_weight if total_weight else None
            completeness = len(usable) / len(applicable) * 100 if applicable else 100.0
            confidence_inputs = [m for m in metric_scores if m.value_status != "not_applicable"]
            confidence = (sum(m.confidence for m in confidence_inputs) / len(confidence_inputs)) if confidence_inputs else 100.0
            categories.append(CategoryScore(
                category_code=category,
                label=CATEGORY_LABELS[category],
                raw_score=raw_score,
                adjusted_score=raw_score,
                category_weight=weight,
                confidence_score=round(confidence, 2),
                completeness_score=round(completeness, 2),
                explanation=category_explanation(CATEGORY_LABELS[category], metric_scores, raw_score),
                metrics=metric_scores,
            ))
        scored = [c for c in categories if c.adjusted_score is not None]
        overall = sum((c.adjusted_score or 0) * c.category_weight for c in scored) / sum(c.category_weight for c in scored) if scored else None
        completeness = sum(c.completeness_score * c.category_weight for c in categories)
        confidence = sum(c.confidence_score * c.category_weight for c in categories)
        easy_hold = self._easy_hold(categories, overall)
        drivers = [m for c in categories for m in c.metrics if m.contribution is not None]
        strengths = [m.label for m in sorted(drivers, key=lambda m: m.contribution or 0, reverse=True)[:5]]
        weaknesses = [m.label for m in sorted(drivers, key=lambda m: m.metric_score or 100)[:5]]
        return BusinessStrengthScorecard(
            analysis_run_id=None,
            asset_id=inputs.asset_id,
            symbol=inputs.symbol,
            name=inputs.name,
            sector=inputs.sector,
            industry=inputs.industry,
            template_code=template.template_code,
            template_name=template.name,
            template_version=template.version,
            methodology_version=METHODOLOGY_VERSION,
            analysis_date=inputs.analysis_date,
            source_data_as_of=inputs.source_data_as_of,
            overall_score=round(overall, 2) if overall is not None else None,
            score_10=round(overall / 10, 1) if overall is not None else None,
            classification=self._classification(overall),
            confidence_score=round(confidence, 2),
            completeness_score=round(completeness, 2),
            easy_hold_score=round(easy_hold, 2) if easy_hold is not None else None,
            easy_hold_label=self._classification(easy_hold),
            status=self._status(overall, missing),
            missing_critical_metrics=sorted(set(missing)),
            stale_metrics=sorted(set(stale)),
            estimated_metrics=sorted(set(estimated)),
            category_scores=categories,
            strengths=strengths,
            weaknesses=weaknesses,
            peer_group=inputs.peer_group,
            warnings=[],
        )

    def _statement_rows(self, asset_id: str, statement_type: str) -> list[tuple[dict[str, Any], date | None, datetime | None]]:
        rows = self.conn.execute(
            """
            SELECT data_json, period_end_date, ingested_at_utc
            FROM financial_statement
            WHERE UPPER(asset_id) = UPPER(?) AND statement_type = ?
            ORDER BY period_end_date DESC NULLS LAST, year DESC, quarter DESC
            LIMIT 8
            """,
            [asset_id, statement_type],
        ).fetchall()
        result = []
        for data_json, period_end, ingested_at in rows:
            data = _json_dict(data_json)
            data["_period_end_date"] = period_end
            result.append((data, period_end, ingested_at))
        return result

    def _input(self, code: str, value: float | None, source_as_of: datetime | None, peer_values: list[float] | None = None, historical_values: list[float | None] | None = None) -> MetricInput:
        return MetricInput(
            code=code,
            value=_float_or_none(value),
            status="derived" if value is not None else "unknown",
            source="financial_statement",
            source_timestamp=source_as_of,
            peer_values=[v for v in (peer_values or []) if v is not None],
            historical_values=[v for v in (historical_values or []) if v is not None],
        )

    def _peer_ids(self, sector: str | None, industry: str | None, template_code: str, asset_id: str) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT asset_id FROM asset
            WHERE asset_id <> ?
              AND ((? IS NOT NULL AND industry = ?) OR (? IS NOT NULL AND sector = ?))
            ORDER BY asset_id
            LIMIT 20
            """,
            [asset_id, industry, industry, sector, sector],
        ).fetchall()
        return [row[0] for row in rows] or [asset_id]

    def _peer_metric_values(self, peer_ids: list[str]) -> dict[str, list[float]]:
        values: dict[str, list[float]] = {"gross_margin": [], "operating_margin": [], "net_margin": [], "roic": []}
        for asset_id in peer_ids:
            rows = self._statement_rows(asset_id, "income")
            if not rows:
                continue
            data = rows[0][0]
            revenue = _first_number(data, "revenue", "totalRevenue")
            if not revenue:
                continue
            for key, field in [("gross_margin", "grossProfit"), ("operating_margin", "operatingIncome"), ("net_margin", "netIncome")]:
                numerator = _first_number(data, field)
                if numerator is not None:
                    values[key].append(numerator / revenue)
        return values

    def _margin(self, statement: dict[str, Any], *fields: str) -> float | None:
        revenue = _first_number(statement, "revenue", "totalRevenue")
        numerator = _first_number(statement, *fields)
        return numerator / revenue if numerator is not None and revenue else None

    def _cagr(self, values: list[float | None]) -> float | None:
        clean = [v for v in values if v is not None and v > 0]
        if len(clean) < 2:
            return None
        years = min(len(clean) - 1, 3)
        return (clean[0] / clean[years]) ** (1 / years) - 1 if clean[years] else None

    def _relative_stdev(self, values: list[float | None]) -> float | None:
        clean = [v for v in values if v is not None]
        if len(clean) < 3:
            return None
        avg = statistics.mean(abs(v) for v in clean)
        return statistics.stdev(clean) / avg if avg else None

    def _drawdown(self, values: list[float | None]) -> float | None:
        clean = [v for v in values if v is not None]
        if len(clean) < 2:
            return None
        peak = clean[0]
        worst = 0.0
        for value in clean:
            peak = max(peak, value)
            if peak > 0:
                worst = min(worst, value / peak - 1)
        return abs(worst)

    def _consistency_score(self, values: list[float | None]) -> float | None:
        clean = [v for v in values if v is not None and v > 0]
        if len(clean) < 3:
            return None
        growth = [clean[i] / clean[i + 1] - 1 for i in range(len(clean) - 1)]
        vol = statistics.stdev(growth) if len(growth) > 1 else 0
        return max(0, min(100, 100 - vol * 250))

    def _stability_score(self, values: list[float | None]) -> float | None:
        vol = self._relative_stdev(values)
        return None if vol is None else max(0, min(100, 100 - vol * 150))

    def _premium(self, value: float | None, peer_values: list[float]) -> float | None:
        if value is None or not peer_values:
            return None
        return value - statistics.median(peer_values)

    def _buyback_net_sbc(self, cashflow: dict[str, Any], market_cap: float | None) -> float | None:
        if not market_cap:
            return None
        buybacks = _first_number(cashflow, "commonStockRepurchased", "repurchaseOfCommonStock", "stockRepurchased")
        sbc = _first_number(cashflow, "stockBasedCompensation", "shareBasedCompensation") or 0
        return (abs(buybacks) - sbc) / market_cap if buybacks is not None else None

    def _rule_of_40(self, revenue_values: list[float | None], fcf: float | None, revenue: float | None) -> float | None:
        growth = self._cagr(revenue_values)
        margin = fcf / revenue if fcf is not None and revenue else None
        if growth is None or margin is None:
            return None
        return growth + margin

    def _metric_confidence(self, status: str, value: float | None, has_peer: bool, has_history: bool) -> float:
        if status == "not_applicable":
            return 100.0
        if value is None or status == "unknown":
            return 35.0
        confidence = 82.0
        if has_peer:
            confidence += 6
        if has_history:
            confidence += 6
        if status == "stale":
            confidence -= 20
        if status == "estimated":
            confidence -= 12
        return max(0, min(100, confidence))

    def _easy_hold(self, categories: list[CategoryScore], overall: float | None) -> float | None:
        if overall is None:
            return None
        by_code = {c.category_code: c.adjusted_score for c in categories}
        weights = {
            "durability": 0.20,
            "competitive_strength": 0.15,
            "financial_strength": 0.15,
            "cyclicality_resilience": 0.20,
            "concentration_risk": 0.15,
            "profitability": 0.10,
            "capital_allocation": 0.05,
        }
        present = [(by_code.get(code), weight) for code, weight in weights.items() if by_code.get(code) is not None]
        return sum(score * weight for score, weight in present) / sum(weight for _, weight in present) if present else overall

    def _classification(self, score: float | None) -> str:
        if score is None:
            return "Insufficient Data"
        if score >= 90:
            return "Exceptional"
        if score >= 80:
            return "Very Strong"
        if score >= 70:
            return "Strong"
        if score >= 60:
            return "Above Average"
        if score >= 50:
            return "Average"
        if score >= 40:
            return "Below Average"
        if score >= 30:
            return "Weak"
        return "Very Weak"

    def _status(self, overall: float | None, missing: list[str]) -> str:
        if overall is None:
            return "insufficient_data"
        return "partial" if missing else "complete"
