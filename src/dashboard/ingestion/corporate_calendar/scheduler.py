"""
scheduler for Domain B corporate calendar ingestion
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from dashboard.ingestion.corporate_calendar.constants import (
    DATASET_EARNINGS_ACTUALS,
    DATASET_EARNINGS_CALENDAR,
    DATASET_FINANCIAL_STATEMENTS,
    DOMAIN_CORPORATE,
    JOB_TYPE_BACKFILL,
    JOB_TYPE_CALENDAR_REFRESH,
    JOB_TYPE_EARNINGS_UPDATE,
    JOB_TYPE_REFRESH,
    PRIORITY_CORPORATE_BACKFILL,
    PRIORITY_EARNINGS_UPDATE,
)
from dashboard.ingestion.corporate_calendar.db.ingestion_repo import (
    CorporateCalendarIngestionRepository,
)
from dashboard.ingestion.corporate_calendar.jobs import (
    enqueue_calendar_refresh_jobs,
)
from dashboard.ingestion.fundamentals.schema import ensure_fundamental_phase1_schema
from dashboard.ingestion.ticker_universe import TickerUniverseRepository

DEFAULT_FUNDAMENTAL_REFRESH_INTERVAL_DAYS = 7


class CorporateCalendarScheduler:
    """
    Creates corporate ingestion jobs only when they are due.

    This scheduler now supports three corporate scheduling paths:

    1. Earnings calendar refresh
    2. Post-earnings actuals / financial statement updates
    3. Subscription-based recurring financial statement refreshes

    The scheduler only creates ingestion_job rows.
    The existing CorporateCalendarWorker remains the only execution path for
    financial statement ingestion.
    """

    def __init__(self, conn) -> None:
        self.conn = conn
        self.repo = CorporateCalendarIngestionRepository(conn)
        self.ticker_universe = TickerUniverseRepository(conn)

    def schedule_calendar_refresh_if_due(
        self,
        lookback_days: int = 7,
        lookahead_days: int = 90,
        refresh_interval_hours: int = 24,
    ) -> list[int]:
        """
        Enqueue calendar refresh jobs if the calendar has not been refreshed recently.
        """
        pending_count = self._count_open_jobs(
            dataset=DATASET_EARNINGS_CALENDAR,
            job_type=JOB_TYPE_CALENDAR_REFRESH,
        )

        if pending_count > 0:
            return []

        latest_success = self._latest_successful_at(DATASET_EARNINGS_CALENDAR)

        if latest_success is not None:
            cutoff = datetime.now() - timedelta(hours=refresh_interval_hours)

            if latest_success >= cutoff:
                return []

        today = date.today()

        return enqueue_calendar_refresh_jobs(
            repo=self.repo,
            start_date=today - timedelta(days=lookback_days),
            end_date=today + timedelta(days=lookahead_days),
        )

    def schedule_fundamental_updates_after_events(
        self,
        lookback_days: int = 14,
        max_assets: int = 25,
    ) -> list[int]:
        """
        Enqueue earnings/fundamental update jobs for recent earnings events.

        This handles the post-earnings path:
        - update earnings actuals
        - update latest financial statements

        This should stay separate from subscription-based recurring refreshes.
        """
        today = date.today()
        start_date = today - timedelta(days=lookback_days)

        asset_ids = self.repo.select_assets_with_recent_earnings_events(
            start_date=start_date,
            end_date=today,
            limit=max_assets,
        )

        job_ids: list[int] = []

        for asset_id in asset_ids:
            if not self._has_open_or_today_job(
                asset_id=asset_id,
                dataset=DATASET_EARNINGS_ACTUALS,
                job_type=JOB_TYPE_EARNINGS_UPDATE,
                today=today,
            ):
                job_ids.append(
                    self.repo.create_job(
                        asset_id=asset_id,
                        job_type=JOB_TYPE_EARNINGS_UPDATE,
                        dataset=DATASET_EARNINGS_ACTUALS,
                        priority=PRIORITY_EARNINGS_UPDATE,
                        start_date=start_date,
                        end_date=today,
                    )
                )

            if not self._has_open_or_today_job(
                asset_id=asset_id,
                dataset=DATASET_FINANCIAL_STATEMENTS,
                job_type=JOB_TYPE_EARNINGS_UPDATE,
                today=today,
            ):
                job_ids.append(
                    self.repo.create_job(
                        asset_id=asset_id,
                        job_type=JOB_TYPE_EARNINGS_UPDATE,
                        dataset=DATASET_FINANCIAL_STATEMENTS,
                        priority=PRIORITY_EARNINGS_UPDATE - 1,
                        start_date=start_date,
                        end_date=today,
                    )
                )

        return job_ids

    def schedule_due_fundamental_subscription_refreshes(
        self,
        max_assets: int = 25,
        asset_id: str | None = None,
    ) -> list[int]:
        """
        Enqueue recurring financial statement refresh jobs for subscribed assets.

        This is Phase 1 subscription monitoring.

        It does not fetch or store statements directly. It only creates normal
        corporate ingestion jobs:

            domain = corporate
            job_type = refresh
            dataset = financial_statements

        The existing CorporateCalendarWorker will process those jobs using the
        existing financial statement ingestion path.
        """
        ensure_fundamental_phase1_schema(self.conn)
        self._ensure_active_universe_subscriptions()
        self._deactivate_entitlement_blocked_subscriptions()

        now = datetime.now()
        today = date.today()

        asset_ids = self.ticker_universe.ingestible_asset_ids(
            include_watchlist=True,
            asset_types=("stock", "adr"),
        )
        if asset_id is not None:
            normalized = asset_id.upper().strip()
            asset_ids = [normalized] if normalized in set(asset_ids) else []
        if not asset_ids:
            return []

        placeholders = ", ".join("?" for _ in asset_ids)
        rows = self.conn.execute(
            f"""
            SELECT
                asset_id,
                refresh_interval_days
            FROM fundamental_subscription
            WHERE asset_id IN ({placeholders})
              AND is_active = TRUE
              AND (
                    next_refresh_at IS NULL
                    OR next_refresh_at <= ?
              )
            ORDER BY COALESCE(next_refresh_at, TIMESTAMP '1970-01-01') ASC,
                     asset_id ASC
            LIMIT ?
            """,
            [*asset_ids, now, max_assets],
        ).fetchall()

        job_ids: list[int] = []

        for asset_id, refresh_interval_days in rows:
            if self._has_open_or_today_job(
                asset_id=asset_id,
                dataset=DATASET_FINANCIAL_STATEMENTS,
                job_type=JOB_TYPE_REFRESH,
                today=today,
            ):
                continue

            job_id = self.repo.create_job(
                asset_id=asset_id,
                job_type=JOB_TYPE_REFRESH,
                dataset=DATASET_FINANCIAL_STATEMENTS,
                priority=PRIORITY_EARNINGS_UPDATE - 1,
                start_date=None,
                end_date=None,
            )

            job_ids.append(job_id)

            self._mark_subscription_refresh_scheduled(
                asset_id=asset_id,
                refresh_interval_days=refresh_interval_days,
            )

        return job_ids

    def schedule_due_fundamental_subscription_backfills(
        self,
        max_assets: int = 25,
        asset_id: str | None = None,
    ) -> list[int]:
        """
        Enqueue one historical financial-statement backfill for subscribed assets.

        Backfill is distinct from recurring refresh:
        - backfill fills the historical quarterly statement store once
        - refresh keeps already-subscribed assets current over time
        """
        ensure_fundamental_phase1_schema(self.conn)
        self._ensure_active_universe_subscriptions()
        self._deactivate_entitlement_blocked_subscriptions()

        asset_ids = self.ticker_universe.ingestible_asset_ids(
            include_watchlist=True,
            asset_types=("stock", "adr"),
        )
        if asset_id is not None:
            normalized = asset_id.upper().strip()
            asset_ids = [normalized] if normalized in set(asset_ids) else []
        if not asset_ids:
            return []

        placeholders = ", ".join("?" for _ in asset_ids)
        rows = self.conn.execute(
            f"""
            SELECT asset_id
            FROM fundamental_subscription
            WHERE asset_id IN ({placeholders})
              AND is_active = TRUE
              AND last_backfill_succeeded_at IS NULL
            ORDER BY COALESCE(last_backfill_requested_at, TIMESTAMP '1970-01-01') ASC,
                     asset_id ASC
            LIMIT ?
            """,
            [*asset_ids, max_assets],
        ).fetchall()

        job_ids: list[int] = []

        for (asset_id,) in rows:
            if self._has_open_job(
                asset_id=asset_id,
                dataset=DATASET_FINANCIAL_STATEMENTS,
                job_type=JOB_TYPE_BACKFILL,
            ):
                continue

            job_id = self.repo.create_job(
                asset_id=asset_id,
                job_type=JOB_TYPE_BACKFILL,
                dataset=DATASET_FINANCIAL_STATEMENTS,
                priority=PRIORITY_CORPORATE_BACKFILL,
                start_date=None,
                end_date=None,
            )
            job_ids.append(job_id)
            self.repo.mark_fundamental_subscription_backfill_requested(asset_id)

        return job_ids

    def _ensure_active_universe_subscriptions(self) -> int:
        """
        Keep fundamental ingestion subscribed to the current ticker universe.

        Portfolio and watchlist membership are the source of truth for which
        stock-like assets need valuation inputs. Subscriptions still remain the
        scheduling control table, but missing rows should not silently block
        statement backfills or recurring refreshes.
        """
        asset_ids = self.ticker_universe.ingestible_asset_ids(
            include_watchlist=True,
            asset_types=("stock", "adr"),
        )
        if not asset_ids:
            return 0

        now = datetime.now()
        rows = [
            (
                asset_id,
                True,
                DEFAULT_FUNDAMENTAL_REFRESH_INTERVAL_DAYS,
                now,
                "ticker_universe",
                now,
                now,
            )
            for asset_id in asset_ids
        ]
        self.conn.executemany(
            """
            INSERT INTO fundamental_subscription (
                asset_id,
                is_active,
                refresh_interval_days,
                next_refresh_at,
                subscription_source,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (asset_id)
            DO UPDATE SET
                next_refresh_at = COALESCE(fundamental_subscription.next_refresh_at, excluded.next_refresh_at),
                updated_at = excluded.updated_at
            WHERE fundamental_subscription.is_active = TRUE
            """,
            rows,
        )
        return len(rows)

    def _deactivate_entitlement_blocked_subscriptions(self) -> int:
        rows = self.conn.execute(
            """
            SELECT DISTINCT s.asset_id, s.last_error
            FROM asset_sync_state s
            JOIN fundamental_subscription f
              ON f.asset_id = s.asset_id
            WHERE s.domain = ?
              AND s.dataset = ?
              AND f.is_active = TRUE
              AND s.last_error ILIKE '%FMP HTTP error 402%'
            """,
            [DOMAIN_CORPORATE, DATASET_FINANCIAL_STATEMENTS],
        ).fetchall()
        for asset_id, last_error in rows:
            self.repo.deactivate_fundamental_subscription(
                asset_id,
                str(last_error)
                or "FMP HTTP error 402: plan does not include this corporate endpoint",
            )
        return len(rows)

    def _mark_subscription_refresh_scheduled(
        self,
        asset_id: str,
        refresh_interval_days: int | None,
    ) -> None:
        """
        Move next_refresh_at forward after enqueueing a refresh job.

        The worker still controls actual ingestion success/failure through
        ingestion_job and asset_sync_state.

        This prevents the scheduler from creating the same recurring refresh
        repeatedly after a completed job.
        """
        now = datetime.now()

        interval_days = (
            int(refresh_interval_days)
            if refresh_interval_days is not None
            else DEFAULT_FUNDAMENTAL_REFRESH_INTERVAL_DAYS
        )

        next_refresh_at = now + timedelta(days=interval_days)

        self.conn.execute(
            """
            UPDATE fundamental_subscription
            SET
                last_refresh_attempted_at = ?,
                next_refresh_at = ?,
                updated_at = ?
            WHERE asset_id = ?
            """,
            [now, next_refresh_at, now, asset_id],
        )

    def _count_open_jobs(self, dataset: str, job_type: str) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM ingestion_job
            WHERE domain = ?
              AND dataset = ?
              AND job_type = ?
              AND status IN ('pending', 'running')
            """,
            [DOMAIN_CORPORATE, dataset, job_type],
        ).fetchone()

        return int(row[0])

    def _latest_successful_at(self, dataset: str):
        row = self.conn.execute(
            """
            SELECT MAX(last_successful_at)
            FROM asset_sync_state
            WHERE domain = ?
              AND dataset = ?
            """,
            [DOMAIN_CORPORATE, dataset],
        ).fetchone()

        if row is None:
            return None

        return row[0]

    def _has_open_or_today_job(
        self,
        asset_id: str,
        dataset: str,
        job_type: str,
        today: date,
    ) -> bool:
        row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM ingestion_job
            WHERE asset_id = ?
              AND domain = ?
              AND dataset = ?
              AND job_type = ?
              AND (
                    status IN ('pending', 'running')
                    OR CAST(created_at AS DATE) = ?
              )
            """,
            [asset_id, DOMAIN_CORPORATE, dataset, job_type, today],
        ).fetchone()

        return int(row[0]) > 0

    def _has_open_job(
        self,
        asset_id: str,
        dataset: str,
        job_type: str,
    ) -> bool:
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
            [asset_id, DOMAIN_CORPORATE, dataset, job_type],
        ).fetchone()

        return int(row[0]) > 0
