"""Application-facing read and write services for the HTTP API."""

from dataclasses import asdict
import json
from typing import Any

from dashboard.api.models import (
    AssetDetail,
    BrokerAccountResponse,
    BrokerConnectionResponse,
    BrokerUserResponse,
    BenchmarkComparisonProfile,
    ComparisonAssetProfile,
    ComparisonFundamentals,
    ComparisonResponse,
    ComparisonReturns,
    IngestionJobResponse,
    NewsItemResponse,
    OverviewUpdatesResponse,
    Page,
    PortfolioCreate,
    PortfolioSummary,
    PortfolioUpdate,
    PositionSummary,
    PricePointResponse,
    PriceMoverResponse,
    TransactionSummary,
    ValuationContext,
)
from dashboard.analytics import AnalyticsEngine, AnalyticsRepository, analytics_report_payload
from dashboard.brokers.repository import BrokerSyncRepository
from dashboard.brokers.models import BrokerUser
from dashboard.brokers.snaptrade import SNAPTRADE_PROVIDER
from dashboard.models.commands import BrokerCommands, IngestionCommands


_HOLDINGS_SQL = """
SELECT portfolio_id, asset_id, SUM(quantity) AS quantity, SUM(book_cost) AS book_cost
FROM (
    SELECT
        portfolio_id,
        asset_id,
        SUM(qty) AS quantity,
        SUM(qty * price) AS book_cost
    FROM txn
    WHERE asset_id IS NOT NULL
      AND txn_type IN ('buy', 'sell')
    GROUP BY portfolio_id, asset_id
    UNION ALL
    SELECT
        portfolio_id,
        asset_id,
        quantity,
        book_cost
    FROM broker_portfolio_position_map
) holdings
GROUP BY portfolio_id, asset_id
"""


_ENRICHED_ASSET_SELECT = """
    a.asset_id,
    COALESCE(a.symbol, a.asset_id) AS symbol,
    a.exchange_code,
    a.asset_type,
    a.asset_subtype,
    a.ccy,
    a.name,
    a.description,
    CASE WHEN cdr_underlying.asset_id IS NOT NULL
        THEN COALESCE(cdr_underlying.sector, a.sector)
        ELSE a.sector
    END AS sector,
    CASE WHEN cdr_underlying.asset_id IS NOT NULL
        THEN COALESCE(cdr_underlying.industry, a.industry)
        ELSE a.industry
    END AS industry,
    CASE WHEN cdr_underlying.asset_id IS NOT NULL
        THEN COALESCE(cdr_underlying.country, a.country)
        ELSE a.country
    END AS country,
    CASE WHEN cdr_underlying.asset_id IS NOT NULL
        THEN COALESCE(cdr_underlying.region, a.region)
        ELSE a.region
    END AS region,
    a.size,
    COALESCE(a.mkt_cap, cdr_underlying.mkt_cap) AS mkt_cap,
    COALESCE(a.shares_outstanding, cdr_underlying.shares_outstanding) AS shares_outstanding,
    COALESCE(a.market_beta, cdr_underlying.market_beta) AS market_beta
"""


_ENRICHED_ASSET_JOIN = """
LEFT JOIN asset cdr_underlying ON UPPER(cdr_underlying.asset_id) = UPPER(
        CASE
            WHEN POSITION('.' IN COALESCE(a.symbol, a.asset_id)) > 0
                THEN SPLIT_PART(COALESCE(a.symbol, a.asset_id), '.', 1)
            ELSE ''
        END
    )
    AND cdr_underlying.asset_id <> a.asset_id
    AND (
        LOWER(COALESCE(a.asset_subtype, '')) LIKE '%cdr%'
        OR LOWER(COALESCE(a.name, '')) LIKE '%depositary receipt%'
        OR LOWER(COALESCE(a.description, '')) LIKE '%depositary receipt%'
        OR LOWER(COALESCE(a.name, '')) LIKE '% cdr%'
        OR LOWER(COALESCE(a.description, '')) LIKE '% cdr%'
        OR (
            POSITION('.' IN COALESCE(a.symbol, a.asset_id)) > 0
            AND (
                a.sector IS NULL
                OR a.industry IS NULL
                OR a.country IS NULL
                OR UPPER(a.country) = 'CA'
            )
        )
    )
"""


