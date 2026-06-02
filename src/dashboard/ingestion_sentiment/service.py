"""Service layer for sentiment and news refreshes."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from dashboard.ingestion_sentiment.models import AssetRef
from dashboard.ingestion_sentiment.providers.base import NewsProvider, SocialProvider
from dashboard.ingestion_sentiment.repo import SentimentIngestionRepository
from dashboard.ingestion_sentiment.scoring import RulesBasedSentimentScorer
from dashboard.ingestion_sentiment.ticker_matching import find_ticker_mentions


class SentimentIngestionService:
    def __init__(
        self,
        conn,
        news_providers: list[NewsProvider] | None = None,
        social_providers: list[SocialProvider] | None = None,
        scorer: RulesBasedSentimentScorer | None = None,
    ) -> None:
        self.conn = conn
        self.repo = SentimentIngestionRepository(conn)
        self.news_providers = news_providers or []
        self.social_providers = social_providers or []
        self.scorer = scorer or RulesBasedSentimentScorer()

    def refresh_news_for_ticker(
        self,
        ticker: str,
        since: datetime | None = None,
        provider_name: str | None = None,
    ) -> int:
        asset = self._asset_ref_for_ticker(ticker)
        if asset is None:
            raise ValueError(f"Unknown sentiment ticker: {ticker}")

        observations_written = 0
        for provider in self.news_providers:
            if provider_name is not None and provider.name != provider_name:
                continue
            articles = provider.fetch_articles_for_ticker(asset.ticker, since)
            for article in articles:
                article_id = self.repo.upsert_article(article)
                mentions = find_ticker_mentions(
                    " ".join(part for part in [article.title, article.summary] if part),
                    [asset],
                )
                self.repo.upsert_article_mentions(article_id, mentions)

                for mention in mentions:
                    base_observation = self.scorer.score_article(article, mention.ticker)
                    observation = self.scorer.with_item_context(
                        base_observation,
                        asset_id=mention.asset_id,
                        ticker=mention.ticker,
                        item_id=article_id,
                        relevance_score=mention.relevance_score,
                    )
                    self.repo.insert_sentiment_observation(observation)
                    observations_written += 1

        return observations_written

    def refresh_social_for_ticker(
        self,
        ticker: str,
        since: datetime | None = None,
        provider_name: str | None = None,
    ) -> int:
        asset = self._asset_ref_for_ticker(ticker)
        if asset is None:
            raise ValueError(f"Unknown sentiment ticker: {ticker}")

        observations_written = 0
        for provider in self.social_providers:
            if provider_name is not None and provider.name != provider_name:
                continue
            posts = provider.fetch_posts_for_ticker(asset.ticker, since)
            for post in posts:
                post_id = self.repo.upsert_social_post(post)
                mentions = find_ticker_mentions(
                    " ".join(part for part in [post.title, post.body] if part),
                    [asset],
                )
                self.repo.upsert_social_post_mentions(post_id, mentions)

                for mention in mentions:
                    base_observation = self.scorer.score_post(post, mention.ticker)
                    observation = self.scorer.with_item_context(
                        base_observation,
                        asset_id=mention.asset_id,
                        ticker=mention.ticker,
                        item_id=post_id,
                        relevance_score=mention.relevance_score,
                    )
                    self.repo.insert_sentiment_observation(observation)
                    observations_written += 1

        return observations_written

    def refresh_ticker(
        self,
        ticker: str,
        source: str = "all",
        since: datetime | None = None,
    ) -> int:
        source = source.lower()
        if source == "all":
            return self.refresh_news_for_ticker(ticker, since) + self.refresh_social_for_ticker(
                ticker,
                since,
            )
        if source == "news":
            return self.refresh_news_for_ticker(ticker, since)
        if source in {"social", "retail"}:
            return self.refresh_social_for_ticker(ticker, since)
        if source in {"reddit", "x"}:
            return self.refresh_social_for_ticker(ticker, since, provider_name=source)
        raise ValueError(f"Unsupported sentiment source: {source}")

    def aggregate_daily_sentiment(self, ticker: str, snapshot_date) -> int:
        from dashboard.ingestion_sentiment.scoring import DailySentimentAggregator

        asset = self._asset_ref_for_ticker(ticker)
        if asset is None:
            raise ValueError(f"Unknown sentiment ticker: {ticker}")

        DailySentimentAggregator(self.repo).aggregate_for_ticker(
            asset_id=asset.asset_id,
            ticker=asset.ticker,
            snapshot_date=snapshot_date,
        )
        return 1

    def refresh_factor_snapshot(self, ticker: str, snapshot_date) -> int:
        from dashboard.ingestion_sentiment.scoring import FactorScorer

        asset = self._asset_ref_for_ticker(ticker)
        if asset is None:
            raise ValueError(f"Unknown sentiment ticker: {ticker}")

        FactorScorer(self.repo).refresh_factor_snapshot(
            asset_id=asset.asset_id,
            ticker=asset.ticker,
            snapshot_date=snapshot_date,
        )
        return 1

    def refresh_quant_rating(self, ticker: str, snapshot_date) -> int:
        from dashboard.ingestion_sentiment.scoring import QuantRatingScorer

        asset = self._asset_ref_for_ticker(ticker)
        if asset is None:
            raise ValueError(f"Unknown sentiment ticker: {ticker}")

        QuantRatingScorer(self.repo).refresh_quant_rating(
            asset_id=asset.asset_id,
            ticker=asset.ticker,
            snapshot_date=snapshot_date,
        )
        return 1

    def _asset_ref_for_ticker(self, ticker: str) -> AssetRef | None:
        normalized = ticker.upper().strip()
        for asset in self.repo.asset_refs():
            if asset.asset_id.upper() == normalized or asset.ticker.upper() == normalized:
                return replace(asset, ticker=asset.ticker.upper())
        return None
