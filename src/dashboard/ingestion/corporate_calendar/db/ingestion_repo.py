"""
repository helpers for Domain B corporate calendar ingestion
"""

from __future__ import annotations

from datetime import date, timedelta
import json
from typing import Optional

from dashboard.ingestion.corporate_calendar.constants import (
    BACKFILL_DONE,
    BACKFILL_FAILED,
    BACKFILL_RUNNING,
    DOMAIN_CORPORATE,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
)
from dashboard.ingestion.corporate_calendar.models import (
    CorporateCalendarEventRow,
    CorporateIngestionJob,
    FinancialStatementRow,
)
from dashboard.ingestion.job_policy import (
    INGESTION_JOB_LEASE_SECONDS,
    MAX_INGESTION_JOB_ATTEMPTS,
    ingestion_worker_id,
)
from dashboard.ingestion.ticker_universe import TickerUniverseRepository
import dashboard.ingestion.corporate_calendar.db.queries as qry


class CorporateCalendarIngestionRepository:
    def __init__(self, conn) -> None:
        self.conn = conn
        self.ticker_universe = TickerUniverseRepository(conn)

    def next_job_id(self) -> int:
        return int(self.conn.execute(qry.NEXT_JOB_ID).fetchone()[0])

    def create_job(
        self,
        asset_id: str,
        job_type: str,
        dataset: str,
        priority: int,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> int:
        job_id = self.next_job_id()

        self.conn.execute(
            qry.INSERT_JOB,
            [
                job_id,
                asset_id,
                DOMAIN_CORPORATE,
                job_type,
                dataset,
                STATUS_PENDING,
                priority,
                start_date,
                end_date,
            ],
        )

        self.ensure_sync_state(asset_id, dataset)
        return job_id

    def ensure_sync_state(self, asset_id: str, dataset: str) -> None:
        self.conn.execute(qry.ENSURE_SYNC_STATE, [asset_id, DOMAIN_CORPORATE, dataset])

    def get_tracked_stock_asset_ids(self) -> list[str]:
        return self.ticker_universe.ingestible_asset_ids(
            include_watchlist=True,
            asset_types=("stock", "adr"),
        )

    def claim_next_pending_job(self) -> Optional[CorporateIngestionJob]:
        row = self.conn.execute(
            qry.CLAIM_NEXT_PENDING_JOB,
            [
                STATUS_RUNNING,
                ingestion_worker_id(),
                INGESTION_JOB_LEASE_SECONDS,
                DOMAIN_CORPORATE,
                STATUS_PENDING,
                MAX_INGESTION_JOB_ATTEMPTS,
                STATUS_PENDING,
            ],
        ).fetchone()

        if row is None:
            return None

        return CorporateIngestionJob(*row)

    def mark_sync_running(
        self,
        asset_id: str,
        dataset: str,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> None:
        self.ensure_sync_state(asset_id, dataset)

        self.conn.execute(
            qry.MARK_SYNC_RUNNING,
            [
                BACKFILL_RUNNING,
                start_date,
                end_date,
                asset_id,
                DOMAIN_CORPORATE,
                dataset,
            ],
        )

    def mark_job_done(
        self,
        job_id: int,
        asset_id: str,
        dataset: str,
        start_date: Optional[date],
        end_date: Optional[date],
        last_successful_date: Optional[date],
    ) -> None:
        self.conn.execute(qry.MARK_JOB_DONE, [STATUS_DONE, job_id])

        self.conn.execute(
            qry.UPSERT_SYNC_STATE,
            [
                asset_id,
                DOMAIN_CORPORATE,
                dataset,
                BACKFILL_DONE,
                start_date,
                end_date,
                last_successful_date,
                None,
                False,
            ],
        )

    def mark_job_failed(
        self,
        job_id: int,
        asset_id: str,
        dataset: str,
        error: str,
    ) -> None:
        self.conn.execute(qry.MARK_JOB_FAILED, [STATUS_FAILED, error, job_id])
        self.ensure_sync_state(asset_id, dataset)

        self.conn.execute(
            qry.UPDATE_SYNC_STATE_FAILED,
            [BACKFILL_FAILED, error, asset_id, DOMAIN_CORPORATE, dataset],
        )

    def upsert_earnings_calendar_rows(
        self,
        rows: list[CorporateCalendarEventRow],
    ) -> None:
        tracked = set(self.get_tracked_stock_asset_ids())

        for row in rows:
            if row.asset_id not in tracked:
                continue

            self.conn.execute(
                qry.UPSERT_EARNINGS_CALENDAR_EVENT,
                [
                    row.asset_id,
                    row.earnings_date,
                    row.fiscal_year,
                    row.fiscal_quarter,
                    row.time,
                    row.eps_estimated,
                    row.eps_actual,
                    row.revenue_estimated,
                    row.revenue_actual,
                    row.source,
                ],
            )

    def upsert_financial_statement_rows(
        self,
        rows: list[FinancialStatementRow],
    ) -> None:
        for row in rows:
            self.conn.execute(
                qry.UPSERT_FINANCIAL_STATEMENT,
                [
                    row.asset_id,
                    row.statement_type,
                    row.fiscal_year,
                    row.fiscal_quarter,
                    row.period_end_date,
                    row.report_date,
                    json.dumps(row.data_json),
                    row.source,
                ],
            )

    def mark_fundamental_subscription_refresh_succeeded(self, asset_id: str) -> None:
        if not self._table_exists("fundamental_subscription"):
            return

        self.conn.execute(
            """
            UPDATE fundamental_subscription
            SET
                last_refresh_succeeded_at = now(),
                updated_at = now()
            WHERE asset_id = ?
            """,
            [asset_id],
        )

    def mark_fundamental_subscription_backfill_requested(self, asset_id: str) -> None:
        if not self._table_exists("fundamental_subscription"):
            return

        self.conn.execute(
            """
            UPDATE fundamental_subscription
            SET
                last_backfill_requested_at = now(),
                updated_at = now()
            WHERE asset_id = ?
            """,
            [asset_id],
        )

    def mark_fundamental_subscription_backfill_succeeded(self, asset_id: str) -> None:
        if not self._table_exists("fundamental_subscription"):
            return

        self.conn.execute(
            """
            UPDATE fundamental_subscription
            SET
                last_backfill_succeeded_at = now(),
                updated_at = now()
            WHERE asset_id = ?
            """,
            [asset_id],
        )

    def deactivate_fundamental_subscription(self, asset_id: str, reason: str) -> None:
        if not self._table_exists("fundamental_subscription"):
            return

        self.conn.execute(
            """
            UPDATE fundamental_subscription
            SET
                is_active = FALSE,
                next_refresh_at = TIMESTAMP '9999-12-31 00:00:00',
                updated_at = now()
            WHERE asset_id = ?
            """,
            [asset_id],
        )

        self.ensure_sync_state(asset_id, "financial_statements")
        self.conn.execute(
            qry.UPDATE_SYNC_STATE_FAILED,
            [BACKFILL_FAILED, reason, asset_id, DOMAIN_CORPORATE, "financial_statements"],
        )

    def select_due_earnings_update_asset_ids(
        self,
        today: date,
        lookback_days: int,
        limit: int,
    ) -> list[str]:
        start_date = today - timedelta(days=lookback_days)

        rows = self.conn.execute(
            qry.SELECT_DUE_EARNINGS_EVENTS,
            [today, start_date, limit],
        ).fetchall()

        return [r[0] for r in rows]
    
    def select_assets_with_recent_earnings_events(
        self,
        start_date: date,
        end_date: date,
        limit: int,
    ) -> list[str]:
        """
        Return tracked stock/ADR asset ids that had earnings events in the date window.

        This is used by the scheduler to create post-event earnings/fundamental
        update jobs.
        """
        rows = self.conn.execute(
            qry.SELECT_ASSETS_WITH_RECENT_EARNINGS_EVENTS,
            [start_date, end_date, limit],
        ).fetchall()

        eligible = set(
            self.ticker_universe.ingestible_asset_ids(
                include_watchlist=True,
                asset_types=("stock", "adr"),
            )
        )
        return [r[0] for r in rows if r[0] in eligible]

    def _table_exists(self, table_name: str) -> bool:
        row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_name = ?
            """,
            [table_name],
        ).fetchone()
        return bool(row and row[0])
