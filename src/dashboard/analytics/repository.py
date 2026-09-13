"""Database reads used by the analytics engine."""

from __future__ import annotations

from datetime import date
from typing import Any

from .calculations import (
    _extract_number,
    _json_object,
    _normalize_code,
    allocation_class,
    normalize_weight,
)
from .models import (
    DEFAULT_BENCHMARK_BY_COUNTRY,
    DEFAULT_BENCHMARK_BY_CURRENCY,
    DataCoverage,
    EtfHoldingAnalytics,
    PositionAnalytics,
    PricePoint,
)


_CDR_SYMBOL_ALIASES = {
    "CEGS": "CEG",
    "NVON": "NVO",
    "NOWS": "NOW",
    "VISA": "V",
}

_KNOWN_CDR_BASE_SYMBOLS = {
    "AAPL",
    "AMD",
    "AMZN",
    "ANET",
    "ASML",
    "AVGO",
    "BKNG",
    "CEG",
    "GEV",
    "GOOG",
    "ISRG",
    "LLY",
    "META",
    "MSFT",
    "MU",
    "NOW",
    "NVDA",
    "NVO",
    "SPGI",
    "TSLA",
    "UBER",
    "V",
}

DEFAULT_CDR_FEE_ADJUSTMENT = 0.006


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

    def default_benchmark_for_asset(self, asset_id: str) -> str | None:
        asset_id = asset_id.upper().strip()
        etf_benchmark = self.etf_profile(asset_id).get("benchmark_index_id")
        if etf_benchmark and self.benchmark_price_history(str(etf_benchmark)):
            return str(etf_benchmark)

        row = self.conn.execute(
            """
            SELECT country, ccy
            FROM asset
            WHERE asset_id = ?
            """,
            [asset_id],
        ).fetchone()
        if not row:
            return self._available_static_benchmark(None, None)
        return self._default_benchmark_for_country_currency(row[0], row[1])

    def default_benchmark_for_portfolio(self, positions: list[PositionAnalytics]) -> str | None:
        weights = {p.asset_id: p.weight for p in positions if p.weight is not None and p.weight > 0}
        if not weights:
            return self._available_static_benchmark(None, None)

        metadata = self.asset_exposure_metadata(list(weights))
        country_weights: dict[str, float] = {}
        currency_weights: dict[str, float] = {}
        for asset_id, weight in weights.items():
            meta = metadata.get(asset_id, {})
            country = _normalize_code(meta.get("country"))
            currency = _normalize_code(meta.get("currency"))
            if country:
                country_weights[country] = country_weights.get(country, 0.0) + weight
            if currency:
                currency_weights[currency] = currency_weights.get(currency, 0.0) + weight

        dominant_country = (
            max(country_weights, key=country_weights.get) if country_weights else None
        )
        dominant_currency = (
            max(currency_weights, key=currency_weights.get) if currency_weights else None
        )
        return self._default_benchmark_for_country_currency(dominant_country, dominant_currency)

    def _default_benchmark_for_country_currency(
        self,
        country: str | None,
        currency: str | None,
    ) -> str | None:
        country = _normalize_code(country)
        currency = _normalize_code(currency)
        metadata_match = self._benchmark_metadata_match(country, currency)
        if metadata_match:
            return metadata_match
        return self._available_static_benchmark(country, currency)

    def _benchmark_metadata_match(self, country: str | None, currency: str | None) -> str | None:
        if not self._table_exists("benchmark_index") or not self._table_exists(
            "benchmark_index_daily_price"
        ):
            return None
        if not country and not currency:
            return None

        match_clauses = []
        params: list[Any] = []
        if country:
            match_clauses.append("UPPER(b.country_code) = ?")
            params.append(country)
        if currency:
            match_clauses.append("UPPER(b.currency) = ?")
            params.append(currency)

        rows = self.conn.execute(
            f"""
            SELECT b.index_id
            FROM benchmark_index b
            WHERE b.is_active = TRUE
              AND ({" OR ".join(match_clauses)})
              AND EXISTS (
                  SELECT 1
                  FROM benchmark_index_daily_price p
                  WHERE p.index_id = b.index_id
              )
            ORDER BY
                CASE WHEN UPPER(COALESCE(b.country_code, '')) = ? THEN 0 ELSE 1 END,
                CASE WHEN b.is_core THEN 0 ELSE 1 END,
                b.index_id
            LIMIT 1
            """,
            [*params, country or ""],
        ).fetchall()
        return rows[0][0] if rows else None

    def _available_static_benchmark(self, country: str | None, currency: str | None) -> str | None:
        candidates = []
        country_key = _normalize_code(country)
        currency_key = _normalize_code(currency)
        if country_key and country_key in DEFAULT_BENCHMARK_BY_COUNTRY:
            candidates.append(DEFAULT_BENCHMARK_BY_COUNTRY[country_key])
        if currency_key and currency_key in DEFAULT_BENCHMARK_BY_CURRENCY:
            candidates.append(DEFAULT_BENCHMARK_BY_CURRENCY[currency_key])
        candidates.extend(["SP500", "TSXCOMP", "DEV_INTL"])
        for candidate in dict.fromkeys(candidates):
            if self.benchmark_price_history(candidate):
                return candidate
        return None

    def latest_price(self, asset_id: str) -> float | None:
        row = self.conn.execute(
            """
            SELECT close
            FROM asset_quote_daily
            WHERE asset_id = ?
              AND close IS NOT NULL
            ORDER BY date DESC
            LIMIT 1
            """,
            [asset_id.upper().strip()],
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else None

    def valuation_asset_id(self, asset_id: str) -> str:
        """Return the asset id whose fundamentals should drive valuation models."""
        asset_id = asset_id.upper().strip()
        row = self.conn.execute(
            """
            SELECT asset_id, symbol, asset_subtype, name, description
            FROM asset
            WHERE asset_id = ?
            """,
            [asset_id],
        ).fetchone()
        if row is None:
            return asset_id

        symbol = str(row[1] or row[0])
        base = symbol.split(".", maxsplit=1)[0].upper()
        base = _CDR_SYMBOL_ALIASES.get(base, base)
        if base == asset_id or not self._looks_like_cdr_listing(row):
            return asset_id
        return base

    def wrapper_fee_adjustment(self, asset_id: str) -> float | None:
        """Return annual wrapper fee drag for held wrappers whose fundamentals use another asset."""
        asset_id = asset_id.upper().strip()
        row = self.conn.execute(
            """
            SELECT asset_id, symbol, asset_subtype, name, description
            FROM asset
            WHERE asset_id = ?
            """,
            [asset_id],
        ).fetchone()
        if row is None or not self._looks_like_cdr_listing(row):
            return None

        stored = self.etf_profile(asset_id).get("expense_ratio")
        if stored is not None:
            value = float(stored)
            return value / 100.0 if value > 1.0 else value
        return DEFAULT_CDR_FEE_ADJUSTMENT

    def annual_dividend_per_share(
        self, asset_id: str, as_of_date: date | None = None
    ) -> float | None:
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
        if row and row[0] is not None and row[0] > 0:
            return float(row[0])
        rows = self.conn.execute(
            """
            SELECT data_json
            FROM financial_statement
            WHERE asset_id = ?
              AND statement_type = 'income'
            ORDER BY year DESC, quarter DESC
            LIMIT 8
            """,
            [asset_id.upper().strip()],
        ).fetchall()
        for statement_row in rows:
            data = _json_object(statement_row[0])
            shares = _extract_number(
                data,
                (
                    "weightedAverageShsOutDil",
                    "weightedAverageShsOut",
                    "weighted_average_shares_diluted",
                    "weighted_average_shares",
                    "sharesOutstanding",
                    "shares_outstanding",
                ),
            )
            if shares is not None and shares > 0:
                return shares
        return None

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
                    (
                        "operatingCashFlow",
                        "cashFlowFromOperations",
                        "netCashProvidedByOperatingActivities",
                    ),
                )
                capex = _extract_number(
                    data, ("capitalExpenditure", "capital_expenditure", "capex")
                )
                if operating is not None and capex is not None:
                    fcf = operating - abs(capex)
            if fcf is not None and fcf > 0:
                return fcf
        return None

    def latest_free_cash_flow_is_nonpositive(self, asset_id: str) -> bool:
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
            fcf = _extract_number(
                data,
                ("freeCashFlow", "free_cash_flow", "free_cashflow"),
            )
            if fcf is None:
                operating = _extract_number(
                    data,
                    (
                        "operatingCashFlow",
                        "cashFlowFromOperations",
                        "netCashProvidedByOperatingActivities",
                    ),
                )
                capex = _extract_number(
                    data,
                    ("capitalExpenditure", "capital_expenditure", "capex"),
                )
                if operating is not None and capex is not None:
                    fcf = operating - abs(capex)
            if fcf is not None:
                return fcf <= 0
        return False

    def current_price_uses_stored_fallback(self, asset_id: str) -> bool:
        row = self.conn.execute(
            """
            SELECT provider
            FROM current_asset_price
            WHERE asset_id = ?
            """,
            [asset_id.upper().strip()],
        ).fetchone()
        return bool(
            row
            and str(row[0] or "").lower() == "stored_close_fallback"
        )

    def financial_statement_history(
        self, asset_id: str, statement_type: str
    ) -> list[dict[str, Any]]:
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
            SELECT asset_type, asset_subtype, symbol, name, sector, industry
            FROM asset
            WHERE asset_id = ?
            """,
            [asset_id.upper().strip()],
        ).fetchone()
        if row is None:
            return {
                "asset_type": None,
                "asset_subtype": None,
                "symbol": None,
                "name": None,
                "sector": None,
                "industry": None,
            }
        return {
            "asset_type": row[0],
            "asset_subtype": row[1],
            "symbol": row[2],
            "name": row[3],
            "sector": row[4],
            "industry": row[5],
        }

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

    def portfolio_direct_holding_weights(
        self, portfolio_id: int
    ) -> dict[str, tuple[str, float | None]]:
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
            SELECT asset_id, symbol, asset_type, asset_subtype, name, sector, industry, country, ccy
            FROM asset
            WHERE asset_id IN ({placeholders})
            """,
            asset_ids,
        ).fetchall()
        return {
            row[0]: {
                "sector": row[5],
                "country": row[7],
                "currency": row[8],
                "asset_class": allocation_class(
                    asset_id=row[0],
                    symbol=row[1],
                    asset_type=row[2],
                    asset_subtype=row[3],
                    name=row[4],
                    sector=row[5],
                    industry=row[6],
                ),
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

    def _has_valuation_inputs(self, asset_id: str) -> bool:
        asset_id = asset_id.upper().strip()
        row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM financial_statement
            WHERE UPPER(asset_id) = ?
            """,
            [asset_id],
        ).fetchone()
        if row and row[0]:
            return True
        row = self.conn.execute(
            """
            SELECT shares_outstanding
            FROM asset
            WHERE UPPER(asset_id) = ?
            """,
            [asset_id],
        ).fetchone()
        if row and row[0] is not None and row[0] > 0:
            return True
        row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM dividend_event
            WHERE UPPER(asset_id) = ?
            """,
            [asset_id],
        ).fetchone()
        return bool(row and row[0])

    @staticmethod
    def _looks_like_cdr_listing(row: Any) -> bool:
        asset_id = str(row[0] or "")
        symbol = str(row[1] or asset_id)
        asset_subtype = str(row[2] or "")
        name = str(row[3] or "")
        description = str(row[4] or "")
        text = f"{asset_id} {symbol} {asset_subtype} {name} {description}".lower()
        base = symbol.split(".", maxsplit=1)[0].upper()
        base = _CDR_SYMBOL_ALIASES.get(base, base)
        if "cdr" in text or "depositary receipt" in text or "depository receipt" in text:
            return True
        return symbol.upper().endswith(".TO") and base in _KNOWN_CDR_BASE_SYMBOLS
