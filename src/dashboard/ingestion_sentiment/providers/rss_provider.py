"""RSS provider shell for compliant feed ingestion."""

from __future__ import annotations

from datetime import datetime

from dashboard.ingestion_sentiment.models import NewsArticleInput


class RssNewsProvider:
    name = "rss"

    def __init__(self, feed_urls: list[str] | None = None) -> None:
        self.feed_urls = feed_urls or []

    def fetch_articles_for_ticker(
        self,
        ticker: str,
        since: datetime | None,
    ) -> list[NewsArticleInput]:
        if not self.feed_urls:
            return []

        raise NotImplementedError(
            "RSS parsing is not implemented yet; inject a provider in tests."
        )

