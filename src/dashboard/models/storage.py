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

    def upsert_portfolio(self, name: str, base_ccy: str = "CAD"):
        """
        Updates or creates a portfolio based on a name.
        - Uses MAX(id)+1 for new portfolios and returns created = true
        - Searches db for given name and returns created = false if found
        """
        id, created = self.conn.execute(qry.CHECK_NEW_PORTFOLIO_ID, [name],).fetchone()
        self.conn.execute(qry.UPSERT_PORTFOLIO, [id, name, base_ccy],)
        return created
    
    def list_portfolios(self):
        """
        Returns all portfolio rows from the database
        """
        return self.conn.execute(qry.LIST_PORTFOLIOS).fetchall()

    def open_portfolio_by_name(self, name: str):
        """
        Returns a PortfolioStore object with the same name as provided as an argument to the function
        """
        id = self.conn.execute(qry.GET_PORTFOLIO_BY_NAME, [name],).fetchone()[0]
        if not id:
            raise ValueError(f"Portfolio not found: {name}")
        return PortfolioStore(self.db, int(id), name)
    
    def upsert_asset(self, asset_id: str, asset_type: str, ccy: str):
        """
        Add/update an asset in the database
        """
        self.conn.execute(qry.UPSERT_ASSET,[asset_id, asset_type, ccy],)


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
    
    def add_txn(
        self,
        time_stamp: datetime,
        txn_type: str, 
        asset_id: str,
        qty: float,
        price: float,
        ccy: str, 
        cash_amt: float,
        fee_amt: float,
        batch_id: str):
        """
        Insert a transaction row and return txn_id
        """
        return self.conn.execute(qry.INSERT_TXN,
            [self.portfolio_id,
            time_stamp,
            txn_type,
            asset_id,
            qty,
            price,
            ccy,
            cash_amt,
            fee_amt,
            batch_id],)