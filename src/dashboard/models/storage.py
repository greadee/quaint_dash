"""~/models/
db wrapper

- DashboardManager: bridge between database and cli_view classes.
- PortfolioManager: only works for one portfolio, cannot be instantiated if DashboardManager has not been.
"""
from datetime import datetime
from dashboard.analytics import AnalyticsEngine, AnalyticsRepository, AnalyticsStorageService
from dashboard.db.db_conn import DB, init_db
from dashboard.db import queries as qry
from dashboard.models.domain import Portfolio, Position, Txn
from dashboard.services.table_formatter import TxnTableFormatter, PositionTableFormatter, PortfolioTableFormatter
from dashboard.ingestion.price_history.service import PriceHistoryIngestionService
from dashboard.ingestion.trading_calendar.service import TradingCalendarIngestionService
from dashboard.ingestion.corporate_calendar.service import CorporateCalendarIngestionService
from dashboard.ingestion.indices.index_service_factory import create_index_scheduler
from dashboard.ingestion.indices.index_service_factory import create_index_ingestion_service
from dashboard.ingestion.ticker_universe import TickerUniverseRepository
from datetime import date


class DashboardManager:
    """
    Creates and opens portfolios (multiple)
    """

    def __init__(self, db: DB):
        self.db = db
        self.conn = db.conn

    def open(self):
        """
        Runs the db initialization statements in schema.sql, returns nothing
        """
        init_db(self.db)

    def check_new_portfolio_id(self, name: str):
        id, created = self.conn.execute(qry.CHECK_NEW_PORTFOLIO_ID, [name],).fetchone()
        return id, created
    
    def upsert_portfolio(self, name: str, base_ccy: str = "CAD"):
        """
        User initiated version: Updates or creates a portfolio based on a name.
        - Uses MAX(id)+1 for new portfolios and returns created = true
        - Searches db for given name and returns created = false if found
        """
        id, created = self.check_new_portfolio_id(name)
        self.conn.execute(qry.UPSERT_PORTFOLIO_USER, [id, name, base_ccy],)
        return created
    
    def _upsert_portfolio_import(self, id: int, name: str, created_at: datetime, updated_at: datetime):
        """
        Import initiated version: Updates or creates a portfolio based on a name.
        - Uses MAX(id)+1 for new portfolios and returns created = true
        - Searches db for given name and returns created = false if found
        """
        _, created = self.check_new_portfolio_id(name)
        self.conn.execute(qry.UPSERT_PORTFOLIO_IMPORT, [id, name, created_at, updated_at],)
        return created

    def open_portfolio_by_id(self, id: int):
        """
        Checks DB for existence of a portfolio by the same name as the parameter id
        If not exists, raises a ValueError
        If exists, returns a PortfolioStore object for the portfolio that was found
        """
        row = self.conn.execute(qry.GET_PORTFOLIO_BY_ID, [id],).fetchone()
        if not row:
            raise ValueError(f"Portfolio not found: {id}")
        return PortfolioManager(self.db, id, row[0])

    def open_portfolio_by_name(self, name: str):
        """
        Checks DB for existence of a portfolio by the same name as the parameter name
        If not exists, raises a ValueError
        If exists, returns a PortfolioStore object for the portfolio that was found        
        """
        row = self.conn.execute(qry.GET_PORTFOLIO_BY_NAME, [name],).fetchone()
        if not row:
            raise ValueError(f"Portfolio not found: {name}")
        return PortfolioManager(self.db, row[0], name)
    
    def upsert_asset(self, asset_id: str, asset_type: str, asset_subtype: str, ccy: str):
        """
        Add/update an asset in the database
        Returns None
        """
        normalized_asset_id = asset_id.upper().strip()
        self.conn.execute(
            qry.UPSERT_ASSET,
            [normalized_asset_id, normalized_asset_id, asset_type, asset_subtype, ccy],
        )

    def update_positions(self):
        """
        Refresh the (derived) position table. 
        - To be used prior to any position access. 
        """
        self.conn.execute(qry.UPDATE_POSITIONS)
        TickerUniverseRepository(self.conn).sync_portfolio_tickers_from_positions()

    def list_portfolios(self, N:int|None):
        """
        List all portfolios in database.
        - Instantiates a Portfolio object for each row returned by the db query.
        - Calls Formatter class to return a string representing a table row.
        - Optional argument (N) determines how many rows to display.
        Returns None.        
        """
        rows = self.conn.execute(qry.LIST_PORTFOLIOS).fetchall()
        if not rows: 
            raise ValueError("No portfolios found.")

        PortfolioTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            PortfolioTableFormatter(Portfolio(*row)).entry()

    def list_txns(self, N:int|None):
        """
        List all transactions in database.
        - Instantiates a Txn object for each row returned by the db query.
        - Calls Formatter class to return a string representing a table row.
        - Optional argument (N) determines how many rows to display.
        Returns None.        
        """
        rows = self.conn.execute(f"{qry.LIST_TXNS};").fetchall()
        if not rows: 
            raise ValueError("No transactions found.")

        TxnTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            TxnTableFormatter(Txn(*row)).entry()
    

    #############################################################################################################################

    # err - out: "string indices must be integers, not 'tuple'\n"

    def list_txns_by_type(self, txn_type:str, N:int|None):
        """
        List all transactions in database filtered by txn_type.
        - Instantiates a Txn object for each row returned by the db query.
        - Calls Formatter class to return a string representing a table row.
        - Optional argument (N) determines how many rows to display.
        Returns None.        
        """
        rows = self.conn.execute(f"{qry.LIST_TXNS_BY_TYPE};", [txn_type],).fetchall()
        if not rows: 
            raise ValueError(f"No transactions found with type: {txn_type}.")
        
        TxnTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            TxnTableFormatter(Txn(*row)).entry()

    #############################################################################################################################

    def list_txns_by_day(self, date_str: str, N:int|None):
        # normalize date_str into a datetime object.
        for fmt in ("%m-%d-%Y", "%m/%d/%Y"):
            try:
                date = datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue
        else:
            raise AttributeError(f"Date {date_str} invalid. Please enter in (MM-DD-YYYY) or (MM/DD/YYYY) format.")
        
        rows = self.conn.execute(f"{qry.LIST_TXNS_BY_DAY};", [date],).fetchall()
        if not rows: 
            raise ValueError(f"No transactions found on: {date.strftime('%m/%d/%Y')}.")
        
        TxnTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            TxnTableFormatter(Txn(*row)).entry()

    def list_txns_by_asset(self, asset_id:str, N:int|None):
        """
        List all transactions in database filtered by asset_id.
        - Instantiates a Txn object for each row returned by the db query.
        - Calls Formatter class to return a string representing a table row.
        - Optional argument (N) determines how many rows to display.
        Returns None.        
        """
        rows = self.conn.execute(f"{qry.LIST_TXNS_BY_ASSET};", [asset_id],).fetchall()
        if not rows: 
            raise ValueError(f"No transactions found with asset: {asset_id}")

        TxnTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            TxnTableFormatter(Txn(*row)).entry()

    def list_positions(self, N:int|None):
        """
        List all positions in database.
        - Instantiates a Position object for each row returned by the db query, or raises a ValueError if the result is empty.
        - Casts Position into PositionTableFormatter for display.
        - Optional argument (N) determines how many rows to display.
        Returns None.          
        """
        rows = self.conn.execute(f"{qry.LIST_POSITIONS};").fetchall()
        if not rows: 
            raise ValueError("No positions found.")
        
        PositionTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            PositionTableFormatter(Position(*row)).entry()
     
    def list_positions_by_asset(self, asset_id:str, N:None|int):
        """
        List all positions in database filtered by asset_id.
        - Instantiates a Position object for each row returned by the db query, or raises a ValueError if the result is empty.
        - Calls Position method .display_str() to return a string representing a table row.
        - Optional argument (N) determines how many rows to display.
        Returns None.          
        """
        rows = self.conn.execute(f"{qry.LIST_POSITIONS_BY_ASSET_ID};", [asset_id],).fetchall()
        if not rows: 
            raise ValueError(f"No positions found with asset id: {asset_id}")
        
        PositionTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            PositionTableFormatter(Position(*row)).entry()
    
    def list_positions_by_type(self, asset_type: str, N:int|None):
        """
        List all positions in database filtered by asset_type.
        - Instantiates a Position object for each row returned by the db query, or raises a ValueError if the result is empty.
        - Calls Position method .display_str() to return a string representing a table row.
        - Optional argument (N) determines how many rows to display.
        Returns None.          
        """
        rows = self.conn.execute(f"{qry.LIST_POSITIONS_BY_ASSET_TYPE};", [asset_type],).fetchall()
        if not rows: 
            raise ValueError(f"No positions found with asset type: {asset_type}")
        
        PositionTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            PositionTableFormatter(Position(*row)).entry()

    def list_positions_by_asset_size(self, asset_size:str, N:int|None):
        """
        List all positions in database filtered by asset_size.
        - Instantiates a Position object for each row returned by the db query, or raises a ValueError if the result is empty.
        - Calls Position method .display_str() to return a string representing a table row.
        - Optional argument (N) determines how many rows to display.
        Returns None.          
        """
        rows = self.conn.execute(f"{qry.LIST_POSITIONS_BY_ASSET_SIZE};", [asset_size],).fetchall()
        if not rows: 
            raise ValueError(f"No positions found with asset subtype: {asset_size}")
        
        PositionTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            PositionTableFormatter(Position(*row)).entry()


    #######################################################################
    ##              analytics reports and optional storage
    #######################################################################

    def asset_analytics_report(self, asset_id: str, benchmark_index_id: str | None = None):
        """
        Build an analytics report for one asset using already stored data.
        """
        repo = AnalyticsRepository(self.conn)
        return AnalyticsEngine(repo).asset_report(
            asset_id=asset_id,
            benchmark_index_id=benchmark_index_id,
        )

    def portfolio_analytics_report(self, portfolio_id: int, benchmark_index_id: str | None = None):
        """
        Build an analytics report for one portfolio using already stored data.
        """
        repo = AnalyticsRepository(self.conn)
        return AnalyticsEngine(repo).portfolio_report(
            portfolio_id=portfolio_id,
            benchmark_index_id=benchmark_index_id,
        )

    def analytics_storage_enabled(self) -> bool:
        repo = AnalyticsRepository(self.conn)
        if not repo._table_exists("analytics_storage_config"):
            return False
        row = self.conn.execute(
            """
            SELECT config_value
            FROM analytics_storage_config
            WHERE config_key = 'enabled'
            """
        ).fetchone()
        return bool(row and str(row[0]).lower() == "true")

    def set_analytics_storage_enabled(self, enabled: bool) -> None:
        AnalyticsStorageService(
            self.conn,
            enabled=self.analytics_storage_enabled(),
        ).set_enabled(enabled)

    def refresh_analytics_storage(
        self,
        asset_ids: list[str] | None = None,
        portfolio_ids: list[int] | None = None,
        benchmark_index_id: str | None = None,
    ):
        return AnalyticsStorageService(
            self.conn,
            enabled=self.analytics_storage_enabled(),
            benchmark_index_id=benchmark_index_id,
        ).refresh_due(
            asset_ids=asset_ids,
            portfolio_ids=portfolio_ids,
        )

    #######################################################################
    ##              read-only broker account linking
    #######################################################################

    def broker_register_snaptrade_user(
        self,
        user_key: str,
        provider_user_id: str | None = None,
    ):
        """
        Register and store a SnapTrade user for read-only broker linking.
        """
        from dashboard.brokers.repository import BrokerSyncRepository
        from dashboard.brokers.snaptrade import SnapTradeProvider

        user_key = user_key.strip()
        provider_user_id = provider_user_id.strip() if provider_user_id else user_key
        if not user_key:
            raise ValueError("Broker user key is required.")

        provider = SnapTradeProvider(self._snaptrade_config())
        user = provider.register_user(provider_user_id)
        user = type(user)(
            provider=user.provider,
            user_key=user_key,
            provider_user_id=user.provider_user_id,
            user_secret=user.user_secret,
            status=user.status,
        )
        BrokerSyncRepository(self.conn).upsert_broker_user(user, self._broker_secret_cipher())
        return user

    def broker_snaptrade_portal(
        self,
        user_key: str,
        broker: str | None = None,
        custom_redirect: str | None = None,
        immediate_redirect: bool = False,
        register_if_missing: bool = False,
        reconnect: str | None = None,
    ):
        """
        Create a SnapTrade hosted portal URL with read-only account permissions.
        """
        from dashboard.brokers.repository import BrokerSyncRepository
        from dashboard.brokers.snaptrade import SNAPTRADE_PROVIDER, SnapTradeProvider

        user_key = user_key.strip()
        if not user_key:
            raise ValueError("Broker user key is required.")

        repo = BrokerSyncRepository(self.conn)
        cipher = self._broker_secret_cipher()
        user = repo.get_broker_user(SNAPTRADE_PROVIDER, user_key, cipher)
        if user is None:
            if not register_if_missing:
                raise ValueError(
                    "No SnapTrade user found. Run broker snaptrade register-user first, "
                    "or pass --register-if-missing."
                )
            user = self.broker_register_snaptrade_user(user_key)

        provider = SnapTradeProvider(self._snaptrade_config())
        return provider.create_connection_portal(
            user,
            broker=broker,
            custom_redirect=custom_redirect,
            immediate_redirect=immediate_redirect,
            reconnect=reconnect,
        )

    def broker_snaptrade_rotate_secret(self, user_key: str):
        from dashboard.brokers.repository import BrokerSyncRepository
        from dashboard.brokers.snaptrade import SNAPTRADE_PROVIDER, SnapTradeProvider

        repo = BrokerSyncRepository(self.conn)
        cipher = self._broker_secret_cipher()
        user = repo.get_broker_user(SNAPTRADE_PROVIDER, user_key.strip(), cipher)
        if user is None:
            raise ValueError(f"No SnapTrade user found: {user_key}")
        rotated = SnapTradeProvider(self._snaptrade_config()).rotate_user_secret(user)
        repo.upsert_broker_user(rotated, cipher)
        return rotated

    def broker_snaptrade_unlink_user(self, user_key: str, delete_provider_user: bool = False):
        from dashboard.brokers.repository import BrokerSyncRepository
        from dashboard.brokers.snaptrade import SNAPTRADE_PROVIDER, SnapTradeProvider

        repo = BrokerSyncRepository(self.conn)
        cipher = self._broker_secret_cipher()
        user = repo.get_broker_user(SNAPTRADE_PROVIDER, user_key.strip(), cipher)
        if user is None:
            raise ValueError(f"No SnapTrade user found: {user_key}")
        provider_response = None
        if delete_provider_user:
            provider_response = SnapTradeProvider(self._snaptrade_config()).delete_user(user)
        repo.update_broker_user_status(SNAPTRADE_PROVIDER, user.user_key, "unlinked")
        return provider_response

    def broker_snaptrade_disable_connection(self, user_key: str, provider_connection_id: str):
        from dashboard.brokers.models import BrokerConnection
        from dashboard.brokers.repository import BrokerSyncRepository
        from dashboard.brokers.snaptrade import SNAPTRADE_PROVIDER, SnapTradeProvider

        repo = BrokerSyncRepository(self.conn)
        cipher = self._broker_secret_cipher()
        user = repo.get_broker_user(SNAPTRADE_PROVIDER, user_key.strip(), cipher)
        if user is None:
            raise ValueError(f"No SnapTrade user found: {user_key}")
        connection = BrokerConnection(
            provider=SNAPTRADE_PROVIDER,
            provider_connection_id=provider_connection_id.strip(),
            institution_name="unknown",
            status="unknown",
            provider_user_id=user.provider_user_id,
        )
        SnapTradeProvider(self._snaptrade_config()).disconnect(user, connection)
        repo.update_connection_status(
            SNAPTRADE_PROVIDER,
            provider_connection_id.strip(),
            "disabled",
        )

    def broker_snaptrade_smoke_test(self, user_key: str | None = None):
        from dashboard.brokers.models import BrokerSmokeTestResult
        from dashboard.brokers.repository import BrokerSyncRepository
        from dashboard.brokers.snaptrade import SNAPTRADE_PROVIDER, SnapTradeError, SnapTradeProvider

        try:
            provider = SnapTradeProvider(self._snaptrade_config())
            status = provider.api_status()
            api_online = bool(status.get("online", True))
        except Exception as exc:
            return BrokerSmokeTestResult(
                provider=SNAPTRADE_PROVIDER,
                api_online=False,
                configured=False,
                user_found=False,
                message=str(exc),
            )

        user_found = False
        if user_key:
            try:
                user_found = (
                    BrokerSyncRepository(self.conn).get_broker_user(
                        SNAPTRADE_PROVIDER,
                        user_key.strip(),
                        self._broker_secret_cipher(),
                    )
                    is not None
                )
            except (SnapTradeError, ValueError) as exc:
                return BrokerSmokeTestResult(
                    provider=SNAPTRADE_PROVIDER,
                    api_online=api_online,
                    configured=True,
                    user_found=False,
                    message=str(exc),
                )

        return BrokerSmokeTestResult(
            provider=SNAPTRADE_PROVIDER,
            api_online=api_online,
            configured=True,
            user_found=user_found,
            message="snaptrade credentials are reachable",
        )

    def broker_snaptrade_sync(
        self,
        user_key: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ):
        from dashboard.brokers.repository import BrokerSyncRepository
        from dashboard.brokers.snaptrade import SnapTradeProvider
        from dashboard.brokers.sync import BrokerSyncService

        service = BrokerSyncService(
            BrokerSyncRepository(self.conn),
            SnapTradeProvider(self._snaptrade_config()),
            self._broker_secret_cipher(),
        )
        return service.sync_user(
            user_key.strip(),
            start_date=self._broker_parse_date(start_date),
            end_date=self._broker_parse_date(end_date),
        )

    def broker_snaptrade_sync_due(
        self,
        max_users: int | None = None,
        min_age_hours: int = 24,
        force: bool = False,
    ):
        from dashboard.brokers.repository import BrokerSyncRepository
        from dashboard.brokers.scheduler import BrokerSyncScheduler
        from dashboard.brokers.snaptrade import SnapTradeProvider

        scheduler = BrokerSyncScheduler(
            BrokerSyncRepository(self.conn),
            SnapTradeProvider(self._snaptrade_config()),
            self._broker_secret_cipher(),
        )
        return scheduler.sync_due_users(
            max_users=max_users,
            min_age_hours=min_age_hours,
            force=force,
        )

    def broker_accounts(self, provider: str = "snaptrade"):
        from dashboard.brokers.repository import BrokerSyncRepository

        return BrokerSyncRepository(self.conn).list_accounts(provider)

    def broker_map_account(
        self,
        provider_account_id: str,
        portfolio_id: int,
        provider: str = "snaptrade",
    ) -> None:
        if not self.conn.execute(
            "SELECT 1 FROM portfolio WHERE portfolio_id = ?",
            [portfolio_id],
        ).fetchone():
            raise ValueError(f"Portfolio not found: {portfolio_id}")
        from dashboard.brokers.repository import BrokerSyncRepository

        BrokerSyncRepository(self.conn).map_account_to_portfolio(
            provider,
            provider_account_id.strip(),
            portfolio_id,
        )

    def broker_import_transactions(
        self,
        provider: str = "snaptrade",
        portfolio_id: int | None = None,
    ):
        from dashboard.brokers.portfolio import BrokerPortfolioIntegrationService

        if portfolio_id is not None and not self.conn.execute(
            "SELECT 1 FROM portfolio WHERE portfolio_id = ?",
            [portfolio_id],
        ).fetchone():
            raise ValueError(f"Portfolio not found: {portfolio_id}")
        return BrokerPortfolioIntegrationService(self.conn).import_mapped_transactions(
            provider=provider,
            portfolio_id=portfolio_id,
        )

    def broker_raw_payload_storage_enabled(self) -> bool:
        from dashboard.brokers.repository import BrokerSyncRepository

        return BrokerSyncRepository(self.conn).raw_payload_storage_enabled()

    def set_broker_raw_payload_storage_enabled(self, enabled: bool) -> None:
        from dashboard.brokers.repository import BrokerSyncRepository

        BrokerSyncRepository(self.conn).set_raw_payload_storage_enabled(enabled)

    @staticmethod
    def _snaptrade_config():
        from dashboard.brokers.snaptrade import SnapTradeConfig

        return SnapTradeConfig.from_env()

    @staticmethod
    def _broker_secret_cipher():
        import os

        from dotenv import load_dotenv

        from dashboard.brokers.secrets import LocalSecretCipher

        load_dotenv()
        key = os.getenv("QUAINT_BROKER_SECRET_KEY")
        if not key:
            raise ValueError("QUAINT_BROKER_SECRET_KEY is required for broker secret storage.")
        return LocalSecretCipher(key)

    @staticmethod
    def _broker_parse_date(value: str | None):
        if value is None:
            return None
        for fmt in ("%Y-%m-%d", "%m-%d-%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Date {value} invalid. Use YYYY-MM-DD, MM-DD-YYYY, or MM/DD/YYYY.")


    #######################################################################
    ##              daily ingestion and historical backfill
    #######################################################################

    def enqueue_market_backfill(
        self,
        asset_id: str | None = None,
        years: int = 10,
        include_dividends: bool = True,
        include_splits: bool = True,
    ) -> int:
        """
        Enqueue Domain A market backfill jobs.

        If asset_id is None, enqueue jobs for all tracked assets.
        """
        service = PriceHistoryIngestionService(self.conn)

        if asset_id is None:
            job_ids = service.enqueue_backfill_all(
                years=years,
                include_dividends=include_dividends,
                include_splits=include_splits,
            )
        else:
            job_ids = service.enqueue_backfill_one(
                asset_id=asset_id.upper().strip(),
                years=years,
                include_dividends=include_dividends,
                include_splits=include_splits,
            )

        return len(job_ids)

    def enqueue_market_refresh(
        self,
        asset_id: str | None = None,
        include_dividends: bool = True,
        include_splits: bool = True,
    ) -> int:
        """
        Enqueue Domain A market refresh jobs.

        If asset_id is None, enqueue jobs for all tracked assets.
        """
        service = PriceHistoryIngestionService(self.conn)

        if asset_id is None:
            job_ids = service.enqueue_refresh_all(
                include_dividends=include_dividends,
                include_splits=include_splits,
            )
        else:
            job_ids = service.enqueue_refresh_one(
                asset_id=asset_id.upper().strip(),
                include_dividends=include_dividends,
                include_splits=include_splits,
            )

        return len(job_ids)

    def list_ingestion_jobs(
        self,
        statuses: list[str] | None = None,
        domain: str | None = None,
        limit: int | None = None,
    ):
        """
        Return ingestion jobs for dev inspection.
        """
        where = []
        params: list[object] = []

        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            where.append(f"status IN ({placeholders})")
            params.extend(statuses)

        if domain:
            where.append("domain = ?")
            params.append(domain)

        query = """
            SELECT
                job_id,
                asset_id,
                domain,
                job_type,
                dataset,
                status,
                priority,
                requested_start_date,
                requested_end_date,
                attempt_count,
                error_message,
                created_at,
                updated_at
            FROM ingestion_job
        """

        if where:
            query += " WHERE " + " AND ".join(where)

        query += " ORDER BY status, priority DESC, created_at ASC"

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        return self.conn.execute(query, params).fetchall()

    def schedule_ingestion_jobs(
        self,
        pipeline: str = "all",
        asset_id: str | None = None,
        max_assets: int = 25,
        years: int = 10,
        prices_only: bool = False,
        calendar_year: int | None = None,
    ) -> int:
        """
        Master scheduler for dev ingestion commands.
        """
        include_dividends = not prices_only
        include_splits = not prices_only
        pipeline = pipeline.replace("_", "-").lower()

        if asset_id is not None and asset_id.lower() == "all":
            asset_id = None

        if pipeline == "all":
            total = 0
            total += self.schedule_due_price_history_backfills(
                max_assets=max_assets,
                years=years,
            )
            total += self.enqueue_market_refresh(
                asset_id=None,
                include_dividends=include_dividends,
                include_splits=include_splits,
            )
            total += self.schedule_due_corporate_calendar_refresh()
            total += self.schedule_due_corporate_fundamental_updates(max_assets=max_assets)
            total += self.schedule_due_fundamental_backfills(max_assets=max_assets)
            total += self.schedule_due_fundamental_refreshes(max_assets=max_assets)
            return total

        if pipeline == "price-backfill":
            return self.enqueue_market_backfill(
                asset_id=asset_id,
                years=years,
                include_dividends=include_dividends,
                include_splits=include_splits,
            )

        if pipeline == "due-price-backfill":
            return self.schedule_due_price_history_backfills(
                max_assets=max_assets,
                years=years,
            )

        if pipeline == "price-refresh":
            return self.enqueue_market_refresh(
                asset_id=asset_id,
                include_dividends=include_dividends,
                include_splits=include_splits,
            )

        if pipeline == "corporate-calendar":
            return self.schedule_due_corporate_calendar_refresh()

        if pipeline == "earnings-updates":
            return self.schedule_due_corporate_fundamental_updates(max_assets=max_assets)

        if pipeline == "fundamentals-backfill":
            return self.schedule_due_fundamental_backfills(max_assets=max_assets)

        if pipeline == "fundamentals-refresh":
            return self.schedule_due_fundamental_refreshes(max_assets=max_assets)

        if pipeline == "metadata":
            return self.refresh_due_asset_metadata(max_assets=max_assets)

        if pipeline == "trading-calendar":
            return self.refresh_trading_calendar(market_code="all", year=calendar_year)

        raise ValueError(f"Unsupported ingestion pipeline: {pipeline}")

    def run_ingestion_jobs(self, domain: str = "all", max_jobs: int = 1) -> int:
        """
        Process pending ingestion jobs through the shared dev command surface.
        """
        domain = domain.lower()

        if domain == "market":
            return PriceHistoryIngestionService(self.conn).process_jobs(max_jobs=max_jobs)

        if domain == "corporate":
            return CorporateCalendarIngestionService(self.conn).process_jobs(max_jobs=max_jobs)

        if domain == "sentiment":
            from dashboard.ingestion_sentiment.scheduler import SentimentIngestionScheduler

            return SentimentIngestionScheduler(self.conn).run_sentiment_jobs(max_jobs=max_jobs)

        if domain != "all":
            raise ValueError(f"Unsupported ingestion job domain: {domain}")

        completed = 0
        while completed < max_jobs:
            did_market = PriceHistoryIngestionService(self.conn).process_jobs(max_jobs=1)
            if did_market:
                completed += did_market
                continue

            did_corporate = CorporateCalendarIngestionService(self.conn).process_jobs(max_jobs=1)
            if did_corporate:
                completed += did_corporate
                continue

            from dashboard.ingestion_sentiment.scheduler import SentimentIngestionScheduler

            did_sentiment = SentimentIngestionScheduler(self.conn).run_sentiment_jobs(max_jobs=1)
            if did_sentiment:
                completed += did_sentiment
                continue

            break

        return completed

    def sentiment_refresh(self, target: str, source: str = "all") -> int:
        from dashboard.ingestion_sentiment.scheduler import SentimentIngestionScheduler
        from dashboard.ingestion_sentiment.service import SentimentIngestionService

        target = target.upper().strip()
        source = source.lower().strip()

        if target == "ALL":
            scheduler = SentimentIngestionScheduler(self.conn)
            total = 0
            if source in {"all", "news"}:
                total += len(scheduler.enqueue_news_refresh_for_universe())
            if source in {"all", "reddit", "x", "social", "retail"}:
                total += len(
                    scheduler.enqueue_retail_sentiment_refresh_for_universe(
                        source="all" if source in {"all", "social", "retail"} else source
                    )
                )
            return total

        return SentimentIngestionService(self.conn).refresh_ticker(target, source=source)

    def run_sentiment_jobs(self, max_jobs: int = 1) -> int:
        from dashboard.ingestion_sentiment.scheduler import SentimentIngestionScheduler

        return SentimentIngestionScheduler(self.conn).run_sentiment_jobs(max_jobs=max_jobs)

    def list_news_for_ticker(self, ticker: str, limit: int = 10, days: int = 30):
        from dashboard.ingestion_sentiment.repo import SentimentIngestionRepository

        return SentimentIngestionRepository(self.conn).list_news_for_ticker(ticker, limit=limit)

    def list_social_for_ticker(self, ticker: str, limit: int = 10, days: int = 30):
        from dashboard.ingestion_sentiment.repo import SentimentIngestionRepository

        return SentimentIngestionRepository(self.conn).list_social_for_ticker(ticker, limit=limit)

    def refresh_factor_snapshot(self, target: str) -> int:
        from datetime import date
        from dashboard.ingestion_sentiment.scheduler import SentimentIngestionScheduler
        from dashboard.ingestion_sentiment.service import SentimentIngestionService

        target = target.upper().strip()
        if target == "ALL":
            return len(
                SentimentIngestionScheduler(self.conn).enqueue_factor_snapshot_refresh(
                    snapshot_date=date.today()
                )
            )
        return SentimentIngestionService(self.conn).refresh_factor_snapshot(target, date.today())

    def refresh_quant_rating(self, target: str) -> int:
        from datetime import date
        from dashboard.ingestion_sentiment.scheduler import SentimentIngestionScheduler
        from dashboard.ingestion_sentiment.service import SentimentIngestionService

        target = target.upper().strip()
        if target == "ALL":
            return len(
                SentimentIngestionScheduler(self.conn).enqueue_quant_rating_refresh(
                    snapshot_date=date.today()
                )
            )
        return SentimentIngestionService(self.conn).refresh_quant_rating(target, date.today())

    def sentiment_summary(self, ticker: str) -> str:
        ticker = ticker.upper().strip()
        row = self.conn.execute(
            """
            SELECT ticker, blended_sentiment_score, retail_sentiment_score, news_sentiment_score
            FROM ticker_sentiment_daily
            WHERE ticker = ?
            ORDER BY date DESC
            LIMIT 1
            """,
            [ticker],
        ).fetchone()
        if row is None:
            return f"Ticker: {ticker}\nNo sentiment summary found."

        return (
            f"Ticker: {row[0]}\n"
            f"Blended sentiment: {self._sentiment_label(row[1])} ({self._fmt_score(row[1])})\n"
            f"Retail sentiment: {self._sentiment_label(row[2])} ({self._fmt_score(row[2])})\n"
            f"News sentiment: {self._sentiment_label(row[3])} ({self._fmt_score(row[3])})"
        )

    def quant_summary(self, ticker: str) -> str:
        ticker = ticker.upper().strip()
        row = self.conn.execute(
            """
            SELECT
                ticker,
                overall_quant_score,
                overall_quant_rating,
                factor_profile,
                growth_rating,
                value_rating,
                quality_rating,
                momentum_rating,
                defensive_rating,
                dividend_rating,
                volatility_rating
            FROM ticker_quant_rating_snapshot
            WHERE ticker = ?
            ORDER BY snapshot_date DESC
            LIMIT 1
            """,
            [ticker],
        ).fetchone()
        if row is None:
            return f"Ticker: {ticker}\nNo quant summary found."

        return (
            f"Ticker: {row[0]}\n"
            f"Internal quant rating: {row[2]} ({self._fmt_score(row[1])})\n"
            f"Quant profile: {row[3] or 'Unclassified'}\n"
            f"Factor ratings: Growth {row[4] or '-'}, Value {row[5] or '-'}, "
            f"Quality {row[6] or '-'}, Momentum {row[7] or '-'}, "
            f"Defensive {row[8] or '-'}, Dividend {row[9] or '-'}, "
            f"Volatility {row[10] or '-'}"
        )

    @staticmethod
    def _fmt_score(score) -> str:
        if score is None:
            return "n/a"
        return f"{score:+.2f}" if abs(score) <= 1 else f"{score:.0f}"

    @staticmethod
    def _sentiment_label(score) -> str:
        if score is None:
            return "No data"
        if score >= 0.4:
            return "Bullish"
        if score > 0.05:
            return "Neutral / Positive"
        if score <= -0.4:
            return "Bearish"
        if score < -0.05:
            return "Neutral / Negative"
        return "Neutral"

    def run_market_backfill_jobs(self, max_jobs: int = 1) -> int:
        """
        Process queued Domain A market backfill jobs.
        """
        service = PriceHistoryIngestionService(self.conn)
        return service.process_backfill_jobs(max_jobs=max_jobs)

    def run_market_refresh_jobs(self, max_jobs: int = 1) -> int:
        """
        Process queued Domain A market refresh jobs.
        """
        service = PriceHistoryIngestionService(self.conn)
        return service.process_refresh_jobs(max_jobs=max_jobs)
    
    def refresh_asset_metadata(self, asset_id: str | None = None) -> int:
        from dashboard.services.asset_importer import AssetImporter

        importer = AssetImporter(self)

        if asset_id is None:
            asset_ids = TickerUniverseRepository(self.conn).ingestible_asset_ids()
        else:
            asset_ids = [asset_id.upper().strip()]

        synced = importer.import_asset_ids(asset_ids)
        return len(synced)

    def refresh_due_asset_metadata(self, max_assets: int = 5) -> int:
        from dashboard.services.asset_importer import AssetImporter

        asset_ids = TickerUniverseRepository(self.conn).ingestible_asset_ids()
        if not asset_ids:
            return 0

        placeholders = ", ".join("?" for _ in asset_ids)
        rows = self.conn.execute(f"""
            SELECT asset_id
            FROM asset_metadata_sync
            WHERE asset_id IN ({placeholders})
              AND (
                sync_status IN ('pending', 'stale', 'failed')
                OR last_succeeded_at IS NULL
                OR last_succeeded_at < now() - INTERVAL 30 DAY
            )
            ORDER BY
                CASE sync_status
                    WHEN 'pending' THEN 1
                    WHEN 'failed' THEN 2
                    WHEN 'stale' THEN 3
                    ELSE 4
                END,
                last_attempted_at NULLS FIRST
            LIMIT ?
        """, [*asset_ids, max_assets]).fetchall()

        asset_ids = [r[0] for r in rows]

        importer = AssetImporter(self)
        synced = importer.import_asset_ids(asset_ids)
        return len(synced)

    def schedule_due_price_history_backfills(self, max_assets: int = 3, years: int = 10) -> int:
        from dashboard.ingestion.price_history.service import PriceHistoryIngestionService

        asset_ids = TickerUniverseRepository(self.conn).ingestible_asset_ids()
        if not asset_ids:
            return 0

        placeholders = ", ".join("?" for _ in asset_ids)
        rows = self.conn.execute(f"""
          SELECT a.asset_id
            FROM asset a
            LEFT JOIN asset_sync_state s
            ON s.asset_id = a.asset_id
            AND s.domain = 'market'
            AND s.dataset = 'price_daily'
        WHERE a.asset_id IN ({placeholders})
        AND (
            s.asset_id IS NULL
            OR s.backfill_status IN ('not_started', 'failed')
            OR s.last_successful_date IS NULL
        )
        AND NOT EXISTS (
            SELECT 1
        FROM ingestion_job j
        WHERE j.asset_id = a.asset_id
        AND j.domain = 'market'
        AND j.dataset = 'price_daily'
        AND j.job_type = 'backfill'
        AND j.status IN ('pending', 'running'))
        ORDER BY a.asset_id
        LIMIT ?;
        """, [*asset_ids, max_assets]).fetchall()

        service = PriceHistoryIngestionService(self.conn)

        total_jobs = 0
        for row in rows:
            asset_id = row[0]
            total_jobs += len(
                service.enqueue_backfill_one(
                    asset_id=asset_id,
                    years=years,
                    include_dividends=True,
                    include_splits=True,
                )
            )

        return total_jobs


    def run_price_history_backfill_jobs(self, max_jobs: int = 1) -> int:
        from dashboard.ingestion.price_history.service import PriceHistoryIngestionService

        service = PriceHistoryIngestionService(self.conn)
        return service.process_backfill_jobs(max_jobs=max_jobs)
    
    ########################
    ##          trading calendar 
    #######################

    def refresh_trading_calendar(
        self,
        market_code: str | None = None,
        year: int | None = None,
    ) -> int:

        if year is None:
            year = date.today().year

        start_date = date(year, 1, 1)
        end_date = date(year + 1, 12, 31)

        service = TradingCalendarIngestionService(self.conn)

        if market_code is None or market_code.lower() == "all":
            return service.refresh_all(start_date=start_date, end_date=end_date)

        return service.refresh_market(
            market_code=market_code,
            start_date=start_date,
            end_date=end_date,
        )


    def is_market_open_day(self, market_code: str, session_date: date) -> bool:
        from dashboard.ingestion.trading_calendar.service import TradingCalendarIngestionService

        service = TradingCalendarIngestionService(self.conn)
        return service.is_market_open_day(market_code, session_date)


    def should_skip_market_refresh(self, market_code: str, session_date: date) -> bool:
        return not self.is_market_open_day(market_code, session_date)
    

    #####################################
    ##      corporate calendar
    #####################################

    def schedule_due_corporate_calendar_refresh(self) -> int:
        service = CorporateCalendarIngestionService(self.conn)

        pending = self.conn.execute("""
            SELECT COUNT(*)
            FROM ingestion_job
            WHERE domain = 'corporate'
            AND dataset = 'earnings_calendar'
            AND job_type = 'calendar_refresh'
            AND status IN ('pending', 'running')
        """).fetchone()[0]

        if pending > 0:
            return 0

        latest_success = self.conn.execute("""
            SELECT MAX(last_successful_at)
            FROM asset_sync_state
            WHERE domain = 'corporate'
            AND dataset = 'earnings_calendar'
        """).fetchone()[0]

        if latest_success is not None:
            recently_refreshed = self.conn.execute("""
                SELECT ? > now() - INTERVAL 1 DAY
            """, [latest_success]).fetchone()[0]

            if recently_refreshed:
                return 0

        return len(service.enqueue_calendar_refresh())

    def schedule_due_corporate_fundamental_updates(
        self,
        max_assets: int = 25,
    ) -> int:
        """
        Schedule earnings/fundamental updates for recent earnings events.
        """
        from dashboard.ingestion.corporate_calendar.service import (
            CorporateCalendarIngestionService,
        )

        service = CorporateCalendarIngestionService(self.conn)

        return len(
            service.schedule_fundamental_updates_after_events(
                lookback_days=14,
                max_assets=max_assets,
            )
        )

    def schedule_due_fundamental_backfills(
        self,
        max_assets: int = 25,
    ) -> int:
        """
        Schedule historical financial-statement backfills for subscribed assets.
        """
        from dashboard.ingestion.corporate_calendar.service import (
            CorporateCalendarIngestionService,
        )

        service = CorporateCalendarIngestionService(self.conn)
        return len(
            service.schedule_due_fundamental_subscription_backfills(
                max_assets=max_assets,
            )
        )

    def schedule_due_fundamental_refreshes(
        self,
        max_assets: int = 25,
    ) -> int:
        """
        Schedule recurring financial-statement refreshes for subscribed assets.
        """
        from dashboard.ingestion.corporate_calendar.service import (
            CorporateCalendarIngestionService,
        )

        service = CorporateCalendarIngestionService(self.conn)
        return len(
            service.schedule_due_fundamental_subscription_refreshes(
                max_assets=max_assets,
            )
        )

    def run_corporate_ingestion_jobs(self, max_jobs: int = 1) -> int:
        """
        Process queued corporate ingestion jobs.
        """
        from dashboard.ingestion.corporate_calendar.service import (
            CorporateCalendarIngestionService,
        )

        service = CorporateCalendarIngestionService(self.conn)
        return service.process_jobs(max_jobs=max_jobs)
    


    #########################################
    ##      indices
    #########################################


    def seed_core_indices(self):
        service = create_index_ingestion_service(self.conn)
        return service.seed_core_universe()


    def refresh_core_index_daily_prices(self, lookback_days: int = 10):
        scheduler = create_index_scheduler(self.conn)
        return scheduler.run_core_daily_refresh(lookback_days=lookback_days)


    def refresh_core_index_intraday_prices(self, interval: str = "5min"):
        scheduler = create_index_scheduler(self.conn)
        return scheduler.run_core_intraday_refresh(interval=interval)


    def refresh_core_index_composition(self):
        scheduler = create_index_scheduler(self.conn)
        return scheduler.run_core_composition_refresh()


    def refresh_core_index_relative_metrics(self):
        scheduler = create_index_scheduler(self.conn)
        return scheduler.run_relative_metrics_against_sp500()
    
    from dashboard.ingestion.indices.index_service_factory import (
    create_index_ingestion_service,
    create_index_scheduler,
)


