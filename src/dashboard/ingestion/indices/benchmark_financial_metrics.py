from __future__ import annotations

import json
import statistics
from datetime import date, datetime
from typing import Any


SECTOR_BENCHMARK_PEERS: dict[str, tuple[str, ...]] = {
    "SEC_COMM": ("Communication Services", "Communications"),
    "SEC_CONS_DISC": ("Consumer Discretionary", "Consumer Cyclical"),
    "SEC_CONS_STAP": ("Consumer Staples", "Consumer Defensive"),
    "SEC_ENERGY": ("Energy",),
    "SEC_FINANCIALS": ("Financials", "Financial Services"),
    "SEC_HEALTHCARE": ("Health Care", "Healthcare"),
    "SEC_INDUSTRIALS": ("Industrials", "Industrial"),
    "SEC_TECH": ("Information Technology", "Technology"),
    "SEC_MATERIALS": ("Materials", "Basic Materials"),
    "SEC_REAL_ESTATE": ("Real Estate",),
    "SEC_UTILITIES": ("Utilities",),
}


UPSERT_BENCHMARK_FINANCIAL_METRIC = """
INSERT INTO benchmark_index_financial_metric (
    index_id,
    metric_date,
    source,
    source_type,
    peer_count,
    covered_peer_count,
    coverage_weight_pct,
    eps_median,
    non_gaap_eps_median,
    forward_eps_median,
    pe_median,
    forward_pe_median,
    peg_median,
    price_to_sales_median,
    ev_to_ebitda_median,
    free_cash_flow_yield_median,
    gross_margin_median,
    operating_margin_median,
    net_margin_median,
    revenue_growth_median,
    eps_growth_median,
    latest_fiscal_period,
    latest_estimate_as_of,
    data_quality,
    notes,
    computed_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
ON CONFLICT (index_id, metric_date, source) DO UPDATE SET
    source_type = excluded.source_type,
    peer_count = excluded.peer_count,
    covered_peer_count = excluded.covered_peer_count,
    coverage_weight_pct = excluded.coverage_weight_pct,
    eps_median = excluded.eps_median,
    non_gaap_eps_median = excluded.non_gaap_eps_median,
    forward_eps_median = excluded.forward_eps_median,
    pe_median = excluded.pe_median,
    forward_pe_median = excluded.forward_pe_median,
    peg_median = excluded.peg_median,
    price_to_sales_median = excluded.price_to_sales_median,
    ev_to_ebitda_median = excluded.ev_to_ebitda_median,
    free_cash_flow_yield_median = excluded.free_cash_flow_yield_median,
    gross_margin_median = excluded.gross_margin_median,
    operating_margin_median = excluded.operating_margin_median,
    net_margin_median = excluded.net_margin_median,
    revenue_growth_median = excluded.revenue_growth_median,
    eps_growth_median = excluded.eps_growth_median,
    latest_fiscal_period = excluded.latest_fiscal_period,
    latest_estimate_as_of = excluded.latest_estimate_as_of,
    data_quality = excluded.data_quality,
    notes = excluded.notes,
    computed_at = now();
"""


