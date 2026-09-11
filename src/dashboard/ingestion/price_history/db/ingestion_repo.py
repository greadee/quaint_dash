"""
repository helpers and SQL queries for Domain A market ingestion
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from dashboard.ingestion.price_history.constants import (
    BACKFILL_DONE,
    BACKFILL_FAILED,
    BACKFILL_RUNNING,
    DATASET_DIVIDENDS,
    DATASET_PRICE_DAILY,
    DATASET_SPLITS,
    DOMAIN_MARKET,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
)
from dashboard.ingestion.price_history.models import DividendEventRow, IngestionJob, PriceDailyRow, SplitEventRow
from dashboard.ingestion.job_policy import (
    INGESTION_JOB_LEASE_SECONDS,
    MAX_INGESTION_JOB_ATTEMPTS,
    ingestion_worker_id,
)
from dashboard.ingestion.ticker_universe import TickerUniverseRepository
import dashboard.ingestion.price_history.db.queries as qry

class PriceHistoryIngestionRepository:
    """
    repository for Domain A ingestion tables
    """

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
                DOMAIN_MARKET,
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
        self.conn.execute(
            qry.ENSURE_SYNC_STATE,
            [asset_id, DOMAIN_MARKET, dataset],
        )

    def claim_next_pending_job(self) -> Optional[IngestionJob]:
        # Work excluded by the claim query must leave the visible pending queue.
        self.conn.execute("""
            UPDATE ingestion_job AS candidate
            SET status = 'superseded',
                terminal_reason = 'newer successful market ingestion covers this job',
                completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE candidate.domain = 'market' AND candidate.status = 'pending'
              AND (
                EXISTS (
                    SELECT 1 FROM ingestion_job newer
                    WHERE newer.asset_id = candidate.asset_id
                      AND newer.domain = candidate.domain
                      AND newer.dataset = candidate.dataset
                      AND newer.status = 'done' AND newer.job_id > candidate.job_id
                ) OR EXISTS (
                    SELECT 1 FROM asset_sync_state sync
                    WHERE sync.asset_id = candidate.asset_id
                      AND sync.domain = candidate.domain
                      AND sync.dataset = candidate.dataset
                      AND (sync.backfill_status = 'done'
                           OR sync.last_successful_at IS NOT NULL
                           OR sync.last_successful_date IS NOT NULL)
                      AND COALESCE(sync.last_successful_at, sync.last_attempted_at,
                          TIMESTAMP '1970-01-01') >= candidate.updated_at
                )
              )
        """)
        row = self.conn.execute(
            qry.CLAIM_NEXT_PENDING_JOB,
            [
                STATUS_RUNNING,
                ingestion_worker_id(),
                INGESTION_JOB_LEASE_SECONDS,
                DOMAIN_MARKET,
                STATUS_PENDING,
                MAX_INGESTION_JOB_ATTEMPTS,
                STATUS_PENDING,
            ],
        ).fetchone()

        if row is None:
            return None

        return IngestionJob(*row)

    def mark_job_done(
        self,
        job_id: int,
        asset_id: str,
        dataset: str,
        start_date: Optional[date],
        end_date: Optional[date],
        last_successful_date: Optional[date]) -> None:
        self.conn.execute(qry.MARK_JOB_DONE, [STATUS_DONE, job_id])
        self.conn.execute(
            qry.UPSERT_SYNC_STATE,
            [
                asset_id,
                DOMAIN_MARKET,
                dataset,
                BACKFILL_DONE,
                start_date,
                end_date,
                last_successful_date,
                None,
                False,
            ],
        )

    def mark_job_failed(self, job_id: int, asset_id: str, dataset: str, error: str) -> None:
        self.conn.execute(qry.MARK_JOB_FAILED, [STATUS_FAILED, error, job_id])

        existing = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM asset_sync_state
            WHERE asset_id = ? AND domain = ? AND dataset = ?
            """,
            [asset_id, DOMAIN_MARKET, dataset],
        ).fetchone()[0]

        if existing == 0:
            self.ensure_sync_state(asset_id, dataset)

        self.conn.execute(
            qry.UPDATE_SYNC_STATE_FAILED,
            [BACKFILL_FAILED, error, asset_id, DOMAIN_MARKET, dataset],
        )

    def mark_sync_running(
        self,
        asset_id: str,
        dataset: str,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> None:
        self.ensure_sync_state(asset_id, dataset)
        self.conn.execute(
            """
            UPDATE asset_sync_state
            SET
                backfill_status = ?,
                backfill_start_date = ?,
                backfill_end_date = ?,
                last_attempted_at = CURRENT_TIMESTAMP,
                last_error = NULL,
                needs_repair = FALSE
            WHERE asset_id = ?
              AND domain = ?
              AND dataset = ?
            """,
            [BACKFILL_RUNNING, start_date, end_date, asset_id, DOMAIN_MARKET, dataset],
        )

    def latest_price_date(self, asset_id: str) -> Optional[date]:
        row = self.conn.execute(qry.LATEST_PRICE_DATE, [asset_id]).fetchone()
        return row[0] if row and row[0] is not None else None

    def latest_dividend_date(self, asset_id: str) -> Optional[date]:
        row = self.conn.execute(qry.LATEST_DIVIDEND_DATE, [asset_id]).fetchone()
        return row[0] if row and row[0] is not None else None

    def latest_split_date(self, asset_id: str) -> Optional[date]:
        row = self.conn.execute(qry.LATEST_SPLIT_DATE, [asset_id]).fetchone()
        return row[0] if row and row[0] is not None else None

    def upsert_price_rows(self, rows: list[PriceDailyRow]) -> None:
        for row in rows:
            self.conn.execute(
                qry.UPSERT_PRICE_DAILY,
                [
                    row.asset_id,
                    row.price_date,
                    row.open_price,
                    row.high_price,
                    row.low_price,
                    row.close_price,
                    row.adj_close_price,
                    row.volume,
                    row.source,
                ],
            )

    def upsert_dividend_rows(self, rows: list[DividendEventRow]) -> None:
        for row in rows:
            self.conn.execute(
                qry.UPSERT_DIVIDEND_EVENT,
                [
                    row.asset_id,
                    row.ex_date,
                    row.payment_date,
                    row.record_date,
                    row.declaration_date,
                    row.dividend_per_share,
                    row.currency,
                    row.source,
                ],
            )

    def upsert_split_rows(self, rows: list[SplitEventRow]) -> None:
        for row in rows:
            self.conn.execute(
                qry.UPSERT_SPLIT_EVENT,
                [
                    row.asset_id,
                    row.ex_date,
                    row.split_from,
                    row.split_to,
                    row.source,
                ],
            )

    def get_all_asset_ids(self) -> list[str]:
        return self.ticker_universe.ingestible_asset_ids()

    def get_latest_dataset_date(self, asset_id: str, dataset: str) -> Optional[date]:
        if dataset == DATASET_PRICE_DAILY:
            stored_date = self.latest_price_date(asset_id)
        elif dataset == DATASET_DIVIDENDS:
            stored_date = self.latest_dividend_date(asset_id)
        elif dataset == DATASET_SPLITS:
            stored_date = self.latest_split_date(asset_id)
        else:
            raise ValueError(f"unsupported dataset: {dataset}")

        sync_row = self.conn.execute(
            """
            SELECT CASE
                WHEN last_successful_date IS NULL THEN backfill_end_date
                WHEN backfill_end_date IS NULL THEN last_successful_date
                ELSE GREATEST(last_successful_date, backfill_end_date)
            END
            FROM asset_sync_state
            WHERE asset_id = ?
              AND domain = ?
              AND dataset = ?
              AND backfill_status = ?
              AND needs_repair = FALSE
            """,
            [asset_id, DOMAIN_MARKET, dataset, BACKFILL_DONE],
        ).fetchone()
        covered_date = sync_row[0] if sync_row else None
        dates = [value for value in (stored_date, covered_date) if value is not None]
        return max(dates) if dates else None
