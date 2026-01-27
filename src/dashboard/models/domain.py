"""/models/
domain models

- Txn: one transaction row, either type: cash or asset 
- Asset: 
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

@dataclass
class Position:
    portfolio_id: int 
    asset: Asset
    qty: float 
    









