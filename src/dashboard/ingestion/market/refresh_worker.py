"""
worker for processing queued market refresh jobs
"""

from __future__ import annotations

from dashboard.ingestion.market.backfill_worker import MarketBackfillWorker


class MarketRefreshWorker(MarketBackfillWorker):
    """
    refresh worker currently uses the same execution flow as backfill
    because refresh jobs are just incremental date-ranged jobs
    """
    pass