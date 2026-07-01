"""Story clustering helpers."""

from __future__ import annotations

from dashboard.news.models import AssetNewsMatch, NormalizedNewsArticle
from dashboard.news.normalization import stable_hash


def cluster_key(article: NormalizedNewsArticle, matches: list[AssetNewsMatch]) -> str:
    primary_assets = ",".join(sorted(match.asset_id for match in matches if match.confidence_score >= 0.7))
    categories = ",".join(sorted(article.categories[:2]))
    return stable_hash([article.story_fingerprint, primary_assets, categories])
