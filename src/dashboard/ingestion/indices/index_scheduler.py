from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable

from dashboard.ingestion.indices.index_ingestion_service import BenchmarkIndexIngestionService


@dataclass(frozen=True)
class IndexJobResult:
    job_type: str
    target_count: int
    row_count: int


class BenchmarkIndexScheduler:
    def __init__(
        self,
        conn: Any,
        service: BenchmarkIndexIngestionService,
        market_is_open_fn: Callable[[datetime], bool] | None = None,
    ):
        self.conn = conn
        self.service = service
        self.market_is_open_fn = market_is_open_fn or self._default_market_is_open

    def run_core_daily_refresh(
        self,
        lookback_days: int = 10,
        end_date: date | None = None,
    ) -> IndexJobResult:
        end = end_date or date.today()
        start = end - timedelta(days=lookback_days)

        row_count = self.service.ingest_core_daily_prices(start, end)
        self.service.compute_core_metrics()

        return IndexJobResult(
            job_type="core_daily_refresh",
            target_count=self._count_indices_by_category("core_geo"),
            row_count=row_count,
        )

    def run_core_intraday_refresh(
        self,
        interval: str = "5min",
        now: datetime | None = None,
    ) -> IndexJobResult:
        if not self.market_is_open_fn(now or datetime.now()):
            return IndexJobResult(
                job_type="core_intraday_refresh",
                target_count=self._count_indices_by_category("core_geo"),
                row_count=0,
            )

        row_count = self.service.ingest_core_intraday_prices(interval)

        return IndexJobResult(
            job_type="core_intraday_refresh",
            target_count=self._count_indices_by_category("core_geo"),
            row_count=row_count,
        )

    def run_core_composition_refresh(
        self,
        snapshot_date: date | None = None,
    ) -> IndexJobResult:
        snap_date = snapshot_date or date.today()
        row_count = self.service.ingest_composition_for_category(
            index_category="core_geo",
            snapshot_date=snap_date,
            continue_on_error=True,
        )

        return IndexJobResult(
            job_type="core_composition_refresh",
            target_count=self._count_indices_by_category("core_geo"),
            row_count=row_count,
        )

    def run_non_core_daily_refresh(
        self,
        lookback_days: int = 10,
        end_date: date | None = None,
    ) -> IndexJobResult:
        end = end_date or date.today()
        start = end - timedelta(days=lookback_days)

        row_count = self.service.ingest_non_core_daily_prices(start, end)
        self.service.compute_non_core_metrics()

        return IndexJobResult(
            job_type="non_core_daily_refresh",
            target_count=self._count_non_core_indices(),
            row_count=row_count,
        )

    def run_non_core_intraday_refresh(
        self,
        interval: str = "5min",
        now: datetime | None = None,
    ) -> IndexJobResult:
        if not self.market_is_open_fn(now or datetime.now()):
            return IndexJobResult(
                job_type="non_core_intraday_refresh",
                target_count=self._count_non_core_indices(),
                row_count=0,
            )

        row_count = self.service.ingest_non_core_intraday_prices(interval)

        return IndexJobResult(
            job_type="non_core_intraday_refresh",
            target_count=self._count_non_core_indices(),
            row_count=row_count,
        )

    def run_non_core_composition_refresh(
        self,
        snapshot_date: date | None = None,
    ) -> IndexJobResult:
        snap_date = snapshot_date or date.today()
        row_count = self.service.ingest_non_core_composition(
            snapshot_date=snap_date,
            continue_on_error=True,
        )

        return IndexJobResult(
            job_type="non_core_composition_refresh",
            target_count=self._count_non_core_indices(),
            row_count=row_count,
        )

    def run_sector_daily_refresh(
        self,
        lookback_days: int = 10,
        end_date: date | None = None,
    ) -> IndexJobResult:
        return self._run_category_daily_refresh("sector", lookback_days, end_date)

    def run_industry_daily_refresh(
        self,
        lookback_days: int = 10,
        end_date: date | None = None,
    ) -> IndexJobResult:
        return self._run_category_daily_refresh("industry", lookback_days, end_date)

    def run_theme_daily_refresh(
        self,
        lookback_days: int = 10,
        end_date: date | None = None,
    ) -> IndexJobResult:
        return self._run_category_daily_refresh("theme", lookback_days, end_date)

    def run_relative_metrics_against_sp500(self) -> IndexJobResult:
        row_count = 0

        for index_id in self._all_active_index_ids():
            if index_id == "SP500":
                continue

            row_count += self.service.compute_relative_metrics(
                index_id=index_id,
                comparison_index_id="SP500",
            )

        return IndexJobResult(
            job_type="all_relative_metrics",
            target_count=max(0, len(self._all_active_index_ids()) - 1),
            row_count=row_count,
        )

    def _run_category_daily_refresh(
        self,
        index_category: str,
        lookback_days: int,
        end_date: date | None,
    ) -> IndexJobResult:
        end = end_date or date.today()
        start = end - timedelta(days=lookback_days)

        row_count = self.service.ingest_daily_prices_for_category(
            index_category=index_category,
            start_date=start,
            end_date=end,
        )

        self.service.compute_metrics_for_category(index_category)

        return IndexJobResult(
            job_type=f"{index_category}_daily_refresh",
            target_count=self._count_indices_by_category(index_category),
            row_count=row_count,
        )

    def _all_active_index_ids(self) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT index_id
            FROM benchmark_index
            WHERE is_active = TRUE
            ORDER BY index_id;
            """
        ).fetchall()

        return [row[0] for row in rows]

    def _count_indices_by_category(self, index_category: str) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM benchmark_index
            WHERE index_category = ?
              AND is_active = TRUE;
            """,
            [index_category],
        ).fetchone()

        return int(row[0])

    def _count_non_core_indices(self) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM benchmark_index
            WHERE index_category IN ('sector', 'industry', 'theme')
              AND is_active = TRUE;
            """
        ).fetchone()

        return int(row[0])

    def _default_market_is_open(self, current_time: datetime) -> bool:
        return True