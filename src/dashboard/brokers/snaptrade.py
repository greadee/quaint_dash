"""SnapTrade read-only provider client."""

from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import time
from typing import Any
from urllib.parse import urlencode

from dotenv import load_dotenv
import requests

from dashboard.brokers.models import BrokerConnectionPortal, BrokerUser


SNAPTRADE_PROVIDER = "snaptrade"
SNAPTRADE_API_BASE_URL = "https://api.snaptrade.com/api/v1"


class SnapTradeError(RuntimeError):
    """Raised when SnapTrade configuration or API calls fail."""


@dataclass(frozen=True, slots=True)
class SnapTradeConfig:
    client_id: str
    consumer_key: str
    base_url: str = SNAPTRADE_API_BASE_URL
    timeout_seconds: float = 20.0

    @classmethod
    def from_env(cls) -> "SnapTradeConfig":
        load_dotenv()
        client_id = os.getenv("SNAPTRADE_CLIENT_ID")
        consumer_key = os.getenv("SNAPTRADE_CONSUMER_KEY")
        if not client_id or not consumer_key:
            raise SnapTradeError(
                "SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY are required."
            )
        return cls(
            client_id=client_id,
            consumer_key=consumer_key,
            base_url=os.getenv("SNAPTRADE_BASE_URL", SNAPTRADE_API_BASE_URL).rstrip("/"),
            timeout_seconds=float(os.getenv("SNAPTRADE_TIMEOUT_SECONDS", "20")),
        )


def compute_snaptrade_signature(
    resource_path: str,
    consumer_key: str,
    body: Any | None,
) -> str:
    """Return SnapTrade's HMAC-SHA256 request signature."""
    if "?" not in resource_path:
        raise ValueError("resource_path must include the exact query string")

    subpath, query = resource_path.split("?", 1)
    sig_object = {
        "content": None if body is None or body == {} else body,
        "path": f"/api/v1{subpath}",
        "query": query,
    }
    sig_content = json.dumps(sig_object, separators=(",", ":"), sort_keys=True)
    digest = hmac.new(
        consumer_key.encode("utf-8"),
        sig_content.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return b64encode(digest).decode("utf-8")


class SnapTradeProvider:
    provider_name = SNAPTRADE_PROVIDER

    def __init__(
        self,
        config: SnapTradeConfig,
        session: requests.Session | None = None,
        clock=time.time,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.clock = clock

    def register_user(self, user_id: str) -> BrokerUser:
        payload = {"userId": user_id}
        data = self._request("POST", "/snapTrade/registerUser", body=payload)
        provider_user_id = data.get("userId")
        user_secret = data.get("userSecret")
        if not provider_user_id or not user_secret:
            raise SnapTradeError("SnapTrade register user response did not include credentials.")
        return BrokerUser(
            provider=self.provider_name,
            user_key=user_id,
            provider_user_id=provider_user_id,
            user_secret=user_secret,
        )

    def create_connection_portal(
        self,
        user: BrokerUser,
        broker: str | None = None,
        custom_redirect: str | None = None,
        immediate_redirect: bool = False,
        dark_mode: bool = False,
    ) -> BrokerConnectionPortal:
        body: dict[str, Any] = {
            "connectionType": "read",
            "connectionPortalVersion": "v4",
            "immediateRedirect": immediate_redirect,
            "darkMode": dark_mode,
        }
        if broker:
            body["broker"] = broker
        if custom_redirect:
            body["customRedirect"] = custom_redirect

        data = self._request(
            "POST",
            "/snapTrade/login",
            body=body,
            user=user,
        )
        redirect_uri = data.get("redirectURI")
        if not redirect_uri:
            raise SnapTradeError("SnapTrade portal response did not include redirectURI.")
        return BrokerConnectionPortal(
            provider=self.provider_name,
            provider_user_id=user.provider_user_id,
            redirect_uri=redirect_uri,
            session_id=data.get("sessionId"),
        )

    def create_connection_portal_url(self, user: BrokerUser) -> str:
        return self.create_connection_portal(user).redirect_uri

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        user: BrokerUser | None = None,
    ) -> dict[str, Any]:
        timestamp = str(int(self.clock()))
        query_items = [
            ("clientId", self.config.client_id),
            ("timestamp", timestamp),
        ]
        if user is not None:
            query_items.extend(
                [
                    ("userId", user.provider_user_id),
                    ("userSecret", user.user_secret),
                ]
            )

        query = urlencode(query_items)
        resource_path = f"{path}?{query}"
        signature = compute_snaptrade_signature(resource_path, self.config.consumer_key, body)
        response = self.session.request(
            method,
            f"{self.config.base_url}{path}",
            params=query_items,
            json=body,
            headers={
                "Content-Type": "application/json",
                "Signature": signature,
            },
            timeout=self.config.timeout_seconds,
        )
        if response.status_code >= 400:
            raise SnapTradeError(
                f"SnapTrade API {method} {path} failed with HTTP {response.status_code}: "
                f"{response.text}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise SnapTradeError("SnapTrade API response was not valid JSON.") from exc
        if not isinstance(data, dict):
            raise SnapTradeError("SnapTrade API response was not an object.")
        return data
