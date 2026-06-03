"""SnapTrade read-only provider client."""

from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import hmac
import json
import os
import time
from typing import Any
from urllib.parse import urlencode

from dotenv import load_dotenv
import requests

from dashboard.brokers.models import (
    BrokerAccount,
    BrokerConnection,
    BrokerConnectionPortal,
    BrokerPosition,
    BrokerTransaction,
    BrokerUser,
)


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
    activity_page_limit: int = 1000

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
            activity_page_limit=int(os.getenv("SNAPTRADE_ACTIVITY_PAGE_LIMIT", "1000")),
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
        reconnect: str | None = None,
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
        if reconnect:
            body["reconnect"] = reconnect

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

    def rotate_user_secret(self, user: BrokerUser) -> BrokerUser:
        data = self._request(
            "POST",
            "/snapTrade/resetUserSecret",
            body={
                "userId": user.provider_user_id,
                "userSecret": user.user_secret,
            },
        )
        user_secret = data.get("userSecret") or data.get("newUserSecret")
        if not user_secret:
            raise SnapTradeError("SnapTrade reset user secret response did not include a new secret.")
        return BrokerUser(
            provider=self.provider_name,
            user_key=user.user_key,
            provider_user_id=user.provider_user_id,
            user_secret=user_secret,
            status=user.status,
        )

    def delete_user(self, user: BrokerUser) -> dict[str, Any]:
        data = self._request(
            "DELETE",
            "/snapTrade/deleteUser",
            query_params=[("userId", user.provider_user_id)],
        )
        if not isinstance(data, dict):
            raise SnapTradeError("SnapTrade delete user response was not an object.")
        return data

    def api_status(self) -> dict[str, Any]:
        data = self._request("GET", "/")
        if not isinstance(data, dict):
            raise SnapTradeError("SnapTrade API status response was not an object.")
        return data

    def list_connections(self, user: BrokerUser) -> list[BrokerConnection]:
        data = self._request("GET", "/authorizations", user=user)
        rows = _require_list(data, "connections")
        return [_connection_from_snaptrade(row, user.provider_user_id) for row in rows]

    def list_accounts(
        self,
        user: BrokerUser,
        connection: BrokerConnection | None = None,
    ) -> list[BrokerAccount]:
        connections = [connection] if connection is not None else self.list_connections(user)
        accounts: list[BrokerAccount] = []
        for conn in connections:
            data = self._request(
                "GET",
                f"/authorizations/{conn.provider_connection_id}/accounts",
                user=user,
            )
            rows = _require_list(data, "accounts")
            accounts.extend(_account_from_snaptrade(row, conn.provider_connection_id) for row in rows)
        return accounts

    def list_positions(self, user: BrokerUser, account: BrokerAccount) -> list[BrokerPosition]:
        data = self._request(
            "GET",
            f"/accounts/{account.provider_account_id}/positions",
            user=user,
        )
        rows = _require_list(data, "positions")
        return [_position_from_snaptrade(row, account.provider_account_id) for row in rows]

    def list_transactions(
        self,
        user: BrokerUser,
        account: BrokerAccount,
        start_date=None,
        end_date=None,
    ) -> list[BrokerTransaction]:
        base_params: list[tuple[str, str]] = []
        if start_date is not None:
            base_params.append(("startDate", start_date.isoformat()))
        if end_date is not None:
            base_params.append(("endDate", end_date.isoformat()))

        rows: list[dict[str, Any]] = []
        offset = 0
        limit = self.config.activity_page_limit
        while True:
            query_params = [
                *base_params,
                ("offset", str(offset)),
                ("limit", str(limit)),
            ]
            data = self._request(
                "GET",
                f"/accounts/{account.provider_account_id}/activities",
                query_params=query_params,
                user=user,
            )
            page_rows = _activity_rows(data)
            rows.extend(page_rows)
            if len(page_rows) < limit:
                break
            offset += limit
        return [_transaction_from_snaptrade(row, account.provider_account_id) for row in rows]

    def disconnect(self, user: BrokerUser, connection: BrokerConnection) -> None:
        self._request(
            "POST",
            f"/authorizations/{connection.provider_connection_id}/disable",
            user=user,
        )

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query_params: list[tuple[str, str]] | None = None,
        user: BrokerUser | None = None,
    ) -> Any:
        timestamp = str(int(self.clock()))
        query_items = [
            ("clientId", self.config.client_id),
            ("timestamp", timestamp),
        ]
        if query_params:
            query_items.extend(query_params)
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
        return data


