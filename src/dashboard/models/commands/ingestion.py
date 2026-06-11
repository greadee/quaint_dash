"""Market, sentiment, calendar, and benchmark ingestion commands."""

from datetime import date

from dashboard.ingestion.corporate_calendar.service import CorporateCalendarIngestionService
from dashboard.ingestion.indices.index_service_factory import (
    create_index_ingestion_service,
    create_index_scheduler,
)
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

        return SentimentIngestionService(self.conn).refresh_ticker(target, source=source)

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
            ),
            (
                JOB_TYPE_FACTOR_SNAPSHOT_REFRESH,
                DATASET_FACTOR_SNAPSHOT,
                PRIORITY_FACTOR_REFRESH,
                "ticker_factor_snapshot",
            ),
            (
                JOB_TYPE_QUANT_RATING_REFRESH,
                DATASET_QUANT_RATING,
                PRIORITY_QUANT_REFRESH,
                "ticker_quant_rating_snapshot",
            ),
        ]

        for job_type, dataset, priority, table_name in specs:
            rows = self._due_sentiment_snapshot_assets(
                asset_ids=asset_ids,
                dataset=dataset,
                job_type=job_type,
                table_name=table_name,
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
                    AND s.snapshot_date = ?
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
