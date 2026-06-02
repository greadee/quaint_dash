"""Deterministic sentiment scoring and daily aggregation."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from math import log1p

from dashboard.ingestion_sentiment.models import (
    NewsArticleInput,
    SentimentDailySnapshot,
    SentimentObservationInput,
    SocialPostInput,
)
from dashboard.ingestion_sentiment.repo import SentimentIngestionRepository


BULLISH_KEYWORDS = {
    "beat",
    "beats",
    "bullish",
    "buy",
    "growth",
    "outperform",
    "raise",
    "raised",
    "raises",
    "strong",
    "upside",
}

BEARISH_KEYWORDS = {
    "bearish",
    "cut",
    "downgrade",
    "downgraded",
    "miss",
    "misses",
    "risk",
    "sell",
    "slowing",
    "weak",
}


class RulesBasedSentimentScorer:
    def score_article(
        self,
        article: NewsArticleInput,
        ticker: str,
    ) -> SentimentObservationInput:
        text = " ".join(part for part in [article.title, article.summary] if part)
        observed_at = article.published_at or datetime.now()
        score = self._score_text(text)
        return SentimentObservationInput(
            asset_id=ticker.upper(),
            ticker=ticker.upper(),
            item_type="news_article",
            item_id=0,
            provider=article.provider,
            observed_at=observed_at,
            **score,
        )

    def score_post(
        self,
        post: SocialPostInput,
        ticker: str,
    ) -> SentimentObservationInput:
        text = " ".join(part for part in [post.title, post.body] if part)
        observed_at = post.published_at or datetime.now()
        score = self._score_text(text)
        engagement_weight = engagement_weight_for_post(post)
        return SentimentObservationInput(
            asset_id=ticker.upper(),
            ticker=ticker.upper(),
            item_type="social_post",
            item_id=0,
            provider=post.provider,
            engagement_weight=engagement_weight,
            observed_at=observed_at,
            **score,
        )

    def with_item_context(
        self,
        observation: SentimentObservationInput,
        asset_id: str,
        ticker: str,
        item_id: int,
        relevance_score: float,
    ) -> SentimentObservationInput:
        return replace(
            observation,
            asset_id=asset_id,
            ticker=ticker.upper(),
            item_id=item_id,
            relevance_score=relevance_score,
        )

    def _score_text(self, text: str) -> dict[str, object]:
        tokens = normalized_tokens(text)
        bullish_count = sum(1 for token in tokens if token in BULLISH_KEYWORDS)
        bearish_count = sum(1 for token in tokens if token in BEARISH_KEYWORDS)
        signal = bullish_count - bearish_count
        signal_strength = abs(signal)

        if signal_strength == 0:
            label = "neutral"
            sentiment_score = 0.0
        else:
            label = "bullish" if signal > 0 else "bearish"
            sentiment_score = max(-1.0, min(1.0, signal / 4.0))

        confidence = min(0.95, 0.35 + 0.15 * (bullish_count + bearish_count))
        explanation = (
            f"bullish_keywords={bullish_count}; "
            f"bearish_keywords={bearish_count}; "
            f"rules_based_score={sentiment_score:.2f}"
        )

        return {
            "sentiment_label": label,
            "sentiment_score": sentiment_score,
            "confidence": confidence,
            "explanation": explanation,
        }


class DailySentimentAggregator:
    BUCKET_WEIGHTS = {
        "retail": 0.35,
        "news": 0.45,
        "analyst": 0.20,
    }

    def __init__(self, repo: SentimentIngestionRepository) -> None:
        self.repo = repo

    def aggregate_for_ticker(
        self,
        asset_id: str,
        ticker: str,
        snapshot_date: date,
    ) -> SentimentDailySnapshot:
        observations = self.repo.sentiment_observations_for_date(asset_id, snapshot_date)
        buckets: dict[str, list[tuple[float, float]]] = {
            "retail": [],
            "news": [],
            "analyst": [],
        }
        counts = {
            "reddit": 0,
            "x": 0,
            "article": 0,
            "bullish": 0,
            "neutral": 0,
            "bearish": 0,
        }

        for row in observations:
            (
                _asset_id,
                _ticker,
                item_type,
                _item_id,
                provider,
                sentiment_label,
                sentiment_score,
                confidence,
                relevance_score,
                source_weight,
                engagement_weight,
                _observed_at,
            ) = row
            bucket = bucket_for_observation(item_type, provider)
            weight = confidence * relevance_score * source_weight * engagement_weight
            buckets[bucket].append((sentiment_score, weight))

            provider_lower = provider.lower()
            if provider_lower == "reddit":
                counts["reddit"] += 1
            elif provider_lower in {"x", "twitter"}:
                counts["x"] += 1
            if item_type == "news_article":
                counts["article"] += 1
            counts[sentiment_label] += 1

        retail_score = weighted_average(buckets["retail"])
        news_score = weighted_average(buckets["news"])
        analyst_score = weighted_average(buckets["analyst"])
        blended_score = blended_bucket_score(
            {
                "retail": retail_score,
                "news": news_score,
                "analyst": analyst_score,
            },
            self.BUCKET_WEIGHTS,
        )
        total_count = counts["reddit"] + counts["x"] + counts["article"]
        average_count = self.repo.recent_average_item_count(asset_id, snapshot_date)

        snapshot = SentimentDailySnapshot(
            asset_id=asset_id,
            ticker=ticker.upper(),
            snapshot_date=snapshot_date,
            retail_sentiment_score=retail_score,
            news_sentiment_score=news_score,
            analyst_sentiment_score=analyst_score,
            blended_sentiment_score=blended_score,
            reddit_post_count=counts["reddit"],
            x_post_count=counts["x"],
            article_count=counts["article"],
            bullish_count=counts["bullish"],
            neutral_count=counts["neutral"],
            bearish_count=counts["bearish"],
            sentiment_momentum_1d=self._momentum(asset_id, snapshot_date, blended_score, 1),
            sentiment_momentum_7d=self._momentum(asset_id, snapshot_date, blended_score, 7),
            sentiment_momentum_30d=self._momentum(asset_id, snapshot_date, blended_score, 30),
            unusual_volume_flag=bool(
                average_count is not None
                and average_count > 0
                and total_count >= 5
                and total_count > 2.0 * average_count
            ),
        )
        self.repo.upsert_ticker_sentiment_daily(snapshot)
        return snapshot

    def _momentum(
        self,
        asset_id: str,
        snapshot_date: date,
        blended_score: float | None,
        days: int,
    ) -> float | None:
        if blended_score is None:
            return None

        previous = self.repo.daily_blended_score(asset_id, snapshot_date - timedelta(days=days))
        if previous is None:
            return None
        return blended_score - previous


def normalized_tokens(text: str) -> list[str]:
    return [
        token.strip(".,!?;:()[]{}'\"").lower()
        for token in text.split()
        if token.strip(".,!?;:()[]{}'\"")
    ]


def engagement_weight_for_post(post: SocialPostInput) -> float:
    engagement = sum(
        value or 0
        for value in [
            post.score,
            post.comment_count,
            post.like_count,
            post.repost_count,
            post.reply_count,
        ]
    )
    return min(3.0, 1.0 + log1p(max(0, engagement)) / 5.0)


def bucket_for_observation(item_type: str, provider: str) -> str:
    provider_lower = provider.lower()
    if item_type == "social_post" or provider_lower in {"reddit", "x", "twitter"}:
        return "retail"
    if item_type == "analyst_rating":
        return "analyst"
    return "news"


def weighted_average(values: list[tuple[float, float]]) -> float | None:
    total_weight = sum(weight for _score, weight in values)
    if total_weight <= 0:
        return None
    return sum(score * weight for score, weight in values) / total_weight


def blended_bucket_score(
    bucket_scores: dict[str, float | None],
    bucket_weights: dict[str, float],
) -> float | None:
    available = {
        bucket: score
        for bucket, score in bucket_scores.items()
        if score is not None
    }
    if not available:
        return None

    total_weight = sum(bucket_weights[bucket] for bucket in available)
    return sum(
        score * (bucket_weights[bucket] / total_weight)
        for bucket, score in available.items()
    )

