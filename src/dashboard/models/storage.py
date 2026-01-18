"""/models/
db wrapper

- PortfolioManager: opens DB and finds/creates portfolios.
- PortfolioStore: works with one portfolio_id.
"""
from dataclasses import classmethod
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

    @classmethod
    def open(cls, db: DB):
        init_db(db)
        return cls(db)

    def create_portfolio(self, name: str, base_ccy: str = "CAD"):
        # Creates a new portfolio row and returns a store object for it.
        # Basic MAX(id)+1 generation for portfolio_id

        # Good enough for a single-user embedded DB.
        id = self.conn.execute(qry.NEW_PORTFOLIO_ID).fetchone()[0]
        self.conn.execute(qry.UPSERT_PORTFOLIO, [id, name, base_ccy],)

        return PortfolioStore(self.db, portfolio_name=name)

    def open_portfolio(self, name: str):
        return PortfolioStore(self.db, portfolio_name=name)


class PortfolioStore:
    """
    Actions in db for a single portfolio
    """

    def __init__(self, db: DB, portfolio_name: str):
        self.db = db
        self.conn = db.conn
        self.portfolio = self._load_portfolio(portfolio_name)

    def _load_portfolio(self, name: str):
        row = self.conn.execute(qry.GET_PORTFOLIO_BY_NAME, [name],).fetchone()
        if row is None:
            raise ValueError(f"Portfolio not found: {name}")
        return Portfolio(*row)

    def _next_txn_id(self) -> int:
        return self.conn.execute(qry.NEW_PORTFOLIO_ID).fetchone()[0]

    def upsert_asset(self, asset_id: str, asset_type: str, ccy: str):
        """
        Add/update an asset
        """

        self.conn.execute(qry.UPSERT_ASSET,[asset_id, asset_type, ccy],)

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
        ext_ref: str):
        """
        Insert a transaction row and return txn_id
        """
        return self.conn.execute(qry.INSERT_TXN,
            [self.portfolio.portfolio_id,
            time_stamp,
            txn_type,
            asset_id,
            qty,
            price,
            ccy,
            cash_amt,
            fee_amt,
            ext_ref],)


    def list_txns(self):
        """
        list transactions for a portfolio
        """
        rows = self.conn.execute(qry.LIST_TXNS_FOR_PORTFOLIO, [self.portfolio.portfolio_id]).fetchall()
        return [Txn(*row) for row in rows]
