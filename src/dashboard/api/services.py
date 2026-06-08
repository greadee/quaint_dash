"""Application-facing read and write services for the HTTP API."""

from dataclasses import asdict

from dashboard.api.models import (
    AssetDetail,
    BrokerAccountResponse,
    BrokerConnectionResponse,
    BrokerUserResponse,
    IngestionJobResponse,
    NewsItemResponse,
    OverviewUpdatesResponse,
    Page,
    PortfolioCreate,
    PortfolioSummary,
    PositionSummary,
    PricePointResponse,
    PriceMoverResponse,
    TransactionSummary,
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

    def list_positions(self, portfolio_id: int | None = None) -> list[PositionSummary]:
        if portfolio_id is not None:
            self.get_portfolio(portfolio_id)
            where = "WHERE portfolio_id = ?"
            params: list[object] = [portfolio_id]
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
                a.sector,
                a.industry,
                a.country,
                a.ccy,
                lp.price,
                COALESCE(h.quantity * lp.price, h.book_cost) AS market_value
                FROM holdings h
                JOIN asset a ON a.asset_id = h.asset_id
                LEFT JOIN latest_prices lp ON lp.asset_id = h.asset_id
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
        return [
            PositionSummary(
                asset_id=row[0],
                symbol=row[1],
                name=row[2],
                asset_type=row[3],
                sector=row[4],
                industry=row[5],
                country=row[6],
                currency=row[7],
                quantity=float(row[8]),
                book_cost=float(row[9]),
                latest_price=_float_or_none(row[10]),
                market_value=_float_or_none(row[11]),
                unrealized_gain=_float_or_none(row[12]),
                weight=_float_or_none(row[13]),
            )
            for row in rows
        ]

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


class AssetApiService:
    def __init__(self, conn) -> None:
        self.conn = conn

    def get_asset(self, asset_id: str) -> AssetDetail:
        asset_id = asset_id.upper().strip()
        row = self.conn.execute(
            """
            SELECT
                a.asset_id,
                COALESCE(a.symbol, a.asset_id),
                a.exchange_code,
                a.asset_type,
                a.asset_subtype,
                a.ccy,
                a.name,
                a.description,
                a.sector,
                a.industry,
                a.country,
                a.region,
                a.size,
                a.mkt_cap,
                a.shares_outstanding,
                a.market_beta,
                (
                    SELECT COALESCE(q.adj_close, q.close)
                    FROM asset_quote_daily q
                    WHERE q.asset_id = a.asset_id
                    ORDER BY q.date DESC
                    LIMIT 1
                )
            FROM asset a
            WHERE a.asset_id = ?
            """,
            [asset_id],
        ).fetchone()
        if row is None:
            raise LookupError(f"Asset not found: {asset_id}")
        return AssetDetail(
            asset_id=row[0],
            symbol=row[1],
            exchange_code=row[2],
            asset_type=row[3],
            asset_subtype=row[4],
            currency=row[5],
            name=row[6],
            description=row[7],
            sector=row[8],
            industry=row[9],
            country=row[10],
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
