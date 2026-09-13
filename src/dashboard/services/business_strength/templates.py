"""Sector-aware deterministic Business Strength templates."""

from __future__ import annotations

from dashboard.services.business_strength.models import (
    DEFAULT_CATEGORY_WEIGHTS,
    MetricDefinition,
    BusinessStrengthTemplate,
)


def metric(
    code: str,
    label: str,
    category: str,
    weight: float,
    direction: str,
    unit: str,
    normalization: str,
    min_value: float | None = None,
    max_value: float | None = None,
    required: bool = True,
) -> MetricDefinition:
    return MetricDefinition(
        code=code,
        label=label,
        category=category,
        weight=weight,
        direction=direction,
        unit=unit,
        normalization=normalization,
        absolute_min=min_value,
        absolute_max=max_value,
        required=required,
    )


BASE_METRICS = (
    metric("revenue_cagr_3y", "Three-year revenue CAGR", "growth_quality", 0.28, "higher_is_better", "percent", "absolute", -0.15, 0.25),
    metric("revenue_growth_consistency", "Revenue growth consistency", "growth_quality", 0.22, "higher_is_better", "score", "absolute", 0, 100),
    metric("gross_margin", "Gross margin", "profitability", 0.20, "higher_is_better", "percent", "peer_and_history", 0.10, 0.80),
    metric("operating_margin", "Operating margin", "profitability", 0.30, "higher_is_better", "percent", "peer_and_history", -0.10, 0.45),
    metric("net_margin", "Net margin", "profitability", 0.20, "higher_is_better", "percent", "absolute", -0.10, 0.35),
    metric("free_cash_flow_margin", "Free-cash-flow margin", "durability", 0.28, "higher_is_better", "percent", "absolute", -0.10, 0.35),
    metric("revenue_volatility", "Revenue volatility", "durability", 0.22, "lower_is_better", "percent", "absolute", 0.00, 0.35),
    metric("net_debt_to_ebitda", "Net debt/EBITDA", "financial_strength", 0.32, "lower_is_better", "multiple", "absolute", -2.0, 5.0),
    metric("current_ratio", "Current ratio", "financial_strength", 0.18, "higher_is_better", "ratio", "absolute", 0.5, 3.0, required=False),
    metric("free_cash_flow_conversion", "Free-cash-flow conversion", "financial_strength", 0.24, "higher_is_better", "ratio", "absolute", 0.0, 1.5),
    metric("roic", "ROIC", "capital_efficiency", 0.42, "higher_is_better", "percent", "peer_and_history", -0.05, 0.35),
    metric("asset_turnover", "Asset turnover", "capital_efficiency", 0.18, "higher_is_better", "ratio", "peer", 0.0, 2.0, required=False),
    metric("share_count_cagr_3y", "Three-year share-count CAGR", "capital_allocation", 0.28, "lower_is_better", "percent", "absolute", -0.08, 0.08, required=False),
    metric("buyback_yield_net_sbc", "Buyback yield net of SBC", "capital_allocation", 0.22, "higher_is_better", "percent", "absolute", -0.05, 0.08, required=False),
    metric("earnings_volatility", "Earnings volatility", "cyclicality_resilience", 0.32, "lower_is_better", "percent", "absolute", 0.0, 0.80),
    metric("fundamental_drawdown", "Fundamental drawdown", "cyclicality_resilience", 0.22, "lower_is_better", "percent", "absolute", 0.0, 0.70),
    metric("customer_concentration", "Largest customer concentration", "concentration_risk", 0.42, "lower_is_better", "percent", "absolute", 0.0, 0.50, required=False),
    metric("revenue_concentration", "Largest segment concentration", "concentration_risk", 0.28, "lower_is_better", "percent", "absolute", 0.20, 1.00, required=False),
    metric("margin_stability", "Margin stability", "competitive_strength", 0.28, "higher_is_better", "score", "absolute", 0, 100, required=False),
    metric("gross_margin_premium", "Gross-margin premium versus peers", "competitive_strength", 0.22, "higher_is_better", "percent", "peer", -0.20, 0.25, required=False),
)


def _template(code: str, name: str, sector: str, industry: str, metrics: tuple[MetricDefinition, ...] = BASE_METRICS, weights: dict[str, float] | None = None) -> BusinessStrengthTemplate:
    return BusinessStrengthTemplate(
        template_code=code,
        name=name,
        sector=sector,
        industry=industry,
        version=1,
        category_weights=weights or DEFAULT_CATEGORY_WEIGHTS,
        metrics=metrics,
    )


