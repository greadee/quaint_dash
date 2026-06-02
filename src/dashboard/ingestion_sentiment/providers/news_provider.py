"""General financial news API provider placeholder."""

from __future__ import annotations

import os
from datetime import datetime

from dashboard.ingestion_sentiment.models import NewsArticleInput


class NewsApiProvider:
    name = "news_api"

    def fetch_articles_for_ticker(
        self,
        ticker: str,
        since: datetime | None,
    ) -> list[NewsArticleInput]:
        if not any(
            [
                os.getenv("NEWS_API_KEY"),
                os.getenv("ALPHA_VANTAGE_API_KEY"),
                os.getenv("FINNHUB_API_KEY"),
                os.getenv("FMP_API_KEY"),
            ]
        ):
            raise RuntimeError(
                "News provider requires NEWS_API_KEY, ALPHA_VANTAGE_API_KEY, "
                "FINNHUB_API_KEY, or FMP_API_KEY."
            )

        raise NotImplementedError(
            "News API integration is not implemented yet; inject a provider in tests."
        )

