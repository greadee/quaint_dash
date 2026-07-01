"""Deterministic news importance and relevance scoring."""

from __future__ import annotations

from datetime import UTC, datetime
from math import exp

from dashboard.news.models import AssetNewsMatch, NormalizedNewsArticle

CATEGORY_WEIGHTS = {
    "bankruptcy": 0.95,
    "merger_acquisition": 0.9,
    "guidance": 0.8,
    "regulatory": 0.8,
    "earnings": 0.75,
    "litigation": 0.75,
    "restructuring": 0.75,
    "capital_raise": 0.7,
    "management_change": 0.65,
    "central_bank": 0.65,
    "buyback": 0.6,
    "dividend": 0.55,
    "analyst_rating": 0.5,
    "product_launch": 0.45,
    "press_release": 0.25,
    "general": 0.3,
}


def score_importance(article: NormalizedNewsArticle) -> float:
    category_score = max(CATEGORY_WEIGHTS.get(category, 0.35) for category in article.categories)
    provider_score = article.provider_importance_score if article.provider_importance_score is not None else 0.5
    score = (category_score * 0.55) + (provider_score * 0.25)
    if article.is_breaking:
        score += 0.15
    if article.is_correction or article.is_retracted:
        score += 0.1
    if article.is_press_release:
        score -= 0.08
    return round(max(0.0, min(1.0, score)), 4)


def score_article_relevance(
    article: NormalizedNewsArticle,
    matches: list[AssetNewsMatch],
    now: datetime | None = None,
) -> float:
    asset_relevance = max((match.relevance_score * match.confidence_score for match in matches), default=0.25)
    recency = recency_decay(article.published_at, now=now)
    score = asset_relevance * article.importance_score * recency
    return round(max(0.0, min(1.0, score)), 4)


def score_portfolio_relevance(
    article_score: float,
    position_weight: float | None,
    exposure_confidence: float,
) -> float:
    weight = max(0.0, min(0.35, position_weight or 0.0))
    weighted = article_score * (0.5 + weight * 1.5) * max(0.0, min(1.0, exposure_confidence))
    return round(max(0.0, min(1.0, weighted)), 4)


def recency_decay(published_at: datetime, now: datetime | None = None) -> float:
    reference = now or datetime.now(UTC)
    published = published_at if published_at.tzinfo else published_at.replace(tzinfo=UTC)
    age_hours = max(0.0, (reference - published.astimezone(UTC)).total_seconds() / 3600)
    return 0.25 + 0.75 * exp(-age_hours / 72)
