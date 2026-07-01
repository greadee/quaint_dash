"""Financial news ingestion orchestration."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from dashboard.news.classification import classify_article
from dashboard.news.entity_resolution import EntityResolver
from dashboard.news.models import NewsIngestionResult, NormalizedNewsArticle
from dashboard.news.normalization import NewsValidationError, normalize_provider_article
from dashboard.news.providers.base import NewsProvider
from dashboard.news.ranking import score_importance
from dashboard.news.repository import NewsRepository


class NewsIngestionService:
    def __init__(self, conn, providers: list[NewsProvider] | None = None) -> None:
        self.conn = conn
        self.repo = NewsRepository(conn)
        self.providers = providers or []
        self.resolver = EntityResolver(conn)

    def ingest_latest(
        self,
        provider: NewsProvider,
        since: datetime | None = None,
        limit: int = 100,
    ) -> NewsIngestionResult:
        provider_id = self.repo.upsert_provider(
            provider_code=provider.provider_code,
            provider_name=provider.provider_name,
            provider_type=provider.provider_type,
            base_url=provider.base_url,
            capabilities=provider.capabilities,
        )
        try:
            provider_articles = provider.fetch_latest(since=since, limit=limit)
        except Exception as exc:
            result = NewsIngestionResult(
                provider_code=provider.provider_code,
                status="failed",
                error_message=str(exc),
            )
            self.repo.mark_ingestion_state(provider_id, "latest", result)
            return result

        result = NewsIngestionResult(
            provider_code=provider.provider_code,
            articles_received=len(provider_articles),
        )
        latest_timestamp = None
        for provider_article in provider_articles:
            try:
                article = normalize_provider_article(provider.provider_code, provider_article)
                article = self._enrich(article)
                article_id, inserted = self.repo.upsert_article(provider_id, article)
                matches = self.resolver.resolve(article)
                self.repo.replace_article_assets(article_id, matches)
                categories_written = self.repo.replace_article_categories(article_id, article.categories)
                self.repo.upsert_cluster(article_id, article, matches)
                result = replace(
                    result,
                    articles_inserted=result.articles_inserted + int(inserted),
                    articles_updated=result.articles_updated + int(not inserted),
                    asset_links_written=result.asset_links_written + len(matches),
                    categories_written=result.categories_written + categories_written,
                    clusters_written=result.clusters_written + 1,
                )
                if latest_timestamp is None or article.published_at > latest_timestamp:
                    latest_timestamp = article.published_at
            except NewsValidationError:
                result = replace(result, articles_rejected=result.articles_rejected + 1)
        self.repo.mark_ingestion_state(
            provider_id,
            "latest",
            result,
            last_provider_timestamp=latest_timestamp,
        )
        return result

    def ingest_all_latest(
        self,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[NewsIngestionResult]:
        return [self.ingest_latest(provider, since=since, limit=limit) for provider in self.providers]

    def _enrich(self, article: NormalizedNewsArticle) -> NormalizedNewsArticle:
        categories = classify_article(article)
        scored = replace(article, categories=categories)
        return replace(scored, importance_score=score_importance(scored))
