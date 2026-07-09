"""Official X API provider for recent retail sentiment ingestion."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from dashboard.ingestion_sentiment.models import SocialPostInput
from dashboard.ingestion_sentiment.providers.http_client import JsonHttpClient


class XProvider:
    name = "x"

    def __init__(
        self,
        *,
        bearer_token: str | None = None,
        post_limit: int | None = None,
        timeout_seconds: float | None = None,
        include_plain_ticker: bool | None = None,
        http_client: JsonHttpClient | None = None,
    ) -> None:
        self.bearer_token = bearer_token or os.getenv("X_BEARER_TOKEN")
        self.post_limit = post_limit or int(os.getenv("X_POST_LIMIT", "25"))
        self.timeout_seconds = timeout_seconds or float(os.getenv("X_REQUEST_TIMEOUT_SECONDS", "10"))
        self.include_plain_ticker = (
            include_plain_ticker
            if include_plain_ticker is not None
            else os.getenv("X_INCLUDE_PLAIN_TICKER", "").lower() in {"1", "true", "yes"}
        )
        self.http_client = http_client or JsonHttpClient()

    def fetch_posts_for_ticker(
        self,
        ticker: str,
        since: datetime | None,
    ) -> list[SocialPostInput]:
        if not self.bearer_token:
            raise RuntimeError("X provider requires X_BEARER_TOKEN.")

        params: dict[str, str | int] = {
            "query": _query_for_ticker(ticker, include_plain_ticker=self.include_plain_ticker),
            "max_results": min(max(self.post_limit, 10), 100),
            "tweet.fields": "author_id,created_at,entities,lang,public_metrics",
        }
        start_time = _recent_start_time(since)
        if start_time is not None:
            params["start_time"] = start_time

        payload = self.http_client.request_json(
            "GET",
            "https://api.x.com/2/tweets/search/recent",
            headers={"Authorization": f"Bearer {self.bearer_token}"},
            params=params,
            timeout=self.timeout_seconds,
        )
        return [
            post
            for item in payload.get("data", [])
            if (post := _post_from_item(item, since)) is not None
        ]


def _post_from_item(item: dict[str, Any], since: datetime | None) -> SocialPostInput | None:
    post_id = item.get("id")
    text = item.get("text")
    if not post_id or not text:
        return None

    published_at = _datetime_from_iso(item.get("created_at"))
    if since is not None and published_at is not None and published_at <= _naive_utc(since):
        return None

    metrics = item.get("public_metrics") if isinstance(item.get("public_metrics"), dict) else {}
    return SocialPostInput(
        provider="x",
        source_post_id=str(post_id),
        source_name="x",
        author=_string_or_none(item.get("author_id")),
        body=str(text),
        url=f"https://x.com/i/web/status/{post_id}",
        published_at=published_at,
        like_count=_int_or_none(metrics.get("like_count")),
        repost_count=_int_or_none(metrics.get("retweet_count")),
        reply_count=_int_or_none(metrics.get("reply_count")),
        raw_payload=item,
    )


def _query_for_ticker(ticker: str, *, include_plain_ticker: bool) -> str:
    normalized = ticker.upper().strip()
    symbol_terms = [f"${normalized}"]
    if include_plain_ticker:
        symbol_terms.append(normalized)
    query = " OR ".join(symbol_terms)
    return f"({query}) lang:en -is:retweet"


def _recent_start_time(since: datetime | None) -> str | None:
    if since is None:
        return None
    lower_bound = datetime.now(tz=UTC) - timedelta(days=6, hours=23)
    value = max(_aware_utc(since), lower_bound)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _datetime_from_iso(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC).replace(tzinfo=None)
    except ValueError:
        return None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    return _aware_utc(value).replace(tzinfo=None)


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
