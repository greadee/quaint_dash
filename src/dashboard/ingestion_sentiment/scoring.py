"""Deterministic sentiment scoring and daily aggregation."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from math import log1p
from statistics import mean, pstdev

from dashboard.ingestion_sentiment.models import (
    FactorSnapshotInput,
    NewsArticleInput,
    QuantRatingSnapshotInput,
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


class FactorScorer:
    def __init__(self, repo: SentimentIngestionRepository) -> None:
        self.repo = repo

    def refresh_factor_snapshot(
        self,
        asset_id: str,
        ticker: str,
        snapshot_date: date,
    ) -> FactorSnapshotInput:
        prices = self.repo.price_history_for_factor(asset_id, snapshot_date)
        metadata = self.repo.asset_factor_metadata(asset_id)
        dividends = self.repo.dividends_for_factor(asset_id, snapshot_date)

        close_rows = [(row[0], row[2] if row[2] is not None else row[1]) for row in prices]
        close_rows = [(d, c) for d, c in close_rows if c is not None and c > 0]
        closes = [row[1] for row in close_rows]
        explanations: list[str] = []

        momentum_score = momentum_factor_score(close_rows)
        if momentum_score is None:
            explanations.append("momentum missing: fewer than 63 trading days of prices")

        realized_vol = realized_volatility(closes)
        volatility_score = volatility_factor_score(realized_vol)
        if volatility_score is None:
            explanations.append("volatility missing: fewer than 2 daily closes")

        beta = metadata[0] if metadata else None
        defensive_score = defensive_factor_score(beta, volatility_score)
        if defensive_score is None:
            explanations.append("defensive missing: beta and volatility unavailable")

        dividend_score = dividend_factor_score(dividends, closes[-1] if closes else None)
        if dividend_score is None:
            explanations.append("dividend missing: no dividend yield data")

        explanations.extend(
            [
                "growth missing: financial statement growth inputs unavailable",
                "value missing: valuation inputs unavailable",
                "quality missing: profitability inputs unavailable",
                "revision missing: analyst estimate inputs unavailable",
            ]
        )

        overall = average_available(
            [
                momentum_score,
                defensive_score,
                dividend_score,
                volatility_score,
            ]
        )
        labels = factor_labels(
            growth_score=None,
            value_score=None,
            quality_score=None,
            momentum_score=momentum_score,
            defensive_score=defensive_score,
            dividend_score=dividend_score,
            volatility_score=volatility_score,
        )

        snapshot = FactorSnapshotInput(
            asset_id=asset_id,
            ticker=ticker.upper(),
            snapshot_date=snapshot_date,
            momentum_score=momentum_score,
            defensive_score=defensive_score,
            dividend_score=dividend_score,
            volatility_score=volatility_score,
            overall_factor_score=overall,
            factor_labels=labels,
            explanation="; ".join(explanations),
        )
        self.repo.upsert_factor_snapshot(snapshot)
        return snapshot


class QuantRatingScorer:
    def __init__(self, repo: SentimentIngestionRepository) -> None:
        self.repo = repo

    def refresh_quant_rating(
        self,
        asset_id: str,
        ticker: str,
        snapshot_date: date,
    ) -> QuantRatingSnapshotInput:
        factor = self.repo.factor_snapshot(asset_id, snapshot_date)
        if factor is None:
            factor = FactorScorer(self.repo).refresh_factor_snapshot(
                asset_id=asset_id,
                ticker=ticker,
                snapshot_date=snapshot_date,
            )

        profile = factor_profile(factor)
        snapshot = QuantRatingSnapshotInput(
            asset_id=asset_id,
            ticker=ticker.upper(),
            snapshot_date=snapshot_date,
            overall_quant_score=factor.overall_factor_score,
            overall_quant_rating=quant_rating(factor.overall_factor_score),
            growth_rating=component_rating(factor.growth_score),
            value_rating=component_rating(factor.value_score),
            quality_rating=component_rating(factor.quality_score),
            momentum_rating=component_rating(factor.momentum_score),
            defensive_rating=component_rating(factor.defensive_score),
            dividend_rating=component_rating(factor.dividend_score),
            volatility_rating=component_rating(factor.volatility_score),
            factor_profile=profile,
            explanation=f"Internal quant rating from factor snapshot: {profile}",
        )
        self.repo.upsert_quant_rating_snapshot(snapshot)
        return snapshot


def momentum_factor_score(close_rows: list[tuple[date, float]]) -> float | None:
    if len(close_rows) < 63:
        return None

    latest = close_rows[-1][1]
    components: list[float] = []
    for lookback in [63, 126, 252]:
        if len(close_rows) > lookback and close_rows[-lookback - 1][1] > 0:
            ret = latest / close_rows[-lookback - 1][1] - 1.0
            components.append(score_return(ret))

    if len(close_rows) >= 200:
        ma200 = mean([row[1] for row in close_rows[-200:]])
        components.append(80.0 if latest >= ma200 else 35.0)

    return average_available(components)


def score_return(value: float) -> float:
    if value >= 0.30:
        return 95.0
    if value >= 0.15:
        return 80.0
    if value >= 0.05:
        return 65.0
    if value >= -0.05:
        return 50.0
    if value >= -0.15:
        return 35.0
    return 20.0


def realized_volatility(closes: list[float]) -> float | None:
    if len(closes) < 2:
        return None

    returns = [
        closes[i] / closes[i - 1] - 1.0
        for i in range(1, len(closes))
        if closes[i - 1] > 0
    ]
    if not returns:
        return None
    return pstdev(returns) * (252 ** 0.5)


def volatility_factor_score(volatility: float | None) -> float | None:
    if volatility is None:
        return None
    if volatility <= 0.15:
        return 90.0
    if volatility <= 0.25:
        return 75.0
    if volatility <= 0.40:
        return 55.0
    if volatility <= 0.60:
        return 35.0
    return 20.0


def defensive_factor_score(beta: float | None, volatility_score: float | None) -> float | None:
    components: list[float] = []
    if beta is not None:
        if beta <= 0.75:
            components.append(90.0)
        elif beta <= 1.0:
            components.append(70.0)
        elif beta <= 1.3:
            components.append(45.0)
        else:
            components.append(25.0)
    if volatility_score is not None:
        components.append(volatility_score)
    return average_available(components)


def dividend_factor_score(dividends: list[tuple[date, float | None]], latest_close: float | None) -> float | None:
    if latest_close is None or latest_close <= 0:
        return None

    annual_dividend = sum(row[1] or 0.0 for row in dividends)
    if annual_dividend <= 0:
        return None

    dividend_yield = annual_dividend / latest_close
    if dividend_yield >= 0.04:
        return 90.0
    if dividend_yield >= 0.025:
        return 75.0
    if dividend_yield >= 0.01:
        return 55.0
    return 30.0


def factor_labels(
    growth_score: float | None,
    value_score: float | None,
    quality_score: float | None,
    momentum_score: float | None,
    defensive_score: float | None,
    dividend_score: float | None,
    volatility_score: float | None,
) -> list[str]:
    labels: list[str] = []
    if growth_score is not None and growth_score >= 70:
        labels.append("Growth")
    if value_score is not None and value_score >= 70:
        labels.append("Value")
    if quality_score is not None and quality_score >= 70:
        labels.append("Quality")
    if momentum_score is not None and momentum_score >= 70:
        labels.append("Momentum")
    if defensive_score is not None and defensive_score >= 70:
        labels.append("Defensive")
    if dividend_score is not None and dividend_score >= 70:
        labels.append("Dividend")
    if (
        momentum_score is not None
        and momentum_score >= 70
        and quality_score is not None
        and quality_score < 45
    ):
        labels.append("Low Quality Momentum")
    if volatility_score is not None and volatility_score < 40 and defensive_score is not None and defensive_score < 45:
        labels.append("Cyclical")
    return labels


def factor_profile(factor: FactorSnapshotInput) -> str | None:
    labels = factor.factor_labels
    if {"Growth", "Quality", "Momentum"}.issubset(labels):
        return "Compounder"
    if "Growth" in labels and "Momentum" in labels and "Quality" not in labels:
        return "Speculative Growth"
    if "Low Quality Momentum" in labels:
        return "Low Quality Momentum"
    if "Cyclical" in labels:
        return "Cyclical"
    for label in ["Momentum", "Quality", "Growth", "Value", "Defensive", "Dividend"]:
        if label in labels:
            return label
    return None


def quant_rating(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 80:
        return "Strong Buy"
    if score >= 65:
        return "Buy"
    if score >= 45:
        return "Hold"
    if score >= 30:
        return "Sell"
    return "Strong Sell"


def component_rating(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 45:
        return "C"
    if score >= 30:
        return "D"
    return "F"


def average_available(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present) / len(present)
