"""
worker for processing queued market backfill jobs
"""

from __future__ import annotations

from dashboard.ingestion.price.constants import DATASET_DIVIDENDS, DATASET_PRICE_DAILY, DATASET_SPLITS
from dashboard.ingestion.market.provider_fmp import FMPMarketProvider
from dashboard.ingestion.market.db.ingestion_repo import MarketIngestionRepository


class MarketBackfillWorker:
    """
    processes queued Domain A backfill jobs one at a time
    """

    def __init__(self, conn, provider: FMPMarketProvider) -> None:
        self.repo = MarketIngestionRepository(conn)
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

            if job.requested_start_date is None or job.requested_end_date is None:
                raise ValueError("backfill job missing requested date range")

            if job.dataset == DATASET_PRICE_DAILY:
                rows = self.provider.fetch_price_daily(
                    asset_id=job.asset_id,
                    start_date=job.requested_start_date,
                    end_date=job.requested_end_date,
                )
                self.repo.upsert_price_rows(rows)
                last_date = max((r.price_date for r in rows), default=None)

            elif job.dataset == DATASET_DIVIDENDS:
                rows = self.provider.fetch_dividends(
                    asset_id=job.asset_id,
                    start_date=job.requested_start_date,
                    end_date=job.requested_end_date,
                )
                self.repo.upsert_dividend_rows(rows)
                last_date = max((r.ex_date for r in rows), default=None)

            elif job.dataset == DATASET_SPLITS:
                rows = self.provider.fetch_splits(
                    asset_id=job.asset_id,
                    start_date=job.requested_start_date,
                    end_date=job.requested_end_date,
                )
                self.repo.upsert_split_rows(rows)
                last_date = max((r.ex_date for r in rows), default=None)

            else:
                raise ValueError(f"unsupported dataset: {job.dataset}")

            self.repo.mark_job_done(
                job_id=job.job_id,
                asset_id=job.asset_id,
                dataset=job.dataset,
                start_date=job.requested_start_date,
                end_date=job.requested_end_date,
                last_successful_date=last_date,
            )
            return True

        except Exception as exc:
            self.repo.mark_job_failed(
                job_id=job.job_id,
                asset_id=job.asset_id,
                dataset=job.dataset,
                error=str(exc),
            )
            return False