def _require_list(data: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise SnapTradeError(f"SnapTrade {label} response was not a list.")
    return [row for row in data if isinstance(row, dict)]


def _activity_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        rows = data.get("data")
    else:
        rows = data
    return _require_list(rows, "activities")


def _connection_from_snaptrade(row: dict[str, Any], provider_user_id: str) -> BrokerConnection:
    brokerage = _dict_value(row, "brokerage")
    institution = (
        _str_value(brokerage, "display_name")
        or _str_value(brokerage, "name")
        or _str_value(row, "name")
        or "Unknown brokerage"
    )
    disabled = bool(row.get("disabled"))
    connection_type = _str_value(row, "type")
    status = "disabled" if disabled else "connected"
    if connection_type and connection_type != "read":
        status = f"{status}:{connection_type}"
    return BrokerConnection(
        provider=SNAPTRADE_PROVIDER,
        provider_connection_id=str(row.get("id")),
        provider_user_id=provider_user_id,
        institution_name=institution,
        status=status,
        raw_payload=row,
    )


def _account_from_snaptrade(row: dict[str, Any], provider_connection_id: str) -> BrokerAccount:
    balance = _first_number(
        _number_value(row, "balance"),
        _nested_number(row, "balance", "total"),
        _nested_number(row, "total_value", "value"),
    )
    currency = (
        _str_value(row, "currency")
        or _nested_str(row, "balance", "currency")
        or _nested_str(row, "total_value", "currency")
    )
    return BrokerAccount(
        provider=SNAPTRADE_PROVIDER,
        provider_account_id=str(row.get("id")),
        provider_connection_id=provider_connection_id,
        account_name=_str_value(row, "name") or _str_value(row, "number"),
        account_type=_str_value(row, "type") or _nested_str(row, "meta", "type"),
        currency=currency,
        balance=balance,
        raw_payload=row,
    )


def _position_from_snaptrade(row: dict[str, Any], provider_account_id: str) -> BrokerPosition:
    symbol = _symbol_from_row(row)
    position_id = _str_value(row, "id") or f"{provider_account_id}:{symbol or 'unknown'}"
    quantity = _first_number(_number_value(row, "units"), _number_value(row, "quantity"))
    market_value = _first_number(
        _number_value(row, "market_value"),
        _number_value(row, "marketValue"),
        _number_value(row, "value"),
    )
    if market_value is None and quantity is not None:
        price = _number_value(row, "price")
        market_value = None if price is None else quantity * price
    return BrokerPosition(
        provider=SNAPTRADE_PROVIDER,
        provider_account_id=provider_account_id,
        provider_position_id=position_id,
        symbol=symbol,
        description=_str_value(row, "description") or _nested_str(row, "symbol", "description"),
        quantity=quantity,
        market_value=market_value,
        currency=_str_value(row, "currency") or _nested_str(row, "symbol", "currency"),
        as_of_date=_date_value(row.get("as_of_date") or row.get("last_updated")),
        raw_payload=row,
    )


def _transaction_from_snaptrade(row: dict[str, Any], provider_account_id: str) -> BrokerTransaction:
    transaction_id = _str_value(row, "id") or _str_value(row, "trade_id")
    if not transaction_id:
        transaction_id = f"{provider_account_id}:{row.get('trade_date') or row.get('date')}:{row.get('type')}"
    return BrokerTransaction(
        provider=SNAPTRADE_PROVIDER,
        provider_transaction_id=transaction_id,
        provider_account_id=provider_account_id,
        txn_type=_str_value(row, "type") or _str_value(row, "action") or "unknown",
        trade_date=_date_value(row.get("trade_date") or row.get("date")),
        symbol=_symbol_from_row(row),
        quantity=_number_value(row, "units") or _number_value(row, "quantity"),
        price=_number_value(row, "price"),
        amount=_number_value(row, "amount"),
        currency=_str_value(row, "currency"),
        raw_payload=row,
    )


def _symbol_from_row(row: dict[str, Any]) -> str | None:
    symbol = row.get("symbol")
    if isinstance(symbol, dict):
        return _str_value(symbol, "symbol") or _str_value(symbol, "ticker") or _str_value(symbol, "raw_symbol")
    return _str_value(row, "symbol") or _str_value(row, "ticker")


def _dict_value(row: dict[str, Any], key: str) -> dict[str, Any]:
    value = row.get(key)
    return value if isinstance(value, dict) else {}


def _str_value(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    return str(value)


def _nested_str(row: dict[str, Any], parent: str, child: str) -> str | None:
    return _str_value(_dict_value(row, parent), child)


def _number_value(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("value")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _nested_number(row: dict[str, Any], parent: str, child: str) -> float | None:
    return _number_value(_dict_value(row, parent), child)


def _first_number(*values: float | None) -> float | None:
    return next((value for value in values if value is not None), None)


def _date_value(value) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    text = str(value)
    if "T" in text:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    return date.fromisoformat(text[:10])