SEMICONDUCTOR_METRICS = tuple(
    m for m in BASE_METRICS if m.code != "current_ratio"
) + (
    metric("rd_intensity", "R&D intensity", "competitive_strength", 0.18, "target_range", "percent", "target_range", 0.08, 0.28, required=False),
    metric("inventory_intensity", "Inventory intensity", "cyclicality_resilience", 0.18, "lower_is_better", "percent", "absolute", 0.0, 0.35, required=False),
)

SOFTWARE_METRICS = BASE_METRICS + (
    metric("rule_of_40", "Rule of 40", "growth_quality", 0.22, "higher_is_better", "percent", "absolute", 0.0, 0.60),
    metric("sbc_to_revenue", "Stock-based compensation to revenue", "capital_allocation", 0.22, "lower_is_better", "percent", "absolute", 0.0, 0.25),
)

FINANCIAL_METRICS = (
    metric("revenue_cagr_3y", "Three-year revenue CAGR", "growth_quality", 0.28, "higher_is_better", "percent", "absolute", -0.10, 0.18),
    metric("net_margin", "Net margin", "profitability", 0.28, "higher_is_better", "percent", "peer_and_history", 0.0, 0.35),
    metric("roe", "Return on equity", "capital_efficiency", 0.36, "higher_is_better", "percent", "peer_and_history", 0.0, 0.22),
    metric("debt_to_equity", "Debt/equity", "financial_strength", 0.24, "lower_is_better", "ratio", "absolute", 0.0, 4.0),
    metric("earnings_volatility", "Earnings volatility", "cyclicality_resilience", 0.30, "lower_is_better", "percent", "absolute", 0.0, 0.80),
    metric("share_count_cagr_3y", "Three-year share-count CAGR", "capital_allocation", 0.28, "lower_is_better", "percent", "absolute", -0.08, 0.08, required=False),
    metric("revenue_concentration", "Largest segment concentration", "concentration_risk", 0.34, "lower_is_better", "percent", "absolute", 0.20, 1.00, required=False),
    metric("revenue_growth_consistency", "Revenue growth consistency", "durability", 0.22, "higher_is_better", "score", "absolute", 0, 100),
    metric("margin_stability", "Margin stability", "competitive_strength", 0.24, "higher_is_better", "score", "absolute", 0, 100, required=False),
)

UTILITY_METRICS = tuple(
    m for m in BASE_METRICS if m.code not in {"gross_margin", "rule_of_40"}
) + (
    metric("debt_to_equity", "Debt/equity", "financial_strength", 0.24, "lower_is_better", "ratio", "absolute", 0.0, 3.0),
)