_CDR_CLASSIFICATION_OVERRIDES = {
    "AAPL": {"sector": "Technology", "industry": "Consumer Electronics", "country": "US"},
    "AMD": {"sector": "Technology", "industry": "Semiconductors", "country": "US"},
    "AMZN": {"sector": "Consumer Cyclical", "industry": "Internet Retail", "country": "US"},
    "ANET": {"sector": "Technology", "industry": "Computer Hardware", "country": "US"},
    "ASML": {"sector": "Technology", "industry": "Semiconductors", "country": "NL"},
    "AVGO": {"sector": "Technology", "industry": "Semiconductors", "country": "US"},
    "GEV": {"sector": "Industrials", "industry": "Electrical Equipment & Parts", "country": "US"},
    "GOOG": {"sector": "Communication Services", "industry": "Internet Content & Information", "country": "US"},
    "ISRG": {"sector": "Healthcare", "industry": "Medical Instruments & Supplies", "country": "US"},
    "LLY": {"sector": "Healthcare", "industry": "Medical - Pharmaceuticals", "country": "US"},
    "META": {"sector": "Communication Services", "industry": "Internet Content & Information", "country": "US"},
    "MSFT": {"sector": "Technology", "industry": "Software - Infrastructure", "country": "US"},
    "MU": {"sector": "Technology", "industry": "Semiconductors", "country": "US"},
    "NOW": {"sector": "Technology", "industry": "Software - Application", "country": "US"},
    "NVDA": {"sector": "Technology", "industry": "Semiconductors", "country": "US"},
    "SPGI": {"sector": "Financial Services", "industry": "Financial Data & Stock Exchanges", "country": "US"},
    "TSLA": {"sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "country": "US"},
    "VISA": {"sector": "Financial Services", "industry": "Credit Services", "country": "US"},
}

_KNOWN_CDR_UNDERLYING_NAMES = {
    "AAPL": "Apple Inc.",
    "AMD": "Advanced Micro Devices, Inc.",
    "AMZN": "Amazon.com, Inc.",
    "ANET": "Arista Networks, Inc.",
    "ASML": "ASML Holding N.V.",
    "AVGO": "Broadcom Inc.",
    "GEV": "GE Vernova Inc.",
    "GOOG": "Alphabet Inc.",
    "ISRG": "Intuitive Surgical, Inc.",
    "LLY": "Eli Lilly and Company",
    "META": "Meta Platforms, Inc.",
    "MSFT": "Microsoft Corporation",
    "MU": "Micron Technology, Inc.",
    "NOW": "ServiceNow, Inc.",
    "NVDA": "NVIDIA Corporation",
    "SPGI": "S&P Global Inc.",
    "TSLA": "Tesla, Inc.",
    "VISA": "Visa Inc.",
}

_CDR_SYMBOL_ALIASES = {
    "NOWS": "NOW",
}


class PortfolioApiService:
    def __init__(self, conn) -> None:
        self.conn = conn

    def list_portfolios(self) -> list[PortfolioSummary]:
        rows = self.conn.execute(
            f"""
            WITH holdings AS ({_HOLDINGS_SQL}),
            latest_prices AS (
                SELECT asset_id, COALESCE(adj_close, close) AS price
                FROM asset_quote_daily
                QUALIFY ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY date DESC) = 1
            ),
            totals AS (
                SELECT
                    h.portfolio_id,
                    COUNT(*) FILTER (WHERE h.quantity <> 0) AS position_count,
                    COALESCE(SUM(h.book_cost) FILTER (WHERE h.quantity <> 0), 0) AS book_cost,
                    COALESCE(
                        SUM(COALESCE(h.quantity * lp.price, h.book_cost)) FILTER (WHERE h.quantity <> 0),
                        0
                    ) AS market_value
                FROM holdings h
                LEFT JOIN latest_prices lp ON lp.asset_id = h.asset_id
                GROUP BY h.portfolio_id
            )
            SELECT
                p.portfolio_id,
                p.portfolio_name,
                p.base_ccy,
                p.created_at,
                p.updated_at,
                COALESCE(t.position_count, 0),
                COALESCE(t.market_value, 0),
                COALESCE(t.book_cost, 0)
            FROM portfolio p
            LEFT JOIN totals t ON t.portfolio_id = p.portfolio_id
            ORDER BY p.portfolio_id
            """
        ).fetchall()
        return [self._portfolio_summary(row) for row in rows]

    def aggregate_portfolio(self) -> PortfolioSummary:
        portfolios = self.list_portfolios()
        if not portfolios:
            raise LookupError("No portfolios found.")
        market_value = sum(item.market_value for item in portfolios)
        book_cost = sum(item.book_cost for item in portfolios)
        return PortfolioSummary(
            portfolio_id=0,
            name="All portfolios",
            base_ccy="CAD",
            created_at=min(item.created_at for item in portfolios),
            updated_at=max(item.updated_at for item in portfolios),
            position_count=sum(item.position_count for item in portfolios),
            market_value=market_value,
            book_cost=book_cost,
            unrealized_gain=market_value - book_cost if market_value else None,
            projected_value=sum(
                item.projected_value for item in portfolios if item.projected_value is not None
            )
            or None,
            projected_value_low=sum(
                item.projected_value_low
                for item in portfolios
                if item.projected_value_low is not None
            )
            or None,
            projected_value_high=sum(
                item.projected_value_high
                for item in portfolios
                if item.projected_value_high is not None
            )
            or None,
            projected_horizon_years=max(
                (
                    item.projected_horizon_years
                    for item in portfolios
                    if item.projected_horizon_years is not None
                ),
                default=None,
            ),
        )

    def get_portfolio(self, portfolio_id: int) -> PortfolioSummary:
        for portfolio in self.list_portfolios():
            if portfolio.portfolio_id == portfolio_id:
                return portfolio
        raise LookupError(f"Portfolio not found: {portfolio_id}")

    def create_portfolio(self, request: PortfolioCreate) -> PortfolioSummary:
        name = request.name.strip()
        if not name:
            raise ValueError("Portfolio name is required.")
        if self.conn.execute(
            "SELECT 1 FROM portfolio WHERE portfolio_name = ?",
            [name],
        ).fetchone():
            raise FileExistsError(f"Portfolio already exists: {name}")
        row = self.conn.execute(
            """
            INSERT INTO portfolio(portfolio_id, portfolio_name, base_ccy)
            SELECT COALESCE(MAX(portfolio_id), 0) + 1, ?, UPPER(?)
            FROM portfolio
            RETURNING portfolio_id
            """,
            [name, request.base_ccy],
        ).fetchone()
        return self.get_portfolio(int(row[0]))

    def update_portfolio(self, portfolio_id: int, request: PortfolioUpdate) -> PortfolioSummary:
        self.get_portfolio(portfolio_id)
        name = request.name.strip()
        if not name:
            raise ValueError("Portfolio name is required.")
        if self.conn.execute(
            """
            SELECT 1
            FROM portfolio
            WHERE portfolio_id <> ?
              AND portfolio_name = ?
            """,
            [portfolio_id, name],
        ).fetchone():
            raise FileExistsError(f"Portfolio already exists: {name}")
        self.conn.execute(
            """
            UPDATE portfolio
            SET portfolio_name = ?,
                updated_at = now()
            WHERE portfolio_id = ?
            """,
            [name, portfolio_id],
        )
        return self.get_portfolio(portfolio_id)

    def delete_portfolio(self, portfolio_id: int) -> dict[str, int]:
        self.get_portfolio(portfolio_id)
        self.conn.execute("UPDATE broker_account SET portfolio_id = NULL WHERE portfolio_id = ?", [portfolio_id])
        self.conn.execute("DELETE FROM broker_portfolio_position_map WHERE portfolio_id = ?", [portfolio_id])
        self.conn.execute("DELETE FROM broker_portfolio_txn_map WHERE portfolio_id = ?", [portfolio_id])
        self.conn.execute("DELETE FROM position WHERE portfolio_id = ?", [portfolio_id])
        self.conn.execute("DELETE FROM portfolio_ticker WHERE portfolio_id = ?", [portfolio_id])
        self.conn.execute("DELETE FROM txn WHERE portfolio_id = ?", [portfolio_id])
        self.conn.execute("DELETE FROM portfolio WHERE portfolio_id = ?", [portfolio_id])
        return {"portfolio_id": portfolio_id}

    def delete_position(self, portfolio_id: int, asset_id: str) -> dict[str, int | str]:
        self.get_portfolio(portfolio_id)
        asset_id = asset_id.upper().strip()
        existing = self.conn.execute(
            f"""
            WITH holdings AS ({_HOLDINGS_SQL})
            SELECT 1
            FROM holdings
            WHERE portfolio_id = ?
              AND UPPER(asset_id) = ?
              AND quantity <> 0
            """,
            [portfolio_id, asset_id],
        ).fetchone()
        if existing is None:
            raise LookupError(f"Holding not found in portfolio {portfolio_id}: {asset_id}")

        broker_rows = int(
            self.conn.execute(
                """
                SELECT COUNT(*)
                FROM broker_portfolio_position_map
                WHERE portfolio_id = ?
                  AND UPPER(asset_id) = ?
                """,
                [portfolio_id, asset_id],
            ).fetchone()[0]
        )
        txn_rows = self.conn.execute(
            """
            DELETE FROM txn
            WHERE portfolio_id = ?
              AND UPPER(asset_id) = ?
            RETURNING txn_id
            """,
            [portfolio_id, asset_id],
        ).fetchall()
        position_rows = self.conn.execute(
            """
            DELETE FROM position
            WHERE portfolio_id = ?
              AND UPPER(asset_id) = ?
            RETURNING asset_id
            """,
            [portfolio_id, asset_id],
        ).fetchall()
        broker_map_rows = self.conn.execute(
            """
            DELETE FROM broker_portfolio_position_map
            WHERE portfolio_id = ?
              AND UPPER(asset_id) = ?
            RETURNING asset_id
            """,
            [portfolio_id, asset_id],
        ).fetchall()
        self.conn.execute(
            """
            DELETE FROM portfolio_ticker
            WHERE portfolio_id = ?
              AND UPPER(asset_id) = ?
            """,
            [portfolio_id, asset_id],
        )
        return {
            "portfolio_id": portfolio_id,
            "asset_id": asset_id,
            "deleted_transactions": len(txn_rows),
            "deleted_positions": len(position_rows),
            "deleted_broker_mappings": len(broker_map_rows),
            "broker_linked": broker_rows > 0,
        }

    def list_positions(self, portfolio_id: int | None = None) -> list[PositionSummary]:
        if portfolio_id is not None:
            self.get_portfolio(portfolio_id)
            where = "WHERE portfolio_id = ?"
            params: list[object] = [portfolio_id, portfolio_id]
        else:
            where = ""
            params = []
        rows = self.conn.execute(
            f"""
            WITH portfolio_holdings AS ({_HOLDINGS_SQL}),
            holdings AS (
                SELECT asset_id, SUM(quantity) AS quantity, SUM(book_cost) AS book_cost
                FROM portfolio_holdings
                {where}
                GROUP BY asset_id
                HAVING SUM(quantity) <> 0
            ),
            broker_links AS (
                SELECT
                    asset_id,
                    COUNT(DISTINCT provider_account_id) AS broker_account_count
                FROM broker_portfolio_position_map
                {where}
                GROUP BY asset_id
            ),
            latest_prices AS (
                SELECT asset_id, COALESCE(adj_close, close) AS price
                FROM asset_quote_daily
                QUALIFY ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY date DESC) = 1
            ),
            valued AS (
                SELECT
                h.*,
                a.symbol,
                a.name,
                a.asset_type,
                CASE WHEN cdr_underlying.asset_id IS NOT NULL
                    THEN COALESCE(cdr_underlying.sector, a.sector)
                    ELSE a.sector
                END AS sector,
                CASE WHEN cdr_underlying.asset_id IS NOT NULL
                    THEN COALESCE(cdr_underlying.industry, a.industry)
                    ELSE a.industry
                END AS industry,
                CASE WHEN cdr_underlying.asset_id IS NOT NULL
                    THEN COALESCE(cdr_underlying.country, a.country)
                    ELSE a.country
                END AS country,
                a.ccy,
                COALESCE(bl.broker_account_count, 0) AS broker_account_count,
                lp.price,
                COALESCE(h.quantity * lp.price, h.book_cost) AS market_value
                FROM holdings h
                JOIN asset a ON a.asset_id = h.asset_id
                {_ENRICHED_ASSET_JOIN}
                LEFT JOIN latest_prices lp ON lp.asset_id = h.asset_id
                LEFT JOIN broker_links bl ON bl.asset_id = h.asset_id
            )
            SELECT
                asset_id,
                COALESCE(symbol, asset_id),
                name,
                asset_type,
                sector,
                industry,
                country,
                ccy,
                broker_account_count,
                quantity,
                book_cost,
                price,
                market_value,
                market_value - book_cost,
                CASE
                    WHEN SUM(market_value) OVER () = 0 THEN NULL
                    ELSE market_value / SUM(market_value) OVER ()
                END
            FROM valued
            ORDER BY market_value DESC NULLS LAST, asset_id
            """,
            params,
        ).fetchall()
        return [self._position_summary(row) for row in rows]

    def _position_summary(self, row) -> PositionSummary:
        classification = _cdr_classification_override(
            asset_id=row[0],
            symbol=row[1],
            name=row[2],
            sector=row[4],
            industry=row[5],
            country=row[6],
        )
        return PositionSummary(
            asset_id=row[0],
            symbol=row[1],
            name=row[2],
            asset_type=row[3],
            sector=classification["sector"],
            industry=classification["industry"],
            country=classification["country"],
            currency=row[7],
            quantity=float(row[9]),
            book_cost=float(row[10]),
            latest_price=_float_or_none(row[11]),
            market_value=_float_or_none(row[12]),
            unrealized_gain=_float_or_none(row[13]),
            weight=_float_or_none(row[14]),
            broker_linked=int(row[8]) > 0,
            broker_account_count=int(row[8]),
        )

    def list_transactions(self, portfolio_id: int | None, limit: int, offset: int) -> Page[TransactionSummary]:
        where = ""
        params: list[object] = []
        if portfolio_id is not None:
            self.get_portfolio(portfolio_id)
            where = "WHERE portfolio_id = ?"
            params.append(portfolio_id)
        total = int(
            self.conn.execute(
                f"SELECT COUNT(*) FROM txn {where}",
                params,
            ).fetchone()[0]
        )
        rows = self.conn.execute(
            f"""
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
                fee_amt,
                batch_id
            FROM txn
            {where}
            ORDER BY time_stamp DESC, txn_id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        items = [
            TransactionSummary(
                transaction_id=int(row[0]),
                portfolio_id=int(row[1]),
                timestamp=row[2],
                transaction_type=row[3],
                asset_id=row[4],
                quantity=_float_or_none(row[5]),
                price=_float_or_none(row[6]),
                currency=row[7],
                cash_amount=_float_or_none(row[8]),
                fee_amount=_float_or_none(row[9]),
                batch_id=int(row[10]),
            )
            for row in rows
        ]
        return Page(items=items, total=total, limit=limit, offset=offset)

    def analytics(self, portfolio_id: int, benchmark_index_id: str | None = None):
        self.get_portfolio(portfolio_id)
        report = AnalyticsEngine(AnalyticsRepository(self.conn)).portfolio_report(
            portfolio_id=portfolio_id,
            benchmark_index_id=benchmark_index_id,
        )
        return analytics_report_payload(report)

    def overview_updates(self) -> OverviewUpdatesResponse:
        portfolios = self.list_portfolios()
        total_market_value = sum(item.market_value for item in portfolios)
        position_count = sum(item.position_count for item in portfolios)
        mover_rows = self.conn.execute(
            f"""
            WITH portfolio_holdings AS ({_HOLDINGS_SQL}),
            holdings AS (
                SELECT asset_id, SUM(quantity) AS quantity, SUM(book_cost) AS book_cost
                FROM portfolio_holdings
                GROUP BY asset_id
                HAVING SUM(quantity) <> 0
            ),
            ranked_prices AS (
                SELECT
                    asset_id,
                    date,
                    COALESCE(adj_close, close) AS price,
                    ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY date DESC) AS price_rank
                FROM asset_quote_daily
                WHERE COALESCE(adj_close, close) IS NOT NULL
            ),
            latest AS (
                SELECT asset_id, price
                FROM ranked_prices
                WHERE price_rank = 1
            ),
            previous AS (
                SELECT asset_id, price
                FROM ranked_prices
                WHERE price_rank = 2
            ),
            valued AS (
                SELECT
                    h.asset_id,
                    COALESCE(a.symbol, h.asset_id) AS symbol,
                    a.name,
                    l.price AS latest_price,
                    p.price AS previous_price,
                    l.price - p.price AS price_change,
                    CASE WHEN p.price IS NULL OR p.price = 0 THEN NULL ELSE (l.price - p.price) / p.price END AS change_percent,
                    COALESCE(h.quantity * l.price, h.book_cost) AS market_value
                FROM holdings h
                JOIN asset a ON a.asset_id = h.asset_id
                JOIN latest l ON l.asset_id = h.asset_id
                JOIN previous p ON p.asset_id = h.asset_id
            )
            SELECT
                asset_id,
                symbol,
                name,
                latest_price,
                previous_price,
                price_change,
                change_percent,
                market_value
            FROM valued
            ORDER BY ABS(COALESCE(change_percent, 0)) DESC, market_value DESC NULLS LAST
            LIMIT 8
            """
        ).fetchall()
        news_rows = self.conn.execute(
            """
            SELECT
                a.title,
                a.provider,
                a.published_at,
                a.url,
                m.asset_id,
                COALESCE(asset.symbol, m.ticker),
                NULL AS sentiment
            FROM news_article a
            LEFT JOIN news_article_asset_mention m ON m.article_id = a.article_id
            LEFT JOIN asset ON asset.asset_id = m.asset_id
            ORDER BY a.published_at DESC NULLS LAST, a.article_id DESC
            LIMIT 8
            """
        ).fetchall()
        return OverviewUpdatesResponse(
            total_market_value=total_market_value,
            position_count=position_count,
            mover_count=len(mover_rows),
            news_count=len(news_rows),
            price_movers=[
                PriceMoverResponse(
                    asset_id=row[0],
                    symbol=row[1],
                    name=row[2],
                    latest_price=_float_or_none(row[3]),
                    previous_price=_float_or_none(row[4]),
                    change=_float_or_none(row[5]),
                    change_percent=_float_or_none(row[6]),
                    market_value=_float_or_none(row[7]),
                    weight=(float(row[7]) / total_market_value) if total_market_value else None,
                )
                for row in mover_rows
            ],
            news=[
                NewsItemResponse(
                    title=row[0],
                    provider=row[1],
                    published_at=row[2],
                    url=row[3],
                    asset_id=row[4],
                    symbol=row[5],
                    sentiment=row[6],
                )
                for row in news_rows
            ],
        )

    def _portfolio_summary(self, row) -> PortfolioSummary:
        market_value = float(row[6])
        book_cost = float(row[7])
        projection = self._portfolio_projection(int(row[0]))
        return PortfolioSummary(
            portfolio_id=int(row[0]),
            name=row[1],
            base_ccy=row[2],
            created_at=row[3],
            updated_at=row[4],
            position_count=int(row[5]),
            market_value=market_value,
            book_cost=book_cost,
            unrealized_gain=market_value - book_cost if market_value else None,
            projected_value=projection.get("projected_value"),
            projected_value_low=projection.get("projected_value_low"),
            projected_value_high=projection.get("projected_value_high"),
            projected_horizon_years=projection.get("projected_horizon_years"),
        )

    def _portfolio_projection(self, portfolio_id: int) -> dict[str, float | int | None]:
        try:
            report = AnalyticsEngine(AnalyticsRepository(self.conn)).portfolio_report(portfolio_id)
        except Exception:
            return {}
        simulation = report.forecast.simulation
        if simulation is None:
            return {}
        return {
            "projected_value": _float_or_none(simulation.p50_value)
            or _float_or_none(simulation.expected_value),
            "projected_value_low": _float_or_none(simulation.p10_value),
            "projected_value_high": _float_or_none(simulation.p90_value),
            "projected_horizon_years": simulation.horizon_years,
        }


class AssetApiService:
    def __init__(self, conn) -> None:
        self.conn = conn

    def get_asset(self, asset_id: str) -> AssetDetail:
        asset_id = asset_id.upper().strip()
        row = self.conn.execute(
            """
            SELECT
                {_ENRICHED_ASSET_SELECT},
                (
                    SELECT COALESCE(q.adj_close, q.close)
                    FROM asset_quote_daily q
                    WHERE q.asset_id = a.asset_id
                    ORDER BY q.date DESC
                    LIMIT 1
                )
            FROM asset a
            {_ENRICHED_ASSET_JOIN}
            WHERE a.asset_id = ?
            """.format(
                _ENRICHED_ASSET_SELECT=_ENRICHED_ASSET_SELECT,
                _ENRICHED_ASSET_JOIN=_ENRICHED_ASSET_JOIN,
            ),
            [asset_id],
        ).fetchone()
        if row is None:
            fallback = _known_underlying_asset_detail(asset_id)
            if fallback is not None:
                return fallback
            raise LookupError(f"Asset not found: {asset_id}")
        classification = _cdr_classification_override(
            asset_id=row[0],
            symbol=row[1],
            name=row[6],
            sector=row[8],
            industry=row[9],
            country=row[10],
        )
        underlying_asset_id = _cdr_underlying_asset_id(row[0], row[1], row[6])
        return AssetDetail(
            asset_id=row[0],
            symbol=row[1],
            is_cdr=underlying_asset_id is not None,
            underlying_asset_id=underlying_asset_id,
            exchange_code=row[2],
            asset_type=row[3],
            asset_subtype=row[4],
            currency=row[5],
            name=row[6],
            description=row[7],
            sector=classification["sector"],
            industry=classification["industry"],
            country=classification["country"],
            region=row[11],
            size=row[12],
            market_cap=_float_or_none(row[13]),
            shares_outstanding=_float_or_none(row[14]),
            market_beta=_float_or_none(row[15]),
            latest_price=_float_or_none(row[16]),
        )

    def price_history(self, asset_id: str, limit: int) -> list[PricePointResponse]:
        self.get_asset(asset_id)
        rows = self.conn.execute(
            """
            SELECT date, COALESCE(adj_close, close)
            FROM (
                SELECT date, adj_close, close
                FROM asset_quote_daily
                WHERE asset_id = ?
                  AND COALESCE(adj_close, close) IS NOT NULL
                ORDER BY date DESC
                LIMIT ?
            )
            ORDER BY date
            """,
            [asset_id.upper().strip(), limit],
        ).fetchall()
        return [PricePointResponse(date=row[0], close=float(row[1])) for row in rows]

    def analytics(self, asset_id: str, benchmark_index_id: str | None = None):
        asset = self.get_asset(asset_id)
        report = AnalyticsEngine(AnalyticsRepository(self.conn)).asset_report(
            asset_id=asset.asset_id,
            benchmark_index_id=benchmark_index_id,
        )
        return analytics_report_payload(report)


class ComparisonApiService:
    def __init__(self, conn) -> None:
        self.conn = conn

    def compare(
        self,
        left_asset_id: str,
        right_asset_id: str | None = None,
        benchmark_index_id: str | None = None,
    ) -> ComparisonResponse:
        left = self.asset_profile(left_asset_id)
        right = self.asset_profile(right_asset_id) if right_asset_id else None
        benchmark = self.benchmark_profile(benchmark_index_id) if benchmark_index_id else None
        return ComparisonResponse(
            left=left,
            right=right,
            benchmark=benchmark,
            insights=self._insights(left, right, benchmark),
        )

    def asset_profile(self, asset_id: str) -> ComparisonAssetProfile:
        asset = AssetApiService(self.conn).get_asset(asset_id)
        prices = self._prices(asset.asset_id)
        latest_price = prices[0][1] if prices else asset.latest_price
        statements = self._income_statements(asset.asset_id)
        latest_statement = statements[0] if statements else {}
        eps = _first_number(latest_statement, "eps", "epsdiluted", "dilutedEPS", "eps_actual")
        revenue = _first_number(latest_statement, "revenue", "totalRevenue", "revenue_actual")
        net_income = _first_number(latest_statement, "netIncome", "net_income", "netIncomeCommonStockholders")
        pe_ratio = latest_price / eps if latest_price is not None and eps and eps > 0 else None
        price_to_sales = (
            asset.market_cap / revenue
            if asset.market_cap is not None and revenue is not None and revenue > 0
            else None
        )
        valuation = self._valuation_context(asset.asset_id, asset.sector, asset.industry, pe_ratio)
        return ComparisonAssetProfile(
            asset_id=asset.asset_id,
            symbol=asset.symbol,
            name=asset.name,
            sector=asset.sector,
            industry=asset.industry,
            country=asset.country,
            currency=asset.currency,
            latest_price=latest_price,
            market_cap=asset.market_cap,
            market_beta=asset.market_beta,
            returns=ComparisonReturns(
                return_1d=_period_return(prices, 1),
                return_5d=_period_return(prices, 5),
                return_21d=_period_return(prices, 21),
                return_252d=_period_return(prices, 252),
            ),
            fundamentals=ComparisonFundamentals(
                revenue=revenue,
                net_income=net_income,
                eps=eps,
                pe_ratio=pe_ratio,
                price_to_sales=price_to_sales,
            ),
            valuation=valuation,
        )

    def benchmark_profile(self, index_id: str) -> BenchmarkComparisonProfile:
        row = self.conn.execute(
            """
            SELECT
                b.index_id,
                b.index_name,
                b.index_category,
                b.currency,
                m.return_1d,
                m.return_21d,
                m.return_252d,
                m.volatility_252d_ann
            FROM benchmark_index b
            LEFT JOIN benchmark_index_daily_metric m ON m.index_id = b.index_id
            WHERE UPPER(b.index_id) = UPPER(?)
            QUALIFY ROW_NUMBER() OVER (PARTITION BY b.index_id ORDER BY m.metric_date DESC NULLS LAST) = 1
            """,
            [index_id.strip()],
        ).fetchone()
        if row is None:
            raise LookupError(f"Benchmark not found: {index_id}")
        return BenchmarkComparisonProfile(
            index_id=row[0],
            name=row[1],
            category=row[2],
            currency=row[3],
            return_1d=_float_or_none(row[4]),
            return_21d=_float_or_none(row[5]),
            return_252d=_float_or_none(row[6]),
            volatility_252d=_float_or_none(row[7]),
        )

    def _prices(self, asset_id: str) -> list[tuple[Any, float]]:
        rows = self.conn.execute(
            """
            SELECT date, COALESCE(adj_close, close)
            FROM asset_quote_daily
            WHERE asset_id = ?
              AND COALESCE(adj_close, close) IS NOT NULL
            ORDER BY date DESC
            LIMIT 260
            """,
            [asset_id],
        ).fetchall()
        return [(row[0], float(row[1])) for row in rows]

    def _income_statements(self, asset_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT period_end_date, data_json
            FROM financial_statement
            WHERE asset_id = ?
              AND statement_type = 'income'
            ORDER BY period_end_date DESC NULLS LAST, year DESC, quarter DESC
            """,
            [asset_id],
        ).fetchall()
        statements: list[dict[str, Any]] = []
        for period_end, payload in rows:
            data = _json_dict(payload)
            if data:
                data["_period_end_date"] = period_end
                statements.append(data)
        return statements

    def _valuation_context(
        self,
        asset_id: str,
        sector: str | None,
        industry: str | None,
        current_pe: float | None,
    ) -> ValuationContext:
        historical_average = self._historical_pe_average(asset_id)
        sector_average = self._peer_pe_average(asset_id, "sector", sector)
        industry_average = self._peer_pe_average(asset_id, "industry", industry)
        return ValuationContext(
            historical_pe_average=historical_average,
            historical_pe_discount=_relative_gap(current_pe, historical_average),
            sector_pe_average=sector_average,
            sector_pe_premium=_relative_gap(current_pe, sector_average),
            industry_pe_average=industry_average,
            industry_pe_premium=_relative_gap(current_pe, industry_average),
        )

    def _historical_pe_average(self, asset_id: str) -> float | None:
        values: list[float] = []
        for statement in self._income_statements(asset_id):
            eps = _first_number(statement, "eps", "epsdiluted", "dilutedEPS", "eps_actual")
            period_end = statement.get("_period_end_date")
            if eps is None or eps <= 0 or period_end is None:
                continue
            price_row = self.conn.execute(
                """
                SELECT COALESCE(adj_close, close)
                FROM asset_quote_daily
                WHERE asset_id = ?
                  AND date <= ?
                  AND COALESCE(adj_close, close) IS NOT NULL
                ORDER BY date DESC
                LIMIT 1
                """,
                [asset_id, period_end],
            ).fetchone()
            if price_row:
                values.append(float(price_row[0]) / eps)
        return sum(values) / len(values) if values else None

    def _peer_pe_average(self, asset_id: str, field: str, value: str | None) -> float | None:
        if not value:
            return None
        rows = self.conn.execute(
            f"""
            SELECT a.asset_id
            FROM asset a
            WHERE a.{field} = ?
              AND a.asset_id <> ?
            ORDER BY a.asset_id
            """,
            [value, asset_id],
        ).fetchall()
        ratios = [ratio for ratio in (self._current_pe(row[0]) for row in rows) if ratio is not None]
        return sum(ratios) / len(ratios) if ratios else None

    def _current_pe(self, asset_id: str) -> float | None:
        prices = self._prices(asset_id)
        latest_price = prices[0][1] if prices else None
        statements = self._income_statements(asset_id)
        eps = _first_number(statements[0], "eps", "epsdiluted", "dilutedEPS", "eps_actual") if statements else None
        return latest_price / eps if latest_price is not None and eps and eps > 0 else None

    def _insights(
        self,
        left: ComparisonAssetProfile,
        right: ComparisonAssetProfile | None,
        benchmark: BenchmarkComparisonProfile | None,
    ) -> list[str]:
        insights: list[str] = []
        discount = left.valuation.historical_pe_discount
        if discount is not None:
            direction = "below" if discount < 0 else "above"
            insights.append(f"{left.symbol} trades {abs(discount) * 100:.1f}% {direction} its historical P/E average.")
        sector_gap = left.valuation.sector_pe_premium
        if sector_gap is not None and left.sector:
            direction = "above" if sector_gap > 0 else "below"
            insights.append(f"{left.symbol} trades {abs(sector_gap) * 100:.1f}% {direction} the {left.sector} peer average.")
        if right and left.returns.return_21d is not None and right.returns.return_21d is not None:
            gap = left.returns.return_21d - right.returns.return_21d
            direction = "outperformed" if gap >= 0 else "underperformed"
            insights.append(f"{left.symbol} {direction} {right.symbol} by {abs(gap) * 100:.1f}% over 21 trading days.")
        if benchmark and left.returns.return_252d is not None and benchmark.return_252d is not None:
            gap = left.returns.return_252d - benchmark.return_252d
            direction = "beat" if gap >= 0 else "lagged"
            insights.append(f"{left.symbol} {direction} {benchmark.index_id} by {abs(gap) * 100:.1f}% over 252 trading days.")
        return insights


