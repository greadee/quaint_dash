"""DuckDB repository for sentiment ingestion."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from dashboard.ingestion_sentiment.models import (
    AssetRef,
    FactorSnapshotInput,
    NewsArticleInput,
    QuantRatingSnapshotInput,
    SentimentDailySnapshot,
    SentimentIngestionJob,
    SentimentObservationInput,
    SocialPostInput,
    TickerMention,
)
from dashboard.ingestion.job_policy import (
    INGESTION_JOB_LEASE_SECONDS,
    MAX_INGESTION_JOB_ATTEMPTS,
    ingestion_worker_id,
)
from dashboard.ingestion_sentiment.constants import (
    DOMAIN_SENTIMENT,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
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

    def insert_sentiment_observation(self, observation: SentimentObservationInput) -> int:
        observation_id = self._next_sentiment_observation_id()
        observed_at = observation.observed_at or datetime.now()

        self.conn.execute(
            qry.INSERT_SENTIMENT_OBSERVATION,
            [
                observation_id,
                observation.asset_id,
                observation.ticker,
                observation.item_type,
                observation.item_id,
                observation.provider,
                observation.sentiment_label,
                observation.sentiment_score,
                observation.confidence,
                observation.relevance_score,
                observation.source_weight,
                observation.engagement_weight,
                observation.explanation,
                observed_at,
            ],
        )
        return observation_id

    def sentiment_observations_for_date(
        self,
        asset_id: str,
        snapshot_date,
    ) -> list[tuple[Any, ...]]:
        return self.conn.execute(
            qry.SELECT_SENTIMENT_OBSERVATIONS_FOR_DATE,
            [asset_id, snapshot_date],
        ).fetchall()

    def upsert_ticker_sentiment_daily(self, snapshot: SentimentDailySnapshot) -> None:
        self.conn.execute(
            qry.UPSERT_TICKER_SENTIMENT_DAILY,
            [
                snapshot.asset_id,
                snapshot.ticker,
                snapshot.snapshot_date,
                snapshot.retail_sentiment_score,
                snapshot.news_sentiment_score,
                snapshot.analyst_sentiment_score,
                snapshot.blended_sentiment_score,
                snapshot.reddit_post_count,
                snapshot.x_post_count,
                snapshot.article_count,
                snapshot.bullish_count,
                snapshot.neutral_count,
                snapshot.bearish_count,
                snapshot.sentiment_momentum_1d,
                snapshot.sentiment_momentum_7d,
                snapshot.sentiment_momentum_30d,
                snapshot.unusual_volume_flag,
            ],
        )

    def daily_blended_score(self, asset_id: str, snapshot_date) -> float | None:
        row = self.conn.execute(qry.SELECT_DAILY_BLENDED_SCORE, [asset_id, snapshot_date]).fetchone()
        return None if row is None else row[0]

    def recent_average_item_count(self, asset_id: str, snapshot_date) -> float | None:
        row = self.conn.execute(qry.SELECT_RECENT_AVG_ITEM_COUNT, [asset_id, snapshot_date, snapshot_date]).fetchone()
        return None if row is None else row[0]

    def create_job(
        self,
        asset_id: str,
        job_type: str,
        dataset: str,
        priority: int,
        start_date=None,
        end_date=None,
    ) -> int:
        job_id = self._next_job_id()
        self.conn.execute(
            qry.INSERT_SENTIMENT_JOB,
            [
                job_id,
                asset_id,
                DOMAIN_SENTIMENT,
                job_type,
                dataset,
                STATUS_PENDING,
                priority,
                start_date,
                end_date,
            ],
        )
        return job_id

    def claim_next_pending_job(self) -> SentimentIngestionJob | None:
        row = self.conn.execute(
            qry.CLAIM_NEXT_PENDING_SENTIMENT_JOB,
            [
                STATUS_RUNNING,
                ingestion_worker_id(),
                INGESTION_JOB_LEASE_SECONDS,
                DOMAIN_SENTIMENT,
                STATUS_PENDING,
                MAX_INGESTION_JOB_ATTEMPTS,
                STATUS_PENDING,
            ],
        ).fetchone()
        if row is None:
            return None

        return SentimentIngestionJob(*row)

    def mark_job_done(self, job_id: int) -> None:
        self.conn.execute(qry.MARK_JOB_DONE, [STATUS_DONE, job_id])

    def mark_job_failed(self, job_id: int, error: str) -> None:
        self.conn.execute(qry.MARK_JOB_FAILED, [STATUS_FAILED, error, job_id])

    def price_history_for_factor(self, asset_id: str, snapshot_date) -> list[tuple[Any, ...]]:
        return self.conn.execute(
            qry.SELECT_PRICE_HISTORY_FOR_FACTOR,
            [asset_id, snapshot_date, snapshot_date],
        ).fetchall()

    def asset_factor_metadata(self, asset_id: str) -> tuple[Any, ...] | None:
        return self.conn.execute(qry.SELECT_ASSET_FACTOR_METADATA, [asset_id]).fetchone()

    def dividends_for_factor(self, asset_id: str, snapshot_date) -> list[tuple[Any, ...]]:
        return self.conn.execute(
            qry.SELECT_DIVIDENDS_FOR_FACTOR,
            [asset_id, snapshot_date, snapshot_date],
        ).fetchall()

    def upsert_factor_snapshot(self, snapshot: FactorSnapshotInput) -> None:
        self.conn.execute(
            qry.UPSERT_FACTOR_SNAPSHOT,
            [
                snapshot.asset_id,
                snapshot.ticker,
                snapshot.snapshot_date,
                snapshot.growth_score,
                snapshot.value_score,
                snapshot.quality_score,
                snapshot.momentum_score,
                snapshot.defensive_score,
                snapshot.dividend_score,
                snapshot.volatility_score,
                snapshot.revision_score,
                snapshot.overall_factor_score,
                json.dumps(snapshot.factor_labels),
                snapshot.explanation,
            ],
        )

    def factor_snapshot(self, asset_id: str, snapshot_date) -> FactorSnapshotInput | None:
        row = self.conn.execute(qry.SELECT_FACTOR_SNAPSHOT, [asset_id, snapshot_date]).fetchone()
        if row is None:
            return None

        return FactorSnapshotInput(
            asset_id=row[0],
            ticker=row[1],
            snapshot_date=row[2],
            growth_score=row[3],
            value_score=row[4],
            quality_score=row[5],
            momentum_score=row[6],
            defensive_score=row[7],
            dividend_score=row[8],
            volatility_score=row[9],
            revision_score=row[10],
            overall_factor_score=row[11],
            factor_labels=json.loads(row[12] or "[]"),
            explanation=row[13],
        )

    def upsert_quant_rating_snapshot(self, snapshot: QuantRatingSnapshotInput) -> None:
        self.conn.execute(
            qry.UPSERT_QUANT_RATING_SNAPSHOT,
            [
                snapshot.asset_id,
                snapshot.ticker,
                snapshot.snapshot_date,
                snapshot.overall_quant_score,
                snapshot.overall_quant_rating,
                snapshot.growth_rating,
                snapshot.value_rating,
                snapshot.quality_rating,
                snapshot.momentum_rating,
                snapshot.defensive_rating,
                snapshot.dividend_rating,
                snapshot.volatility_rating,
                snapshot.factor_profile,
                snapshot.explanation,
            ],
        )

    def _next_article_id(self) -> int:
        return int(self.conn.execute(qry.NEXT_NEWS_ARTICLE_ID).fetchone()[0])

    def _next_social_post_id(self) -> int:
        return int(self.conn.execute(qry.NEXT_SOCIAL_POST_ID).fetchone()[0])

    def _next_sentiment_observation_id(self) -> int:
        return int(self.conn.execute(qry.NEXT_SENTIMENT_OBSERVATION_ID).fetchone()[0])

    def _next_job_id(self) -> int:
        return int(self.conn.execute(qry.NEXT_JOB_ID).fetchone()[0])


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
