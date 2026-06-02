"""Provider registry for optional sentiment ingestion providers."""

from __future__ import annotations

from dashboard.ingestion_sentiment.providers.base import NewsProvider, SocialProvider
from dashboard.ingestion_sentiment.providers.news_provider import NewsApiProvider
from dashboard.ingestion_sentiment.providers.reddit_provider import RedditProvider
from dashboard.ingestion_sentiment.providers.rss_provider import RssNewsProvider
from dashboard.ingestion_sentiment.providers.x_provider import XProvider


def default_news_providers() -> list[NewsProvider]:
    return [
        RssNewsProvider(feed_urls=[]),
        NewsApiProvider(),
    ]


def default_social_providers() -> list[SocialProvider]:
    return [
        RedditProvider(),
        XProvider(),
    ]

