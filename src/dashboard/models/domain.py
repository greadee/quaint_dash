"""~/models/
domain models

    Txn: Single source of truth, main method of position, and portfolio composition calculations.
    Asset: May be formed as a result of a reference by a txn.
    Portfolio: Formed as a result of txn imports, represents the metadata of the aggregation of all txn by some portfolio_id.
    Position: Datatype derived from txn, main method of portfolio composition display
    ImportData: Metadata return type per portfolio for transaction batch import
    PortfolioImportData: Metadata return type for transaction batch import
"""
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)

class Txn:
    """
    Single source of truth, main method of position, and portfolio composition calculations.

    param - txn_id: sequential id for each transaction.
          - portfolio_id: in which portfolio the transaction occured.
          - time_stamp: time of transaction occurence.
          - txn_type: 'buy', 'sell', 'contribution', 'withdrawal', 'dividend', 'interest'.

      # asset transaction attributes -> if cash transaction, then these are null
          - asset_id: asset ticker symbol, all uppercase, non-NYSE listings are suffixed with the exchange symbol (BN.TO, PNG.V).
          - qty: quantity of asset involved in transaction.
          - price: price of asset at the time of transaction.

      # cash transaction attributes -> if asset transaction, then (ccy, cash_amt) are null and fee_amt can be null
          - ccy: currency of cash in transaction.
          - cash_amt: cash value of transaction.
          - fee_amt: cash value of fees incurred on the transaction.

      # import data -> can only ever be set after the transaction has been recorded in the database
          - batch_id: sequantial id for each transaction import batch.
    """
    txn_id: int 
    portfolio_id: str  
    time_stamp: datetime
    txn_type: str 

    asset_id: str | None
    qty: float | None
    price: float | None

    ccy: str 
    cash_amt: float | None
    fee_amt: float | None

    batch_id: str 

@dataclass(frozen=True)
class Asset:
    """
    Metadata for the assets involved in transactions, and on watchlists.

    param - asset_id: asset ticker symbol, all uppercase, non-NYSE listings are suffixed with the exchange symbol (BN.TO, PNG.V).
          - asset_type: 'stock', 'etf', ...
          - asset_subtype: stocks: sector/geo, etf: size/geo, ...
          - ccy: currency that the asset is domiciled in.
    """
    asset_id: str
    asset_type: str 
    asset_subtype: str
    ccy: str

@dataclass
class Portfolio:
    """
    Metadata for the aggregation of transactions by the same portfolio_id.
    
    param - portfolio_id: sequential id for each portfolio.
          - portfolio_name: user denoted name for the portfolio.
          - created_at: time of creation
          - updated_at: time of last transaction inside of the portfolio.
          - base_ccy: currency to display portfolio metrics involving cash values.
    """
    portfolio_id: int
    portfolio_name: str
    created_at: datetime 
    updated_at: datetime
    base_ccy: str = "CAD"

@dataclass
class Position:
    """
    Metadata for the aggregation of transactions by the same portfolio_id and asset_id.

    param - portfolio_id: sequential id for each portfolio.
          - asset_id: asset ticker symbol, all uppercase, non-NYSE listings are suffixed with the exchange symbol (BN.TO, PNG.V).
          - qty: sum total of the quantity attribute of each transaction involved.
          - book_cost: sum total of the quantity times price attribtue of each transaction involved.
          - last_updated: time of last transaction inside of portfolio on a specific asset.    
    """
    portfolio_id: int 
    asset_id: str
    qty: float 
    book_cost: float 
    last_updated: datetime


@dataclass(frozen=True)
class PortfolioImportData:
    """
    Metadata return type per portfolio for transaction batch import

    param: portfolio_id - sequential id for each portfolio.
           portfolio_name - user denoted name for the portfolio.
           created - whether the portfolio was updated or created
           batch_id - sequential id for each import batch.
    """
    portfolio_id: int 
    portfolio_name: str 
    created: bool
    batch_id: int

@dataclass(frozen=True)
class ImportData:
    """
    Metadata return type for transaction batch import

    param: batch_id - sequential id for each import batch.
           batch_type - imported from: "manual-entry"/"csv-import".
           inserted_rows - number of rows appended to db.
           portfolios_affected - portfolio_name for portfolios that had transactions added in the batch.
    """
    batch_id: int
    batch_type: str
    inserted_rows: int
    portfolios_affected: list[PortfolioImportData]





