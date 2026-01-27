"""/models/
db wrapper

- PortfolioManager: opens DB and finds/creates portfolios.
- PortfolioStore: works with one portfolio_id.
"""
from datetime import datetime
from dashboard.db.db_conn import DB, init_db
from dashboard.db import queries as qry
from dashboard.models.domain import Portfolio, Txn

class PortfolioManager:
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
    
    def list_portfolios(self):
        """
        Returns all portfolio rows from the database
        """
        return self.conn.execute(qry.LIST_PORTFOLIOS).fetchall()
    

    def open_portfolio_by_id(self, id: int):
        """
        Checks DB for existence of a portfolio by the same name as the parameter id
        If not exists, raises a ValueError
        If exists, returns a PortfolioStore object for the portfolio that was found
        """
        row = self.conn.execute(qry.GET_PORTFOLIO_BY_ID, [id],).fetchone()[0]
        if not row:
            raise ValueError(f"Portfolio not found: {id}")
        return PortfolioStore(self.db, id, row['portfolio_name'])

    def open_portfolio_by_name(self, name: str):
        """
        Checks DB for existence of a portfolio by the same name as the parameter name
        If not exists, raises a ValueError
        If exists, returns a PortfolioStore object for the portfolio that was found        
        """
        row = self.conn.execute(qry.GET_PORTFOLIO_BY_NAME, [name],).fetchone()[0]
        if not row:
            raise ValueError(f"Portfolio not found: {name}")
        return PortfolioStore(self.db, row['portfolio_id'], name)
    
    def upsert_asset(self, asset_id: str, asset_type: str, asset_subtype: str, ccy: str):
        """
        Add/update an asset in the database
        """
        self.conn.execute(qry.UPSERT_ASSET,[asset_id, asset_type, asset_subtype, ccy],)


class PortfolioStore():
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
    
    def list_txns(self):
        """
        list transactions for a portfolio. 
        """
        rows = self.conn.execute(qry.LIST_TXNS_FOR_PORTFOLIO, [self.portfolio_id]).fetchall()
        return [Txn(*row) for row in rows]
    
    