def seed_all_benchmark_indices(self):
    service = create_index_ingestion_service(self.conn)
    return service.seed_all_universes()


def seed_core_indices(self):
    service = create_index_ingestion_service(self.conn)
    return service.seed_core_universe()


def seed_sector_industry_indices(self):
    service = create_index_ingestion_service(self.conn)
    return service.seed_sector_industry_universe()


def refresh_core_index_daily_prices(self, lookback_days: int = 10):
    scheduler = create_index_scheduler(self.conn)
    return scheduler.run_core_daily_refresh(lookback_days=lookback_days)


def refresh_core_index_intraday_prices(self, interval: str = "5min"):
    scheduler = create_index_scheduler(self.conn)
    return scheduler.run_core_intraday_refresh(interval=interval)


def refresh_core_index_composition(self):
    scheduler = create_index_scheduler(self.conn)
    return scheduler.run_core_composition_refresh()


def refresh_non_core_index_daily_prices(self, lookback_days: int = 10):
    scheduler = create_index_scheduler(self.conn)
    return scheduler.run_non_core_daily_refresh(lookback_days=lookback_days)


def refresh_non_core_index_intraday_prices(self, interval: str = "5min"):
    scheduler = create_index_scheduler(self.conn)
    return scheduler.run_non_core_intraday_refresh(interval=interval)


