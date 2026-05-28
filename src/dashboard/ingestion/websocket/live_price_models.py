from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal


MarketSession = Literal["pre", "regular", "after", "closed", "unknown"]


@dataclass(frozen=True)
class LivePriceTick:
    symbol: str
    price: float
    provider: str
    market_session: MarketSession
    asset_id: str | None = None
    volume: float | None = None
    bid: float | None = None
    ask: float | None = None
    trade_ts_utc: datetime | None = None
    raw_json: dict[str, Any] | None = None