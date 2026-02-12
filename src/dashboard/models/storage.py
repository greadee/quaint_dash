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

# SHOULD PORTFOLIOMANAGER BE MADE TO EXTEND DASHBOARDMANAGER?

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
        Instantiates a Portfolio object for each row returned by the db query.
        Calls Portfolio method .display_str() to return a string representing a table row.
        Optional argument (N) determines how many rows to display.
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
        Instantiates a Txn object for each row returned by the db query.
        Calls Txn method .display_str() to return a string representing a table row.
        Optional argument (N) determines how many rows to display.
        Returns None.        
        """
        rows = self.conn.execute(f"{qry.LIST_TXNS};").fetchall()
        if not rows: 
            raise ValueError("No transactions found.")

        TxnTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            TxnTableFormatter(Txn(*row)).entry()
    
    def list_txns_by_type(self, txn_type:str, N:int|None):
        """
        List all transactions in database filtered by txn_type.
        Instantiates a Txn object for each row returned by the db query.
        Calls Txn method .display_str() to return a string representing a table row.
        Optional argument (N) determines how many rows to display.
        Returns None.        
        """
        rows = self.conn.execute(f"{qry.LIST_TXNS_BY_TYPE};", [txn_type],).fetchall()
        if not rows: 
            raise ValueError(f"No transactions found with type: {txn_type}.")
        
        TxnTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            TxnTableFormatter(Txn(*row)).entry()

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
        Instantiates a Txn object for each row returned by the db query.
        Calls Txn method .display_str() to return a string representing a table row.
        Optional argument (N) determines how many rows to display.
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

    def list_positions_by_subtype(self, asset_subtype:str, N:int|None):
        """
        List all positions in database filtered by asset_subtype.
        - Instantiates a Position object for each row returned by the db query, or raises a ValueError if the result is empty.
        - Calls Position method .display_str() to return a string representing a table row.
        - Optional argument (N) determines how many rows to display.
        Returns None.          
        """
        rows = self.conn.execute(f"{qry.LIST_POSITIONS_BY_ASSET_SUBTYPE};", [asset_subtype],).fetchall()
        if not rows: 
            raise ValueError(f"No positions found with asset subtype: {asset_subtype}")
        
        PositionTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            PositionTableFormatter(Position(*row)).entry()

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
        - Calls Txn method .display_str() to return a string representing a table row.
        - Optional argument (N) determines how many rows to display.
        Returns None.        
        """
        query = f"SELECT * FROM ({qry.LIST_TXNS_BY_TYPE}) p WHERE p.portfolio_id = ?;"
        rows = self.conn.execute(query [txn_type, self.portfolio_id],).fetchall()
        if not rows: 
            raise ValueError(f"No transactions found with type: {txn_type}.")
        
        TxnTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            TxnTableFormatter(Txn(*row)).entry()

    def list_txns_by_day(self, date_str:str, N:int|None):
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
        - Calls Txn method .display_str() to return a string representing a table row.
        - Optional argument (N) determines how many rows to display.
        Returns None.          
        """
        query = f"SELECT * FROM ({qry.LIST_TXNS_BY_ASSET}) p WHERE p.portfolio_id = ?;"
        rows = self.conn.execute(query [asset_id, self.portfolio_id],).fetchall()
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
        - Calls Position method .display_str() to return a string representing a table row.
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
        - Calls Position method .display_str() to return a string representing a table row.
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
        - Calls Position method .display_str() to return a string representing a table row.
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
    
    def list_positions_by_subtype(self, asset_subtype:str, N:int|None):
        """
        List positions belonging to the Portfolio in PortfolioView filtered by asset_subtype.
        - Instantiates a Position object for each row returned by the db query, or raises a ValueError if the result is empty.
        - Calls Position method .display_str() to return a string representing a table row.
        - Optional argument (N) determines how many rows to display.
        Returns None.          
        """
        query = f"SELECT * FROM ({qry.LIST_POSITIONS_BY_ASSET_SUBTYPE}) p WHERE p.portfolio_id = ?;"
        rows =  self.conn.execute(query, [asset_subtype, self.portfolio_id],).fetchall()
        if not rows: 
            raise ValueError(f"No positions in portfolio: {self.portfolio_name} of subtype: {asset_subtype}.")
        
        PositionTableFormatter.header()

        to_list = rows if N is None else rows[:N]
        for row in to_list:
            PositionTableFormatter(Position(*row)).entry()
        
    
    