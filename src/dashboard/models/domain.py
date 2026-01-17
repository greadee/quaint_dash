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
    timestamp: datetime
    txn_type: str 

    asset_id: str 
    qty: float
    price: float

    ccy: str 
    cash_amt: float
    fee_amt: float

    ext_ref: str # manual csv, broker ingest, etc.

@dataclass(frozen=True)
class Asset:
    asset_id: str
    asset_type: str 
    asset_subtype: str
    ccy: str

@dataclass
class Portfolio:
    portfolio_id: int
    name: str
    base_ccy: str = "CAD"

@dataclass
class Position:
    portfolio_id: int 
    asset: Asset
    qty: float 
    









