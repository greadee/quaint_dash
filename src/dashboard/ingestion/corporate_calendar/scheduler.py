"""
scheduler for Domain B corporate calendar ingestion

This module decides WHEN jobs should be created.
The worker decides HOW a queued job is processed.

Current scheduling rules:
    1. Refresh the earnings calendar at most once per day.
    2. After an earnings event date passes, enqueue earnings/fundamental jobs.
    3. Keep checking recent events for a short window because financial statements
       can lag the earnings calendar event.
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

    This keeps repeated CLI/app-start calls safe. Calling these scheduler methods
    many times should not flood ingestion_job with duplicate pending work.
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

        Suggested cadence:
            daily

        Date window:
            today - 7 days through today + 90 days

        The 7-day lookback catches revised actual EPS/revenue values.
        The 90-day lookahead covers roughly one earnings season.
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
        Enqueue earnings/fundamental update jobs for assets with recent earnings events.

        Suggested cadence:
            daily, after the calendar refresh job has run

        Why this re-checks the last 14 days:
            EPS actuals may appear quickly, but full statements can lag.
            Rechecking recent event windows is a simple way to avoid missing late data.

        Duplicate protection:
            This avoids creating more jobs for the same asset/dataset on the same day
            if that job is already pending/running/done today.
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

    def _latest_successful_at(self, dataset: str) -> datetime | None:
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