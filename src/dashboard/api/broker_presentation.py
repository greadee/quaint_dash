"""Strict presentation boundary for broker instrument identity.

Only an explicit scalar allowlist crosses into ordinary API responses. Persisted raw
provider payloads and provider identifiers remain untouched and are never copied here.
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any

from dashboard.api.models import BrokerInstrumentDisplay

_SYMBOL_PATTERN = re.compile(r"[A-Za-z0-9.^_:/-]{1,32}")


def present_broker_instrument(
    *,
    provider_symbol: object,
    provider_description: object = None,
    provider_currency: object = None,
    local_asset_id: object = None,
    local_symbol: object = None,
    local_name: object = None,
    local_exchange: object = None,
    local_currency: object = None,
) -> BrokerInstrumentDisplay:
    """Normalize an instrument-shaped value without forwarding arbitrary provider data."""

    payload = _instrument_payload(provider_symbol)
    symbol = _symbol(
        _scalar(local_symbol)
        or _payload_scalar(payload, "symbol", "ticker", "raw_symbol")
        or _scalar(provider_symbol)
    )
    asset_id = _identifier(local_asset_id)
    name = _text(
        _scalar(local_name)
        or _payload_scalar(payload, "description", "name")
        or _scalar(provider_description),
        160,
    )
    exchange = _text(
        _scalar(local_exchange)
        or _payload_scalar(payload, "exchange_code", "exchange", "exchange_name"),
        40,
    )
    currency = _currency(
        _scalar(local_currency)
        or _payload_scalar(payload, "currency", "currency_code")
        or _scalar(provider_currency)
    )
    resolution_status = "resolved" if asset_id else "unresolved" if symbol else "unsupported"
    label = symbol or name or "Unsupported broker instrument"
    if symbol and name and name.casefold() != symbol.casefold():
        label = f"{symbol} - {name}"
    return BrokerInstrumentDisplay(
        symbol=symbol,
        name=name,
        exchange=exchange,
        currency=currency,
        local_asset_id=asset_id,
        resolution_status=resolution_status,
        display_label=label[:200],
    )


def _instrument_payload(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    text = value.strip()
    if not text.startswith("{") or len(text) > 20_000:
        return {}
    for loader in (json.loads, ast.literal_eval):
        try:
            payload = loader(text)
        except (ValueError, SyntaxError, TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _payload_scalar(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = next(
            (
                payload[candidate]
                for candidate in (key, key.upper(), key.lower())
                if candidate in payload
            ),
            None,
        )
        scalar = _scalar(value)
        if scalar:
            return scalar
    return None


def _scalar(value: object) -> str | None:
    if isinstance(value, dict):
        return _payload_scalar(value, "code", "symbol", "name", "description", "value")
    if not isinstance(value, (str, int, float)):
        return None
    text = str(value).strip()
    if not text or text.startswith(("{", "[")):
        return None
    return text


def _symbol(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized if _SYMBOL_PATTERN.fullmatch(normalized) else None


def _identifier(value: object) -> str | None:
    text = _scalar(value)
    if text is None or len(text) > 120 or any(character in text for character in "{}[]"):
        return None
    return text


def _currency(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized if len(normalized) == 3 and normalized.isalpha() else None


def _text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    if not normalized or normalized.startswith(("{", "[")):
        return None
    if normalized.lower().startswith(("http://", "https://")):
        return None
    return normalized[:limit]
