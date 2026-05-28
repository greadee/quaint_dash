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
    JOB_TYPE_CALENDAR_REFRESH,
    JOB_TYPE_EARNINGS_UPDATE,
    PRIORITY_EARNINGS_UPDATE,
)
from dashboard.ingestion.corporate_calendar.db.ingestion_repo import (
    CorporateCalendarIngestionRepository,
)
from dashboard.ingestion.corporate_calendar.jobs import (
    enqueue_calendar_refresh_jobs,
)


class CorporateCalendarScheduler:
    """
    Creates corporate ingestion jobs only when they are due.
    """

    def __init__(self, conn) -> None:
        self.conn = conn
        self.repo = CorporateCalendarIngestionRepository(conn)

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