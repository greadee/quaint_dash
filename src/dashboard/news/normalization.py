"""Provider response normalization for financial news."""

from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dashboard.news.models import NormalizedNewsArticle, ProviderNewsArticle

_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
UTC = timezone.utc


class NewsValidationError(ValueError):
    """Provider payload cannot be safely normalized."""


def normalize_provider_article(provider_code: str, article: ProviderNewsArticle) -> NormalizedNewsArticle:
    headline = clean_text(article.headline)
    if not headline:
        raise NewsValidationError("provider article is missing a headline")
    if not article.provider_article_id.strip():
        raise NewsValidationError("provider article is missing provider_article_id")

    published_at = normalize_datetime(article.published_at)
    if published_at > datetime.now(UTC) + timedelta(minutes=10):
        raise NewsValidationError("provider article has a future published timestamp")

    canonical_url = normalize_url(article.url)
    summary = clean_text(article.summary)
    categories = [normalize_category_code(item) for item in article.provider_categories]
    categories = [item for item in categories if item]
    if article.is_press_release and "press_release" not in categories:
        categories.append("press_release")
    if not categories:
        categories.append("general")

    content_hash = stable_hash(
        [
            provider_code,
            article.provider_article_id,
            headline,
            summary or "",
            canonical_url or "",
            published_at.isoformat(),
        ]
    )
    headline_hash = stable_hash([normalize_for_hash(headline)])
    story_fingerprint = stable_hash(
        [
            normalize_for_hash(headline),
            published_at.strftime("%Y-%m-%dT%H"),
            ",".join(sorted(symbol.upper().strip() for symbol in article.symbols)),
            ",".join(sorted(categories)),
        ]
    )
    return NormalizedNewsArticle(
        provider_code=provider_code,
        provider_article_id=article.provider_article_id.strip(),
        headline=headline,
        source_name=clean_text(article.source_name) or provider_code,
        published_at=published_at,
        canonical_url=canonical_url,
        summary=summary,
        subheadline=clean_text(article.subheadline),
        article_body=clean_text(article.article_body),
        image_url=normalize_url(article.image_url),
        author=clean_text(article.author),
        language=normalize_language(article.language),
        provider_updated_at=normalize_datetime(article.updated_at) if article.updated_at else None,
        symbols=[normalize_symbol(symbol) for symbol in article.symbols if normalize_symbol(symbol)],
        entities=[clean_text(entity) for entity in article.entities if clean_text(entity)],
        provider_categories=[clean_text(item) for item in article.provider_categories if clean_text(item)],
        categories=categories,
        sentiment_score=normalize_sentiment_score(article.sentiment_score),
        sentiment_label=normalize_sentiment_label(article.sentiment_label, article.sentiment_score),
        provider_importance_score=article.importance_score,
        importance_score=0.0,
        is_breaking=article.is_breaking,
        is_press_release=article.is_press_release or "press_release" in categories,
        is_correction=article.is_correction,
        is_retracted=article.is_retracted,
        is_paywalled=article.is_paywalled,
        content_hash=content_hash,
        headline_hash=headline_hash,
        story_fingerprint=story_fingerprint,
        raw_payload=article.raw_payload,
    )


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalize_url(value: str | None) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise NewsValidationError(f"invalid article URL: {text}")
    query = [
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in _TRACKING_KEYS and not key.lower().startswith(_TRACKING_PREFIXES)
    ]
    normalized_path = parsed.path or "/"
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            normalized_path,
            urlencode(query, doseq=True),
            "",
        )
    )


def normalize_language(value: str | None) -> str:
    text = clean_text(value)
    if not text:
        return "en"
    return text.split("-")[0].lower()[:8]


def normalize_symbol(value: str | None) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    return text.upper()


def normalize_category_code(value: str | None) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    mapping = {
        "m_a": "merger_acquisition",
        "ma": "merger_acquisition",
        "mergers_acquisitions": "merger_acquisition",
        "analyst_action": "analyst_rating",
        "analyst_actions": "analyst_rating",
        "ratings": "analyst_rating",
        "central_banks": "central_bank",
        "press_releases": "press_release",
        "dividends": "dividend",
    }
    return mapping.get(normalized, normalized)


def normalize_sentiment_score(value: float | None) -> float | None:
    if value is None:
        return None
    return max(-1.0, min(1.0, float(value)))


def normalize_sentiment_label(label: str | None, score: float | None) -> str | None:
    text = clean_text(label)
    if text:
        normalized = text.lower().replace(" ", "_")
        if normalized in {"very_negative", "negative", "neutral", "positive", "very_positive"}:
            return normalized
    normalized_score = normalize_sentiment_score(score)
    if normalized_score is None:
        return None
    if normalized_score <= -0.6:
        return "very_negative"
    if normalized_score < -0.05:
        return "negative"
    if normalized_score >= 0.6:
        return "very_positive"
    if normalized_score > 0.05:
        return "positive"
    return "neutral"


def normalize_for_hash(value: str) -> str:
    text = html.unescape(value).lower()
    text = re.sub(r"[^\w\s$%.+-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def stable_hash(parts: list[str]) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