def refresh_non_core_index_composition(self):
    scheduler = create_index_scheduler(self.conn)
    return scheduler.run_non_core_composition_refresh()


def refresh_sector_index_daily_prices(self, lookback_days: int = 10):
    scheduler = create_index_scheduler(self.conn)
    return scheduler.run_sector_daily_refresh(lookback_days=lookback_days)


def refresh_industry_index_daily_prices(self, lookback_days: int = 10):
    scheduler = create_index_scheduler(self.conn)
    return scheduler.run_industry_daily_refresh(lookback_days=lookback_days)


def refresh_theme_index_daily_prices(self, lookback_days: int = 10):
    scheduler = create_index_scheduler(self.conn)
    return scheduler.run_theme_daily_refresh(lookback_days=lookback_days)


def refresh_all_benchmark_relative_metrics(self):
    scheduler = create_index_scheduler(self.conn)
    return scheduler.run_relative_metrics_against_sp500()
    

    #######################################
    ##      live prices
    #######################################


    def get_current_live_prices(self):
        return self.conn.execute(
            """
            SELECT
                asset_id,
                symbol,
                price,
                volume,
                bid,
                ask,
                provider,
                market_session,
                trade_ts_utc,
                updated_at
            FROM current_asset_price
            ORDER BY symbol
            """
        ).fetchall()


    def get_live_price_for_asset(self, asset_id: str):
        return self.conn.execute(
            """
            SELECT
                asset_id,
                symbol,
                price,
                volume,
                bid,
                ask,
                provider,
                market_session,
                trade_ts_utc,
                updated_at
            FROM current_asset_price
            WHERE asset_id = ?
            """,
            [asset_id],
        ).fetchone()
    
    def run_live_price_stream(
        self,
        include_watchlist: bool = False,
        enable_extended_hours: bool = True,
    ) -> None:
        """
        Run the live price streaming worker.

        Portfolio assets are streamed by default.
        Watchlist assets can optionally be included.
        Extended-hours streaming can optionally be disabled.
        """
        from dashboard.ingestion.websocket.live_price_worker import LivePriceWorker

        worker = LivePriceWorker(self.conn)
        worker.run(
            include_watchlist=include_watchlist,
            enable_extended_hours=enable_extended_hours,
        )


