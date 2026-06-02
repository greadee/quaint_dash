"""Provider protocols for sentiment ingestion."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from dashboard.ingestion_sentiment.models import (
    NewsArticleInput,
    SentimentObservationInput,
    SocialPostInput,
)


class NewsProvider(Protocol):
    name: str

    def fetch_articles_for_ticker(
        self,
        ticker: str,
        since: datetime | None,
    ) -> list[NewsArticleInput]:
        ...


class SocialProvider(Protocol):
    name: str

    def fetch_posts_for_ticker(
        self,
        ticker: str,
        since: datetime | None,
    ) -> list[SocialPostInput]:
        ...


class SentimentScorer(Protocol):
    def score_article(
        self,
        article: NewsArticleInput,
        ticker: str,
    ) -> SentimentObservationInput:
        ...

    def score_post(
        self,
        post: SocialPostInput,
        ticker: str,
    ) -> SentimentObservationInput:
        ...