class CommandApiService(BrokerCommands, IngestionCommands):
    """Reuse command orchestration without coupling HTTP routes to the CLI manager."""

    def __init__(self, conn) -> None:
        self.conn = conn

    def broker_connections(self) -> list[BrokerConnectionResponse]:
        return [
            BrokerConnectionResponse(
                provider=item.provider,
                connection_id=item.connection_id,
                provider_connection_id=item.provider_connection_id,
                institution_name=item.institution_name,
                status=item.status,
            )
            for item in BrokerSyncRepository(self.conn).list_connections()
        ]

    def broker_account_responses(self) -> list[BrokerAccountResponse]:
        position_values = self._broker_account_position_values()
        responses: list[BrokerAccountResponse] = []
        for item in self.broker_accounts():
            if not _is_visible_broker_account(item.raw_payload):
                continue
            position_value, position_currency = position_values.get(
                item.provider_account_id,
                (None, None),
            )
            currency = item.currency or _currency_from_raw_account(item.raw_payload) or position_currency
            responses.append(
                BrokerAccountResponse(
                    provider=item.provider,
                    provider_account_id=item.provider_account_id,
                    provider_connection_id=item.provider_connection_id,
                    account_name=item.account_name,
                    account_type=item.account_type,
                    currency=_valid_currency(currency),
                    balance=self._account_display_balance(
                        item.balance,
                        position_value,
                    ),
                    portfolio_id=item.portfolio_id,
                )
            )
        return responses

    def _broker_account_position_values(self) -> dict[str, tuple[float | None, str | None]]:
        rows = self.conn.execute(
            """
            WITH latest_positions AS (
                SELECT
                    provider,
                    provider_account_id,
                    provider_position_id,
                    MAX(as_of_date) AS as_of_date
                FROM broker_position_snapshot
                GROUP BY provider, provider_account_id, provider_position_id
            )
            SELECT
                p.provider_account_id,
                SUM(p.market_value) FILTER (WHERE p.market_value IS NOT NULL) AS market_value,
                MAX(p.currency) FILTER (WHERE p.currency IS NOT NULL) AS currency
            FROM broker_position_snapshot p
            JOIN latest_positions latest
              ON latest.provider = p.provider
             AND latest.provider_account_id = p.provider_account_id
             AND latest.provider_position_id = p.provider_position_id
             AND latest.as_of_date = p.as_of_date
            WHERE p.provider = ?
            GROUP BY p.provider_account_id
            """,
            [SNAPTRADE_PROVIDER],
        ).fetchall()
        return {row[0]: (_float_or_none(row[1]), row[2]) for row in rows}

    @staticmethod
    def _account_display_balance(
        account_balance: float | None,
        position_value: float | None,
    ) -> float | None:
        if position_value is not None and (account_balance is None or account_balance == 0):
            return position_value
        return account_balance

    def register_broker_user(self, user_key: str) -> BrokerUserResponse:
        user = self.broker_register_snaptrade_user(user_key)
        return BrokerUserResponse(
            provider=user.provider,
            user_key=user.user_key,
            provider_user_id=user.provider_user_id,
            status=user.status,
        )

    def save_existing_broker_user(
        self,
        user_key: str,
        provider_user_id: str,
        user_secret: str,
    ) -> BrokerUserResponse:
        user = BrokerUser(
            provider=SNAPTRADE_PROVIDER,
            user_key=user_key.strip(),
            provider_user_id=provider_user_id.strip(),
            user_secret=user_secret.strip(),
            status="active",
        )
        if not user.user_key or not user.provider_user_id or not user.user_secret:
            raise ValueError("User key, provider user ID, and user secret are required.")
        repo, cipher = self._broker_repo_and_cipher()
        repo.upsert_broker_user(user, cipher)
        return BrokerUserResponse(
            provider=user.provider,
            user_key=user.user_key,
            provider_user_id=user.provider_user_id,
            status=user.status,
        )

    def ingestion_jobs(self, status: str | None, domain: str | None, limit: int):
        statuses = [status] if status else None
        rows = self.list_ingestion_jobs(statuses=statuses, domain=domain, limit=limit)
        return [
            IngestionJobResponse(
                job_id=int(row[0]),
                asset_id=row[1],
                domain=row[2],
                job_type=row[3],
                dataset=row[4],
                status=row[5],
                priority=int(row[6]),
                requested_start_date=row[7],
                requested_end_date=row[8],
                attempt_count=int(row[9]),
                error_message=row[10],
                created_at=row[11],
                updated_at=row[12],
            )
            for row in rows
        ]

    def retry_failed_ingestion_jobs(self, domain: str | None, max_jobs: int) -> int:
        where = ["status = 'failed'"]
        params: list[object] = []
        if domain:
            where.append("domain = ?")
            params.append(domain)
        params.append(max_jobs)
        rows = self.conn.execute(
            f"""
            UPDATE ingestion_job
            SET
                status = 'pending',
                error_message = NULL,
                updated_at = now()
            WHERE job_id IN (
                SELECT job_id
                FROM ingestion_job
                WHERE {" AND ".join(where)}
                ORDER BY updated_at ASC, job_id ASC
                LIMIT ?
            )
            RETURNING job_id
            """,
            params,
        ).fetchall()
        return len(rows)

    @staticmethod
    def action_result(value) -> dict:
        if hasattr(value, "__dataclass_fields__"):
            return asdict(value)
        if isinstance(value, dict):
            return value
        return {"count": value} if isinstance(value, int) else {"value": value}


