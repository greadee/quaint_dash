"""Deterministic offline news provider for development and tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from dashboard.news.models import (
    ProviderCapabilities,
    ProviderHealthStatus,
    ProviderNewsArticle,
)

UTC = timezone.utc


def default_mock_articles() -> list[ProviderNewsArticle]:
    return [
        ProviderNewsArticle(
            provider_article_id="mock-nvda-earnings-1",
            headline="NVIDIA raises guidance after data center revenue beats expectations",
            summary="NVIDIA reported stronger data center revenue and raised forward guidance.",
            source_name="Mock Markets",
            published_at=datetime(2026, 6, 30, 14, 30, tzinfo=UTC),
            url="https://example.test/news/nvda-guidance",
            symbols=["NVDA"],
            provider_categories=["earnings", "guidance"],
            importance_score=0.88,
            is_breaking=True,
            raw_payload={"fixture": "nvda-guidance"},
        ),
        ProviderNewsArticle(
            provider_article_id="mock-msft-regulatory-1",
            headline="Regulators open new antitrust probe into Microsoft cloud licensing",
            summary="A regulator opened an antitrust review focused on cloud licensing practices.",
            source_name="Mock Markets",
            published_at=datetime(2026, 6, 30, 13, 0, tzinfo=UTC),
            url="https://example.test/news/msft-antitrust?utm_source=test",
            symbols=["MSFT"],
            provider_categories=["regulatory"],
            importance_score=0.8,
            sentiment_score=-0.45,
            sentiment_label="negative",
            raw_payload={"fixture": "msft-regulatory"},
        ),
        ProviderNewsArticle(
            provider_article_id="mock-service-now-1",
            headline="ServiceNow announces enterprise workflow product launch",
            summary="ServiceNow announced a workflow product update for enterprise customers.",
            source_name="Mock Wire",
            published_at=datetime(2026, 6, 30, 12, 15, tzinfo=UTC),
            url="https://example.test/news/servicenow-product",
            symbols=[],
            entities=["ServiceNow Inc."],
            provider_categories=["product_launch", "technology"],
            importance_score=0.42,
            raw_payload={"fixture": "servicenow-product"},
        ),
    ]


@dataclass(slots=True)
class MockNewsProvider:
    articles: list[ProviderNewsArticle] = field(default_factory=default_mock_articles)
    provider_code: str = "mock_news"
    provider_name: str = "Mock News"
    provider_type: str = "fixture"
    base_url: str | None = "https://example.test"
    capabilities: ProviderCapabilities = field(
        default_factory=lambda: ProviderCapabilities(
            supports_latest_news=True,
            supports_symbol_news=True,
            supports_summaries=True,
            supports_sentiment=True,
            supports_categories=True,
            supports_company_entities=True,
            supports_provider_updates=True,
        )
    )

    def fetch_latest(
        self,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[ProviderNewsArticle]:
        items = self._after_since(self.articles, since)
        return sorted(items, key=lambda item: item.published_at, reverse=True)[:limit]

    def fetch_for_symbols(
        self,
        symbols: list[str],
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[ProviderNewsArticle]:
        wanted = {symbol.upper().strip() for symbol in symbols}
        items = [
            item
            for item in self._after_since(self.articles, since)
            if wanted.intersection({symbol.upper().strip() for symbol in item.symbols})
        ]
        return sorted(items, key=lambda item: item.published_at, reverse=True)[:limit]

    def fetch_article(self, provider_article_id: str) -> ProviderNewsArticle:
        for article in self.articles:
            if article.provider_article_id == provider_article_id:
                return article
        raise LookupError(f"Mock article not found: {provider_article_id}")

    def health_check(self) -> ProviderHealthStatus:
        return ProviderHealthStatus(
            provider_code=self.provider_code,
            status="healthy",
            checked_at=datetime.now(UTC),
            message=f"{len(self.articles)} fixture article(s) available",
        )

    @staticmethod
    def _after_since(
        articles: list[ProviderNewsArticle],
        since: datetime | None,
    ) -> list[ProviderNewsArticle]:
        if since is None:
            return list(articles)
        return [article for article in articles if article.published_at >= since]
