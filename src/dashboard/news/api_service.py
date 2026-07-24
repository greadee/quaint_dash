"""Application service for financial news API routes."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from dashboard.analytics.repository import AnalyticsRepository
from dashboard.api.models import (
    NewsArticleAssetResponse,
    NewsArticleCategoryResponse,
    NewsArticleResponse,
    NewsAlertRuleRequest,
    NewsAlertRuleResponse,
    NewsCategorySummaryResponse,
    NewsFeedResponse,
    NewsProviderHealthResponse,
    NewsProviderResponse,
    NewsRefreshResponse,
    NewsStoryClusterSummary,
    NewsUserStateResponse,
)
from dashboard.news.ingestion import NewsIngestionService
from dashboard.news.models import ProviderCapabilities
from dashboard.news.providers.fmp_provider import FmpNewsProvider, FmpNewsProviderError

UTC = timezone.utc


class NewsApiService:
    def __init__(self, conn) -> None:
        self.conn = conn

    def feed(
        self,
        *,
        q: str | None = None,
        provider: str | None = None,
        source: str | None = None,
        asset_id: str | None = None,
        portfolio_id: int | None = None,
        category: str | None = None,
        sentiment: str | None = None,
        breaking: bool | None = None,
        press_release: bool | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        sort: str = "recency",
        limit: int = 25,
        offset: int = 0,
        user_id: str = "local",
    ) -> NewsFeedResponse:
        if asset_id is not None:
            asset_id = self._asset_filter_ids(asset_id)
        where, params = self._filters(
            q=q,
            provider=provider,
            source=source,
            asset_id=asset_id,
            portfolio_id=portfolio_id,
            category=category,
            sentiment=sentiment,
            breaking=breaking,
            press_release=press_release,
            start_date=start_date,
            end_date=end_date,
        )
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        score_sql = self._score_sql(portfolio_id=portfolio_id)
        order_sql = (
            "relevance_score DESC NULLS LAST, a.published_at DESC NULLS LAST, a.article_id DESC"
            if sort == "relevance"
            else "a.published_at DESC NULLS LAST, relevance_score DESC NULLS LAST, a.article_id DESC"
        )
        rows = self.conn.execute(
            f"""
            WITH filtered AS (
                SELECT
                    a.article_id,
                    {score_sql} AS relevance_score
                FROM news_article a
                LEFT JOIN news_provider p ON p.provider_id = a.provider_id
                {where_sql}
                GROUP BY a.article_id, a.importance_score, a.published_at
            ),
            total AS (
                SELECT COUNT(*) AS total_count FROM filtered
            )
            SELECT
                a.article_id,
                COALESCE(p.provider_code, a.provider) AS provider_code,
                p.provider_name,
                a.provider_article_id,
                COALESCE(a.headline, a.title) AS headline,
                a.summary,
                COALESCE(a.canonical_url, a.url) AS canonical_url,
                a.source_name,
                a.author,
                a.language,
                a.published_at,
                a.updated_at,
                a.importance_score,
                f.relevance_score,
                a.sentiment_score,
                a.sentiment_label,
                COALESCE(a.is_breaking, FALSE) AS is_breaking,
                COALESCE(a.is_press_release, FALSE) AS is_press_release,
                COALESCE(a.is_correction, FALSE) AS is_correction,
                COALESCE(a.is_retracted, FALSE) AS is_retracted,
                COALESCE(a.is_paywalled, FALSE) AS is_paywalled,
                COALESCE(us.is_read, FALSE) AS is_read,
                COALESCE(us.is_saved, FALSE) AS is_saved,
                total.total_count
            FROM filtered f
            JOIN news_article a ON a.article_id = f.article_id
            LEFT JOIN news_provider p ON p.provider_id = a.provider_id
            LEFT JOIN news_user_article_state us
              ON us.article_id = a.article_id AND us.user_id = ?
            CROSS JOIN total
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
            """,
            [*params, user_id, limit, offset],
        ).fetchall()
        total = int(rows[0][-1]) if rows else self._count_for_empty(where_sql, params)
        article_ids = [int(row[0]) for row in rows]
        assets = self._assets_by_article(article_ids)
        categories = self._categories_by_article(article_ids)
        clusters = self._clusters_by_article(article_ids)
        return NewsFeedResponse(
            items=[
                self._article_from_row(
                    row,
                    assets=assets.get(int(row[0]), []),
                    categories=categories.get(int(row[0]), []),
                    cluster=clusters.get(int(row[0])),
                )
                for row in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
            sort=sort,
            generated_at=datetime.now(UTC),
            **self._feed_metadata(),
        )

    def latest(self, limit: int = 25, offset: int = 0) -> NewsFeedResponse:
        return self.feed(limit=limit, offset=offset, sort="recency")

    def breaking(self, limit: int = 25, offset: int = 0) -> NewsFeedResponse:
        return self.feed(breaking=True, limit=limit, offset=offset, sort="recency")

    def search(
        self,
        q: str,
        *,
        provider: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        sort: str = "relevance",
        limit: int = 25,
        offset: int = 0,
    ) -> NewsFeedResponse:
        return self.feed(
            q=q,
            provider=provider,
            start_date=start_date,
            end_date=end_date,
            sort=sort,
            limit=limit,
            offset=offset,
        )

    def article(self, article_id: int, user_id: str = "local") -> NewsArticleResponse:
        row = self.conn.execute(
            """
            SELECT
                a.article_id,
                COALESCE(p.provider_code, a.provider) AS provider_code,
                p.provider_name,
                a.provider_article_id,
                COALESCE(a.headline, a.title) AS headline,
                a.summary,
                COALESCE(a.canonical_url, a.url) AS canonical_url,
                a.source_name,
                a.author,
                a.language,
                a.published_at,
                a.updated_at,
                a.importance_score,
                COALESCE((
                    SELECT MAX(aa.relevance_score * aa.confidence_score)
                    FROM news_article_asset aa
                    WHERE aa.article_id = a.article_id
                ), 0.25) * COALESCE(a.importance_score, 0.3) AS relevance_score,
                a.sentiment_score,
                a.sentiment_label,
                COALESCE(a.is_breaking, FALSE) AS is_breaking,
                COALESCE(a.is_press_release, FALSE) AS is_press_release,
                COALESCE(a.is_correction, FALSE) AS is_correction,
                COALESCE(a.is_retracted, FALSE) AS is_retracted,
                COALESCE(a.is_paywalled, FALSE) AS is_paywalled,
                COALESCE(us.is_read, FALSE) AS is_read,
                COALESCE(us.is_saved, FALSE) AS is_saved,
                1 AS total_count
            FROM news_article a
            LEFT JOIN news_provider p ON p.provider_id = a.provider_id
            LEFT JOIN news_user_article_state us
              ON us.article_id = a.article_id AND us.user_id = ?
            WHERE a.article_id = ?
            """,
            [user_id, article_id],
        ).fetchone()
        if row is None:
            raise LookupError(f"News article not found: {article_id}")
        assets = self._assets_by_article([article_id])
        categories = self._categories_by_article([article_id])
        clusters = self._clusters_by_article([article_id])
        return self._article_from_row(
            row,
            assets=assets.get(article_id, []),
            categories=categories.get(article_id, []),
            cluster=clusters.get(article_id),
        )

    def asset_feed(
        self,
        asset_id: str,
        *,
        category: str | None = None,
        limit: int = 10,
        offset: int = 0,
        sort: str = "recency",
    ) -> NewsFeedResponse:
        return self.feed(asset_id=asset_id, category=category, limit=limit, offset=offset, sort=sort)

    def portfolio_feed(
        self,
        portfolio_id: int,
        *,
        category: str | None = None,
        limit: int = 10,
        offset: int = 0,
        sort: str = "relevance",
    ) -> NewsFeedResponse:
        return self.feed(
            portfolio_id=portfolio_id,
            category=category,
            limit=limit,
            offset=offset,
            sort=sort,
        )

    def providers(self) -> list[NewsProviderResponse]:
        rows = self.conn.execute(
            """
            SELECT
                p.provider_code,
                p.provider_name,
                p.provider_type,
                p.is_enabled,
                p.supports_latest_news,
                p.supports_symbol_news,
                p.supports_full_text,
                p.supports_sentiment,
                p.supports_categories,
                MAX(s.last_attempted_at),
                MAX(s.last_succeeded_at),
                MAX(s.last_error_at),
                STRING_AGG(s.last_error_message, ' | ') FILTER (
                    WHERE s.last_error_message IS NOT NULL AND s.last_error_message <> ''
                ),
                MAX(s.sync_status)
            FROM news_provider p
            LEFT JOIN news_ingestion_state s ON s.provider_id = p.provider_id
            GROUP BY
                p.provider_code, p.provider_name, p.provider_type, p.is_enabled,
                p.supports_latest_news, p.supports_symbol_news, p.supports_full_text,
                p.supports_sentiment, p.supports_categories
            ORDER BY MIN(p.priority), p.provider_code
            """
        ).fetchall()
        return [
            NewsProviderResponse(
                provider_code=row[0],
                provider_name=row[1],
                provider_type=row[2],
                is_enabled=bool(row[3]),
                supports_latest_news=bool(row[4]),
                supports_symbol_news=bool(row[5]),
                supports_full_text=bool(row[6]),
                supports_sentiment=bool(row[7]),
                supports_categories=bool(row[8]),
                last_attempted_at=row[9],
                last_succeeded_at=row[10],
                last_error_at=row[11],
                last_error_message=row[12],
                sync_status=row[13],
            )
            for row in rows
        ]

    def categories(self) -> list[NewsCategorySummaryResponse]:
        rows = self.conn.execute(
            """
            SELECT c.category_code, c.category_name, c.default_importance_weight, COUNT(ac.article_id)
            FROM news_category c
            LEFT JOIN news_article_category ac ON ac.category_id = c.category_id
            GROUP BY c.category_code, c.category_name, c.default_importance_weight
            ORDER BY c.category_code
            """
        ).fetchall()
        return [
            NewsCategorySummaryResponse(
                category_code=row[0],
                category_name=row[1],
                default_importance_weight=float(row[2]),
                article_count=int(row[3]),
            )
            for row in rows
        ]

    def provider_health(self, stale_after_minutes: int = 60) -> list[NewsProviderHealthResponse]:
        rows = self.conn.execute(
            """
            SELECT
                p.provider_code,
                p.provider_name,
                p.is_enabled,
                s.sync_status,
                s.last_attempted_at,
                s.last_succeeded_at,
                s.last_error_at,
                s.last_error_message,
                COALESCE(s.articles_received, 0),
                COALESCE(s.articles_inserted, 0),
                COALESCE(s.articles_updated, 0),
                COALESCE(s.articles_rejected, 0)
            FROM news_provider p
            LEFT JOIN news_ingestion_state s ON s.provider_id = p.provider_id
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY p.provider_id
                ORDER BY s.last_attempted_at DESC NULLS LAST, s.updated_at DESC NULLS LAST
            ) = 1
            ORDER BY p.priority, p.provider_code
            """
        ).fetchall()
        health: list[NewsProviderHealthResponse] = []
        for row in rows:
            last_succeeded = row[5]
            staleness = None
            if last_succeeded is not None:
                comparison_now = datetime.now(UTC) if last_succeeded.tzinfo else datetime.now()
                staleness = max(0.0, (comparison_now - last_succeeded).total_seconds() / 60)
            status_text = "healthy"
            if row[6] is not None or row[3] == "failed":
                status_text = "failed"
            elif last_succeeded is None:
                status_text = "not_started"
            elif staleness is not None and staleness > stale_after_minutes:
                status_text = "stale"
            health.append(
                NewsProviderHealthResponse(
                    provider_code=row[0],
                    provider_name=row[1],
                    is_enabled=bool(row[2]),
                    sync_status=row[3],
                    last_attempted_at=row[4],
                    last_succeeded_at=last_succeeded,
                    last_error_at=row[6],
                    last_error_message=row[7],
                    articles_received=int(row[8]),
                    articles_inserted=int(row[9]),
                    articles_updated=int(row[10]),
                    articles_rejected=int(row[11]),
                    feed_staleness_minutes=staleness,
                    status=status_text,
                )
            )
        return health

    def refresh_subscribed(self, *, min_interval_minutes: int = 15, limit: int = 100) -> NewsRefreshResponse:
        if self._recent_refresh_attempt(minutes=min_interval_minutes):
            return NewsRefreshResponse(
                status="skipped_recent_refresh",
                generated_at=datetime.now(UTC),
                results=[],
            )
        service = NewsIngestionService(self.conn)
        results = []
        try:
            provider = FmpNewsProvider()
            watermark = self._latest_provider_timestamp(provider.provider_code, "subscribed")
            result = service.ingest_subscribed(provider, since=watermark, limit=limit)
            results.append(self._result_dict(result))
        except (FmpNewsProviderError, RuntimeError) as exc:
            provider_id = service.repo.upsert_provider(
                provider_code="fmp_news",
                provider_name="Financial Modeling Prep News",
                provider_type="api",
                base_url="https://financialmodelingprep.com/stable",
                capabilities=ProviderCapabilities(
                    supports_latest_news=True,
                    supports_symbol_news=True,
                    supports_summaries=True,
                    supports_images=True,
                    supports_categories=True,
                    supports_press_releases=True,
                ),
            )
            from dashboard.news.models import NewsIngestionResult

            result = NewsIngestionResult(provider_code="fmp_news", status="failed", error_message=str(exc))
            service.repo.mark_ingestion_state(provider_id, "subscribed", result)
            results.append(self._result_dict(result))
        earnings = service.ingest_earnings_events()
        results.append(self._result_dict(earnings))
        return NewsRefreshResponse(
            status="success" if any(item["status"] == "success" for item in results) else "degraded",
            generated_at=datetime.now(UTC),
            results=results,
        )

    def create_alert_rule(
        self,
        payload: NewsAlertRuleRequest,
        *,
        user_id: str = "local",
    ) -> NewsAlertRuleResponse:
        alert_rule_id = int(self.conn.execute("SELECT nextval('seq_news_alert_rule_id')").fetchone()[0])
        self.conn.execute(
            """
            INSERT INTO news_alert_rule(
                alert_rule_id, user_id, rule_name, target_scope, keyword_query,
                min_importance, sentiment_threshold, breaking_only, delivery_channel,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, now(), now())
            """,
            [
                alert_rule_id,
                user_id,
                payload.rule_name,
                payload.target_scope,
                payload.keyword_query,
                payload.min_importance,
                payload.sentiment_threshold,
                payload.breaking_only,
                payload.delivery_channel,
            ],
        )
        self._replace_alert_assets(alert_rule_id, payload.asset_ids)
        self._replace_alert_portfolios(alert_rule_id, payload.portfolio_ids)
        return self.alert_rule(alert_rule_id, user_id=user_id)

    def update_alert_rule(
        self,
        alert_rule_id: int,
        payload: NewsAlertRuleRequest,
        *,
        user_id: str = "local",
    ) -> NewsAlertRuleResponse:
        if self.conn.execute(
            "SELECT 1 FROM news_alert_rule WHERE alert_rule_id = ? AND user_id = ?",
            [alert_rule_id, user_id],
        ).fetchone() is None:
            raise LookupError(f"News alert rule not found: {alert_rule_id}")
        self.conn.execute("DELETE FROM news_alert_rule_asset WHERE alert_rule_id = ?", [alert_rule_id])
        self.conn.execute("DELETE FROM news_alert_rule_portfolio WHERE alert_rule_id = ?", [alert_rule_id])
        result = self.conn.execute(
            """
            UPDATE news_alert_rule
            SET rule_name = ?,
                target_scope = ?,
                keyword_query = ?,
                min_importance = ?,
                sentiment_threshold = ?,
                breaking_only = ?,
                delivery_channel = ?,
                updated_at = now()
            WHERE alert_rule_id = ? AND user_id = ?
            RETURNING alert_rule_id
            """,
            [
                payload.rule_name,
                payload.target_scope,
                payload.keyword_query,
                payload.min_importance,
                payload.sentiment_threshold,
                payload.breaking_only,
                payload.delivery_channel,
                alert_rule_id,
                user_id,
            ],
        ).fetchone()
        if result is None:
            raise LookupError(f"News alert rule not found: {alert_rule_id}")
        self._replace_alert_assets(alert_rule_id, payload.asset_ids)
        self._replace_alert_portfolios(alert_rule_id, payload.portfolio_ids)
        return self.alert_rule(alert_rule_id, user_id=user_id)

    def delete_alert_rule(self, alert_rule_id: int, *, user_id: str = "local") -> dict[str, int | str]:
        if self.conn.execute(
            "SELECT 1 FROM news_alert_rule WHERE alert_rule_id = ? AND user_id = ?",
            [alert_rule_id, user_id],
        ).fetchone() is None:
            raise LookupError(f"News alert rule not found: {alert_rule_id}")
        self.conn.execute("DELETE FROM news_alert_delivery WHERE alert_rule_id = ?", [alert_rule_id])
        self.conn.execute("DELETE FROM news_alert_rule_asset WHERE alert_rule_id = ?", [alert_rule_id])
        self.conn.execute("DELETE FROM news_alert_rule_portfolio WHERE alert_rule_id = ?", [alert_rule_id])
        self.conn.execute("DELETE FROM news_alert_rule WHERE alert_rule_id = ? AND user_id = ?", [alert_rule_id, user_id])
        return {"status": "deleted", "alert_rule_id": alert_rule_id}

    def alert_rule(self, alert_rule_id: int, *, user_id: str = "local") -> NewsAlertRuleResponse:
        rules = self.alert_rules(user_id=user_id, alert_rule_id=alert_rule_id)
        if not rules:
            raise LookupError(f"News alert rule not found: {alert_rule_id}")
        return rules[0]

    def alert_rules(
        self,
        *,
        user_id: str = "local",
        alert_rule_id: int | None = None,
    ) -> list[NewsAlertRuleResponse]:
        params: list[Any] = [user_id]
        rule_filter = ""
        if alert_rule_id is not None:
            rule_filter = "AND alert_rule_id = ?"
            params.append(alert_rule_id)
        rows = self.conn.execute(
            f"""
            SELECT
                alert_rule_id, user_id, rule_name, target_scope, keyword_query,
                min_importance, sentiment_threshold, breaking_only, is_active,
                delivery_channel, created_at, updated_at
            FROM news_alert_rule
            WHERE user_id = ?
            {rule_filter}
            ORDER BY is_active DESC, updated_at DESC, alert_rule_id DESC
            """,
            params,
        ).fetchall()
        rule_ids = [int(row[0]) for row in rows]
        assets = self._alert_assets(rule_ids)
        portfolios = self._alert_portfolios(rule_ids)
        return [
            NewsAlertRuleResponse(
                alert_rule_id=int(row[0]),
                user_id=row[1],
                rule_name=row[2],
                target_scope=row[3],
                keyword_query=row[4],
                min_importance=row[5],
                sentiment_threshold=row[6],
                breaking_only=bool(row[7]),
                is_active=bool(row[8]),
                delivery_channel=row[9],
                asset_ids=assets.get(int(row[0]), []),
                portfolio_ids=portfolios.get(int(row[0]), []),
                created_at=row[10],
                updated_at=row[11],
            )
            for row in rows
        ]

    def set_read_state(
        self,
        article_id: int,
        *,
        is_read: bool,
        user_id: str = "local",
    ) -> NewsUserStateResponse:
        if self.conn.execute("SELECT 1 FROM news_article WHERE article_id = ?", [article_id]).fetchone() is None:
            raise LookupError(f"News article not found: {article_id}")
        self.conn.execute(
            """
            INSERT INTO news_user_article_state(
                user_id, article_id, is_read, read_at, created_at, updated_at
            )
            VALUES (?, ?, ?, CASE WHEN ? THEN now() ELSE NULL END, now(), now())
            ON CONFLICT(user_id, article_id) DO UPDATE SET
                is_read = excluded.is_read,
                read_at = CASE WHEN excluded.is_read THEN COALESCE(news_user_article_state.read_at, now()) ELSE NULL END,
                updated_at = now()
            """,
            [user_id, article_id, is_read, is_read],
        )
        return self.user_state(article_id, user_id=user_id)

    def set_saved_state(
        self,
        article_id: int,
        *,
        is_saved: bool,
        user_id: str = "local",
    ) -> NewsUserStateResponse:
        if self.conn.execute("SELECT 1 FROM news_article WHERE article_id = ?", [article_id]).fetchone() is None:
            raise LookupError(f"News article not found: {article_id}")
        self.conn.execute(
            """
            INSERT INTO news_user_article_state(
                user_id, article_id, is_saved, saved_at, created_at, updated_at
            )
            VALUES (?, ?, ?, CASE WHEN ? THEN now() ELSE NULL END, now(), now())
            ON CONFLICT(user_id, article_id) DO UPDATE SET
                is_saved = excluded.is_saved,
                saved_at = CASE WHEN excluded.is_saved THEN COALESCE(news_user_article_state.saved_at, now()) ELSE NULL END,
                updated_at = now()
            """,
            [user_id, article_id, is_saved, is_saved],
        )
        return self.user_state(article_id, user_id=user_id)

    def user_state(self, article_id: int, user_id: str = "local") -> NewsUserStateResponse:
        row = self.conn.execute(
            """
            SELECT article_id, user_id, is_read, read_at, is_saved, saved_at
            FROM news_user_article_state
            WHERE article_id = ? AND user_id = ?
            """,
            [article_id, user_id],
        ).fetchone()
        if row is None:
            return NewsUserStateResponse(article_id=article_id, user_id=user_id)
        return NewsUserStateResponse(
            article_id=int(row[0]),
            user_id=row[1],
            is_read=bool(row[2]),
            read_at=row[3],
            is_saved=bool(row[4]),
            saved_at=row[5],
        )

    def _replace_alert_assets(self, alert_rule_id: int, asset_ids: list[str]) -> None:
        self.conn.execute("DELETE FROM news_alert_rule_asset WHERE alert_rule_id = ?", [alert_rule_id])
        for asset_id in dict.fromkeys(item.upper().strip() for item in asset_ids if item.strip()):
            self.conn.execute(
                "INSERT INTO news_alert_rule_asset(alert_rule_id, asset_id) VALUES (?, ?)",
                [alert_rule_id, asset_id],
            )

    def _replace_alert_portfolios(self, alert_rule_id: int, portfolio_ids: list[int]) -> None:
        self.conn.execute("DELETE FROM news_alert_rule_portfolio WHERE alert_rule_id = ?", [alert_rule_id])
        for portfolio_id in dict.fromkeys(portfolio_ids):
            self.conn.execute(
                "INSERT INTO news_alert_rule_portfolio(alert_rule_id, portfolio_id) VALUES (?, ?)",
                [alert_rule_id, portfolio_id],
            )

    def _alert_assets(self, rule_ids: list[int]) -> dict[int, list[str]]:
        if not rule_ids:
            return {}
        placeholders = ", ".join("?" for _ in rule_ids)
        rows = self.conn.execute(
            f"""
            SELECT alert_rule_id, asset_id
            FROM news_alert_rule_asset
            WHERE alert_rule_id IN ({placeholders})
            ORDER BY alert_rule_id, asset_id
            """,
            rule_ids,
        ).fetchall()
        grouped: dict[int, list[str]] = {}
        for row in rows:
            grouped.setdefault(int(row[0]), []).append(row[1])
        return grouped

    def _alert_portfolios(self, rule_ids: list[int]) -> dict[int, list[int]]:
        if not rule_ids:
            return {}
        placeholders = ", ".join("?" for _ in rule_ids)
        rows = self.conn.execute(
            f"""
            SELECT alert_rule_id, portfolio_id
            FROM news_alert_rule_portfolio
            WHERE alert_rule_id IN ({placeholders})
            ORDER BY alert_rule_id, portfolio_id
            """,
            rule_ids,
        ).fetchall()
        grouped: dict[int, list[int]] = {}
        for row in rows:
            grouped.setdefault(int(row[0]), []).append(int(row[1]))
        return grouped

    def _filters(self, **filters: Any) -> tuple[list[str], list[Any]]:
        where = ["COALESCE(a.is_active, TRUE) = TRUE"]
        params: list[Any] = []
        if filters.get("q"):
            like = f"%{str(filters['q']).strip().lower()}%"
            where.append(
                "("
                "LOWER(COALESCE(a.headline, a.title)) LIKE ? OR "
                "LOWER(COALESCE(a.summary, '')) LIKE ? OR "
                "LOWER(a.source_name) LIKE ? OR "
                "EXISTS ("
                " SELECT 1 FROM news_article_asset aa JOIN asset ax ON ax.asset_id = aa.asset_id"
                " WHERE aa.article_id = a.article_id AND ("
                " LOWER(ax.asset_id) LIKE ? OR LOWER(COALESCE(ax.symbol, ax.asset_id)) LIKE ? OR"
                " LOWER(COALESCE(ax.name, '')) LIKE ?"
                " )"
                ") OR EXISTS ("
                " SELECT 1 FROM news_article_category ac JOIN news_category c ON c.category_id = ac.category_id"
                " WHERE ac.article_id = a.article_id AND LOWER(c.category_code) LIKE ?"
                ")"
                ")"
            )
            params.extend([like, like, like, like, like, like, like])
        if filters.get("provider"):
            where.append("LOWER(COALESCE(p.provider_code, a.provider)) = LOWER(?)")
            params.append(filters["provider"])
        if filters.get("source"):
            where.append("LOWER(a.source_name) = LOWER(?)")
            params.append(filters["source"])
        if filters.get("asset_id"):
            asset_ids = self._coerce_asset_ids(filters["asset_id"])
            placeholders = ", ".join("?" for _ in asset_ids)
            where.append(
                f"EXISTS (SELECT 1 FROM news_article_asset aa WHERE aa.article_id = a.article_id AND UPPER(aa.asset_id) IN ({placeholders}))"
            )
            params.extend(asset_ids)
        if filters.get("portfolio_id") is not None:
            where.append(
                "EXISTS ("
                " SELECT 1"
                " FROM news_article_asset aa"
                " JOIN position pos ON UPPER(pos.asset_id) = UPPER(aa.asset_id)"
                " WHERE aa.article_id = a.article_id AND pos.portfolio_id = ? AND COALESCE(pos.qty, 0) <> 0"
                " UNION ALL"
                " SELECT 1"
                " FROM news_article_asset aa"
                " JOIN position pos ON UPPER("
                "   CASE"
                "     WHEN POSITION('.' IN pos.asset_id) > 0 THEN"
                "       CASE SPLIT_PART(pos.asset_id, '.', 1)"
                "         WHEN 'NOWS' THEN 'NOW'"
                "         WHEN 'VISA' THEN 'V'"
                "         ELSE SPLIT_PART(pos.asset_id, '.', 1)"
                "       END"
                "     ELSE pos.asset_id"
                "   END"
                " ) = UPPER(aa.asset_id)"
                " JOIN asset held_asset ON held_asset.asset_id = pos.asset_id"
                " WHERE aa.article_id = a.article_id AND pos.portfolio_id = ? AND COALESCE(pos.qty, 0) <> 0"
                "   AND ("
                "     LOWER(COALESCE(held_asset.asset_subtype, '')) LIKE '%cdr%'"
                "     OR LOWER(COALESCE(held_asset.name, '')) LIKE '%depositary receipt%'"
                "     OR LOWER(COALESCE(held_asset.description, '')) LIKE '%depositary receipt%'"
                "     OR LOWER(COALESCE(held_asset.name, '')) LIKE '% cdr%'"
                "     OR LOWER(COALESCE(held_asset.description, '')) LIKE '% cdr%'"
                "   )"
                ")"
            )
            params.extend([filters["portfolio_id"], filters["portfolio_id"]])
        if filters.get("category"):
            where.append(
                "EXISTS ("
                " SELECT 1 FROM news_article_category ac JOIN news_category c ON c.category_id = ac.category_id"
                " WHERE ac.article_id = a.article_id AND c.category_code = ?"
                ")"
            )
            params.append(filters["category"])
        if filters.get("sentiment"):
            where.append("a.sentiment_label = ?")
            params.append(filters["sentiment"])
        if filters.get("breaking") is not None:
            where.append("COALESCE(a.is_breaking, FALSE) = ?")
            params.append(filters["breaking"])
        if filters.get("press_release") is not None:
            where.append("COALESCE(a.is_press_release, FALSE) = ?")
            params.append(filters["press_release"])
        if filters.get("start_date") is not None:
            where.append("CAST(a.published_at AS DATE) >= ?")
            params.append(filters["start_date"])
        if filters.get("end_date") is not None:
            where.append("CAST(a.published_at AS DATE) <= ?")
            params.append(filters["end_date"])
        return where, params

    def _feed_metadata(self) -> dict[str, Any]:
        rows = self.provider_health(stale_after_minutes=120)
        if not rows:
            return {
                "last_successful_sync_at": None,
                "provider_status": "not_started",
                "provider_message": "No news provider sync has run yet.",
                "is_cached": True,
            }
        successes = [row.last_succeeded_at for row in rows if row.last_succeeded_at is not None]
        failures = [row for row in rows if row.status in {"failed", "stale"}]
        status_text = "healthy"
        if failures and successes:
            status_text = "degraded"
        elif failures:
            status_text = "failed"
        message = None
        if failures:
            message = "; ".join(
                f"{row.provider_code}: {row.last_error_message or row.status}" for row in failures[:3]
            )
        return {
            "last_successful_sync_at": max(successes) if successes else None,
            "provider_status": status_text,
            "provider_message": message,
            "is_cached": True,
        }

    def _recent_refresh_attempt(self, *, minutes: int) -> bool:
        row = self.conn.execute(
            """
            SELECT MAX(last_attempted_at)
            FROM news_ingestion_state
            WHERE feed_type IN ('subscribed', 'earnings')
            """
        ).fetchone()
        if not row or row[0] is None:
            return False
        attempted = row[0]
        now = datetime.now(UTC) if attempted.tzinfo else datetime.now()
        return (now - attempted) < timedelta(minutes=minutes)

    def _latest_provider_timestamp(self, provider_code: str, feed_type: str) -> datetime | None:
        row = self.conn.execute(
            """
            SELECT s.last_provider_timestamp
            FROM news_ingestion_state s
            JOIN news_provider p ON p.provider_id = s.provider_id
            WHERE p.provider_code = ? AND s.feed_type = ?
            """,
            [provider_code, feed_type],
        ).fetchone()
        return None if not row else row[0]

    @staticmethod
    def _result_dict(result) -> dict[str, int | str | None]:
        return {
            "provider_code": result.provider_code,
            "status": result.status,
            "articles_received": result.articles_received,
            "articles_inserted": result.articles_inserted,
            "articles_updated": result.articles_updated,
            "articles_rejected": result.articles_rejected,
            "asset_links_written": result.asset_links_written,
            "categories_written": result.categories_written,
            "clusters_written": result.clusters_written,
            "error_message": result.error_message,
        }

    @staticmethod
    def _score_sql(*, portfolio_id: int | None) -> str:
        if portfolio_id is None:
            return """
            COALESCE((
                SELECT MAX(aa.relevance_score * aa.confidence_score)
                FROM news_article_asset aa
                WHERE aa.article_id = a.article_id
            ), 0.25) * COALESCE(a.importance_score, 0.3)
            """
        return f"""
            COALESCE((
                SELECT MAX(
                    aa.relevance_score
                    * aa.confidence_score
                    * COALESCE(a.importance_score, 0.3)
                    * (
                        0.5 + LEAST(
                            0.35,
                            ABS(pos.book_cost) / NULLIF((
                                SELECT SUM(ABS(total_pos.book_cost))
                                FROM position total_pos
                                WHERE total_pos.portfolio_id = pos.portfolio_id
                                  AND COALESCE(total_pos.qty, 0) <> 0
                            ), 0)
                        ) * 1.5
                    )
                )
                FROM news_article_asset aa
                JOIN position pos
                  ON UPPER(pos.asset_id) = UPPER(aa.asset_id)
                  OR UPPER(
                    CASE
                      WHEN POSITION('.' IN pos.asset_id) > 0 THEN
                        CASE SPLIT_PART(pos.asset_id, '.', 1)
                          WHEN 'NOWS' THEN 'NOW'
                          WHEN 'VISA' THEN 'V'
                          ELSE SPLIT_PART(pos.asset_id, '.', 1)
                        END
                      ELSE pos.asset_id
                    END
                  ) = UPPER(aa.asset_id)
                LEFT JOIN asset held_asset ON held_asset.asset_id = pos.asset_id
                WHERE aa.article_id = a.article_id
                  AND pos.portfolio_id = {int(portfolio_id)}
                  AND COALESCE(pos.qty, 0) <> 0
                  AND (
                    UPPER(pos.asset_id) = UPPER(aa.asset_id)
                    OR LOWER(COALESCE(held_asset.asset_subtype, '')) LIKE '%cdr%'
                    OR LOWER(COALESCE(held_asset.name, '')) LIKE '%depositary receipt%'
                    OR LOWER(COALESCE(held_asset.description, '')) LIKE '%depositary receipt%'
                    OR LOWER(COALESCE(held_asset.name, '')) LIKE '% cdr%'
                    OR LOWER(COALESCE(held_asset.description, '')) LIKE '% cdr%'
                  )
            ), 0.0)
            """

    def _asset_filter_ids(self, asset_id: str) -> list[str]:
        normalized = str(asset_id).upper().strip()
        asset_ids = [normalized]
        try:
            valuation_asset_id = AnalyticsRepository(self.conn).valuation_asset_id(normalized)
        except Exception:
            valuation_asset_id = normalized
        if valuation_asset_id and valuation_asset_id.upper() not in asset_ids:
            asset_ids.append(valuation_asset_id.upper())
        return asset_ids

    @staticmethod
    def _coerce_asset_ids(value: Any) -> list[str]:
        values = value if isinstance(value, list) else [value]
        normalized = [str(item).upper().strip() for item in values if str(item).strip()]
        return normalized or [""]

    def _count_for_empty(self, where_sql: str, params: list[Any]) -> int:
        row = self.conn.execute(
            f"""
            SELECT COUNT(*)
            FROM news_article a
            LEFT JOIN news_provider p ON p.provider_id = a.provider_id
            {where_sql}
            """,
            params,
        ).fetchone()
        return int(row[0])

    def _assets_by_article(self, article_ids: list[int]) -> dict[int, list[NewsArticleAssetResponse]]:
        if not article_ids:
            return {}
        placeholders = ", ".join("?" for _ in article_ids)
        rows = self.conn.execute(
            f"""
            SELECT
                aa.article_id,
                aa.asset_id,
                COALESCE(a.symbol, a.asset_id) AS symbol,
                a.name,
                aa.relevance_score,
                aa.confidence_score,
                aa.match_method,
                aa.is_primary_entity
            FROM news_article_asset aa
            JOIN asset a ON a.asset_id = aa.asset_id
            WHERE aa.article_id IN ({placeholders})
            ORDER BY aa.article_id, aa.is_primary_entity DESC, aa.confidence_score DESC
            """,
            article_ids,
        ).fetchall()
        grouped: dict[int, list[NewsArticleAssetResponse]] = {}
        for row in rows:
            grouped.setdefault(int(row[0]), []).append(
                NewsArticleAssetResponse(
                    asset_id=row[1],
                    symbol=row[2],
                    name=row[3],
                    relevance_score=float(row[4]),
                    confidence_score=float(row[5]),
                    match_method=row[6],
                    is_primary_entity=bool(row[7]),
                )
            )
        return grouped

    def _categories_by_article(
        self,
        article_ids: list[int],
    ) -> dict[int, list[NewsArticleCategoryResponse]]:
        if not article_ids:
            return {}
        placeholders = ", ".join("?" for _ in article_ids)
        rows = self.conn.execute(
            f"""
            SELECT
                ac.article_id,
                c.category_code,
                c.category_name,
                ac.confidence_score,
                ac.is_primary
            FROM news_article_category ac
            JOIN news_category c ON c.category_id = ac.category_id
            WHERE ac.article_id IN ({placeholders})
            ORDER BY ac.article_id, ac.is_primary DESC, ac.confidence_score DESC
            """,
            article_ids,
        ).fetchall()
        grouped: dict[int, list[NewsArticleCategoryResponse]] = {}
        for row in rows:
            grouped.setdefault(int(row[0]), []).append(
                NewsArticleCategoryResponse(
                    category_code=row[1],
                    category_name=row[2],
                    confidence_score=float(row[3]),
                    is_primary=bool(row[4]),
                )
            )
        return grouped

    def _clusters_by_article(self, article_ids: list[int]) -> dict[int, NewsStoryClusterSummary]:
        if not article_ids:
            return {}
        placeholders = ", ".join("?" for _ in article_ids)
        rows = self.conn.execute(
            f"""
            SELECT
                ca.article_id,
                c.cluster_id,
                c.cluster_key,
                c.article_count,
                c.importance_score,
                c.first_published_at,
                c.last_updated_at
            FROM news_story_cluster_article ca
            JOIN news_story_cluster c ON c.cluster_id = ca.cluster_id
            WHERE ca.article_id IN ({placeholders})
            """,
            article_ids,
        ).fetchall()
        return {
            int(row[0]): NewsStoryClusterSummary(
                cluster_id=int(row[1]),
                cluster_key=row[2],
                article_count=int(row[3]),
                importance_score=float(row[4]),
                first_published_at=row[5],
                last_updated_at=row[6],
            )
            for row in rows
        }

    @staticmethod
    def _article_from_row(
        row,
        *,
        assets: list[NewsArticleAssetResponse],
        categories: list[NewsArticleCategoryResponse],
        cluster: NewsStoryClusterSummary | None,
    ) -> NewsArticleResponse:
        return NewsArticleResponse(
            article_id=int(row[0]),
            provider_code=row[1],
            provider_name=row[2],
            provider_article_id=row[3],
            headline=row[4],
            summary=row[5],
            canonical_url=row[6],
            source_name=row[7],
            author=row[8],
            language=row[9],
            published_at=row[10],
            updated_at=row[11],
            importance_score=row[12],
            relevance_score=row[13],
            sentiment_score=row[14],
            sentiment_label=row[15],
            is_breaking=bool(row[16]),
            is_press_release=bool(row[17]),
            is_correction=bool(row[18]),
            is_retracted=bool(row[19]),
            is_paywalled=bool(row[20]),
            is_read=bool(row[21]),
            is_saved=bool(row[22]),
            assets=assets,
            categories=categories,
            cluster=cluster,
        )
