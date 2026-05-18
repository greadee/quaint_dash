"""
FMP provider wrapper for domain A (EOD daily updated) market ingestion
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, Optional
from urllib.parse import urlencode
from urllib.request import urlopen
import json

from dashboard.ingestion.market.models import PriceDailyRow, DividendEventRow, SplitEventRow


class FMPMarketProvider:
    """
    small wrapper around FMP endpoints for daily market data
    """

    BASE_URL = "https://financialmodelingprep.com/stable"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        if not self.api_key:
            raise ValueError("missing FMP api key; set FMP_API_KEY")

    def _get_json(self, path: str, params: dict[str, Any]) -> Any:
        params = dict(params)
        params["apikey"] = self.api_key
        url = f"{self.BASE_URL}{path}?{urlencode(params)}"

        with urlopen(url) as resp:
            payload = resp.read().decode("utf-8")

        return json.loads(payload)

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[date]:
        if not value:
            return None
        return datetime.strptime(value[:10], "%Y-%m-%d").date()

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        return float(value)

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        return int(value)

    def fetch_price_daily(
        self,
        asset_id: str,
        start_date: date,
        end_date: date,
    ) -> list[PriceDailyRow]:
        """
        fetch daily ohlcv rows for an asset over a date range
        """
        data = self._get_json(
            "/historical-price-eod/full",
            {
                "symbol": asset_id,
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
            },
        )

        rows: list[PriceDailyRow] = []
        for item in data:
            d = self._parse_date(item.get("date"))
            if d is None:
                continue

            rows.append(
                PriceDailyRow(
                    asset_id=asset_id,
                    price_date=d,
                    open_price=self._to_float(item.get("open")),
                    high_price=self._to_float(item.get("high")),
                    low_price=self._to_float(item.get("low")),
                    close_price=self._to_float(item.get("close")),
                    adj_close_price=self._to_float(item.get("adjClose")),
                    volume=self._to_int(item.get("volume")),
                    source="fmp",
                )
            )

        return rows

    def fetch_dividends(
        self,
        asset_id: str,
        start_date: date,
        end_date: date,
    ) -> list[DividendEventRow]:
        """
        fetch dividend events over a date range
        """
        data = self._get_json(
            "/historical-price-eod/dividend",
            {
                "symbol": asset_id,
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
            },
        )

        rows: list[DividendEventRow] = []
        for item in data:
            ex_date = self._parse_date(item.get("date"))
            if ex_date is None:
                continue

            rows.append(
                DividendEventRow(
                    asset_id=asset_id,
                    ex_date=ex_date,
                    payment_date=self._parse_date(item.get("paymentDate")),
                    record_date=self._parse_date(item.get("recordDate")),
                    declaration_date=self._parse_date(item.get("declarationDate")),
                    dividend_per_share=self._to_float(item.get("dividend")),
                    currency=item.get("currency"),
                    source="fmp",
                )
            )

        return rows

    def fetch_splits(
        self,
        asset_id: str,
        start_date: date,
        end_date: date,
    ) -> list[SplitEventRow]:
        """
        fetch split events over a date range
        """
        data = self._get_json(
            "/historical-price-eod/stock_split",
            {
                "symbol": asset_id,
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
            },
        )

        rows: list[SplitEventRow] = []
        for item in data:
            ex_date = self._parse_date(item.get("date"))
            if ex_date is None:
                continue

            rows.append(
                SplitEventRow(
                    asset_id=asset_id,
                    ex_date=ex_date,
                    split_from=self._to_int(item.get("numerator")),
                    split_to=self._to_int(item.get("denominator")),
                    source="fmp",
                )
            )

        return rows