class BusinessStrengthTemplateRegistry:
    """Owns active deterministic templates and classification rules."""

    def __init__(self) -> None:
        templates = [
            _template("base", "Base operating company", "General", "General"),
            _template("semiconductor_designer", "Semiconductor designer", "Technology", "Semiconductors", SEMICONDUCTOR_METRICS),
            _template("semiconductor_foundry", "Semiconductor foundry", "Technology", "Semiconductors", SEMICONDUCTOR_METRICS),
            _template("semiconductor_equipment", "Semiconductor equipment", "Technology", "Semiconductor Equipment", SEMICONDUCTOR_METRICS),
            _template("memory_semiconductor", "Memory semiconductor", "Technology", "Semiconductors", SEMICONDUCTOR_METRICS),
            _template("networking_hardware", "Networking hardware", "Technology", "Communications Equipment", SEMICONDUCTOR_METRICS),
            _template("enterprise_software", "Enterprise software", "Technology", "Software", SOFTWARE_METRICS),
            _template("saas", "SaaS", "Technology", "Software", SOFTWARE_METRICS),
            _template("payments_network", "Payments network", "Financial Services", "Payments", FINANCIAL_METRICS + (metric("operating_margin", "Operating margin", "profitability", 0.25, "higher_is_better", "percent", "absolute", 0.0, 0.70),)),
            _template("bank", "Bank", "Financial Services", "Banks", FINANCIAL_METRICS),
            _template("insurance", "Insurance", "Financial Services", "Insurance", FINANCIAL_METRICS),
            _template("asset_manager", "Asset manager", "Financial Services", "Asset Management", FINANCIAL_METRICS),
            _template("exchange_financial_data", "Exchange and financial data", "Financial Services", "Financial Data", FINANCIAL_METRICS),
            _template("alternative_asset_manager", "Alternative asset manager", "Financial Services", "Alternative Asset Management", FINANCIAL_METRICS),
            _template("medical_device", "Medical device", "Healthcare", "Medical Devices", BASE_METRICS),
            _template("pharmaceutical", "Pharmaceutical", "Healthcare", "Pharmaceuticals", BASE_METRICS),
            _template("industrial_compounder", "Industrial compounder", "Industrials", "Industrial Conglomerates", BASE_METRICS),
            _template("engineering_consulting", "Engineering and consulting", "Industrials", "Engineering", BASE_METRICS),
            _template("waste_management", "Waste management", "Industrials", "Waste Management", BASE_METRICS),
            _template("consumer_staples", "Consumer staples", "Consumer Defensive", "Consumer Staples", BASE_METRICS),
            _template("consumer_discretionary", "Consumer discretionary", "Consumer Cyclical", "Consumer Discretionary", BASE_METRICS),
            _template("marketplace", "Marketplace", "Consumer Cyclical", "Marketplace", SOFTWARE_METRICS),
            _template("travel", "Travel", "Consumer Cyclical", "Travel", BASE_METRICS),
            _template("utility", "Utility", "Utilities", "Utilities", UTILITY_METRICS),
            _template("midstream", "Midstream energy", "Energy", "Midstream", UTILITY_METRICS),
            _template("reit", "REIT", "Real Estate", "REIT", UTILITY_METRICS),
            _template("diversified_holding_company", "Diversified holding company", "Financial Services", "Holding Company", FINANCIAL_METRICS),
        ]
        self._templates = {template.template_code: template for template in templates}
        self.validate()

    def all(self) -> list[BusinessStrengthTemplate]:
        return list(self._templates.values())

    def get(self, template_code: str) -> BusinessStrengthTemplate:
        return self._templates.get(template_code, self._templates["base"])

    def classify(self, symbol: str, sector: str | None, industry: str | None, name: str | None) -> tuple[BusinessStrengthTemplate, str, float]:
        symbol = symbol.upper()
        base_symbol = symbol.split(".", maxsplit=1)[0]
        text = " ".join(part or "" for part in [sector, industry, name]).lower()
        ticker_map = {
            "NVDA": "semiconductor_designer", "AMD": "semiconductor_designer", "AVGO": "semiconductor_designer",
            "TSM": "semiconductor_foundry", "ASML": "semiconductor_equipment", "MU": "memory_semiconductor",
            "ANET": "networking_hardware", "MSFT": "enterprise_software", "NOW": "saas", "CRM": "saas",
            "CSU.TO": "enterprise_software", "TOI.TO": "enterprise_software", "V": "payments_network", "MA": "payments_network",
            "JPM": "bank", "FFH": "insurance", "BN": "diversified_holding_company", "KKR": "alternative_asset_manager",
            "SPGI": "exchange_financial_data", "NDAQ": "exchange_financial_data", "ISRG": "medical_device", "BSX": "medical_device",
            "LLY": "pharmaceutical", "WCN": "waste_management", "WSP": "engineering_consulting", "FTS": "utility",
            "ENB": "midstream", "AMZN": "marketplace", "META": "marketplace", "GOOG": "marketplace", "GOOGL": "marketplace",
            "MELI": "marketplace", "BKNG": "travel",
        }
        if symbol in ticker_map:
            return self.get(ticker_map[symbol]), "verified_ticker_classification", 0.95
        if base_symbol in ticker_map:
            return self.get(ticker_map[base_symbol]), "verified_ticker_classification", 0.93
        rules = [
            ("semiconductor", "semiconductor_designer"),
            ("software", "enterprise_software"),
            ("bank", "bank"),
            ("insurance", "insurance"),
            ("reit", "reit"),
            ("utility", "utility"),
            ("midstream", "midstream"),
            ("medical device", "medical_device"),
            ("pharmaceutical", "pharmaceutical"),
            ("waste", "waste_management"),
            ("travel", "travel"),
            ("marketplace", "marketplace"),
        ]
        for needle, code in rules:
            if needle in text:
                return self.get(code), "sector_industry_rule", 0.78
        return self.get("base"), "base_fallback", 0.55

    def validate(self) -> None:
        for template in self._templates.values():
            total = round(sum(template.category_weights.values()), 6)
            if total != 1:
                raise ValueError(f"{template.template_code} category weights sum to {total}")
            seen = set()
            for item in template.metrics:
                if item.code in seen:
                    raise ValueError(f"{template.template_code} has duplicate metric {item.code}")
                seen.add(item.code)
                if item.direction not in {"higher_is_better", "lower_is_better", "target_range"}:
                    raise ValueError(f"{item.code} has invalid direction")
                if item.category not in template.category_weights:
                    raise ValueError(f"{item.code} uses missing category {item.category}")
