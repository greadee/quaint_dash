"""/services/

format domain models as a table for display in the CLI.

    TableFormatter: Abstract parent class, formats a specific object type into a table entry
    TxnTableFormatter: Abstract child class, formats a Txn object into a table entry.
    AssetTableFormatter: Abstract child class, formats a Asset object into a table entry. ** PHASE 2: Data ingestion **
    PortfolioTableFormatter: Abstract child class, formats a Portfolio object into a table entry.
    PositionTableFormatter: Abstract child class, formats a Position object into a table entry.
    PortfolioImportDataTableFormatter: Abstract child class, formats a PortfolioImportData object into a table entry.
    ImportDataTableFormatter: Abstract child class, formats a ImportData object into a table entry.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from dashboard.models.domain import *

@dataclass 
class TableFormatter(ABC):
    """
    Formats application domain models for display in the CLI.

    param - abstract methods take an instance of the domain model as an argument.
    """
    
    @classmethod
    @abstractmethod
    def header(cls):
        """
        Print formatted row header for the specific object type and object attributes.
        Class method to be called without the need for object instantiation.
        Abstract method to be defined by each TableFormatter subclass.
        """
        pass 

    @abstractmethod 
    def entry(self):
        """
        Print formatted row entry with object attributes as fields in each column.
        Abstract method to be defined by each TableFormatter subclass.
        """
        pass
    
@dataclass 
class TxnTableFormatter:
    """
    Formats Txn objects for display in CLI.

    param - txn: Txn object to display
    """
    txn: Txn
    
    @classmethod
    @abstractmethod
    def header(cls):
        """
        Print formatted row header for Txns.
        """
        print(f'\n| {"TRANSACTION ID":^14} | {"PORTFOLIO ID":^12} | {"TIMESTAMP":^20} | {"TRANSACTION TYPE":^16} | {"ASSET ID":^8} | {"QUANTITY":^8} | {"PRICE":^8} | {"CCY":^5} | {"$ IN CASH":^10} | {"$ IN FEES":^10} | {"BATCH ID":^8} |') 

    @abstractmethod 
    def entry(self):
        """
        Print a normalized, padded string representing the Txn object as one row in a list table.
        """
        asset = self.txn.asset_id if self.txn.asset_id is not None else "-"
        qty = f"{self.txn.qty:.4f}" if self.txn.qty is not None else "-"
        price = f"{self.txn.price:.2f}" if self.txn.price is not None else "-"
        cash_amt = f"{self.txn.cash_amt:.2f}" if self.txn.cash_amt is not None else "-"
        fee_amt = f"{self.txn.fee_amt:.2f}" if self.txn.fee_amt is not None else "-"
        print(f"| {self.txn.txn_id:>14} | {self.txn.portfolio_id:>12} | {self.txn.time_stamp.strftime('%d/%m/%Y, %H:%M:%S'):>20} | {self.txn.txn_type:>16} | {asset:>8} | {qty:>8} | {price:>8} | {self.txn.ccy:>5} | {cash_amt:>10} | {fee_amt:>10} | {self.txn.batch_id:>8} |")

@dataclass 
class AssetTableFormatter:
    """
    Formats PortfolioImportData objects for display in CLI.

    ** To be implemented in phase 2 following asset data ingestion ** 

    param - asset: Asset object to display
    """
    asset: Asset

    @classmethod
    @abstractmethod
    def header(cls):
        pass 

    @abstractmethod 
    def entry(self):
        pass

@dataclass 
class PortfolioTableFormatter:
    """
    Formats Portfolio objects for display in CLI.

    param - portfolio: Portfolio object to display
    """
    portfolio: Portfolio
    
    @classmethod
    @abstractmethod
    def header(cls):
        """
        Print formatted row header for Portfolios.
        """
        print(f'\n| {"PORTFOLIO ID":^12} | {"PORTFOLIO NAME":^14} | {"CREATED AT":^20} | {"UPDATED AT":^20} | {"CCY":^5} |') 

    @abstractmethod 
    def entry(self):
        """
        Print a padded string representing the Portfolio object as one row in a list table.
        """
        print(f"| {self.portfolio.portfolio_id:>12} | {self.portfolio.portfolio_name:<14} | {self.portfolio.created_at.strftime('%d/%m/%Y, %H:%M:%S'):20} | {self.portfolio.updated_at.strftime('%d/%m/%Y, %H:%M:%S'):20} | {self.portfolio.base_ccy:^5} |")

@dataclass 
class PositionTableFormatter:
    """
    Formats Position objects for display in CLI.

    param - position: Position object to display
    """
    position: Position
    
    @classmethod
    @abstractmethod
    def header(cls):
        """
        Print formatted row header for Positions.
        """
        print(f'\n| {"PORTFOLIO ID":>12} | {"ASSET ID":<8} | {"QUANTITY":>8} | {"BOOK COST":>9} | {"LAST UPDATED":20} |')

    @abstractmethod 
    def entry(self):
        """
        Print a normalized, padded string representing the Position object as one row in a list table.
        """
        qty = f"{self.position.qty:.4f}" 
        book_cost = f"{self.position.book_cost:.2f}"

        print(f"| {self.position.portfolio_id:>12} | {self.position.asset_id:<8} | {qty:>8} | {book_cost:>9} | {self.position.last_updated.strftime('%d/%m/%Y, %H:%M:%S'):20} |")


@dataclass 
class PortfolioImportDataTableFormatter:
    """
    Formats PortfolioImportData objects for display in CLI.

    param - p_impData: PortfolioImportData object to display
    """
    p_impData: PortfolioImportData

    @classmethod
    @abstractmethod
    def header(cls):
        """
        Print formatted row header for PortfolioImportData objectss.
        """
        print(f'\n| {"PORTFOLIO ID":^12} | {"PORTFOLIO NAME":^14} | {"CREATED":^7} | {"BATCH ID":^8}|')
 

    @abstractmethod 
    def entry(self):
        """
        Print a padded string representing the PortfolioImportData object as one row in a list table.
        """
        print(f"| {self.p_impData.portfolio_id:>12} | {self.p_impData.portfolio_name:<14} | {self.p_impData.created:>7} | {self.p_impData.batch_id:>8} |")

@dataclass 
class ImportDataTableFormatter:
    """
    Formats ImportData objects for display in CLI.

    param - importData: ImportDataobject to display
    """
    importData: ImportData

    @classmethod
    @abstractmethod
    def header(cls):
        """
        Print formatted row header for ImportDatas objects.
        """
        print(f'\n| {"BATCH ID":^11} | {"BATCH TYPE":^13} | {"INSERTED ROWS":^13} | {"PORTFOLIOS AFFECTED":^19} |')
 
    @abstractmethod 
    def entry(self):
        """
        Print a padded string representing the ImportData object as one row in a list table.
        """
        print(f"| {self.importData.batch_id:>11} | {self.importData.batch_type:<13} | {self.importData.inserted_rows:>13} | {len(self.importData.portfolios_affected):>19} |")