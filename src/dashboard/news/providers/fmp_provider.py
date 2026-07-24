"""Financial Modeling Prep stable API adapter for normalized news."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from dotenv import load_dotenv

from dashboard.ingestion.rate_limits import (
    InMemoryRateLimiter,
    RateLimitExceeded,
    RateLimitPolicy,
    default_rate_limiter,
    fmp_rate_limit_policy,
)
from dashboard.news.models import ProviderCapabilities, ProviderHealthStatus, ProviderNewsArticle

load_dotenv()

UTC = timezone.utc


class FmpNewsProviderError(RuntimeError):
    """Raised for FMP news adapter failures with secret-safe messages."""


@dataclass(slots=True)
class FmpNewsProvider:
    """Adapter for FMP stable stock-news and press-release endpoints."""

    api_key: str | None = None
    base_url: str = "https://financialmodelingprep.com/stable"
    rate_limiter: InMemoryRateLimiter | None = None
    rate_limit_policy: RateLimitPolicy | None = None
    provider_code: str = "fmp_news"
    provider_name: str = "Financial Modeling Prep News"
    provider_type: str = "api"
    capabilities: ProviderCapabilities = field(
        default_factory=lambda: ProviderCapabilities(
            supports_latest_news=True,
            supports_symbol_news=True,
            supports_summaries=True,
            supports_images=True,
            supports_categories=True,
            supports_press_releases=True,
        )
    )

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.getenv("FMP_API_KEY")
        self.base_url = self.base_url.rstrip("/")
        self.rate_limiter = self.rate_limiter or default_rate_limiter()
        self.rate_limit_policy = self.rate_limit_policy or fmp_rate_limit_policy()
        if not self.api_key:
            raise FmpNewsProviderError("FMP_API_KEY is not configured")

    def fetch_latest(
        self,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[ProviderNewsArticle]:
        pages = max(1, min(5, (limit + 99) // 100))
        articles: list[ProviderNewsArticle] = []
        for page in range(pages):
            data = self._get_json("news/stock-latest", {"page": page, "limit": min(100, limit)})
            articles.extend(self._parse_items(data, default_symbols=[]))
            if len(articles) >= limit:
                break
        return self._filtered(articles, since, limit)

    def fetch_for_symbols(
        self,
        symbols: list[str],
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[ProviderNewsArticle]:
        normalized_symbols = _normalize_symbols(symbols)
        if not normalized_symbols:
            return []
        articles: dict[str, ProviderNewsArticle] = {}
        per_symbol_limit = max(10, min(100, limit))
        for symbol in normalized_symbols:
            data = self._get_json(
                "news/stock",
                {"symbols": symbol, "page": 0, "limit": per_symbol_limit},
            )
            for article in self._parse_items(data, default_symbols=[symbol]):
                articles.setdefault(article.provider_article_id, article)
        return self._filtered(list(articles.values()), since, limit)

    def fetch_press_releases_for_symbols(
        self,
        symbols: list[str],
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[ProviderNewsArticle]:
        normalized_symbols = _normalize_symbols(symbols)
        if not normalized_symbols:
            return []
        articles: dict[str, ProviderNewsArticle] = {}
        per_symbol_limit = max(10, min(100, limit))
        for symbol in normalized_symbols:
            data = self._get_json(
                "news/press-releases",
                {"symbols": symbol, "page": 0, "limit": per_symbol_limit},
            )
            for article in self._parse_items(data, default_symbols=[symbol], force_press_release=True):
                articles.setdefault(article.provider_article_id, article)
        return self._filtered(list(articles.values()), since, limit)

    def fetch_article(self, provider_article_id: str) -> ProviderNewsArticle:
        raise LookupError("FMP stable news API does not expose a detail lookup by provider article ID")

    def health_check(self) -> ProviderHealthStatus:
        try:
            self._get_json("news/stock-latest", {"page": 0, "limit": 1})
        except Exception as exc:
            return ProviderHealthStatus(
                provider_code=self.provider_code,
                status="failed",
                checked_at=datetime.now(UTC),
                message=str(exc),
            )
        return ProviderHealthStatus(
            provider_code=self.provider_code,
            status="healthy",
            checked_at=datetime.now(UTC),
            message="FMP stable news endpoint returned data",
        )

    def _get_json(self, path: str, params: dict[str, Any]) -> Any:
        query = dict(params)
        query["apikey"] = self.api_key
        url = f"{self.base_url}/{path.lstrip('/')}?{urllib.parse.urlencode(query)}"
        try:
            self.rate_limiter.acquire(self.rate_limit_policy)
            with urllib.request.urlopen(url, timeout=20) as response:
                payload = response.read().decode("utf-8")
        except RateLimitExceeded:
            raise
        except urllib.error.HTTPError as exc:
            if exc.code == 401 or exc.code == 403:
                raise FmpNewsProviderError("FMP authentication or entitlement failed") from exc
            if exc.code == 429:
                raise RateLimitExceeded("FMP rate limit exceeded") from exc
            raise FmpNewsProviderError(f"FMP HTTP error {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise FmpNewsProviderError(f"FMP connection error: {exc.reason}") from exc
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise FmpNewsProviderError("FMP returned malformed JSON") from exc
        if isinstance(data, dict) and "Error Message" in data:
            message = str(data["Error Message"])
            if "limit" in message.lower() or "rate" in message.lower():
                raise RateLimitExceeded("FMP rate limit exceeded")
            raise FmpNewsProviderError(message)
        return data

    def _parse_items(
        self,
        data: Any,
        *,
        default_symbols: list[str],
        force_press_release: bool = False,
    ) -> list[ProviderNewsArticle]:
        if isinstance(data, dict):
            items = data.get("data") or data.get("content") or data.get("results") or []
        else:
            items = data or []
        if not isinstance(items, list):
            raise FmpNewsProviderError("FMP returned an unexpected news payload shape")
        parsed: list[ProviderNewsArticle] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            headline = item.get("title") or item.get("headline")
            published = _parse_fmp_datetime(
                item.get("publishedDate") or item.get("published_at") or item.get("date")
            )
            if not headline or published is None:
                continue
            url = item.get("url") or item.get("link")
            symbols = _symbols_from_item(item, default_symbols)
            is_press_release = force_press_release or _looks_like_press_release(item)
            categories = list(dict.fromkeys([
                *(["press_release"] if is_press_release else []),
                *_category_values(item),
            ]))
            parsed.append(
                ProviderNewsArticle(
                    provider_article_id=str(item.get("id") or _stable_item_id(url, headline, published, symbols)),
                    headline=str(headline),
                    source_name=str(item.get("site") or item.get("publisher") or item.get("source") or "FMP"),
                    published_at=published,
                    url=str(url) if url else None,
                    summary=item.get("text") or item.get("summary") or item.get("snippet"),
                    image_url=item.get("image"),
                    symbols=symbols,
                    provider_categories=categories or ["general"],
                    is_press_release=is_press_release,
                    raw_payload={
                        key: value
                        for key, value in item.items()
                        if key.lower() not in {"apikey", "api_key", "token"}
                    },
                )
            )
        return parsed

    @staticmethod
    def _filtered(
        articles: list[ProviderNewsArticle],
        since: datetime | None,
        limit: int,
    ) -> list[ProviderNewsArticle]:
        cutoff = since.astimezone(UTC) if since and since.tzinfo else since
        if cutoff is not None:
            articles = [item for item in articles if item.published_at >= cutoff]
        return sorted(articles, key=lambda item: item.published_at, reverse=True)[:limit]


def _parse_fmp_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for candidate in (text, text.replace(" ", "T")):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
        except ValueError:
            continue
    return None


def _normalize_symbols(symbols: list[str]) -> list[str]:
    normalized: list[str] = []
    for symbol in symbols:
        text = str(symbol or "").strip().upper()
        if not text or text in normalized:
            continue
        normalized.append(text)
    return normalized


def _symbols_from_item(item: dict[str, Any], default_symbols: list[str]) -> list[str]:
    raw = item.get("symbol") or item.get("symbols") or item.get("ticker") or item.get("tickers")
    if isinstance(raw, str):
        values = [part.strip() for part in raw.replace(";", ",").split(",")]
    elif isinstance(raw, list):
        values = [str(part).strip() for part in raw]
    else:
        values = default_symbols
    return _normalize_symbols(values)


def _category_values(item: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("category", "type"):
        value = item.get(key)
        if value:
            values.append(str(value))
    return values


def _looks_like_press_release(item: dict[str, Any]) -> bool:
    text = " ".join(str(item.get(key) or "") for key in ("title", "site", "source", "url")).lower()
    return "press release" in text or "prnewswire" in text or "globenewswire" in text


def _stable_item_id(
    url: str | None,
    headline: str,
    published: datetime,
    symbols: list[str],
) -> str:
    seed = "\n".join([url or "", headline, published.isoformat(), ",".join(sorted(symbols))])
    return "fmp-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
