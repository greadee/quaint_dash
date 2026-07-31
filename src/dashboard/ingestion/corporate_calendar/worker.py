"""
worker for processing queued corporate calendar / fundamentals jobs
"""

from __future__ import annotations

from datetime import date

from dashboard.ingestion.corporate_calendar.models import CorporateCalendarEventRow
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
from dashboard.ingestion.corporate_calendar.provider_fmp import FmpEntitlementError
from dashboard.ingestion.job_policy import is_permanent_ingestion_failure


class CorporateCalendarWorker:
    def __init__(
        self,
        conn,
        provider: FmpCorporateCalendarProvider,
        backup_earnings_provider=None,
    ) -> None:
        self.repo = CorporateCalendarIngestionRepository(conn)
        self.provider = provider
        self.backup_earnings_provider = backup_earnings_provider

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
                rows = self._fetch_earnings_with_backup(job.asset_id)

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

        except FmpEntitlementError as exc:
            error = str(exc)
            self.repo.mark_job_failed(
                job_id=job.job_id,
                asset_id=job.asset_id,
                dataset=job.dataset,
                error=error,
            )
            if job.dataset == DATASET_FINANCIAL_STATEMENTS:
                self.repo.deactivate_fundamental_subscription(job.asset_id, error)
            return True

        except Exception as exc:
            self.repo.mark_job_failed(
                job_id=job.job_id,
                asset_id=job.asset_id,
                dataset=job.dataset,
                error=str(exc),
            )

            return False

    def _fetch_earnings_with_backup(
        self,
        asset_id: str,
    ) -> list[CorporateCalendarEventRow]:
        primary_rows: list[CorporateCalendarEventRow] = []
        primary_error: Exception | None = None
        try:
            primary_rows = self.provider.fetch_earnings_for_symbol(asset_id, limit=16)
        except Exception as exc:
            primary_error = exc

        if _has_complete_earnings_surprise(primary_rows):
            return primary_rows

        backup_rows: list[CorporateCalendarEventRow] = []
        backup_error: Exception | None = None
        if self.backup_earnings_provider is not None:
            try:
                backup_rows = self.backup_earnings_provider.fetch_earnings_for_symbol(
                    asset_id,
                    limit=16,
                )
            except Exception as exc:
                backup_error = exc

        merged = _merge_earnings_rows(primary_rows, backup_rows)
        if merged:
            return merged
        if primary_error is not None and backup_error is not None:
            if is_permanent_ingestion_failure(str(primary_error)):
                raise RuntimeError(
                    f"backup earnings provider failed: {backup_error}; "
                    "primary earnings provider unavailable by entitlement"
                ) from backup_error
            raise RuntimeError(
                f"primary earnings provider failed: {primary_error}; "
                f"backup earnings provider failed: {backup_error}"
            ) from backup_error
        if primary_error is not None and self.backup_earnings_provider is None:
            raise primary_error
        if backup_error is not None and not primary_rows:
            raise backup_error
        return []


def _has_complete_earnings_surprise(
    rows: list[CorporateCalendarEventRow],
) -> bool:
    completed_events = [
        row
        for row in rows
        if row.earnings_date <= date.today()
    ]
    if not completed_events:
        return False
    latest = max(completed_events, key=lambda row: row.earnings_date)
    return (
        latest.eps_estimated is not None
        and latest.eps_actual is not None
    ) or (
        latest.revenue_estimated is not None
        and latest.revenue_actual is not None
    )


def _merge_earnings_rows(
    primary_rows: list[CorporateCalendarEventRow],
    backup_rows: list[CorporateCalendarEventRow],
) -> list[CorporateCalendarEventRow]:
    merged = {
        (row.asset_id, row.earnings_date): row
        for row in primary_rows
    }
    for backup in backup_rows:
        key = (backup.asset_id, backup.earnings_date)
        primary = merged.get(key)
        if primary is None:
            merged[key] = backup
            continue
        contributed = any(
            primary_value is None and backup_value is not None
            for primary_value, backup_value in (
                (primary.eps_estimated, backup.eps_estimated),
                (primary.eps_actual, backup.eps_actual),
                (primary.revenue_estimated, backup.revenue_estimated),
                (primary.revenue_actual, backup.revenue_actual),
            )
        )
        merged[key] = CorporateCalendarEventRow(
            asset_id=primary.asset_id,
            earnings_date=primary.earnings_date,
            fiscal_year=primary.fiscal_year or backup.fiscal_year,
            fiscal_quarter=primary.fiscal_quarter or backup.fiscal_quarter,
            time=primary.time or backup.time,
            eps_estimated=(
                primary.eps_estimated
                if primary.eps_estimated is not None
                else backup.eps_estimated
            ),
            eps_actual=(
                primary.eps_actual
                if primary.eps_actual is not None
                else backup.eps_actual
            ),
            revenue_estimated=(
                primary.revenue_estimated
                if primary.revenue_estimated is not None
                else backup.revenue_estimated
            ),
            revenue_actual=(
                primary.revenue_actual
                if primary.revenue_actual is not None
                else backup.revenue_actual
            ),
            source=(
                f"{primary.source}+{backup.source}"
                if contributed and primary.source != backup.source
                else primary.source
            ),
        )
    return sorted(
        merged.values(),
        key=lambda row: (row.earnings_date, row.asset_id),
        reverse=True,
    )