def _float_or_none(value) -> float | None:
    return float(value) if value is not None else None


def _cdr_classification_override(
    *,
    asset_id: str,
    symbol: str,
    name: str | None,
    sector: str | None,
    industry: str | None,
    country: str | None,
) -> dict[str, str | None]:
    base_symbol = _cdr_base_symbol(asset_id, symbol, name)
    override = _CDR_CLASSIFICATION_OVERRIDES.get(base_symbol)
    if not override:
        return {"sector": sector, "industry": industry, "country": country}
    return {
        "sector": sector or override["sector"],
        "industry": industry or override["industry"],
        "country": override["country"] if country is None or country.upper() == "CA" else country,
    }


def _cdr_base_symbol(asset_id: str, symbol: str, name: str | None) -> str:
    candidate = symbol or asset_id
    base = candidate.split(".", maxsplit=1)[0].upper()
    base = _CDR_SYMBOL_ALIASES.get(base, base)
    if base in _CDR_CLASSIFICATION_OVERRIDES and _looks_like_cdr_listing(asset_id, symbol, name):
        return base
    text = f"{asset_id} {symbol} {name or ''}".lower()
    if "cdr" not in text and "depositary receipt" not in text:
        return ""
    return base


def _looks_like_cdr_listing(asset_id: str, symbol: str, name: str | None) -> bool:
    text = f"{asset_id} {symbol} {name or ''}".lower()
    if "cdr" in text or "depositary receipt" in text or "depository receipt" in text:
        return True
    return (symbol or asset_id).upper().endswith(".TO")


