"""Financial news ingestion orchestration."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from dashboard.news.classification import classify_article
from dashboard.news.entity_resolution import EntityResolver
from dashboard.news.models import NewsIngestionResult, NormalizedNewsArticle
from dashboard.news.normalization import NewsValidationError, normalize_provider_article
from dashboard.news.providers.base import NewsProvider
from dashboard.news.ranking import score_importance
from dashboard.news.repository import NewsRepository
from dashboard.ingestion.ticker_universe import TickerUniverseRepository

UTC = timezone.utc


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

    def ingest_subscribed(
        self,
        provider: NewsProvider,
        since: datetime | None = None,
        limit: int = 100,
        include_watchlist: bool = True,
    ) -> NewsIngestionResult:
        subscriptions = TickerUniverseRepository(self.conn).stream_subscriptions(
            include_portfolios=True,
            include_watchlist=include_watchlist,
        )
        symbols = [item.symbol for item in subscriptions]
        provider_id = self.repo.upsert_provider(
            provider_code=provider.provider_code,
            provider_name=provider.provider_name,
            provider_type=provider.provider_type,
            base_url=provider.base_url,
            capabilities=provider.capabilities,
        )
        if not symbols:
            result = NewsIngestionResult(provider_code=provider.provider_code, status="no_subscriptions")
            self.repo.mark_ingestion_state(provider_id, "subscribed", result)
            return result
        try:
            provider_articles = provider.fetch_for_symbols(symbols=symbols, since=since, limit=limit)
            if hasattr(provider, "fetch_press_releases_for_symbols"):
                provider_articles.extend(
                    provider.fetch_press_releases_for_symbols(symbols=symbols, since=since, limit=limit)
                )
        except Exception as exc:
            result = NewsIngestionResult(
                provider_code=provider.provider_code,
                status="failed",
                error_message=str(exc),
            )
            self.repo.mark_ingestion_state(provider_id, "subscribed", result)
            return result

        return self._persist_provider_articles(provider_id, provider.provider_code, provider_articles)

    def ingest_earnings_events(
        self,
        *,
        lookback_days: int = 14,
        lookahead_days: int = 60,
        limit: int = 200,
    ) -> NewsIngestionResult:
        provider_code = "corporate_calendar"
        provider_id = self.repo.upsert_provider(
            provider_code=provider_code,
            provider_name="Corporate Calendar",
            provider_type="internal",
            base_url=None,
            capabilities=self.repo.internal_provider_capabilities(),
        )
        start_date = date.today() - timedelta(days=lookback_days)
        end_date = date.today() + timedelta(days=lookahead_days)
        rows = self.conn.execute(
            """
            SELECT
                e.asset_id,
                COALESCE(a.symbol, e.asset_id) AS symbol,
                a.name,
                e.earnings_date,
                e.fiscal_year,
                e.fiscal_quarter,
                e.time,
                e.eps_estimated,
                e.eps_actual,
                e.revenue_estimated,
                e.revenue_actual,
                e.source,
                e.as_of_ts
            FROM earnings_calendar_event e
            LEFT JOIN asset a ON a.asset_id = e.asset_id
            WHERE e.earnings_date BETWEEN ? AND ?
              AND (
                EXISTS (SELECT 1 FROM portfolio_ticker pt WHERE pt.asset_id = e.asset_id AND pt.is_active = TRUE)
                OR EXISTS (SELECT 1 FROM watchlist_ticker wt WHERE wt.asset_id = e.asset_id AND wt.is_active = TRUE)
                OR EXISTS (SELECT 1 FROM position p WHERE p.asset_id = e.asset_id AND COALESCE(p.qty, 0) <> 0)
              )
            ORDER BY e.earnings_date DESC, e.asset_id
            LIMIT ?
            """,
            [start_date, end_date, limit],
        ).fetchall()
        articles = [self._earnings_article(row) for row in rows]
        return self._persist_provider_articles(provider_id, provider_code, articles)

    def ingest_all_latest(
        self,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[NewsIngestionResult]:
        return [self.ingest_latest(provider, since=since, limit=limit) for provider in self.providers]

    def _persist_provider_articles(
        self,
        provider_id: int,
        provider_code: str,
        provider_articles,
    ) -> NewsIngestionResult:
        result = NewsIngestionResult(
            provider_code=provider_code,
            articles_received=len(provider_articles),
        )
        latest_timestamp = None
        seen: set[str] = set()
        for provider_article in provider_articles:
            if provider_article.provider_article_id in seen:
                continue
            seen.add(provider_article.provider_article_id)
            try:
                article = normalize_provider_article(provider_code, provider_article)
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
            "subscribed" if provider_code != "corporate_calendar" else "earnings",
            result,
            last_provider_timestamp=latest_timestamp,
        )
        return result

    def _enrich(self, article: NormalizedNewsArticle) -> NormalizedNewsArticle:
        categories = classify_article(article)
        scored = replace(article, categories=categories)
        return replace(scored, importance_score=score_importance(scored))

    @staticmethod
    def _earnings_article(row) -> object:
        from dashboard.news.models import ProviderNewsArticle

        symbol = str(row[1] or row[0]).upper()
        company = row[2] or symbol
        earnings_date = row[3]
        fiscal = f" Q{row[5]} {row[4]}" if row[4] and row[5] else ""
        has_actuals = row[8] is not None or row[10] is not None
        if has_actuals:
            headline = f"{company} reports earnings{fiscal}"
            summary_parts = []
            if row[8] is not None:
                summary_parts.append(f"actual EPS {row[8]}")
            if row[7] is not None:
                summary_parts.append(f"estimated EPS {row[7]}")
            if row[10] is not None:
                summary_parts.append(f"actual revenue {row[10]}")
            if row[9] is not None:
                summary_parts.append(f"estimated revenue {row[9]}")
            provider_id = f"earnings-reported-{symbol}-{earnings_date.isoformat()}"
            category = "earnings_reported"
        else:
            timing = f" ({row[6]})" if row[6] else ""
            headline = f"{company} scheduled to report earnings{fiscal} on {earnings_date.isoformat()}{timing}"
            summary_parts = []
            if row[7] is not None:
                summary_parts.append(f"consensus EPS {row[7]}")
            if row[9] is not None:
                summary_parts.append(f"consensus revenue {row[9]}")
            provider_id = f"earnings-upcoming-{symbol}-{earnings_date.isoformat()}"
            category = "earnings_upcoming"
        as_of = row[12]
        if isinstance(as_of, datetime):
            published_at = as_of.replace(tzinfo=UTC) if as_of.tzinfo is None else as_of.astimezone(UTC)
        else:
            published_at = datetime.now(UTC)
        if published_at > datetime.now(UTC):
            published_at = datetime.now(UTC)
        return ProviderNewsArticle(
            provider_article_id=provider_id,
            headline=headline,
            summary="; ".join(summary_parts) or None,
            source_name=f"{row[11] or 'stored'} earnings calendar",
            published_at=published_at,
            updated_at=row[12],
            symbols=[symbol, str(row[0]).upper()],
            provider_categories=["earnings", category],
            importance_score=0.85 if has_actuals else 0.65,
            is_breaking=has_actuals and earnings_date == date.today(),
            raw_payload={
                "asset_id": row[0],
                "symbol": symbol,
                "earnings_date": earnings_date.isoformat(),
                "fiscal_year": row[4],
                "fiscal_quarter": row[5],
                "time": row[6],
                "eps_estimated": row[7],
                "eps_actual": row[8],
                "revenue_estimated": row[9],
                "revenue_actual": row[10],
                "source": row[11],
            },
        )
