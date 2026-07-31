"""Market, sentiment, calendar, and benchmark ingestion commands."""

from datetime import date, timedelta

from dashboard.ingestion.corporate_calendar.service import CorporateCalendarIngestionService
from dashboard.ingestion.indices.index_service_factory import (
    create_index_ingestion_service,
    create_index_scheduler,
)
from dashboard.ingestion.rate_limits import default_rate_limiter
from dashboard.ingestion.ticker_universe import TickerUniverseRepository
from dashboard.ingestion.trading_calendar.service import TradingCalendarIngestionService


def _price_history_service(conn):
    # Keep the historical dashboard.models.storage patch point used by callers and tests.
    from dashboard.models import storage

    return storage.PriceHistoryIngestionService(conn)


def _scoped_ingestible_asset_ids(
    conn,
    asset_id: str | None = None,
    asset_types: tuple[str, ...] | None = None,
) -> list[str]:
    asset_ids = TickerUniverseRepository(conn).ingestible_asset_ids(
        include_watchlist=True,
        asset_types=asset_types,
    )
    if asset_id is None:
        return asset_ids

    normalized = asset_id.upper().strip()
    return [normalized] if normalized in set(asset_ids) else []


class IngestionCommands:
    def enqueue_market_backfill(
        self,
        asset_id: str | None = None,
        years: int = 10,
        include_dividends: bool = True,
        include_splits: bool = True,
    ) -> int:
        """
        Enqueue Domain A market backfill jobs.

        If asset_id is None, enqueue jobs for all tracked assets.
        """
        service = _price_history_service(self.conn)

        if asset_id is None:
            job_ids = service.enqueue_backfill_all(
                years=years,
                include_dividends=include_dividends,
                include_splits=include_splits,
            )
        else:
            job_ids = service.enqueue_backfill_one(
                asset_id=asset_id.upper().strip(),
                years=years,
                include_dividends=include_dividends,
                include_splits=include_splits,
            )

        return len(job_ids)

    def enqueue_market_refresh(
        self,
        asset_id: str | None = None,
        include_dividends: bool = True,
        include_splits: bool = True,
    ) -> int:
        """
        Enqueue Domain A market refresh jobs.

        If asset_id is None, enqueue jobs for all tracked assets.
        """
        service = _price_history_service(self.conn)

        if asset_id is None:
            job_ids = service.enqueue_refresh_all(
                include_dividends=include_dividends,
                include_splits=include_splits,
            )
        else:
            job_ids = service.enqueue_refresh_one(
                asset_id=asset_id.upper().strip(),
                include_dividends=include_dividends,
                include_splits=include_splits,
            )

        return len(job_ids)

    def list_ingestion_jobs(
        self,
        statuses: list[str] | None = None,
        domain: str | None = None,
        limit: int | None = None,
    ):
        """
        Return ingestion jobs for dev inspection.
        """
        where = []
        params: list[object] = []

        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            where.append(f"status IN ({placeholders})")
            params.extend(statuses)

        if domain:
            where.append("domain = ?")
            params.append(domain)

        query = """
            SELECT
                job_id,
                asset_id,
                domain,
                job_type,
                dataset,
                status,
                priority,
                requested_start_date,
                requested_end_date,
                attempt_count,
                error_message,
                created_at,
                updated_at
            FROM ingestion_job
        """

        if where:
            query += " WHERE " + " AND ".join(where)

        query += " ORDER BY status, priority DESC, created_at ASC"

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        return self.conn.execute(query, params).fetchall()

    def schedule_ingestion_jobs(
        self,
        pipeline: str = "all",
        asset_id: str | None = None,
        max_assets: int = 25,
        years: int = 10,
        prices_only: bool = False,
        calendar_year: int | None = None,
        ranking_factor: str = "aggregate",
        ranking_universe: str = "tracked",
        ranking_timeframe: str = "monthly",
        missing_only: bool = False,
        stale_only: bool = False,
    ) -> int:
        """
        Master scheduler for dev ingestion commands.
        """
        include_dividends = not prices_only
        include_splits = not prices_only
        pipeline = pipeline.replace("_", "-").lower()

        if asset_id is not None and asset_id.lower() == "all":
            asset_id = None
        asset_id = asset_id.upper().strip() if asset_id else None

        if pipeline == "all":
            total = 0
            total += self.schedule_due_price_history_backfills(
                max_assets=max_assets,
                years=years,
                asset_id=asset_id,
            )
            total += self.schedule_due_market_refreshes(
                max_assets=max_assets,
                asset_id=asset_id,
                include_dividends=include_dividends,
                include_splits=include_splits,
            )
            if asset_id is None:
                total += self.schedule_due_corporate_calendar_refresh()
                total += self.schedule_due_corporate_fundamental_updates(max_assets=max_assets)
            total += self.schedule_due_fundamental_backfills(
                max_assets=max_assets,
                asset_id=asset_id,
            )
            total += self.schedule_due_fundamental_refreshes(
                max_assets=max_assets,
                asset_id=asset_id,
            )
            return total

        if pipeline == "market":
            total = 0
            total += self.schedule_due_price_history_backfills(
                max_assets=max_assets,
                years=years,
                asset_id=asset_id,
            )
            total += self.schedule_due_market_refreshes(
                max_assets=max_assets,
                asset_id=asset_id,
                include_dividends=include_dividends,
                include_splits=include_splits,
            )
            return total

        if pipeline == "corporate":
            total = 0
            if asset_id is None:
                total += self.schedule_due_corporate_calendar_refresh()
                total += self.schedule_due_corporate_fundamental_updates(max_assets=max_assets)
            total += self.schedule_due_fundamental_backfills(
                max_assets=max_assets,
                asset_id=asset_id,
            )
            total += self.schedule_due_fundamental_refreshes(
                max_assets=max_assets,
                asset_id=asset_id,
            )
            return total

        if pipeline == "sentiment":
            return self.schedule_due_sentiment_snapshot_refreshes(max_assets=max_assets)

        if pipeline == "ranking":
            return self.schedule_ranking_input_jobs(
                factor=ranking_factor,
                universe=ranking_universe,
                asset_id=asset_id,
                max_assets=max_assets,
                years=years,
                timeframe=ranking_timeframe,
                missing_only=missing_only,
                stale_only=stale_only,
            )

        if pipeline == "price-backfill":
            return self.enqueue_market_backfill(
                asset_id=asset_id,
                years=years,
                include_dividends=include_dividends,
                include_splits=include_splits,
            )

        if pipeline == "due-price-backfill":
            return self.schedule_due_price_history_backfills(
                max_assets=max_assets,
                years=years,
                asset_id=asset_id,
            )

        if pipeline == "price-refresh":
            return self.enqueue_market_refresh(
                asset_id=asset_id,
                include_dividends=include_dividends,
                include_splits=include_splits,
            )

        if pipeline == "corporate-calendar":
            return self.schedule_due_corporate_calendar_refresh()

        if pipeline == "earnings-updates":
            return self.schedule_due_corporate_fundamental_updates(max_assets=max_assets)

        if pipeline == "fundamentals-backfill":
            return self.schedule_due_fundamental_backfills(
                max_assets=max_assets,
                asset_id=asset_id,
            )

        if pipeline == "fundamentals-refresh":
            return self.schedule_due_fundamental_refreshes(
                max_assets=max_assets,
                asset_id=asset_id,
            )

        if pipeline == "metadata":
            return self.refresh_due_asset_metadata(max_assets=max_assets)

        if pipeline == "metadata-refresh":
            return self.refresh_asset_metadata(asset_id=asset_id)

        if pipeline == "trading-calendar":
            return self.refresh_trading_calendar(market_code="all", year=calendar_year)

        raise ValueError(f"Unsupported ingestion pipeline: {pipeline}")

    def schedule_due_routine_ingestion_jobs(
        self,
        max_assets: int = 25,
        years: int = 10,
        prices_only: bool = False,
    ) -> int:
        """
        Schedule routine background-safe ingestion work.

        This intentionally excludes historical backfills, provider-sensitive
        news/social refreshes, retries, and broker work. Those remain explicit
        Operations actions.
        """
        include_dividends = not prices_only
        include_splits = not prices_only
        total = 0
        total += self.schedule_due_market_refreshes(
            max_assets=max_assets,
            include_dividends=include_dividends,
            include_splits=include_splits,
        )
        total += self.schedule_due_corporate_calendar_refresh()
        total += self.schedule_due_corporate_fundamental_updates(max_assets=max_assets)
        total += self.schedule_due_fundamental_refreshes(max_assets=max_assets)
        total += self.schedule_due_sentiment_snapshot_refreshes(max_assets=max_assets)
        return total

    def run_ingestion_jobs(self, domain: str = "all", max_jobs: int = 1) -> int:
        """
        Process pending ingestion jobs through the shared dev command surface.
        """
        default_rate_limiter().reset_run_counts()
        domain = domain.lower()

        if domain == "market":
            return _price_history_service(self.conn).process_jobs(max_jobs=max_jobs)

        if domain == "corporate":
            return CorporateCalendarIngestionService(self.conn).process_jobs(max_jobs=max_jobs)

        if domain == "sentiment":
            from dashboard.ingestion_sentiment.scheduler import SentimentIngestionScheduler

            return SentimentIngestionScheduler(self.conn).run_sentiment_jobs(max_jobs=max_jobs)

        if domain != "all":
            raise ValueError(f"Unsupported ingestion job domain: {domain}")

        completed = 0
        while completed < max_jobs:
            did_market = _price_history_service(self.conn).process_jobs(max_jobs=1)
            if did_market:
                completed += did_market
                continue

            did_corporate = CorporateCalendarIngestionService(self.conn).process_jobs(max_jobs=1)
            if did_corporate:
                completed += did_corporate
                continue

            from dashboard.ingestion_sentiment.scheduler import SentimentIngestionScheduler

            did_sentiment = SentimentIngestionScheduler(self.conn).run_sentiment_jobs(max_jobs=1)
            if did_sentiment:
                completed += did_sentiment
                continue

            break

        return completed

    def sentiment_refresh(self, target: str, source: str = "all") -> int:
        from dashboard.ingestion_sentiment.scheduler import SentimentIngestionScheduler
        from dashboard.ingestion_sentiment.service import SentimentIngestionService
        from dashboard.ingestion_sentiment.providers.provider_registry import (
            default_news_providers,
            default_social_providers,
        )

        target = target.upper().strip()
        source = source.lower().strip()

        if target == "ALL":
            scheduler = SentimentIngestionScheduler(self.conn)
            total = 0
            if source in {"all", "news"}:
                total += len(scheduler.enqueue_news_refresh_for_universe())
            if source in {"all", "reddit", "x", "social", "retail"}:
                total += len(
                    scheduler.enqueue_retail_sentiment_refresh_for_universe(
                        source="all" if source in {"all", "social", "retail"} else source
                    )
                )
            return total

        return SentimentIngestionService(
            self.conn,
            news_providers=default_news_providers(),
            social_providers=default_social_providers(),
        ).refresh_ticker(target, source=source)

    def run_sentiment_jobs(self, max_jobs: int = 1) -> int:
        from dashboard.ingestion_sentiment.scheduler import SentimentIngestionScheduler

        return SentimentIngestionScheduler(self.conn).run_sentiment_jobs(max_jobs=max_jobs)

    def list_news_for_ticker(self, ticker: str, limit: int = 10, days: int = 30):
        from dashboard.ingestion_sentiment.repo import SentimentIngestionRepository

        return SentimentIngestionRepository(self.conn).list_news_for_ticker(ticker, limit=limit)

    def list_social_for_ticker(self, ticker: str, limit: int = 10, days: int = 30):
        from dashboard.ingestion_sentiment.repo import SentimentIngestionRepository

        return SentimentIngestionRepository(self.conn).list_social_for_ticker(ticker, limit=limit)

    def refresh_factor_snapshot(self, target: str) -> int:
        from datetime import date
        from dashboard.ingestion_sentiment.scheduler import SentimentIngestionScheduler
        from dashboard.ingestion_sentiment.service import SentimentIngestionService

        target = target.upper().strip()
        if target == "ALL":
            return len(
                SentimentIngestionScheduler(self.conn).enqueue_factor_snapshot_refresh(
                    snapshot_date=date.today()
                )
            )
        return SentimentIngestionService(self.conn).refresh_factor_snapshot(target, date.today())

    def refresh_quant_rating(self, target: str) -> int:
        from datetime import date
        from dashboard.ingestion_sentiment.scheduler import SentimentIngestionScheduler
        from dashboard.ingestion_sentiment.service import SentimentIngestionService

        target = target.upper().strip()
        if target == "ALL":
            return len(
                SentimentIngestionScheduler(self.conn).enqueue_quant_rating_refresh(
                    snapshot_date=date.today()
                )
            )
        return SentimentIngestionService(self.conn).refresh_quant_rating(target, date.today())

    def sentiment_summary(self, ticker: str) -> str:
        ticker = ticker.upper().strip()
        row = self.conn.execute(
            """
            SELECT ticker, blended_sentiment_score, retail_sentiment_score, news_sentiment_score
            FROM ticker_sentiment_daily
            WHERE ticker = ?
            ORDER BY date DESC
            LIMIT 1
            """,
            [ticker],
        ).fetchone()
        if row is None:
            return f"Ticker: {ticker}\nNo sentiment summary found."

        return (
            f"Ticker: {row[0]}\n"
            f"Blended sentiment: {self._sentiment_label(row[1])} ({self._fmt_score(row[1])})\n"
            f"Retail sentiment: {self._sentiment_label(row[2])} ({self._fmt_score(row[2])})\n"
            f"News sentiment: {self._sentiment_label(row[3])} ({self._fmt_score(row[3])})"
        )

    def quant_summary(self, ticker: str) -> str:
        ticker = ticker.upper().strip()
        row = self.conn.execute(
            """
            SELECT
                ticker,
                overall_quant_score,
                overall_quant_rating,
                factor_profile,
                growth_rating,
                value_rating,
                quality_rating,
                momentum_rating,
                defensive_rating,
                dividend_rating,
                volatility_rating
            FROM ticker_quant_rating_snapshot
            WHERE ticker = ?
            ORDER BY snapshot_date DESC
            LIMIT 1
            """,
            [ticker],
        ).fetchone()
        if row is None:
            return f"Ticker: {ticker}\nNo quant summary found."

        return (
            f"Ticker: {row[0]}\n"
            f"Internal quant rating: {row[2]} ({self._fmt_score(row[1])})\n"
            f"Quant profile: {row[3] or 'Unclassified'}\n"
            f"Factor ratings: Growth {row[4] or '-'}, Value {row[5] or '-'}, "
            f"Quality {row[6] or '-'}, Momentum {row[7] or '-'}, "
            f"Defensive {row[8] or '-'}, Dividend {row[9] or '-'}, "
            f"Volatility {row[10] or '-'}"
        )

    @staticmethod
    def _fmt_score(score) -> str:
        if score is None:
            return "n/a"
        return f"{score:+.2f}" if abs(score) <= 1 else f"{score:.0f}"

    @staticmethod
    def _sentiment_label(score) -> str:
        if score is None:
            return "No data"
        if score >= 0.4:
            return "Bullish"
        if score > 0.05:
            return "Neutral / Positive"
        if score <= -0.4:
            return "Bearish"
        if score < -0.05:
            return "Neutral / Negative"
        return "Neutral"

    def run_market_backfill_jobs(self, max_jobs: int = 1) -> int:
        """
        Process queued Domain A market backfill jobs.
        """
        service = _price_history_service(self.conn)
        return service.process_backfill_jobs(max_jobs=max_jobs)

    def run_market_refresh_jobs(self, max_jobs: int = 1) -> int:
        """
        Process queued Domain A market refresh jobs.
        """
        service = _price_history_service(self.conn)
        return service.process_refresh_jobs(max_jobs=max_jobs)

    def refresh_asset_metadata(self, asset_id: str | None = None) -> int:
        from dashboard.services.asset_importer import AssetImporter

        importer = AssetImporter(self)

        if asset_id is None:
            asset_ids = TickerUniverseRepository(self.conn).ingestible_asset_ids()
        else:
            asset_ids = [asset_id.upper().strip()]

        synced = importer.import_asset_ids(asset_ids)
        return len(synced)

    def refresh_due_asset_metadata(self, max_assets: int = 5) -> int:
        from dashboard.services.asset_importer import AssetImporter

        asset_ids = TickerUniverseRepository(self.conn).ingestible_asset_ids()
        if not asset_ids:
            return 0

        placeholders = ", ".join("?" for _ in asset_ids)
        rows = self.conn.execute(
            f"""
            SELECT asset_id
            FROM asset_metadata_sync
            WHERE asset_id IN ({placeholders})
              AND (
                sync_status IN ('pending', 'stale', 'failed')
                OR last_succeeded_at IS NULL
                OR last_succeeded_at < now() - INTERVAL 30 DAY
            )
            ORDER BY
                CASE sync_status
                    WHEN 'pending' THEN 1
                    WHEN 'failed' THEN 2
                    WHEN 'stale' THEN 3
                    ELSE 4
                END,
                last_attempted_at NULLS FIRST
            LIMIT ?
        """,
            [*asset_ids, max_assets],
        ).fetchall()

        asset_ids = [r[0] for r in rows]

        importer = AssetImporter(self)
        synced = importer.import_asset_ids(asset_ids)
        return len(synced)

    def schedule_due_price_history_backfills(
        self,
        max_assets: int = 3,
        years: int = 10,
        asset_id: str | None = None,
    ) -> int:
        asset_ids = _scoped_ingestible_asset_ids(self.conn, asset_id=asset_id)
        if not asset_ids:
            return 0

        placeholders = ", ".join("?" for _ in asset_ids)
        rows = self.conn.execute(
            f"""
          SELECT a.asset_id
            FROM asset a
            LEFT JOIN asset_sync_state s
            ON s.asset_id = a.asset_id
            AND s.domain = 'market'
            AND s.dataset = 'price_daily'
        WHERE a.asset_id IN ({placeholders})
        AND (
            s.asset_id IS NULL
            OR s.backfill_status IN ('not_started', 'failed')
            OR s.last_successful_date IS NULL
        )
        AND NOT EXISTS (
            SELECT 1
        FROM ingestion_job j
        WHERE j.asset_id = a.asset_id
        AND j.domain = 'market'
        AND j.dataset = 'price_daily'
        AND j.job_type = 'backfill'
        AND j.status IN ('pending', 'running'))
        ORDER BY a.asset_id
        LIMIT ?;
        """,
            [*asset_ids, max_assets],
        ).fetchall()

        service = _price_history_service(self.conn)

        total_jobs = 0
        for row in rows:
            asset_id = row[0]
            total_jobs += len(
                service.enqueue_backfill_one(
                    asset_id=asset_id,
                    years=years,
                    include_dividends=True,
                    include_splits=True,
                )
            )

        return total_jobs

    def schedule_due_market_refreshes(
        self,
        max_assets: int = 25,
        asset_id: str | None = None,
        include_dividends: bool = True,
        include_splits: bool = True,
    ) -> int:
        asset_ids = _scoped_ingestible_asset_ids(self.conn, asset_id=asset_id)
        if not asset_ids:
            return 0

        placeholders = ", ".join("?" for _ in asset_ids)
        rows = self.conn.execute(
            f"""
            SELECT a.asset_id
            FROM asset a
            WHERE a.asset_id IN ({placeholders})
              AND NOT EXISTS (
                  SELECT 1
                  FROM ingestion_job j
                  WHERE j.asset_id = a.asset_id
                    AND j.domain = 'market'
                    AND j.job_type = 'refresh'
                    AND j.dataset IN ('price_daily', 'dividends', 'splits')
                    AND j.status IN ('pending', 'running')
              )
            ORDER BY a.asset_id
            LIMIT ?
            """,
            [*asset_ids, max_assets],
        ).fetchall()

        total_jobs = 0
        for row in rows:
            total_jobs += self.enqueue_market_refresh(
                asset_id=row[0],
                include_dividends=include_dividends,
                include_splits=include_splits,
            )
        return total_jobs

    def run_price_history_backfill_jobs(self, max_jobs: int = 1) -> int:
        service = _price_history_service(self.conn)
        return service.process_backfill_jobs(max_jobs=max_jobs)

    def schedule_ranking_input_jobs(
        self,
        *,
        factor: str = "aggregate",
        universe: str = "tracked",
        asset_id: str | None = None,
        max_assets: int = 25,
        years: int = 10,
        timeframe: str = "monthly",
        missing_only: bool = False,
        stale_only: bool = False,
    ) -> int:
        factor = factor.replace("-", "_").lower().strip()
        universe = universe.lower().strip()
        if factor == "aggregate":
            total = 0
            for child_factor in [
                "share_price_momentum",
                "news_sentiment",
                "retail_sentiment",
                "earnings_momentum",
                "institutional_buying",
            ]:
                total += self.schedule_ranking_input_jobs(
                    factor=child_factor,
                    universe=universe,
                    asset_id=asset_id,
                    max_assets=max_assets,
                    years=years,
                    timeframe=timeframe,
                    missing_only=missing_only,
                    stale_only=stale_only,
                )
            return total

        asset_ids = self._ranking_asset_ids(
            universe=universe,
            asset_id=asset_id,
            max_assets=max_assets,
        )
        if not asset_ids:
            return 0

        if factor == "share_price_momentum":
            return self._schedule_ranking_price_jobs(
                asset_ids=asset_ids,
                years=years,
                missing_only=missing_only,
                stale_only=stale_only,
            )
        if factor == "news_sentiment":
            return self._schedule_ranking_sentiment_jobs(
                asset_ids=asset_ids,
                source="news",
                missing_only=missing_only,
                stale_only=stale_only,
            )
        if factor == "retail_sentiment":
            return self._schedule_ranking_sentiment_jobs(
                asset_ids=asset_ids,
                source="retail",
                missing_only=missing_only,
                stale_only=stale_only,
            )
        if factor == "earnings_momentum":
            return self._schedule_ranking_earnings_jobs(
                asset_ids=asset_ids,
                missing_only=missing_only,
                stale_only=stale_only,
            )
        if factor == "institutional_buying":
            from dashboard.api.services import PortfolioApiService

            rows = [
                {
                    "asset_id": asset_id,
                    "symbol": asset_id,
                    "exchange_code": None,
                    "currency": "USD",
                    "latest_price": None,
                    "market_value": None,
                    "is_tracked": True,
                    "is_held": False,
                    "is_watchlisted": False,
                    "latest_price_date": None,
                    "catalog_only": False,
                }
                for asset_id in asset_ids
            ]
            PortfolioApiService(self.conn)._ensure_stock_ranking_inputs(rows)
            return len(rows)
        raise ValueError(f"Unsupported ranking factor: {factor}")

    def _ranking_asset_ids(
        self,
        *,
        universe: str,
        asset_id: str | None,
        max_assets: int,
    ) -> list[str]:
        if asset_id:
            normalized = asset_id.upper().strip()
            self._ensure_catalog_asset(normalized)
            return [normalized]

        if universe == "tracked":
            return TickerUniverseRepository(self.conn).ingestible_asset_ids(
                include_watchlist=True,
                asset_types=("stock",),
            )[:max_assets]
        if universe != "all":
            raise ValueError(f"Unsupported ranking universe: {universe}")

        rows = self.conn.execute(
            """
            SELECT asset_id
            FROM asset
            WHERE COALESCE(asset_type, 'stock') = 'stock'
            ORDER BY asset_id
            LIMIT ?
            """,
            [max_assets],
        ).fetchall()
        asset_ids = [row[0] for row in rows]
        remaining = max_assets - len(asset_ids)
        if remaining <= 0:
            return asset_ids

        catalog_rows = self.conn.execute(
            """
            SELECT asset_id
            FROM stock_catalog
            WHERE asset_id NOT IN (SELECT asset_id FROM asset)
            ORDER BY symbol
            LIMIT ?
            """,
            [remaining],
        ).fetchall()
        for row in catalog_rows:
            self._ensure_catalog_asset(row[0])
            asset_ids.append(row[0])
        return asset_ids

    def _ensure_catalog_asset(self, asset_id: str) -> None:
        exists = self.conn.execute(
            "SELECT 1 FROM asset WHERE asset_id = ?",
            [asset_id],
        ).fetchone()
        if exists:
            return
        row = self.conn.execute(
            """
            SELECT asset_id, symbol, exchange_code, ccy, name, sector, industry, country, region
            FROM stock_catalog
            WHERE asset_id = ? OR UPPER(symbol) = UPPER(?)
            LIMIT 1
            """,
            [asset_id, asset_id],
        ).fetchone()
        if row is None:
            return
        self.conn.execute(
            """
            INSERT INTO asset(
                asset_id, symbol, exchange_code, asset_type, ccy, name,
                sector, industry, country, region, track
            )
            VALUES (?, ?, ?, 'stock', ?, ?, ?, ?, ?, ?, FALSE)
            """,
            list(row),
        )

    def _schedule_ranking_price_jobs(
        self,
        *,
        asset_ids: list[str],
        years: int,
        missing_only: bool,
        stale_only: bool,
    ) -> int:
        service = _price_history_service(self.conn)
        total = 0
        for asset_id in self._filter_ranking_asset_ids(
            asset_ids,
            factor="share_price_momentum",
            missing_only=missing_only,
            stale_only=stale_only,
        ):
            total += len(
                service.enqueue_backfill_one(
                    asset_id=asset_id,
                    years=years,
                    include_dividends=True,
                    include_splits=True,
                )
            )
        return total

    def _schedule_ranking_sentiment_jobs(
        self,
        *,
        asset_ids: list[str],
        source: str,
        missing_only: bool,
        stale_only: bool,
    ) -> int:
        from dashboard.ingestion_sentiment.constants import (
            DATASET_NEWS,
            DATASET_REDDIT,
            DATASET_SENTIMENT_DAILY,
            DATASET_X,
            JOB_TYPE_NEWS_RSS_REFRESH,
            JOB_TYPE_SENTIMENT_DAILY_AGGREGATE,
            JOB_TYPE_SENTIMENT_REDDIT_REFRESH,
            JOB_TYPE_SENTIMENT_X_REFRESH,
            PRIORITY_DAILY_AGGREGATE,
            PRIORITY_NEWS_REFRESH,
            PRIORITY_RETAIL_REFRESH,
        )
        from dashboard.ingestion_sentiment.repo import SentimentIngestionRepository

        repo = SentimentIngestionRepository(self.conn)
        total = 0
        snapshot_date = date.today()
        job_specs = (
            [(JOB_TYPE_NEWS_RSS_REFRESH, DATASET_NEWS, PRIORITY_NEWS_REFRESH)]
            if source == "news"
            else [
                (JOB_TYPE_SENTIMENT_REDDIT_REFRESH, DATASET_REDDIT, PRIORITY_RETAIL_REFRESH),
                (JOB_TYPE_SENTIMENT_X_REFRESH, DATASET_X, PRIORITY_RETAIL_REFRESH),
            ]
        )
        factor = "news_sentiment" if source == "news" else "retail_sentiment"
        for asset_id in self._filter_ranking_asset_ids(
            asset_ids,
            factor=factor,
            missing_only=missing_only,
            stale_only=stale_only,
        ):
            for job_type, dataset, priority in job_specs:
                if self._open_ranking_job_count(asset_id, "sentiment", dataset, job_type):
                    continue
                repo.create_job(
                    asset_id=asset_id,
                    job_type=job_type,
                    dataset=dataset,
                    priority=priority,
                    start_date=snapshot_date,
                    end_date=snapshot_date,
                )
                total += 1
            if not self._open_ranking_job_count(
                asset_id,
                "sentiment",
                DATASET_SENTIMENT_DAILY,
                JOB_TYPE_SENTIMENT_DAILY_AGGREGATE,
            ):
                repo.create_job(
                    asset_id=asset_id,
                    job_type=JOB_TYPE_SENTIMENT_DAILY_AGGREGATE,
                    dataset=DATASET_SENTIMENT_DAILY,
                    priority=PRIORITY_DAILY_AGGREGATE,
                    start_date=snapshot_date,
                    end_date=snapshot_date,
                )
                total += 1
        return total

    def _schedule_ranking_earnings_jobs(
        self,
        *,
        asset_ids: list[str],
        missing_only: bool,
        stale_only: bool,
    ) -> int:
        from dashboard.ingestion.fundamentals.subscription_service import (
            FundamentalSubscriptionService,
        )

        subscription = FundamentalSubscriptionService(self.conn)
        total = 0
        for asset_id in self._filter_ranking_asset_ids(
            asset_ids,
            factor="earnings_momentum",
            missing_only=missing_only,
            stale_only=stale_only,
        ):
            subscription.subscribe_asset(asset_id, subscription_source="ranking")
            total += self.schedule_due_fundamental_backfills(max_assets=1, asset_id=asset_id)
            total += self.schedule_due_fundamental_refreshes(max_assets=1, asset_id=asset_id)
        total += self.schedule_due_corporate_calendar_refresh()
        return total

    def _filter_ranking_asset_ids(
        self,
        asset_ids: list[str],
        *,
        factor: str,
        missing_only: bool,
        stale_only: bool,
    ) -> list[str]:
        if not missing_only and not stale_only:
            return asset_ids
        return [
            asset_id
            for asset_id in asset_ids
            if (
                (missing_only and self._ranking_factor_missing(asset_id, factor))
                or (stale_only and self._ranking_factor_stale(asset_id, factor))
            )
        ]

    def _ranking_factor_missing(self, asset_id: str, factor: str) -> bool:
        if factor == "share_price_momentum":
            row = self.conn.execute(
                """
                SELECT COUNT(*)
                FROM asset_quote_daily
                WHERE asset_id = ? AND COALESCE(adj_close, close) IS NOT NULL
                """,
                [asset_id],
            ).fetchone()
            return int(row[0]) < 22
        if factor == "news_sentiment":
            row = self.conn.execute(
                """
                SELECT COUNT(*)
                FROM ticker_sentiment_daily
                WHERE asset_id = ? AND news_sentiment_score IS NOT NULL AND article_count > 0
                """,
                [asset_id],
            ).fetchone()
            return int(row[0]) == 0
        if factor == "retail_sentiment":
            row = self.conn.execute(
                """
                SELECT COUNT(*)
                FROM ticker_sentiment_daily
                WHERE asset_id = ?
                  AND retail_sentiment_score IS NOT NULL
                  AND (reddit_post_count + x_post_count) > 0
                """,
                [asset_id],
            ).fetchone()
            return int(row[0]) == 0
        if factor == "earnings_momentum":
            statements = self.conn.execute(
                """
                SELECT COUNT(*)
                FROM financial_statement
                WHERE asset_id = ? AND statement_type = 'income'
                """,
                [asset_id],
            ).fetchone()
            events = self.conn.execute(
                """
                SELECT COUNT(*)
                FROM earnings_calendar_event
                WHERE asset_id = ?
                  AND (eps_actual IS NOT NULL OR revenue_actual IS NOT NULL)
                """,
                [asset_id],
            ).fetchone()
            return int(statements[0]) < 2 and int(events[0]) == 0
        if factor == "institutional_buying":
            row = self.conn.execute(
                """
                SELECT COUNT(*)
                FROM institutional_buying_daily
                WHERE asset_id = ?
                  AND net_flow_score IS NOT NULL
                  AND accumulation_score IS NOT NULL
                """,
                [asset_id],
            ).fetchone()
            return int(row[0]) == 0
        return True

    def _ranking_factor_stale(self, asset_id: str, factor: str) -> bool:
        if factor == "share_price_momentum":
            row = self.conn.execute(
                "SELECT MAX(date) FROM asset_quote_daily WHERE asset_id = ?",
                [asset_id],
            ).fetchone()
            return row[0] is None or row[0] < date.today() - timedelta(days=5)
        if factor in {"news_sentiment", "retail_sentiment"}:
            row = self.conn.execute(
                "SELECT MAX(date) FROM ticker_sentiment_daily WHERE asset_id = ?",
                [asset_id],
            ).fetchone()
            return row[0] is None or row[0] < date.today() - timedelta(days=2)
        if factor == "earnings_momentum":
            row = self.conn.execute(
                """
                SELECT MAX(COALESCE(period_end_date, report_date))
                FROM financial_statement
                WHERE asset_id = ? AND statement_type = 'income'
                """,
                [asset_id],
            ).fetchone()
            return row[0] is None or row[0] < date.today() - timedelta(days=150)
        if factor == "institutional_buying":
            row = self.conn.execute(
                "SELECT MAX(date) FROM institutional_buying_daily WHERE asset_id = ?",
                [asset_id],
            ).fetchone()
            return row[0] is None or row[0] < date.today() - timedelta(days=5)
        return True

    def _open_ranking_job_count(
        self,
        asset_id: str,
        domain: str,
        dataset: str,
        job_type: str,
    ) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM ingestion_job
            WHERE asset_id = ?
              AND domain = ?
              AND dataset = ?
              AND job_type = ?
              AND status IN ('pending', 'running')
            """,
            [asset_id, domain, dataset, job_type],
        ).fetchone()
        return int(row[0])

    ########################
    ##          trading calendar
    #######################

    def refresh_trading_calendar(
        self,
        market_code: str | None = None,
        year: int | None = None,
    ) -> int:

        if year is None:
            year = date.today().year

        start_date = date(year, 1, 1)
        end_date = date(year + 1, 12, 31)

        service = TradingCalendarIngestionService(self.conn)

        if market_code is None or market_code.lower() == "all":
            return service.refresh_all(start_date=start_date, end_date=end_date)

        return service.refresh_market(
            market_code=market_code,
            start_date=start_date,
            end_date=end_date,
        )

    def is_market_open_day(self, market_code: str, session_date: date) -> bool:
        from dashboard.ingestion.trading_calendar.service import TradingCalendarIngestionService

        service = TradingCalendarIngestionService(self.conn)
        return service.is_market_open_day(market_code, session_date)

    def should_skip_market_refresh(self, market_code: str, session_date: date) -> bool:
        return not self.is_market_open_day(market_code, session_date)

    #####################################
    ##      corporate calendar
    #####################################

    def schedule_due_corporate_calendar_refresh(self) -> int:
        service = CorporateCalendarIngestionService(self.conn)

        pending = self.conn.execute("""
            SELECT COUNT(*)
            FROM ingestion_job
            WHERE domain = 'corporate'
            AND dataset = 'earnings_calendar'
            AND job_type = 'calendar_refresh'
            AND status IN ('pending', 'running')
        """).fetchone()[0]

        if pending > 0:
            return 0

        latest_success = self.conn.execute("""
            SELECT MAX(last_successful_at)
            FROM asset_sync_state
            WHERE domain = 'corporate'
            AND dataset = 'earnings_calendar'
        """).fetchone()[0]

        if latest_success is not None:
            recently_refreshed = self.conn.execute(
                """
                SELECT ? > now() - INTERVAL 1 DAY
            """,
                [latest_success],
            ).fetchone()[0]

            if recently_refreshed:
                return 0

        return len(service.enqueue_calendar_refresh())

    def schedule_due_corporate_fundamental_updates(
        self,
        max_assets: int = 25,
    ) -> int:
        """
        Schedule earnings/fundamental updates for recent earnings events.
        """
        from dashboard.ingestion.corporate_calendar.service import (
            CorporateCalendarIngestionService,
        )

        service = CorporateCalendarIngestionService(self.conn)

        return len(
            service.schedule_fundamental_updates_after_events(
                lookback_days=14,
                max_assets=max_assets,
            )
        )

    def schedule_due_fundamental_backfills(
        self,
        max_assets: int = 25,
        asset_id: str | None = None,
    ) -> int:
        """
        Schedule historical financial-statement backfills for subscribed assets.
        """
        from dashboard.ingestion.corporate_calendar.service import (
            CorporateCalendarIngestionService,
        )

        service = CorporateCalendarIngestionService(self.conn)
        return len(
            service.schedule_due_fundamental_subscription_backfills(
                max_assets=max_assets,
                asset_id=asset_id,
            )
        )

    def schedule_due_fundamental_refreshes(
        self,
        max_assets: int = 25,
        asset_id: str | None = None,
    ) -> int:
        """
        Schedule recurring financial-statement refreshes for subscribed assets.
        """
        from dashboard.ingestion.corporate_calendar.service import (
            CorporateCalendarIngestionService,
        )

        service = CorporateCalendarIngestionService(self.conn)
        return len(
            service.schedule_due_fundamental_subscription_refreshes(
                max_assets=max_assets,
                asset_id=asset_id,
            )
        )

    def schedule_due_sentiment_snapshot_refreshes(self, max_assets: int = 25) -> int:
        """
        Schedule local sentiment aggregates, factor snapshots, and quant ratings.
        """
        from dashboard.ingestion_sentiment.constants import (
            DATASET_FACTOR_SNAPSHOT,
            DATASET_QUANT_RATING,
            DATASET_SENTIMENT_DAILY,
            JOB_TYPE_FACTOR_SNAPSHOT_REFRESH,
            JOB_TYPE_QUANT_RATING_REFRESH,
            JOB_TYPE_SENTIMENT_DAILY_AGGREGATE,
            PRIORITY_DAILY_AGGREGATE,
            PRIORITY_FACTOR_REFRESH,
            PRIORITY_QUANT_REFRESH,
        )
        from dashboard.ingestion_sentiment.repo import SentimentIngestionRepository

        asset_ids = TickerUniverseRepository(self.conn).ingestible_asset_ids()
        if not asset_ids:
            return 0

        repo = SentimentIngestionRepository(self.conn)
        snapshot_date = date.today()
        total = 0
        specs = [
            (
                JOB_TYPE_SENTIMENT_DAILY_AGGREGATE,
                DATASET_SENTIMENT_DAILY,
                PRIORITY_DAILY_AGGREGATE,
                "ticker_sentiment_daily",
                "date",
            ),
            (
                JOB_TYPE_FACTOR_SNAPSHOT_REFRESH,
                DATASET_FACTOR_SNAPSHOT,
                PRIORITY_FACTOR_REFRESH,
                "ticker_factor_snapshot",
                "snapshot_date",
            ),
            (
                JOB_TYPE_QUANT_RATING_REFRESH,
                DATASET_QUANT_RATING,
                PRIORITY_QUANT_REFRESH,
                "ticker_quant_rating_snapshot",
                "snapshot_date",
            ),
        ]

        for job_type, dataset, priority, table_name, date_column in specs:
            rows = self._due_sentiment_snapshot_assets(
                asset_ids=asset_ids,
                dataset=dataset,
                job_type=job_type,
                table_name=table_name,
                date_column=date_column,
                snapshot_date=snapshot_date,
                max_assets=max_assets,
            )
            for asset_id in rows:
                repo.create_job(
                    asset_id=asset_id,
                    job_type=job_type,
                    dataset=dataset,
                    priority=priority,
                    start_date=snapshot_date,
                    end_date=snapshot_date,
                )
                total += 1
        return total

    def _due_sentiment_snapshot_assets(
        self,
        asset_ids: list[str],
        dataset: str,
        job_type: str,
        table_name: str,
        date_column: str,
        snapshot_date: date,
        max_assets: int,
    ) -> list[str]:
        placeholders = ", ".join("?" for _ in asset_ids)
        rows = self.conn.execute(
            f"""
            SELECT a.asset_id
            FROM asset a
            WHERE a.asset_id IN ({placeholders})
              AND NOT EXISTS (
                  SELECT 1
                  FROM ingestion_job j
                  WHERE j.asset_id = a.asset_id
                    AND j.domain = 'sentiment'
                    AND j.dataset = ?
                    AND j.job_type = ?
                    AND j.status IN ('pending', 'running')
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM {table_name} s
                  WHERE s.asset_id = a.asset_id
                    AND s.{date_column} = ?
              )
            ORDER BY a.asset_id
            LIMIT ?
            """,
            [*asset_ids, dataset, job_type, snapshot_date, max_assets],
        ).fetchall()
        return [row[0] for row in rows]

    def run_corporate_ingestion_jobs(self, max_jobs: int = 1) -> int:
        """
        Process queued corporate ingestion jobs.
        """
        from dashboard.ingestion.corporate_calendar.service import (
            CorporateCalendarIngestionService,
        )

        service = CorporateCalendarIngestionService(self.conn)
        return service.process_jobs(max_jobs=max_jobs)

    #########################################
    ##      indices
    #########################################

    def seed_core_indices(self):
        service = create_index_ingestion_service(self.conn)
        return service.seed_core_universe()

    def refresh_core_index_daily_prices(self, lookback_days: int = 10):
        scheduler = create_index_scheduler(self.conn)
        return scheduler.run_core_daily_refresh(lookback_days=lookback_days)

    def refresh_core_index_intraday_prices(self, interval: str = "5min"):
        scheduler = create_index_scheduler(self.conn)
        return scheduler.run_core_intraday_refresh(interval=interval)

    def refresh_core_index_composition(self):
        scheduler = create_index_scheduler(self.conn)
        return scheduler.run_core_composition_refresh()

    def refresh_core_index_relative_metrics(self):
        scheduler = create_index_scheduler(self.conn)
        return scheduler.run_relative_metrics_against_sp500()

    from dashboard.ingestion.indices.index_service_factory import (
        create_index_ingestion_service,
        create_index_scheduler,
    )
