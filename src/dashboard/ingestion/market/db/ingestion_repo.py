"""
repository helpers and SQL queries for Domain A market ingestion
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from dashboard.ingestion.market.constants import (
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
from dashboard.ingestion.market.models import DividendEventRow, IngestionJob, PriceDailyRow, SplitEventRow
import dashboard.ingestion.market.db.queries as qry

class MarketIngestionRepository:
    """
    repository for Domain A ingestion tables
    """

    def __init__(self, conn) -> None:
        self.conn = conn

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
        row = self.conn.execute(
            qry.SELECT_NEXT_PENDING_JOB,
            [DOMAIN_MARKET, STATUS_PENDING],
        ).fetchone()

        if row is None:
            return None

        job = IngestionJob(*row)
        self.conn.execute(qry.MARK_JOB_RUNNING, [STATUS_RUNNING, job.job_id])
        return job

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
        rows = self.conn.execute(qry.SELECT_ALL_ASSET_IDS).fetchall()
        return [r[0] for r in rows]

    def get_latest_dataset_date(self, asset_id: str, dataset: str) -> Optional[date]:
        if dataset == DATASET_PRICE_DAILY:
            return self.latest_price_date(asset_id)
        if dataset == DATASET_DIVIDENDS:
            return self.latest_dividend_date(asset_id)
        if dataset == DATASET_SPLITS:
            return self.latest_split_date(asset_id)
        raise ValueError(f"unsupported dataset: {dataset}")