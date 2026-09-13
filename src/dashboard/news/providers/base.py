"""Provider protocol for financial news adapters."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from dashboard.news.models import ProviderCapabilities, ProviderHealthStatus, ProviderNewsArticle


class NewsProvider(Protocol):
    provider_code: str
    provider_name: str
    provider_type: str
    base_url: str | None
    capabilities: ProviderCapabilities

    def fetch_latest(
        self,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[ProviderNewsArticle]:
        ...

    def fetch_for_symbols(
        self,
        symbols: list[str],
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[ProviderNewsArticle]:
        ...

    def fetch_article(self, provider_article_id: str) -> ProviderNewsArticle:
        ...

    def health_check(self) -> ProviderHealthStatus:
        ...
