"""Official Reddit API provider for retail sentiment ingestion."""

from __future__ import annotations

import base64
import os
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from dashboard.ingestion_sentiment.models import SocialPostInput
from dashboard.ingestion_sentiment.providers.http_client import JsonHttpClient


DEFAULT_SUBREDDITS = ["stocks", "investing", "wallstreetbets", "SecurityAnalysis"]


class RedditProvider:
    name = "reddit"

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        user_agent: str | None = None,
        subreddits: list[str] | None = None,
        post_limit: int | None = None,
        timeout_seconds: float | None = None,
        http_client: JsonHttpClient | None = None,
    ) -> None:
        self.client_id = client_id or os.getenv("REDDIT_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("REDDIT_CLIENT_SECRET")
        self.user_agent = user_agent or os.getenv("REDDIT_USER_AGENT")
        self.subreddits = subreddits or _env_csv("REDDIT_SUBREDDITS") or DEFAULT_SUBREDDITS
        self.post_limit = post_limit or int(os.getenv("REDDIT_POST_LIMIT", "25"))
        self.timeout_seconds = timeout_seconds or float(os.getenv("REDDIT_REQUEST_TIMEOUT_SECONDS", "10"))
        self.http_client = http_client or JsonHttpClient()
        self._access_token: str | None = None

    def fetch_posts_for_ticker(
        self,
        ticker: str,
        since: datetime | None,
    ) -> list[SocialPostInput]:
        if not all([self.client_id, self.client_secret, self.user_agent]):
            raise RuntimeError(
                "Reddit provider requires REDDIT_CLIENT_ID, "
                "REDDIT_CLIENT_SECRET, and REDDIT_USER_AGENT."
            )

        subreddit_path = "+".join(_clean_subreddit(name) for name in self.subreddits if name.strip())
        if not subreddit_path:
            return []

        payload = self.http_client.request_json(
            "GET",
            f"https://oauth.reddit.com/r/{subreddit_path}/search",
            headers={
                "Authorization": f"Bearer {self._token()}",
                "User-Agent": self.user_agent or "quaint-dash-sentiment/1.0",
            },
            params={
                "q": _query_for_ticker(ticker),
                "restrict_sr": "1",
                "sort": "new",
                "t": "week",
                "limit": min(max(self.post_limit, 1), 100),
            },
            timeout=self.timeout_seconds,
        )
        return [
            post
            for child in payload.get("data", {}).get("children", [])
            if (post := _post_from_child(child, since)) is not None
        ]

    def _token(self) -> str:
        if self._access_token:
            return self._access_token

        credentials = f"{self.client_id}:{self.client_secret}".encode("utf-8")
        encoded_credentials = base64.b64encode(credentials).decode("ascii")
        payload = self.http_client.request_json(
            "POST",
            "https://www.reddit.com/api/v1/access_token",
            headers={
                "Authorization": f"Basic {encoded_credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": self.user_agent or "quaint-dash-sentiment/1.0",
            },
            data=urlencode({"grant_type": "client_credentials"}).encode("ascii"),
            timeout=self.timeout_seconds,
        )
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("Reddit provider did not return an access token.")
        self._access_token = str(token)
        return self._access_token


def _post_from_child(child: dict[str, Any], since: datetime | None) -> SocialPostInput | None:
    data = child.get("data", {})
    if not isinstance(data, dict):
        return None

    post_id = data.get("name") or data.get("id")
    title = data.get("title")
    created_utc = data.get("created_utc")
    if not post_id or not title:
        return None

    published_at = _datetime_from_epoch(created_utc)
    if since is not None and published_at is not None and published_at <= _naive_utc(since):
        return None

    permalink = data.get("permalink")
    url = f"https://www.reddit.com{permalink}" if permalink else data.get("url")
    subreddit = str(data.get("subreddit") or "reddit")
    body = data.get("selftext") or None
    if data.get("removed_by_category") or data.get("over_18"):
        body = None

    return SocialPostInput(
        provider="reddit",
        source_post_id=str(post_id),
        source_name=f"r/{subreddit}",
        author=_string_or_none(data.get("author")),
        title=str(title),
        body=_string_or_none(body),
        url=_string_or_none(url),
        published_at=published_at,
        score=_int_or_none(data.get("score")),
        comment_count=_int_or_none(data.get("num_comments")),
        raw_payload=data,
    )


def _query_for_ticker(ticker: str) -> str:
    normalized = ticker.upper().strip()
    return f'("{normalized}" OR ${normalized})'


def _clean_subreddit(name: str) -> str:
    return name.strip().removeprefix("r/").replace("/", "")


def _env_csv(name: str) -> list[str]:
    return [part.strip() for part in os.getenv(name, "").split(",") if part.strip()]


def _datetime_from_epoch(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=UTC).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


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
