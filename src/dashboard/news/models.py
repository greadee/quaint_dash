"""Domain models for normalized financial news."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    supports_latest_news: bool = True
    supports_symbol_news: bool = False
    supports_full_article_body: bool = False
    supports_summaries: bool = False
    supports_images: bool = False
    supports_sentiment: bool = False
    supports_categories: bool = False
    supports_streaming: bool = False
    supports_webhooks: bool = False
    supports_languages: bool = False
    supports_regions: bool = False
    supports_company_entities: bool = False
    supports_press_releases: bool = False
    supports_provider_updates: bool = False
    supports_article_corrections: bool = False


@dataclass(frozen=True, slots=True)
class ProviderHealthStatus:
    provider_code: str
    status: str
    checked_at: datetime
    message: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderNewsArticle:
    provider_article_id: str
    headline: str
    source_name: str
    published_at: datetime
    url: str | None = None
    summary: str | None = None
    subheadline: str | None = None
    article_body: str | None = None
    image_url: str | None = None
    author: str | None = None
    language: str | None = None
    updated_at: datetime | None = None
    symbols: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    provider_categories: list[str] = field(default_factory=list)
    sentiment_score: float | None = None
    sentiment_label: str | None = None
    importance_score: float | None = None
    is_breaking: bool = False
    is_press_release: bool = False
    is_correction: bool = False
    is_retracted: bool = False
    is_paywalled: bool = False
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NormalizedNewsArticle:
    provider_code: str
    provider_article_id: str
    headline: str
    source_name: str
    published_at: datetime
    canonical_url: str | None
    summary: str | None = None
    subheadline: str | None = None
    article_body: str | None = None
    image_url: str | None = None
    author: str | None = None
    language: str = "en"
    provider_updated_at: datetime | None = None
    symbols: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    provider_categories: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    sentiment_score: float | None = None
    sentiment_label: str | None = None
    provider_importance_score: float | None = None
    importance_score: float = 0.0
    is_breaking: bool = False
    is_press_release: bool = False
    is_correction: bool = False
    is_retracted: bool = False
    is_paywalled: bool = False
    content_hash: str = ""
    headline_hash: str = ""
    story_fingerprint: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AssetNewsMatch:
    asset_id: str
    ticker: str
    relevance_score: float
    confidence_score: float
    match_method: str
    mention_type: str = "company"
    is_primary_entity: bool = False
    provider_assigned: bool = False


@dataclass(frozen=True, slots=True)
class NewsIngestionResult:
    provider_code: str
    articles_received: int = 0
    articles_inserted: int = 0
    articles_updated: int = 0
    articles_rejected: int = 0
    asset_links_written: int = 0
    categories_written: int = 0
    clusters_written: int = 0
    status: str = "success"
    error_message: str | None = None
