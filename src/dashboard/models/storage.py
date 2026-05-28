"""~/models/
db wrapper

- DashboardManager: bridge between database and cli_view classes.
- PortfolioManager: only works for one portfolio, cannot be instantiated if DashboardManager has not been.
"""
from datetime import datetime
from dashboard.db.db_conn import DB, init_db
from dashboard.db import queries as qry
from dashboard.models.domain import Portfolio, Position, Txn
from dashboard.services.table_formatter import TxnTableFormatter, PositionTableFormatter, PortfolioTableFormatter
from dashboard.ingestion.price_history.service import PriceHistoryIngestionService
from dashboard.ingestion.trading_calendar.service import TradingCalendarIngestionService
from dashboard.ingestion.corporate_calendar.service import CorporateCalendarIngestionService
from dashboard.ingestion.indices.index_service_factory import create_index_scheduler
from dashboard.ingestion.indices.index_service_factory import create_index_ingestion_service
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
        self.conn.execute(qry.UPSERT_ASSET,[asset_id, asset_type, asset_subtype, ccy],)

    def update_positions(self):
        """
        Refresh the (derived) position table. 
        - To be used prior to any position access. 
        """
        self.conn.execute(qry.UPDATE_POSITIONS)

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
            rows = self.conn.execute("""
                SELECT asset_id
                FROM asset
                WHERE track = TRUE
                ORDER BY asset_id
            """).fetchall()
            asset_ids = [r[0] for r in rows]
        else:
            asset_ids = [asset_id.upper().strip()]

        synced = importer.import_asset_ids(asset_ids)
        return len(synced)

    def refresh_due_asset_metadata(self, max_assets: int = 5) -> int:
        from dashboard.services.asset_importer import AssetImporter

        rows = self.conn.execute("""
            SELECT asset_id
            FROM asset_metadata_sync
            WHERE sync_status IN ('pending', 'stale', 'failed')
            OR last_succeeded_at IS NULL
            OR last_succeeded_at < now() - INTERVAL 30 DAY
            ORDER BY
                CASE sync_status
                    WHEN 'pending' THEN 1
                    WHEN 'failed' THEN 2
                    WHEN 'stale' THEN 3
                    ELSE 4
                END,
                last_attempted_at NULLS FIRST
            LIMIT ?
        """, [max_assets]).fetchall()

        asset_ids = [r[0] for r in rows]

        importer = AssetImporter(self)
        synced = importer.import_asset_ids(asset_ids)
        return len(synced)

    def schedule_due_price_history_backfills(self, max_assets: int = 3, years: int = 10) -> int:
        from dashboard.ingestion.price_history.service import PriceHistoryIngestionService

        rows = self.conn.execute("""
          SELECT a.asset_id
            FROM asset a
            LEFT JOIN asset_sync_state s
            ON s.asset_id = a.asset_id
            AND s.domain = 'market'
            AND s.dataset = 'price_daily'
        WHERE a.track = TRUE
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
        """, [max_assets]).fetchall()

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
        
    
    