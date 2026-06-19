"""
~/services/

Asset data ingestion from FMP for assets registered in the local database

    AssetImporter: fetches metadata for one or more asset ids and updates
    both asset and asset_metadata_sync tables
"""
from dataclasses import dataclass
from typing import Iterable, Any
import json
import os
import urllib.parse
import urllib.request
import urllib.error

from dashboard.models.storage import DashboardManager
from dashboard.db import queries as qry
from dashboard.ingestion.rate_limits import (
    InMemoryRateLimiter,
    RateLimitExceeded,
    RateLimitPolicy,
    default_rate_limiter,
    fmp_rate_limit_policy,
)

from dotenv import load_dotenv
load_dotenv()


@dataclass
class AssetImporter:
    """
    Handles asset metadata ingestion for already-registered asset ids.

    param - manager: DashboardManager for database access.
          - api_key: FMP API key. If omitted, reads FMP_API_KEY from env.
          - base_url: FMP profile endpoint base url.
    """
    manager: DashboardManager
    api_key: str | None = None
    base_url: str = "https://financialmodelingprep.com/stable/profile"
    rate_limiter: InMemoryRateLimiter | None = None
    rate_limit_policy: RateLimitPolicy | None = None

    def __post_init__(self):
        """
        Load API key from .env if not explicitly provided.
        """
        if self.api_key is None:
            self.api_key = os.getenv("FMP_API_KEY")

        if not self.api_key:
            raise RuntimeError("FMP_API_KEY not found in environment or .env file")

        if self.rate_limiter is None:
            self.rate_limiter = default_rate_limiter()
        if self.rate_limit_policy is None:
            self.rate_limit_policy = fmp_rate_limit_policy()

    def import_stage_assets(self) -> list[str]:
        """
        Ingest metadata for the distinct asset ids currently present in norm_stg_txn.

        returns - list of asset ids successfully synced.
        """
        conn = self.manager.conn
        rows = conn.execute(qry.LIST_IMPORTED_STAGE_ASSET_IDS).fetchall()
        asset_ids = [row[0] for row in rows]
        return self.import_asset_ids(asset_ids)

    def import_asset_ids(self, asset_ids: Iterable[str]) -> list[str]:
        """
        Ingest metadata for a provided iterable of asset ids.

        returns - list of asset ids successfully synced.
        """
        synced: list[str] = []

        for asset_id in asset_ids:
            if not asset_id:
                continue

            try:
                self._mark_running(asset_id)
                profile = self._fetch_profile(asset_id)

                if profile is None:
                    raise ValueError(f"No FMP profile returned for asset_id={asset_id}")

                mapped = self._map_profile_to_asset_fields(asset_id, profile)
                self._upsert_asset_metadata(mapped)
                self._mark_success(asset_id)
                synced.append(asset_id)

            except Exception as exc:
                self._mark_failed(asset_id, str(exc))

        return synced

    def _fetch_profile(self, asset_id: str) -> dict[str, Any] | None:
        """
        Fetch the FMP profile for one asset id.

        returns - parsed profile dict, or None if the response is empty.
        raises - RuntimeError when API key is missing or HTTP response is bad.
        """
        if not self.api_key:
            raise RuntimeError("Missing FMP_API_KEY environment variable")

        query = urllib.parse.urlencode({
            "symbol": asset_id,
            "apikey": self.api_key,
        })
        url = f"{self.base_url}?{query}"

        try:
            self.rate_limiter.acquire(self.rate_limit_policy)
            with urllib.request.urlopen(url, timeout=15) as response:
                status = getattr(response, "status", 200)
                if status == 429:
                    raise RateLimitExceeded("FMP rate limit exceeded")
                if status != 200:
                    raise RuntimeError(f"FMP request failed with status {status}")

                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise RateLimitExceeded("FMP rate limit exceeded") from exc
            raise RuntimeError(f"FMP HTTP error {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"FMP connection error: {exc.reason}") from exc

        data = json.loads(payload)

        if isinstance(data, list):
            if not data:
                return None
            return data[0]

        if isinstance(data, dict):
            if "Error Message" in data:
                message = str(data["Error Message"])
                if "limit" in message.lower() or "rate" in message.lower():
                    raise RateLimitExceeded(message)
                raise RuntimeError(message)
            return data

        return None

    def _map_profile_to_asset_fields(self, asset_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        """
        Map an FMP profile payload into local asset fields.

        returns - dict containing SQL parameter values for UPSERT_ASSET_METADATA.
        """
        market_cap = self._to_float(profile.get("marketCap"))
        shares_outstanding = self._shares_outstanding_from_profile(profile, market_cap)

        asset_type = self._infer_asset_type(profile)
        size = self._infer_size(market_cap)

        return {
            "asset_id": asset_id,
            "asset_type": asset_type,
            "ccy": profile.get("currency"),
            "name": profile.get("companyName"),
            "sector": profile.get("sector"),
            "industry": profile.get("industry"),
            "size": size,
            "country": profile.get("country"),
            "region": None,
            "description": profile.get("description"),
            "market_beta": self._to_float(profile.get("beta")),
            "mkt_cap": market_cap,
            "shares_outstanding": shares_outstanding,
        }

    def _shares_outstanding_from_profile(
        self,
        profile: dict[str, Any],
        market_cap: float | None,
    ) -> float | None:
        for key in (
            "sharesOutstanding",
            "shares_outstanding",
            "weightedAverageShsOut",
            "weightedAverageShsOutDil",
        ):
            value = self._to_float(profile.get(key))
            if value is not None and value > 0:
                return value

        price = self._to_float(profile.get("price"))
        if market_cap is not None and market_cap > 0 and price is not None and price > 0:
            return market_cap / price

        return None

    def _infer_asset_type(self, profile: dict[str, Any]) -> str:
        """
        Infer a local asset_type from the FMP profile payload.
        """
        if profile.get("isEtf") is True:
            return "etf"
        if profile.get("isFund") is True:
            return "fund"
        if profile.get("isAdr") is True:
            return "stock"

        return "stock"

    def _infer_size(self, market_cap: float | None) -> str | None:
        """
        Infer company size from market capitalization.

        mega - <500B
        large - 100B -> 500B
        mid   - 10B -> 100B
        small - 10B -> 2B
        micro - 100M -> 2B
        """
        if market_cap is None:
            return None
        if market_cap >= 500_000_000_000:
            return "mega"
        if market_cap >= 100_000_000_000:
            return "large"
        if market_cap >= 10_000_000_000:
            return "mid"
        if market_cap >= 2_000_000_000:
            return "small"
        if market_cap >= 100_000_000:
            return "micro"
        return None

    def _upsert_asset_metadata(self, fields: dict[str, Any]) -> None:
        """
        Update the local asset row with fetched metadata.
        """
        self.manager.conn.execute(
            qry.UPSERT_ASSET_METADATA,
            [
                fields["asset_type"],
                fields["ccy"],
                fields["name"],
                fields["sector"],
                fields["industry"],
                fields["size"],
                fields["country"],
                fields["region"],
                fields["description"],
                fields["market_beta"],
                fields["mkt_cap"],
                fields["shares_outstanding"],
                fields["asset_id"],
            ],          
        )

    def _mark_running(self, asset_id: str) -> None:
        """
        Mark asset metadata sync as running.
        """
        self.manager.conn.execute(qry.MARK_ASSET_METADATA_SYNC_RUNNING, [asset_id])

    def _mark_success(self, asset_id: str) -> None:
        """
        Mark asset metadata sync as successful.
        """
        self.manager.conn.execute(qry.MARK_ASSET_METADATA_SYNC_SUCCESS, [asset_id])

    def _mark_failed(self, asset_id: str, error_text: str) -> None:
        """
        Mark asset metadata sync as failed.
        """
        self.manager.conn.execute(qry.MARK_ASSET_METADATA_SYNC_FAILED, [error_text, asset_id])

    @staticmethod
    def _to_float(value: Any) -> float | None:
        """
        Best-effort float conversion for API values.
        """
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value: Any) -> int | None:
        """
        Best-effort int conversion for API values.
        """
        if value in (None, ""):
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
