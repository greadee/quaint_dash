from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from dashboard.ingestion.indices.index_ingestion_service import BenchmarkIndexIngestionService


@dataclass(frozen=True)
class IndexJobResult:
    job_type: str
    target_count: int
    row_count: int


class BenchmarkIndexScheduler:
    """
    Thin scheduler/worker wrapper.

    Keep this small. The heavy work stays inside BenchmarkIndexIngestionService.
    Later this can be wired to your generic ingestion_job table.
    """

    def __init__(
        self,
        conn: Any,
        service: BenchmarkIndexIngestionService,
    ):
        self.conn = conn
        self.service = service

    def run_core_daily_refresh(
        self,
        lookback_days: int = 10,
        end_date: date | None = None,
    ) -> IndexJobResult:
        """
        Refresh recent daily bars for all core indices.

        A short lookback makes this idempotent and handles late corrections.
        """
        end = end_date or date.today()
        start = end - timedelta(days=lookback_days)

        row_count = self.service.ingest_core_daily_prices(
            start_date=start,
            end_date=end,
        )

        self.service.compute_core_metrics()

        return IndexJobResult(
            job_type="core_daily_refresh",
            target_count=self._count_core_indices(),
            row_count=row_count,
        )

    def run_core_intraday_refresh(
        self,
        interval: str = "5min",
    ) -> IndexJobResult:
        row_count = self.service.ingest_core_intraday_prices(interval=interval)

        return IndexJobResult(
            job_type="core_intraday_refresh",
            target_count=self._count_core_indices(),
            row_count=row_count,
        )

    def run_core_composition_refresh(
        self,
        snapshot_date: date | None = None,
    ) -> IndexJobResult:
        snap_date = snapshot_date or date.today()
        row_count = 0

        for index_id in self._core_index_ids():
            try:
                row_count += self.service.ingest_composition(index_id, snap_date)
            except ValueError:
                # Some core benchmarks will only have proxy/manual composition at first.
                # Do not fail the whole batch because one benchmark lacks constituents.
                continue

        return IndexJobResult(
            job_type="core_composition_refresh",
            target_count=self._count_core_indices(),
            row_count=row_count,
        )

    def run_relative_metrics_against_sp500(self) -> IndexJobResult:
        row_count = 0

        for index_id in self._core_index_ids():
            if index_id == "SP500":
                continue

            row_count += self.service.compute_relative_metrics(
                index_id=index_id,
                comparison_index_id="SP500",
            )

        return IndexJobResult(
            job_type="core_relative_metrics",
            target_count=max(0, self._count_core_indices() - 1),
            row_count=row_count,
        )

    def _core_index_ids(self) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT index_id
            FROM benchmark_index
            WHERE is_core = TRUE
              AND is_active = TRUE
            ORDER BY index_id;
            """
        ).fetchall()

        return [row[0] for row in rows]

    def _count_core_indices(self) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM benchmark_index
            WHERE is_core = TRUE
              AND is_active = TRUE;
            """
        ).fetchone()

        return int(row[0])