class PortfolioManager():
    """
    Actions in db for a single portfolio
    """

    def __init__(self, db: DB, id: int, name: str):
        self.db = db
        self.conn = db.conn
        self.portfolio_id = id
        self.portfolio_name = name

    def load_portfolio(self):
        """
        Returns a Portfolio object from ID -> To return more useful data later.
        """
        row = self.conn.execute(qry.GET_PORTFOLIO_BY_ID, [self.portfolio_id],).fetchone()
        if row is None:
            raise ValueError(f"Portfolio not found: {self.portfolio_name}")
        return Portfolio(*row)
    
    def list_txns(self, N:int|None):
        """
        List transactions belonging to the Portfolio in PortfolioView.
        - Instantiates a Txn object for each row returned by the db query, or raises a ValueError if the result is empty.
        - Calls Txn method .display_str() to return a string representing a table row.
        - Optional argument (N) determines how many rows to display.
        Returns None.     
        """
        query = f"SELECT * FROM ({qry.LIST_TXNS}) t WHERE t.portfolio_id = ?;"
        rows = self.conn.execute(query, [self.portfolio_id]).fetchall()
        if not rows: 
            raise ValueError(f"No transactions in portfolio: {self.portfolio_name}")
        
        TxnTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            TxnTableFormatter(Txn(*row)).entry()

    def list_txns_by_type(self, txn_type:str, N:int|None):
        """
        List transactions belonging to the Portfolio in PortfolioView filtered by txn_type.
        - Instantiates a Txn object for each row returned by the db query, or raises a ValueError if the result is empty.
        - Calls Formatter class to return a string representing a table row for each row returned.
        - Optional argument (N) determines how many rows to display.
        Returns None.        
        """
        query = f"SELECT * FROM ({qry.LIST_TXNS_BY_TYPE}) p WHERE p.portfolio_id = ?;"
        rows = self.conn.execute(query, [txn_type, self.portfolio_id],).fetchall()
        if not rows: 
            raise ValueError(f"No transactions found with type: {txn_type}.")
        
        TxnTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            TxnTableFormatter(Txn(*row)).entry()        

    def list_txns_by_day(self, date_str:str, N:int|None):
        """
        List transactions belonging to the Portfolio in PortfolioView filtered by (timestamp.date()).
        - Instantiates a Txn object for each row returned by the db query, or raises a ValueError if the result is empty.
        - Calls Formatter class to return a string representing a table row for each row returned.
        - Optional argument (N) determines how many rows to display.
        Returns None.          
        """
         # normalize date_str into a datetime object.
        for fmt in ("%m-%d-%Y", "%m/%d/%Y"):
            try:
                date = datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue
        else:
            raise AttributeError(f"Date {date_str} invalid. Please enter in (MM-DD-YYYY) or (MM/DD/YYYY) format.")
        
        query = f"SELECT * FROM ({qry.LIST_TXNS_BY_DAY}) d WHERE d.portfolio_id = ?"
        rows = self.conn.execute(query, [date, self.portfolio_id],).fetchall()
        if not rows: 
            raise ValueError(f"No transactions found on: {date.strftime('%m/%d/%Y')}.")
        
        TxnTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            TxnTableFormatter(Txn(*row)).entry()

    def list_txns_by_position(self, asset_id:str, N:int|None):
        """
        List transactions belonging to the Portfolio in PortfolioView filtered by (portfolio_id, asset_id).
        - Instantiates a Txn object for each row returned by the db query, or raises a ValueError if the result is empty.
        - Calls Formatter class to return a string representing a table row for each row returned.
        - Optional argument (N) determines how many rows to display.
        Returns None.          
        """
        query = f"SELECT * FROM ({qry.LIST_TXNS_BY_ASSET}) p WHERE p.portfolio_id = ?;"
        rows = self.conn.execute(query, [asset_id, self.portfolio_id],).fetchall()
        if not rows: 
            raise ValueError(f"No transactions found with asset: {asset_id}")
        
        TxnTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            TxnTableFormatter(Txn(*row)).entry()
        
    def list_positions(self, N:int|None):
        """
        List positions belonging to the Portfolio in PortfolioView.
        - Instantiates a Position object for each row returned by the db query, or raises a ValueError if the result is empty.
        - Calls Formatter class to return a string representing a table row for each row returned.
        - Optional argument (N) determines how many rows to display.
        Returns None.          
        """
        query = f"SELECT * FROM ({qry.LIST_POSITIONS}) p WHERE p.portfolio_id = ?;"
        rows = self.conn.execute(query, [self.portfolio_id],).fetchall()
        if not rows: 
            raise ValueError(f"No positions in portfolio: {self.portfolio_name}")
        
        PositionTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            PositionTableFormatter(Position(*row)).entry()
    
    def list_positions_by_asset(self, asset_id:str, N:int|None):
        """
        List positions belonging to the Portfolio in PortfolioView filtered by asset_id.
        - Instantiates a Position object for each row returned by the db query, or raises a ValueError if the result is empty.
        - Calls Formatter class to return a string representing a table row for each row returned.
        - Optional argument (N) determines how many rows to display.
        Returns None.          
        """
        query = f"SELECT * FROM ({qry.LIST_POSITIONS_BY_ASSET_ID}) p WHERE p.portfolio_id = ?;"
        rows = self.conn.execute(query, [asset_id, self.portfolio_id],).fetchall()
        if not rows: 
            raise ValueError(f"No positions in portfolio: {self.portfolio_name} with asset:{asset_id}.")
        
        PositionTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            PositionTableFormatter(Position(*row)).entry()
  
    def list_positions_by_type(self, asset_type:str, N:int|None):
        """
        List positions belonging to the Portfolio in PortfolioView filtered by asset_type.
        - Instantiates a Position object for each row returned by the db query, or raises a ValueError if the result is empty.
        - Calls Formatter class to return a string representing a table row for each row returned.
        - Optional argument (N) determines how many rows to display.
        Returns None.          
        """
        query = f"SELECT * FROM ({qry.LIST_POSITIONS_BY_ASSET_TYPE}) p WHERE p.portfolio_id = ?;"
        rows = self.conn.execute(query, [asset_type, self.portfolio_id],).fetchall()
        if not rows: 
            raise ValueError(f"No positions in portfolio: {self.portfolio_name} of type: {asset_type}.")
        
        PositionTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            PositionTableFormatter(Position(*row)).entry()
    
    def list_positions_by_size(self, asset_size:str, N:int|None):
        """
        List positions belonging to the Portfolio in PortfolioView filtered by asset_size.
        - Instantiates a Position object for each row returned by the db query, or raises a ValueError if the result is empty.
        - Calls Formatter class to return a string representing a table row for each row returned.
        - Optional argument (N) determines how many rows to display.
        Returns None.          
        """
        query = f"SELECT * FROM ({qry.LIST_POSITIONS_BY_ASSET_SIZE}) p WHERE p.portfolio_id = ?;"
        rows =  self.conn.execute(query, [asset_size, self.portfolio_id],).fetchall()
        if not rows: 
            raise ValueError(f"No positions in portfolio: {self.portfolio_name} of subtype: {asset_size}.")
        
        PositionTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            PositionTableFormatter(Position(*row)).entry()
        
    
    
