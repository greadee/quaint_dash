"""Application-facing read and write services for the HTTP API."""

from dashboard.api.models import (
    Page,
    PortfolioCreate,
    PortfolioSummary,
    PositionSummary,
    TransactionSummary,
)


class PortfolioApiService:
    def __init__(self, conn) -> None:
        self.conn = conn

    def list_portfolios(self) -> list[PortfolioSummary]:
        rows = self.conn.execute(
            """
            WITH holdings AS (
                SELECT portfolio_id, asset_id, SUM(qty) AS quantity, SUM(qty * price) AS book_cost
                FROM txn
                WHERE asset_id IS NOT NULL AND txn_type IN ('buy', 'sell')
                GROUP BY portfolio_id, asset_id
            ),
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
                        SUM(h.quantity * lp.price) FILTER (WHERE h.quantity <> 0 AND lp.price IS NOT NULL),
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

    def list_positions(self, portfolio_id: int) -> list[PositionSummary]:
        self.get_portfolio(portfolio_id)
        rows = self.conn.execute(
            """
            WITH holdings AS (
                SELECT asset_id, SUM(qty) AS quantity, SUM(qty * price) AS book_cost
                FROM txn
                WHERE portfolio_id = ?
                  AND asset_id IS NOT NULL
                  AND txn_type IN ('buy', 'sell')
                GROUP BY asset_id
                HAVING SUM(qty) <> 0
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
                    a.ccy,
                    lp.price,
                    h.quantity * lp.price AS market_value
                FROM holdings h
                JOIN asset a ON a.asset_id = h.asset_id
                LEFT JOIN latest_prices lp ON lp.asset_id = h.asset_id
            )
            SELECT
                asset_id,
                COALESCE(symbol, asset_id),
                name,
                asset_type,
                ccy,
                quantity,
                book_cost,
                price,
                market_value,
                CASE WHEN price IS NULL THEN NULL ELSE market_value - book_cost END,
                CASE
                    WHEN price IS NULL OR SUM(market_value) OVER () = 0 THEN NULL
                    ELSE market_value / SUM(market_value) OVER ()
                END
            FROM valued
            ORDER BY market_value DESC NULLS LAST, asset_id
            """,
            [portfolio_id],
        ).fetchall()
        return [
            PositionSummary(
                asset_id=row[0],
                symbol=row[1],
                name=row[2],
                asset_type=row[3],
                currency=row[4],
                quantity=float(row[5]),
                book_cost=float(row[6]),
                latest_price=_float_or_none(row[7]),
                market_value=_float_or_none(row[8]),
                unrealized_gain=_float_or_none(row[9]),
                weight=_float_or_none(row[10]),
            )
            for row in rows
        ]

    def list_transactions(self, portfolio_id: int, limit: int, offset: int) -> Page[TransactionSummary]:
        self.get_portfolio(portfolio_id)
        total = int(
            self.conn.execute(
                "SELECT COUNT(*) FROM txn WHERE portfolio_id = ?",
                [portfolio_id],
            ).fetchone()[0]
        )
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
                fee_amt,
                batch_id
            FROM txn
            WHERE portfolio_id = ?
            ORDER BY time_stamp DESC, txn_id DESC
            LIMIT ? OFFSET ?
            """,
            [portfolio_id, limit, offset],
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

    @staticmethod
    def _portfolio_summary(row) -> PortfolioSummary:
        market_value = float(row[6])
        book_cost = float(row[7])
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
        )


def _float_or_none(value) -> float | None:
    return float(value) if value is not None else None
