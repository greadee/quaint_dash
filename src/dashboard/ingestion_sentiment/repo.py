"""DuckDB repository for sentiment ingestion."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from dashboard.ingestion_sentiment.models import (
    AssetRef,
    NewsArticleInput,
    SocialPostInput,
    TickerMention,
)
import dashboard.ingestion_sentiment.queries as qry


class SentimentIngestionRepository:
    def __init__(self, conn) -> None:
        self.conn = conn

    def asset_refs(self) -> list[AssetRef]:
        rows = self.conn.execute(qry.SELECT_ASSET_REFS).fetchall()
        return [AssetRef(asset_id=row[0], ticker=row[1], name=row[2]) for row in rows]

    def upsert_article(self, article: NewsArticleInput) -> int:
        article_id = self._next_article_id()
        content_hash = article_content_hash(article)
        raw_payload_json = json.dumps(article.raw_payload, sort_keys=True)

        params = [
            article_id,
            article.source_item_id,
            article.source_name,
            article.provider,
            article.title,
            article.summary,
            article.url,
            article.author,
            article.published_at,
            raw_payload_json,
            content_hash,
        ]

        if article.source_item_id:
            self.conn.execute(qry.UPSERT_NEWS_ARTICLE_BY_SOURCE_ITEM, params)
            row = self.conn.execute(
                qry.SELECT_NEWS_ARTICLE_ID_BY_SOURCE_ITEM,
                [article.provider, article.source_item_id],
            ).fetchone()
        else:
            self.conn.execute(qry.UPSERT_NEWS_ARTICLE_BY_HASH, params)
            row = self.conn.execute(qry.SELECT_NEWS_ARTICLE_ID_BY_HASH, [content_hash]).fetchone()

        return int(row[0])

    def upsert_article_mentions(
        self,
        article_id: int,
        mentions: list[TickerMention],
    ) -> None:
        for mention in mentions:
            self.conn.execute(
                qry.UPSERT_NEWS_ARTICLE_MENTION,
                [
                    article_id,
                    mention.asset_id,
                    mention.ticker,
                    mention.relevance_score,
                    mention.mention_reason,
                ],
            )

    def upsert_social_post(self, post: SocialPostInput) -> int:
        post_id = self._next_social_post_id()
        raw_payload_json = json.dumps(post.raw_payload, sort_keys=True)

        self.conn.execute(
            qry.UPSERT_SOCIAL_POST,
            [
                post_id,
                post.provider,
                post.source_post_id,
                post.source_name,
                post.author,
                post.title,
                post.body,
                post.url,
                post.published_at,
                post.score,
                post.comment_count,
                post.like_count,
                post.repost_count,
                post.reply_count,
                raw_payload_json,
                social_content_hash(post),
            ],
        )

        row = self.conn.execute(
            qry.SELECT_SOCIAL_POST_ID,
            [post.provider, post.source_post_id],
        ).fetchone()
        return int(row[0])

    def upsert_social_post_mentions(
        self,
        post_id: int,
        mentions: list[TickerMention],
    ) -> None:
        for mention in mentions:
            self.conn.execute(
                qry.UPSERT_SOCIAL_POST_MENTION,
                [
                    post_id,
                    mention.asset_id,
                    mention.ticker,
                    mention.relevance_score,
                    mention.mention_reason,
                ],
            )

    def list_news_for_ticker(self, ticker: str, limit: int = 10) -> list[tuple[Any, ...]]:
        return self.conn.execute(qry.SELECT_NEWS_FOR_TICKER, [ticker.upper(), limit]).fetchall()

    def list_social_for_ticker(self, ticker: str, limit: int = 10) -> list[tuple[Any, ...]]:
        return self.conn.execute(qry.SELECT_SOCIAL_FOR_TICKER, [ticker.upper(), limit]).fetchall()

    def _next_article_id(self) -> int:
        return int(self.conn.execute(qry.NEXT_NEWS_ARTICLE_ID).fetchone()[0])

    def _next_social_post_id(self) -> int:
        return int(self.conn.execute(qry.NEXT_SOCIAL_POST_ID).fetchone()[0])


def article_content_hash(article: NewsArticleInput) -> str:
    return _stable_hash(
        [
            article.provider,
            article.source_name,
            article.title,
            article.url,
            _iso_or_empty(article.published_at),
        ]
    )


def social_content_hash(post: SocialPostInput) -> str:
    return _stable_hash(
        [
            post.provider,
            post.source_name,
            post.source_post_id,
            post.title,
            post.body,
            post.url,
            _iso_or_empty(post.published_at),
        ]
    )


def _stable_hash(parts: list[str | None]) -> str:
    normalized = "\n".join((part or "").strip() for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _iso_or_empty(value: datetime | None) -> str:
    return "" if value is None else value.isoformat()