class BenchmarkFinancialMetricService:
    """Compute stored benchmark financial snapshots from persisted company data."""

    def __init__(self, conn: Any):
        self.conn = conn

    def compute_sector_financial_metrics(self, metric_date: date | None = None) -> int:
        metric_date = metric_date or date.today()
        count = 0
        for index_id in self._active_sector_index_ids():
            count += self.compute_sector_benchmark(index_id, metric_date)
        return count

    def compute_sector_benchmark(self, index_id: str, metric_date: date | None = None) -> int:
        metric_date = metric_date or date.today()
        peer_sectors = SECTOR_BENCHMARK_PEERS.get(index_id.upper())
        if not peer_sectors:
            return 0

        peers = self._sector_peers(peer_sectors)
        values = [self._asset_metrics(row) for row in peers]
        covered = [value for value in values if value.has_any_financial_metric()]

        latest_fiscal_period = max(
            (value.latest_fiscal_period for value in covered if value.latest_fiscal_period is not None),
            default=None,
        )
        latest_estimate_as_of = max(
            (value.latest_estimate_as_of for value in covered if value.latest_estimate_as_of is not None),
            default=None,
        )
        data_quality = self._quality(len(peers), len(covered))
        notes = (
            f"Median from asset.sector peers: {', '.join(peer_sectors)}. "
            "Metrics use stored company statements, quotes, and estimates; unavailable values stay null."
        )

        self.conn.execute(
            UPSERT_BENCHMARK_FINANCIAL_METRIC,
            [
                index_id.upper(),
                metric_date,
                "computed_from_company_fundamentals",
                "asset_sector_median",
                len(peers),
                len(covered),
                None,
                _median([value.eps for value in values]),
                _median([value.non_gaap_eps for value in values]),
                _median([value.forward_eps for value in values]),
                _median([value.pe for value in values]),
                _median([value.forward_pe for value in values]),
                _median([value.peg for value in values]),
                _median([value.price_to_sales for value in values]),
                _median([value.ev_to_ebitda for value in values]),
                _median([value.free_cash_flow_yield for value in values]),
                _median([value.gross_margin for value in values]),
                _median([value.operating_margin for value in values]),
                _median([value.net_margin for value in values]),
                _median([value.revenue_growth for value in values]),
                _median([value.eps_growth for value in values]),
                latest_fiscal_period,
                latest_estimate_as_of,
                data_quality,
                notes,
            ],
        )
        self._mark_sync_success(index_id.upper(), "financial_metrics", metric_date)
        return 1

    def store_sector_provider_summary(
        self,
        *,
        index_id: str,
        metric_date: date,
        peer_count: int,
        covered_peer_count: int,
        metrics: dict[str, float | None],
        source: str,
        source_type: str,
        notes: str,
    ) -> int:
        data_quality = self._quality(peer_count, covered_peer_count)
        self.conn.execute(
            UPSERT_BENCHMARK_FINANCIAL_METRIC,
            [
                index_id.upper(),
                metric_date,
                source,
                source_type,
                peer_count,
                covered_peer_count,
                None,
                metrics.get("eps_median"),
                metrics.get("non_gaap_eps_median"),
                metrics.get("forward_eps_median"),
                metrics.get("pe_median"),
                metrics.get("forward_pe_median"),
                metrics.get("peg_median"),
                metrics.get("price_to_sales_median"),
                metrics.get("ev_to_ebitda_median"),
                metrics.get("free_cash_flow_yield_median"),
                metrics.get("gross_margin_median"),
                metrics.get("operating_margin_median"),
                metrics.get("net_margin_median"),
                metrics.get("revenue_growth_median"),
                metrics.get("eps_growth_median"),
                None,
                None,
                data_quality,
                notes,
            ],
        )
        self._mark_sync_success(index_id.upper(), "financial_metrics", metric_date)
        return 1

    def _active_sector_index_ids(self) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT index_id
            FROM benchmark_index
            WHERE index_category = 'sector'
              AND is_active = TRUE
            ORDER BY index_id;
            """
        ).fetchall()
        return [str(row[0]) for row in rows]

    def _sector_peers(self, peer_sectors: tuple[str, ...]) -> list[tuple[Any, ...]]:
        placeholders = ", ".join("?" for _ in peer_sectors)
        return self.conn.execute(
            f"""
            SELECT asset_id, mkt_cap, shares_outstanding
            FROM asset
            WHERE LOWER(sector) IN ({placeholders})
              AND COALESCE(asset_type, 'stock') = 'stock'
            ORDER BY asset_id;
            """,
            [sector.lower() for sector in peer_sectors],
        ).fetchall()

    def _asset_metrics(self, row: tuple[Any, ...]) -> "_AssetFinancialMetrics":
        asset_id = str(row[0])
        market_cap = _float_or_none(row[1])
        shares_outstanding = _float_or_none(row[2])
        latest_price = self._latest_price(asset_id)
        income = self._statements(asset_id, "income")
        balance = self._statements(asset_id, "balance")
        cashflow = self._statements(asset_id, "cashflow")
        current_income = income[0] if income else {}
        previous_income = income[1] if len(income) > 1 else {}
        current_balance = balance[0] if balance else {}
        current_cashflow = cashflow[0] if cashflow else {}
        estimate = self._latest_estimate(asset_id)

        eps = _first_number(current_income, "eps", "epsdiluted", "dilutedEPS", "eps_actual")
        non_gaap_eps = _first_number(
            current_income,
            "epsNonGaap",
            "epsNonGAAP",
            "nonGaapEPS",
            "non_gaap_eps",
            "normalizedEPS",
            "epsNormalized",
        )
        previous_eps = _first_number(previous_income, "eps", "epsdiluted", "dilutedEPS", "eps_actual")
        revenue = _first_number(current_income, "revenue", "totalRevenue", "revenue_actual")
        previous_revenue = _first_number(previous_income, "revenue", "totalRevenue", "revenue_actual")
        gross_profit = _first_number(current_income, "grossProfit", "gross_profit")
        operating_income = _first_number(current_income, "operatingIncome", "operating_income")
        net_income = _first_number(current_income, "netIncome", "net_income", "netIncomeCommonStockholders")
        ebitda = _first_number(current_income, "ebitda", "EBITDA")
        free_cash_flow = _first_number(current_cashflow, "freeCashFlow", "free_cash_flow")
        operating_cash_flow = _first_number(current_cashflow, "operatingCashFlow", "netCashProvidedByOperatingActivities")
        capex = _first_number(current_cashflow, "capitalExpenditure", "capital_expenditure")
        if free_cash_flow is None and operating_cash_flow is not None and capex is not None:
            free_cash_flow = operating_cash_flow + capex
        total_debt = _first_number(current_balance, "totalDebt", "debt")
        cash = _first_number(current_balance, "cashAndCashEquivalents", "cashAndShortTermInvestments", "cash")
        enterprise_value = None
        if market_cap is not None:
            enterprise_value = market_cap + (total_debt or 0.0) - (cash or 0.0)

        forward_eps = _first_number(estimate, "eps_estimated")
        pe = latest_price / eps if latest_price is not None and eps is not None and eps > 0 else None
        forward_pe = (
            latest_price / forward_eps
            if latest_price is not None and forward_eps is not None and forward_eps > 0
            else None
        )
        revenue_growth = _growth_rate(revenue, previous_revenue)
        eps_growth = _growth_rate(eps, previous_eps)

        return _AssetFinancialMetrics(
            eps=eps,
            non_gaap_eps=non_gaap_eps,
            forward_eps=forward_eps,
            pe=pe,
            forward_pe=forward_pe,
            peg=pe / (eps_growth * 100.0) if pe is not None and eps_growth is not None and eps_growth > 0 else None,
            price_to_sales=market_cap / revenue if market_cap is not None and revenue and revenue > 0 else None,
            ev_to_ebitda=enterprise_value / ebitda if enterprise_value is not None and ebitda and ebitda > 0 else None,
            free_cash_flow_yield=free_cash_flow / market_cap if free_cash_flow is not None and market_cap and market_cap > 0 else None,
            gross_margin=gross_profit / revenue if gross_profit is not None and revenue and revenue > 0 else None,
            operating_margin=operating_income / revenue if operating_income is not None and revenue and revenue > 0 else None,
            net_margin=net_income / revenue if net_income is not None and revenue and revenue > 0 else None,
            revenue_growth=revenue_growth,
            eps_growth=eps_growth,
            latest_fiscal_period=_max_date(
                current_income.get("_period_end_date"),
                current_balance.get("_period_end_date"),
                current_cashflow.get("_period_end_date"),
            ),
            latest_estimate_as_of=estimate.get("_as_of_ts"),
            shares_outstanding=shares_outstanding,
        )

    def _latest_price(self, asset_id: str) -> float | None:
        row = self.conn.execute(
            """
            SELECT COALESCE(adj_close, close)
            FROM asset_quote_daily
            WHERE asset_id = ?
              AND COALESCE(adj_close, close) IS NOT NULL
            ORDER BY date DESC
            LIMIT 1;
            """,
            [asset_id],
        ).fetchone()
        return _float_or_none(row[0]) if row else None

    def _statements(self, asset_id: str, statement_type: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT period_end_date, data_json
            FROM financial_statement
            WHERE asset_id = ?
              AND statement_type = ?
            ORDER BY period_end_date DESC NULLS LAST, year DESC, quarter DESC;
            """,
            [asset_id, statement_type],
        ).fetchall()
        statements: list[dict[str, Any]] = []
        for period_end, payload in rows:
            data = _json_dict(payload)
            if data:
                data["_period_end_date"] = period_end
                statements.append(data)
        return statements

    def _latest_estimate(self, asset_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT eps_estimated, revenue_estimated, as_of_ts
            FROM earnings_calendar_event
            WHERE asset_id = ?
              AND (eps_estimated IS NOT NULL OR revenue_estimated IS NOT NULL)
            ORDER BY earnings_date DESC
            LIMIT 1;
            """,
            [asset_id],
        ).fetchone()
        if row is None:
            return {}
        return {
            "eps_estimated": _float_or_none(row[0]),
            "revenue_estimated": _float_or_none(row[1]),
            "_as_of_ts": row[2],
        }

    def _mark_sync_success(self, index_id: str, job_type: str, success_date: date) -> None:
        self.conn.execute(
            """
            INSERT INTO benchmark_index_sync_state (
                index_id,
                job_type,
                last_success_at,
                last_attempt_at,
                last_success_date,
                last_error,
                updated_at
            )
            VALUES (?, ?, now(), now(), ?, NULL, now())
            ON CONFLICT (index_id, job_type) DO UPDATE SET
                last_success_at = now(),
                last_attempt_at = now(),
                last_success_date = excluded.last_success_date,
                last_error = NULL,
                updated_at = now();
            """,
            [index_id, job_type, success_date],
        )

    def _quality(self, peer_count: int, covered_count: int) -> str:
        if peer_count == 0 or covered_count == 0:
            return "unavailable"
        if covered_count / peer_count >= 0.8:
            return "ready"
        return "partial"


class _AssetFinancialMetrics:
    def __init__(
        self,
        *,
        eps: float | None,
        non_gaap_eps: float | None,
        forward_eps: float | None,
        pe: float | None,
        forward_pe: float | None,
        peg: float | None,
        price_to_sales: float | None,
        ev_to_ebitda: float | None,
        free_cash_flow_yield: float | None,
        gross_margin: float | None,
        operating_margin: float | None,
        net_margin: float | None,
        revenue_growth: float | None,
        eps_growth: float | None,
        latest_fiscal_period: date | None,
        latest_estimate_as_of: datetime | None,
        shares_outstanding: float | None,
    ):
        self.eps = eps
        self.non_gaap_eps = non_gaap_eps
        self.forward_eps = forward_eps
        self.pe = pe
        self.forward_pe = forward_pe
        self.peg = peg
        self.price_to_sales = price_to_sales
        self.ev_to_ebitda = ev_to_ebitda
        self.free_cash_flow_yield = free_cash_flow_yield
        self.gross_margin = gross_margin
        self.operating_margin = operating_margin
        self.net_margin = net_margin
        self.revenue_growth = revenue_growth
        self.eps_growth = eps_growth
        self.latest_fiscal_period = latest_fiscal_period
        self.latest_estimate_as_of = latest_estimate_as_of
        self.shares_outstanding = shares_outstanding

    def has_any_financial_metric(self) -> bool:
        return any(
            value is not None
            for value in [
                self.eps,
                self.non_gaap_eps,
                self.forward_eps,
                self.pe,
                self.forward_pe,
                self.peg,
                self.price_to_sales,
                self.ev_to_ebitda,
                self.free_cash_flow_yield,
                self.gross_margin,
                self.operating_margin,
                self.net_margin,
                self.revenue_growth,
                self.eps_growth,
            ]
        )


def _median(values: list[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return float(statistics.median(present)) if present else None


def _growth_rate(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous <= 0:
        return None
    return (current / previous) - 1.0


def _max_date(*values: Any) -> date | None:
    dates = [value for value in values if isinstance(value, date)]
    return max(dates) if dates else None


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _first_number(values: dict[str, Any], *keys: str) -> float | None:
    lower_values = {key.lower(): value for key, value in values.items()}
    for key in keys:
        value = values.get(key)
        if value is None:
            value = lower_values.get(key.lower())
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
