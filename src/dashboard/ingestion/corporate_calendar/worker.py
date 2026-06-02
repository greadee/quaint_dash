"""
worker for processing queued corporate calendar / fundamentals jobs
"""

from __future__ import annotations

from dashboard.ingestion.corporate_calendar.constants import (
    DATASET_EARNINGS_ACTUALS,
    DATASET_EARNINGS_CALENDAR,
    DATASET_FINANCIAL_STATEMENTS,
    JOB_TYPE_BACKFILL,
    JOB_TYPE_REFRESH,
)
from dashboard.ingestion.corporate_calendar.db.ingestion_repo import (
    CorporateCalendarIngestionRepository,
)
from dashboard.ingestion.corporate_calendar.provider_fmp import FmpCorporateCalendarProvider


class CorporateCalendarWorker:
    def __init__(self, conn, provider: FmpCorporateCalendarProvider) -> None:
        self.repo = CorporateCalendarIngestionRepository(conn)
        self.provider = provider

    def run_once(self) -> bool:
        job = self.repo.claim_next_pending_job()

        if job is None:
            return False

        try:
            self.repo.mark_sync_running(
                asset_id=job.asset_id,
                dataset=job.dataset,
                start_date=job.requested_start_date,
                end_date=job.requested_end_date,
            )

            if job.dataset == DATASET_EARNINGS_CALENDAR:
                if job.requested_start_date is None or job.requested_end_date is None:
                    raise ValueError("calendar job missing requested date range")

                rows = self.provider.fetch_earnings_calendar(
                    job.requested_start_date,
                    job.requested_end_date,
                )

                self.repo.upsert_earnings_calendar_rows(rows)
                last_date = max((r.earnings_date for r in rows), default=job.requested_end_date)

            elif job.dataset == DATASET_EARNINGS_ACTUALS:
                rows = self.provider.fetch_earnings_for_symbol(job.asset_id, limit=16)

                self.repo.upsert_earnings_calendar_rows(rows)
                last_date = max((r.earnings_date for r in rows), default=None)

            elif job.dataset == DATASET_FINANCIAL_STATEMENTS:
                rows = self.provider.fetch_quarterly_statements(job.asset_id, limit=16)

                self.repo.upsert_financial_statement_rows(rows)
                last_date = max((r.period_end_date for r in rows), default=None)

            else:
                raise ValueError(f"unsupported corporate dataset: {job.dataset}")

            self.repo.mark_job_done(
                job_id=job.job_id,
                asset_id=job.asset_id,
                dataset=job.dataset,
                start_date=job.requested_start_date,
                end_date=job.requested_end_date,
                last_successful_date=last_date,
            )

            if job.dataset == DATASET_FINANCIAL_STATEMENTS:
                if job.job_type == JOB_TYPE_REFRESH:
                    self.repo.mark_fundamental_subscription_refresh_succeeded(job.asset_id)
                elif job.job_type == JOB_TYPE_BACKFILL:
                    self.repo.mark_fundamental_subscription_backfill_succeeded(job.asset_id)

            return True

        except Exception as exc:
            self.repo.mark_job_failed(
                job_id=job.job_id,
                asset_id=job.asset_id,
                dataset=job.dataset,
                error=str(exc),
            )

            return False
