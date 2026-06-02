"""Dataclasses for sentiment ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional


@dataclass(frozen=True, slots=True)
class AssetRef:
    asset_id: str
    ticker: str
    name: Optional[str] = None


@dataclass(frozen=True, slots=True)
class TickerMention:
    asset_id: str
    ticker: str
    relevance_score: float
    mention_reason: str


@dataclass(frozen=True, slots=True)
class NewsArticleInput:
    source_name: str
    provider: str
    title: str
    source_item_id: Optional[str] = None
    summary: Optional[str] = None
    url: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SocialPostInput:
    provider: str
    source_post_id: str
    source_name: str
    author: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    score: Optional[int] = None
    comment_count: Optional[int] = None
    like_count: Optional[int] = None
    repost_count: Optional[int] = None
    reply_count: Optional[int] = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SentimentObservationInput:
    asset_id: str
    ticker: str
    item_type: str
    item_id: int
    provider: str
    sentiment_label: str
    sentiment_score: float
    confidence: float
    relevance_score: float = 1.0
    source_weight: float = 1.0
    engagement_weight: float = 1.0
    explanation: Optional[str] = None
    observed_at: Optional[datetime] = None


@dataclass(frozen=True, slots=True)
class SentimentDailySnapshot:
    asset_id: str
    ticker: str
    snapshot_date: date
    retail_sentiment_score: Optional[float]
    news_sentiment_score: Optional[float]
    analyst_sentiment_score: Optional[float]
    blended_sentiment_score: Optional[float]
    reddit_post_count: int = 0
    x_post_count: int = 0
    article_count: int = 0
    bullish_count: int = 0
    neutral_count: int = 0
    bearish_count: int = 0
    sentiment_momentum_1d: Optional[float] = None
    sentiment_momentum_7d: Optional[float] = None
    sentiment_momentum_30d: Optional[float] = None
    unusual_volume_flag: bool = False


@dataclass(frozen=True, slots=True)
class FactorSnapshotInput:
    asset_id: str
    ticker: str
    snapshot_date: date
    growth_score: Optional[float] = None
    value_score: Optional[float] = None
    quality_score: Optional[float] = None
    momentum_score: Optional[float] = None
    defensive_score: Optional[float] = None
    dividend_score: Optional[float] = None
    volatility_score: Optional[float] = None
    revision_score: Optional[float] = None
    overall_factor_score: Optional[float] = None
    factor_labels: list[str] = field(default_factory=list)
    explanation: Optional[str] = None


@dataclass(frozen=True, slots=True)
class QuantRatingSnapshotInput:
    asset_id: str
    ticker: str
    snapshot_date: date
    overall_quant_score: Optional[float]
    overall_quant_rating: Optional[str]
    growth_rating: Optional[str] = None
    value_rating: Optional[str] = None
    quality_rating: Optional[str] = None
    momentum_rating: Optional[str] = None
    defensive_rating: Optional[str] = None
    dividend_rating: Optional[str] = None
    volatility_rating: Optional[str] = None
    factor_profile: Optional[str] = None
    explanation: Optional[str] = None


@dataclass(frozen=True, slots=True)
class SentimentIngestionJob:
    job_id: int
    asset_id: str
    domain: str
    job_type: str
    dataset: str
    status: str
    priority: int
    requested_start_date: Optional[date]
    requested_end_date: Optional[date]
    attempt_count: int
    error_message: Optional[str]

