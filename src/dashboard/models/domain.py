"""~/models/
domain models

Txn:
Asset:
Portfolio:
Position:
"""
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class Txn:
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

    def display_str(self):
        """
        Print a normalized, padded string representing the object as one row in a list table.
        """
        asset = self.asset_id if self.asset_id is not None else "-"
        qty = f"{self.qty:.4f}" if self.qty is not None else "-"
        price = f"{self.price:.2f}" if self.price is not None else "-"
        cash_amt = f"{self.cash_amt:.2f}" if self.cash_amt is not None else "-"
        fee_amt = f"{self.fee_amt:.2f}" if self.fee_amt is not None else "-"
        print(f"| {self.txn_id:>14} | {self.portfolio_id:>12} | {self.time_stamp.strftime('%d/%m/%Y, %H:%M:%S'):>20} | {self.txn_type:>16} | {asset:>8} | {qty:>8} | {price:>8} | {self.ccy:>5} | {cash_amt:>10} | {fee_amt:>10} | {self.batch_id:>8} |")

@dataclass(frozen=True)
class Asset:
    asset_id: str
    asset_type: str 
    asset_subtype: str
    ccy: str

@dataclass
class Portfolio:
    portfolio_id: int
    portfolio_name: str
    created_at: datetime 
    updated_at: datetime
    base_ccy: str = "CAD"

    def display_str(self):
        """
        Print a padded string representing the object as one row in a list table.
        """
        print(f"| {self.portfolio_id:>12} | {self.portfolio_name:<14} | {self.created_at.strftime('%d/%m/%Y, %H:%M:%S'):20} | {self.updated_at.strftime('%d/%m/%Y, %H:%M:%S'):20} | {self.base_ccy:^5} |")

@dataclass
class Position:
    portfolio_id: int 
    asset_id: str
    qty: float 
    book_cost: float 
    last_updated: datetime

    def display_str(self):
        """
        Print a normalized, padded string representing the object as one row in a list table.
        """
        qty = f"{self.qty:.4f}" 
        book_cost = f"{self.book_cost:.2f}"

        print(f"| {self.portfolio_id:>11} | {self.asset_id:<8} | {qty:>8} | {book_cost:>9} | {self.last_updated.strftime('%d/%m/%Y, %H:%M:%S'):20} |")









