"""
service layer for Domain B corporate calendar enqueueing and worker execution
"""

from __future__ import annotations

from datetime import date, timedelta

from dashboard.ingestion.corporate_calendar.db.ingestion_repo import (
    CorporateCalendarIngestionRepository,
)
from dashboard.ingestion.corporate_calendar.jobs import (
    enqueue_calendar_refresh_jobs,
    enqueue_corporate_backfill_jobs,
    enqueue_earnings_update_jobs,
)
from dashboard.ingestion.corporate_calendar.provider_fmp import FmpCorporateCalendarProvider
from dashboard.ingestion.corporate_calendar.worker import CorporateCalendarWorker


class CorporateCalendarIngestionService:
    """
    Higher-level entry point for CLI / scheduler code.
    """

    def __init__(self, conn, provider: FmpCorporateCalendarProvider | None = None) -> None:
        self.conn = conn
        self.repo = CorporateCalendarIngestionRepository(conn)
        self.provider = provider or FmpCorporateCalendarProvider()

    def enqueue_calendar_refresh(
        self,
        lookback_days: int = 7,
        lookahead_days: int = 90,
    ) -> list[int]:
        today = date.today()

        return enqueue_calendar_refresh_jobs(
            repo=self.repo,
            start_date=today - timedelta(days=lookback_days),
            end_date=today + timedelta(days=lookahead_days),
        )

    def enqueue_due_earnings_updates(
        self,
        lookback_days: int = 14,
        max_assets: int = 25,
    ) -> list[int]:
        return enqueue_earnings_update_jobs(
            repo=self.repo,
            today=date.today(),
            lookback_days=lookback_days,
            max_assets=max_assets,
        )

    def enqueue_backfill(self, years: int = 10) -> list[int]:
        today = date.today()

        return enqueue_corporate_backfill_jobs(
            repo=self.repo,
            start_date=today - timedelta(days=365 * years),
            end_date=today,
        )

    def process_jobs(self, max_jobs: int = 1) -> int:
        worker = CorporateCalendarWorker(self.conn, self.provider)

        completed = 0

        for _ in range(max_jobs):
            if not worker.run_once():
                break

            completed += 1

        return completed
    
    def schedule_calendar_refresh_if_due(
        self,
        lookback_days: int = 7,
        lookahead_days: int = 90,
        refresh_interval_hours: int = 24,
    ) -> list[int]:
        """
        Scheduler entry point for refreshing the earnings calendar.

        This is safe to call daily or on app startup.
        """
        scheduler = CorporateCalendarScheduler(self.conn)

        return scheduler.schedule_calendar_refresh_if_due(
            lookback_days=lookback_days,
            lookahead_days=lookahead_days,
            refresh_interval_hours=refresh_interval_hours,
        )

    def schedule_fundamental_updates_after_events(
        self,
        lookback_days: int = 14,
        max_assets: int = 25,
    ) -> list[int]:
        """
        Scheduler entry point for post-earnings fundamental ingestion.

        This should run after the earnings calendar refresh.
        """
        scheduler = CorporateCalendarScheduler(self.conn)

        return scheduler.schedule_fundamental_updates_after_events(
            lookback_days=lookback_days,
            max_assets=max_assets,
        )