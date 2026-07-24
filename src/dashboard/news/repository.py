"""DuckDB persistence for normalized financial news."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from dashboard.news.clustering import cluster_key
from dashboard.news.models import (
    AssetNewsMatch,
    NewsIngestionResult,
    NormalizedNewsArticle,
    ProviderCapabilities,
)

UTC = timezone.utc


class NewsRepository:
    def __init__(self, conn) -> None:
        self.conn = conn

    @staticmethod
    def internal_provider_capabilities() -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_latest_news=True,
            supports_symbol_news=True,
            supports_summaries=True,
            supports_categories=True,
            supports_company_entities=True,
        )

    def upsert_provider(
        self,
        *,
        provider_code: str,
        provider_name: str,
        provider_type: str,
        base_url: str | None,
        capabilities: ProviderCapabilities,
    ) -> int:
        row = self.conn.execute(
            "SELECT provider_id FROM news_provider WHERE provider_code = ?",
            [provider_code],
        ).fetchone()
        params = [
            provider_code,
            provider_name,
            provider_type,
            base_url,
            capabilities.supports_streaming,
            capabilities.supports_symbol_news,
            capabilities.supports_full_article_body,
            capabilities.supports_latest_news,
            capabilities.supports_summaries,
            capabilities.supports_images,
            capabilities.supports_sentiment,
            capabilities.supports_categories,
            capabilities.supports_languages,
            capabilities.supports_regions,
            capabilities.supports_company_entities,
            capabilities.supports_press_releases,
            capabilities.supports_provider_updates,
            capabilities.supports_article_corrections,
        ]
        if row is None:
            provider_id = int(
                self.conn.execute("SELECT nextval('seq_financial_news_provider_id')").fetchone()[0]
            )
            self.conn.execute(
                """
                INSERT INTO news_provider(
                    provider_id, provider_code, provider_name, provider_type, base_url,
                    supports_streaming, supports_symbol_news, supports_full_text,
                    supports_latest_news, supports_summaries, supports_images,
                    supports_sentiment, supports_categories, supports_languages,
                    supports_regions, supports_company_entities, supports_press_releases,
                    supports_provider_updates, supports_article_corrections
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [provider_id, *params],
            )
            return provider_id

        provider_id = int(row[0])
        self.conn.execute(
            """
            UPDATE news_provider
            SET provider_name = ?,
                provider_type = ?,
                base_url = ?,
                supports_streaming = ?,
                supports_symbol_news = ?,
                supports_full_text = ?,
                supports_latest_news = ?,
                supports_summaries = ?,
                supports_images = ?,
                supports_sentiment = ?,
                supports_categories = ?,
                supports_languages = ?,
                supports_regions = ?,
                supports_company_entities = ?,
                supports_press_releases = ?,
                supports_provider_updates = ?,
                supports_article_corrections = ?,
                updated_at = now()
            WHERE provider_id = ?
            """,
            [*params[1:], provider_id],
        )
        return provider_id

    def upsert_article(
        self,
        provider_id: int,
        article: NormalizedNewsArticle,
    ) -> tuple[int, bool]:
        row = self.conn.execute(
            """
            SELECT article_id
            FROM news_article
            WHERE provider_id = ? AND provider_article_id = ?
            """,
            [provider_id, article.provider_article_id],
        ).fetchone()
        raw_payload_json = json.dumps(article.raw_payload, sort_keys=True)
        if row is None:
            article_id = int(self.conn.execute("SELECT nextval('seq_news_article_id')").fetchone()[0])
            self.conn.execute(
                """
                INSERT INTO news_article(
                    article_id, provider_id, provider_article_id, source_item_id, source_name,
                    provider, title, headline, subheadline, summary, article_body, url,
                    canonical_url, image_url, author, language, published_at,
                    provider_updated_at, fetched_at, first_ingested_at, last_ingested_at,
                    raw_payload_json, content_hash, headline_hash, story_fingerprint,
                    importance_score, sentiment_score, sentiment_label, is_breaking,
                    is_press_release, is_correction, is_retracted, is_paywalled, is_active,
                    created_at, updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now(), now(), now(),
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE, now(), now()
                )
                """,
                self._article_params(article_id, provider_id, article, raw_payload_json),
            )
            return article_id, True

        article_id = int(row[0])
        self._clear_article_dependents(article_id)
        self.conn.execute(
            """
            UPDATE news_article
            SET source_name = ?,
                provider = ?,
                title = ?,
                headline = ?,
                subheadline = ?,
                summary = ?,
                article_body = ?,
                url = ?,
                canonical_url = ?,
                image_url = ?,
                author = ?,
                language = ?,
                published_at = COALESCE(published_at, ?),
                provider_updated_at = ?,
                last_ingested_at = now(),
                raw_payload_json = ?,
                content_hash = ?,
                headline_hash = ?,
                story_fingerprint = ?,
                importance_score = ?,
                sentiment_score = ?,
                sentiment_label = ?,
                is_breaking = ?,
                is_press_release = ?,
                is_correction = ?,
                is_retracted = ?,
                is_paywalled = ?,
                is_active = TRUE,
                updated_at = now()
            WHERE article_id = ?
            """,
            [
                article.source_name,
                article.provider_code,
                article.headline,
                article.headline,
                article.subheadline,
                article.summary,
                article.article_body,
                article.canonical_url,
                article.canonical_url,
                article.image_url,
                article.author,
                article.language,
                article.published_at,
                article.provider_updated_at,
                raw_payload_json,
                article.content_hash,
                article.headline_hash,
                article.story_fingerprint,
                article.importance_score,
                article.sentiment_score,
                article.sentiment_label,
                article.is_breaking,
                article.is_press_release,
                article.is_correction,
                article.is_retracted,
                article.is_paywalled,
                article_id,
            ],
        )
        return article_id, False

    def replace_article_assets(self, article_id: int, matches: list[AssetNewsMatch]) -> None:
        self.conn.execute("DELETE FROM news_article_asset WHERE article_id = ?", [article_id])
        for match in matches:
            self.conn.execute(
                """
                INSERT INTO news_article_asset(
                    article_id, asset_id, relevance_score, confidence_score, match_method,
                    mention_type, is_primary_entity, provider_assigned, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, now(), now())
                """,
                [
                    article_id,
                    match.asset_id,
                    match.relevance_score,
                    match.confidence_score,
                    match.match_method,
                    match.mention_type,
                    match.is_primary_entity,
                    match.provider_assigned,
                ],
            )

    def replace_article_categories(self, article_id: int, categories: list[str]) -> int:
        self.conn.execute("DELETE FROM news_article_category WHERE article_id = ?", [article_id])
        written = 0
        for index, category_code in enumerate(dict.fromkeys(categories)):
            row = self.conn.execute(
                "SELECT category_id FROM news_category WHERE category_code = ?",
                [category_code],
            ).fetchone()
            if row is None:
                row = self.conn.execute(
                    "SELECT category_id FROM news_category WHERE category_code = 'general'",
                ).fetchone()
            self.conn.execute(
                """
                INSERT INTO news_article_category(
                    article_id, category_id, confidence_score, classification_source,
                    is_primary, created_at
                )
                VALUES (?, ?, ?, 'deterministic', ?, now())
                """,
                [article_id, int(row[0]), 0.9 if index == 0 else 0.65, index == 0],
            )
            written += 1
        return written

    def upsert_cluster(
        self,
        article_id: int,
        article: NormalizedNewsArticle,
        matches: list[AssetNewsMatch],
    ) -> int:
        key = cluster_key(article, matches)
        row = self.conn.execute(
            "SELECT cluster_id FROM news_story_cluster WHERE cluster_key = ?",
            [key],
        ).fetchone()
        if row is None:
            cluster_id = int(
                self.conn.execute("SELECT nextval('seq_news_story_cluster_id')").fetchone()[0]
            )
            self.conn.execute(
                """
                INSERT INTO news_story_cluster(
                    cluster_id, cluster_key, primary_article_id, cluster_headline,
                    cluster_summary, first_published_at, last_updated_at, article_count,
                    importance_score, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, now(), now())
                """,
                [
                    cluster_id,
                    key,
                    article_id,
                    article.headline,
                    article.summary,
                    article.published_at,
                    article.provider_updated_at or article.published_at,
                    article.importance_score,
                ],
            )
        else:
            cluster_id = int(row[0])

        self.conn.execute(
            """
            INSERT INTO news_story_cluster_article(
                cluster_id, article_id, similarity_score, is_primary, created_at
            )
            VALUES (?, ?, 1.0, FALSE, now())
            ON CONFLICT(cluster_id, article_id) DO UPDATE SET
                similarity_score = excluded.similarity_score
            """,
            [cluster_id, article_id],
        )
        self._refresh_cluster(cluster_id)
        return cluster_id

    def mark_ingestion_state(
        self,
        provider_id: int,
        feed_type: str,
        result: NewsIngestionResult,
        cursor: str | None = None,
        last_provider_timestamp: datetime | None = None,
    ) -> None:
        now = datetime.now(UTC)
        existing = self.conn.execute(
            """
            SELECT 1 FROM news_ingestion_state
            WHERE provider_id = ? AND feed_type = ?
            """,
            [provider_id, feed_type],
        ).fetchone()
        params = [
            cursor,
            last_provider_timestamp,
            now,
            now if result.status == "success" else None,
            now if result.status != "success" else None,
            result.error_message,
            result.status,
            result.articles_received,
            result.articles_inserted,
            result.articles_updated,
            result.articles_rejected,
        ]
        if existing is None:
            self.conn.execute(
                """
                INSERT INTO news_ingestion_state(
                    provider_id, feed_type, cursor, last_provider_timestamp,
                    last_attempted_at, last_succeeded_at, last_error_at,
                    last_error_message, sync_status, articles_received,
                    articles_inserted, articles_updated, articles_rejected,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now(), now())
                """,
                [provider_id, feed_type, *params],
            )
            return
        self.conn.execute(
            """
            UPDATE news_ingestion_state
            SET cursor = COALESCE(?, cursor),
                last_provider_timestamp = COALESCE(?, last_provider_timestamp),
                last_attempted_at = ?,
                last_succeeded_at = COALESCE(?, last_succeeded_at),
                last_error_at = ?,
                last_error_message = ?,
                sync_status = ?,
                articles_received = ?,
                articles_inserted = ?,
                articles_updated = ?,
                articles_rejected = ?,
                updated_at = now()
            WHERE provider_id = ? AND feed_type = ?
            """,
            [*params, provider_id, feed_type],
        )

    def provider_id(self, provider_code: str) -> int | None:
        row = self.conn.execute(
            "SELECT provider_id FROM news_provider WHERE provider_code = ?",
            [provider_code],
        ).fetchone()
        return None if row is None else int(row[0])

    @staticmethod
    def _article_params(
        article_id: int,
        provider_id: int,
        article: NormalizedNewsArticle,
        raw_payload_json: str,
    ) -> list[Any]:
        return [
            article_id,
            provider_id,
            article.provider_article_id,
            article.provider_article_id,
            article.source_name,
            article.provider_code,
            article.headline,
            article.headline,
            article.subheadline,
            article.summary,
            article.article_body,
            article.canonical_url,
            article.canonical_url,
            article.image_url,
            article.author,
            article.language,
            article.published_at,
            article.provider_updated_at,
            raw_payload_json,
            article.content_hash,
            article.headline_hash,
            article.story_fingerprint,
            article.importance_score,
            article.sentiment_score,
            article.sentiment_label,
            article.is_breaking,
            article.is_press_release,
            article.is_correction,
            article.is_retracted,
            article.is_paywalled,
        ]

    def _refresh_cluster(self, cluster_id: int) -> None:
        row = self.conn.execute(
            """
            SELECT
                COUNT(*),
                MIN(a.published_at),
                MAX(COALESCE(a.provider_updated_at, a.published_at)),
                MAX(a.importance_score)
            FROM news_story_cluster_article ca
            JOIN news_article a ON a.article_id = ca.article_id
            WHERE ca.cluster_id = ?
            """,
            [cluster_id],
        ).fetchone()
        primary = self.conn.execute(
            """
            SELECT a.article_id, a.headline, a.summary
            FROM news_story_cluster_article ca
            JOIN news_article a ON a.article_id = ca.article_id
            WHERE ca.cluster_id = ?
            ORDER BY a.importance_score DESC NULLS LAST, a.published_at ASC
            LIMIT 1
            """,
            [cluster_id],
        ).fetchone()
        self.conn.execute(
            """
            UPDATE news_story_cluster
            SET primary_article_id = ?,
                cluster_headline = ?,
                cluster_summary = ?,
                first_published_at = ?,
                last_updated_at = ?,
                article_count = ?,
                importance_score = ?,
                updated_at = now()
            WHERE cluster_id = ?
            """,
            [
                primary[0],
                primary[1],
                primary[2],
                row[1],
                row[2],
                int(row[0]),
                row[3] or 0.0,
                cluster_id,
            ],
        )
        self.conn.execute(
            "UPDATE news_story_cluster_article SET is_primary = article_id = ? WHERE cluster_id = ?",
            [primary[0], cluster_id],
        )

    def _clear_article_dependents(self, article_id: int) -> None:
        self.conn.execute(
            "UPDATE news_story_cluster SET primary_article_id = NULL WHERE primary_article_id = ?",
            [article_id],
        )
        self.conn.execute("DELETE FROM news_story_cluster_article WHERE article_id = ?", [article_id])
        self.conn.execute("DELETE FROM news_article_category WHERE article_id = ?", [article_id])
        self.conn.execute("DELETE FROM news_article_asset WHERE article_id = ?", [article_id])