def _cdr_underlying_asset_id(asset_id: str, symbol: str, name: str | None) -> str | None:
    base_symbol = _cdr_base_symbol(asset_id, symbol, name)
    return base_symbol or None


def _known_underlying_asset_detail(asset_id: str) -> AssetDetail | None:
    classification = _CDR_CLASSIFICATION_OVERRIDES.get(asset_id)
    if classification is None:
        return None
    return AssetDetail(
        asset_id=asset_id,
        symbol=asset_id,
        is_cdr=False,
        underlying_asset_id=None,
        exchange_code=None,
        asset_type="stock",
        asset_subtype=None,
        currency="USD",
        name=_KNOWN_CDR_UNDERLYING_NAMES.get(asset_id),
        description=None,
        sector=classification["sector"],
        industry=classification["industry"],
        country=classification["country"],
        region=None,
        size=None,
        market_cap=None,
        shares_outstanding=None,
        market_beta=None,
        latest_price=None,
    )


def _json_dict(value) -> dict[str, Any]:
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
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            continue
    return None


def _period_return(prices: list[tuple[Any, float]], periods: int) -> float | None:
    if len(prices) <= periods:
        return None
    latest = prices[0][1]
    previous = prices[periods][1]
    if previous == 0:
        return None
    return latest / previous - 1


def _relative_gap(value: float | None, comparison: float | None) -> float | None:
    if value is None or comparison is None or comparison == 0:
        return None
    return value / comparison - 1


def _currency_from_raw_account(raw_payload: dict) -> str | None:
    balance = raw_payload.get("balance")
    if not isinstance(balance, dict):
        return None
    total = balance.get("total")
    if isinstance(total, dict):
        currency = total.get("currency")
        if currency:
            return str(currency)
    currency = balance.get("currency")
    return str(currency) if currency else None


def _is_visible_broker_account(raw_payload: dict) -> bool:
    status = str(raw_payload.get("status", "")).strip().lower()
    if status in {"archived", "closed", "disabled", "inactive"}:
        return False
    if raw_payload.get("closed") is True or raw_payload.get("disabled") is True:
        return False
    return True


def _valid_currency(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text if len(text) == 3 and text.isalpha() else None
