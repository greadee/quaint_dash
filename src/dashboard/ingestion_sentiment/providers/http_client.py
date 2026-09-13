"""Small JSON HTTP client used by optional sentiment providers."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class JsonHttpClient:
    def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str | int] | None = None,
        data: bytes | None = None,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        if params:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urlencode(params)}"

        request = Request(
            url,
            data=data,
            headers=headers or {},
            method=method.upper(),
        )
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
        if not payload:
            return {}
        decoded = json.loads(payload)
        if not isinstance(decoded, dict):
            raise RuntimeError(f"Expected JSON object from {url}")
        return decoded
