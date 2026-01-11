from dataclasses import dataclass 
from typing import Optional

@dataclass
class Position: 
    ticker: str 
    quantity: float 
    asset_type: str # stock or etf
    currency: str 
    country: Optional[str]
    sector: Optional[str]
