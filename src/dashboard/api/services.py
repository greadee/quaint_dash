"""Application-facing read and write services for the HTTP API."""

from dataclasses import asdict
from datetime import date, timedelta
import json
from typing import Any

from dashboard.api.models import (
    AssetDetail,
    AssetActivitySummary,
    AssetHoldingSummary,
    BrokerAccountResponse,
    BrokerConnectionResponse,
    BrokerUserResponse,
    BenchmarkAvailableMetricRange,
    BenchmarkAvailablePriceRange,
    BenchmarkConstituent,
    BenchmarkComparisonProfile,
    BenchmarkDailyMetric,
    BenchmarkDefaultResponse,
    BenchmarkExposure,
    BenchmarkIndexDetail,
    BenchmarkIndexSummary,
    BenchmarkPricePoint,
    BenchmarkSymbol,
    BenchmarkSyncState,
    ComparisonAssetProfile,
    ComparisonFundamentals,
    ComparisonResponse,
    ComparisonReturns,
    IngestionJobResponse,
    NewsItemResponse,
    OverviewUpdatesResponse,
    Page,
    PortfolioCreate,
    PortfolioSummary,
    PortfolioUpdate,
    PositionSummary,
    PricePointResponse,
    PriceMoverResponse,
    TransactionSummary,
    ValuationContext,
)
from dashboard.analytics import AnalyticsEngine, AnalyticsRepository, analytics_report_payload
from dashboard.analytics.models import PositionAnalytics
from dashboard.brokers.repository import BrokerSyncRepository
from dashboard.brokers.models import BrokerUser
from dashboard.brokers.snaptrade import SNAPTRADE_PROVIDER
from dashboard.ingestion.indices.index_service_factory import (
    create_index_ingestion_service,
    create_index_scheduler,
)
from dashboard.models.commands import BrokerCommands, IngestionCommands


_HOLDINGS_SQL = """
SELECT portfolio_id, asset_id, SUM(quantity) AS quantity, SUM(book_cost) AS book_cost
FROM (
    SELECT
        portfolio_id,
        asset_id,
        SUM(qty) AS quantity,
        SUM(qty * price) AS book_cost
    FROM txn
    WHERE asset_id IS NOT NULL
      AND txn_type IN ('buy', 'sell')
      AND NOT EXISTS (
        SELECT 1
        FROM broker_portfolio_txn_map tm
        JOIN broker_portfolio_position_map pm
          ON pm.provider = tm.provider
         AND pm.provider_account_id = tm.provider_account_id
         AND pm.portfolio_id = txn.portfolio_id
         AND pm.asset_id = txn.asset_id
        WHERE tm.txn_id = txn.txn_id
      )
    GROUP BY portfolio_id, asset_id
    UNION ALL
    SELECT
        portfolio_id,
        asset_id,
        quantity,
        book_cost
    FROM broker_portfolio_position_map
) holdings
GROUP BY portfolio_id, asset_id
"""


_ENRICHED_ASSET_SELECT = """
    a.asset_id,
    COALESCE(a.symbol, a.asset_id) AS symbol,
    a.exchange_code,
    a.asset_type,
    a.asset_subtype,
    a.ccy,
    a.name,
    a.description,
    CASE WHEN cdr_underlying.asset_id IS NOT NULL
        THEN COALESCE(cdr_underlying.sector, a.sector)
        ELSE a.sector
    END AS sector,
    CASE WHEN cdr_underlying.asset_id IS NOT NULL
        THEN COALESCE(cdr_underlying.industry, a.industry)
        ELSE a.industry
    END AS industry,
    CASE WHEN cdr_underlying.asset_id IS NOT NULL
        THEN COALESCE(cdr_underlying.country, a.country)
        ELSE a.country
    END AS country,
    CASE WHEN cdr_underlying.asset_id IS NOT NULL
        THEN COALESCE(cdr_underlying.region, a.region)
        ELSE a.region
    END AS region,
    a.size,
    COALESCE(a.mkt_cap, cdr_underlying.mkt_cap) AS mkt_cap,
    COALESCE(a.shares_outstanding, cdr_underlying.shares_outstanding) AS shares_outstanding,
    COALESCE(a.market_beta, cdr_underlying.market_beta) AS market_beta
"""


class BenchmarkApiService:
    def __init__(self, conn) -> None:
        self.conn = conn

    def list_benchmarks(
        self,
        q: str | None = None,
        category: str | None = None,
        region: str | None = None,
        country_code: str | None = None,
        currency: str | None = None,
        is_core: bool | None = None,
        is_active: bool | None = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BenchmarkIndexSummary]:
        where = []
        params: list[Any] = []
        if q:
            like = f"%{q.strip().lower()}%"
            where.append(
                "("
                "LOWER(b.index_id) LIKE ? OR LOWER(b.index_name) LIKE ? OR "
                "LOWER(b.index_family) LIKE ? OR LOWER(COALESCE(b.notes, '')) LIKE ?"
                ")"
            )
            params.extend([like, like, like, like])
        if category:
            where.append("b.index_category = ?")
            params.append(category)
        if region:
            where.append("LOWER(COALESCE(b.region, '')) = LOWER(?)")
            params.append(region)
        if country_code:
            where.append("UPPER(COALESCE(b.country_code, '')) = UPPER(?)")
            params.append(country_code)
        if currency:
            where.append("UPPER(b.currency) = UPPER(?)")
            params.append(currency)
        if is_core is not None:
            where.append("b.is_core = ?")
            params.append(is_core)
        if is_active is not None:
            where.append("b.is_active = ?")
            params.append(is_active)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self.conn.execute(
            f"""
            WITH latest_metrics AS (
                SELECT *
                FROM benchmark_index_daily_metric
                QUALIFY ROW_NUMBER() OVER (PARTITION BY index_id ORDER BY metric_date DESC) = 1
            ),
            latest_prices AS (
                SELECT *
                FROM benchmark_index_daily_price
                QUALIFY ROW_NUMBER() OVER (PARTITION BY index_id ORDER BY price_date DESC) = 1
            ),
            latest_compositions AS (
                SELECT *
                FROM benchmark_index_composition_snapshot
                QUALIFY ROW_NUMBER() OVER (
                    PARTITION BY index_id
                    ORDER BY snapshot_date DESC, fetched_at DESC
                ) = 1
            ),
            sync_rollup AS (
                SELECT
                    index_id,
                    MAX(last_success_at) FILTER (WHERE job_type = 'daily_price') AS daily_price_last_success_at,
                    MAX(last_success_at) FILTER (WHERE job_type = 'composition') AS composition_last_success_at,
                    STRING_AGG(last_error, ' | ' ORDER BY updated_at DESC) FILTER (
                        WHERE last_error IS NOT NULL AND last_error <> ''
                    ) AS last_error
                FROM benchmark_index_sync_state
                GROUP BY index_id
            )
            SELECT
                b.index_id,
                b.index_name,
                b.index_family,
                b.index_category,
                b.region,
                b.country_code,
                b.currency,
                b.is_core,
                b.is_active,
                b.notes,
                m.metric_date,
                p.close,
                m.return_1d,
                m.return_21d,
                m.return_252d,
                m.volatility_252d_ann,
                c.snapshot_date,
                c.constituent_count,
                c.data_quality,
                s.daily_price_last_success_at,
                s.composition_last_success_at,
                s.last_error
            FROM benchmark_index b
            LEFT JOIN latest_metrics m ON m.index_id = b.index_id
            LEFT JOIN latest_prices p ON p.index_id = b.index_id
            LEFT JOIN latest_compositions c ON c.index_id = b.index_id
            LEFT JOIN sync_rollup s ON s.index_id = b.index_id
            {where_sql}
            ORDER BY b.is_core DESC, b.index_category, b.index_id
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        return [self._summary_from_row(row) for row in rows]

    def get_benchmark(self, index_id: str) -> BenchmarkIndexDetail:
        summary = self._get_summary(index_id)
        if summary is None:
            raise LookupError(f"Benchmark not found: {index_id}")
        symbols = [
            BenchmarkSymbol(
                provider=row[0],
                provider_symbol=row[1],
                symbol_purpose=row[2],
                is_primary=bool(row[3]),
                is_proxy=bool(row[4]),
            )
            for row in self.conn.execute(
                """
                SELECT provider, provider_symbol, symbol_purpose, is_primary, is_proxy
                FROM benchmark_index_symbol
                WHERE UPPER(index_id) = UPPER(?)
                ORDER BY is_primary DESC, symbol_purpose, provider
                """,
                [index_id],
            ).fetchall()
        ]
        sync_state = {
            row[0]: BenchmarkSyncState(
                job_type=row[0],
                last_success_at=row[1],
                last_attempt_at=row[2],
                last_success_date=row[3],
                last_error=row[4],
                updated_at=row[5],
            )
            for row in self.conn.execute(
                """
                SELECT job_type, last_success_at, last_attempt_at, last_success_date, last_error, updated_at
                FROM benchmark_index_sync_state
                WHERE UPPER(index_id) = UPPER(?)
                ORDER BY job_type
                """,
                [index_id],
            ).fetchall()
        }
        snapshot_dates = [
            row[0]
            for row in self.conn.execute(
                """
                SELECT DISTINCT snapshot_date
                FROM benchmark_index_composition_snapshot
                WHERE UPPER(index_id) = UPPER(?)
                ORDER BY snapshot_date DESC
                """,
                [index_id],
            ).fetchall()
        ]
        price_range = self.conn.execute(
            """
            SELECT MIN(price_date), MAX(price_date)
            FROM benchmark_index_daily_price
            WHERE UPPER(index_id) = UPPER(?)
            """,
            [index_id],
        ).fetchone()
        metric_range = self.conn.execute(
            """
            SELECT MIN(metric_date), MAX(metric_date)
            FROM benchmark_index_daily_metric
            WHERE UPPER(index_id) = UPPER(?)
            """,
            [index_id],
        ).fetchone()
        return BenchmarkIndexDetail(
            **summary.model_dump(),
            symbols=symbols,
            sync_state=sync_state,
            available_snapshot_dates=snapshot_dates,
            available_price_range=BenchmarkAvailablePriceRange(
                first_price_date=price_range[0],
                last_price_date=price_range[1],
            ),
            available_metric_range=BenchmarkAvailableMetricRange(
                first_metric_date=metric_range[0],
                last_metric_date=metric_range[1],
            ),
        )

    def prices(
        self,
        index_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 365,
    ) -> list[BenchmarkPricePoint]:
        self._require_benchmark(index_id)
        where = ["UPPER(index_id) = UPPER(?)"]
        params: list[Any] = [index_id]
        if start_date is not None:
            where.append("price_date >= ?")
            params.append(start_date)
        if end_date is not None:
            where.append("price_date <= ?")
            params.append(end_date)
        rows = self.conn.execute(
            f"""
            SELECT price_date, open, high, low, close, adj_close, volume, source, source_symbol, is_proxy
            FROM (
                SELECT *
                FROM benchmark_index_daily_price
                WHERE {" AND ".join(where)}
                ORDER BY price_date DESC
                LIMIT ?
            )
            ORDER BY price_date
            """,
            [*params, limit],
        ).fetchall()
        return [
            BenchmarkPricePoint(
                date=row[0],
                open=_float_or_none(row[1]),
                high=_float_or_none(row[2]),
                low=_float_or_none(row[3]),
                close=float(row[4]),
                adj_close=_float_or_none(row[5]),
                volume=_float_or_none(row[6]),
                source=row[7],
                source_symbol=row[8],
                is_proxy=bool(row[9]),
            )
            for row in rows
        ]

    def metrics(self, index_id: str, limit: int = 365) -> list[BenchmarkDailyMetric]:
        self._require_benchmark(index_id)
        rows = self.conn.execute(
            """
            SELECT
                metric_date,
                return_1d,
                return_5d,
                return_21d,
                return_63d,
                return_126d,
                return_252d,
                return_ytd,
                volatility_21d_ann,
                volatility_63d_ann,
                volatility_252d_ann,
                sma_50,
                sma_200,
                high_52w,
                low_52w,
                drawdown_from_52w_high
            FROM (
                SELECT *
                FROM benchmark_index_daily_metric
                WHERE UPPER(index_id) = UPPER(?)
                ORDER BY metric_date DESC
                LIMIT ?
            )
            ORDER BY metric_date
            """,
            [index_id, limit],
        ).fetchall()
        return [
            BenchmarkDailyMetric(
                metric_date=row[0],
                return_1d=_float_or_none(row[1]),
                return_5d=_float_or_none(row[2]),
                return_21d=_float_or_none(row[3]),
                return_63d=_float_or_none(row[4]),
                return_126d=_float_or_none(row[5]),
                return_252d=_float_or_none(row[6]),
                return_ytd=_float_or_none(row[7]),
                volatility_21d_ann=_float_or_none(row[8]),
                volatility_63d_ann=_float_or_none(row[9]),
                volatility_252d_ann=_float_or_none(row[10]),
                sma_50=_float_or_none(row[11]),
                sma_200=_float_or_none(row[12]),
                high_52w=_float_or_none(row[13]),
                low_52w=_float_or_none(row[14]),
                drawdown_from_52w_high=_float_or_none(row[15]),
            )
            for row in rows
        ]

    def constituents(
        self,
        index_id: str,
        snapshot_date: date | None = None,
        source: str | None = None,
        limit: int = 100,
        offset: int = 0,
        sort: str = "weight_desc",
    ) -> Page[BenchmarkConstituent]:
        self._require_benchmark(index_id)
        snap_date = snapshot_date or self._latest_snapshot_date(index_id)
        if snap_date is None:
            return Page(items=[], total=0, limit=limit, offset=offset)
        where = ["UPPER(index_id) = UPPER(?)", "snapshot_date = ?"]
        params: list[Any] = [index_id, snap_date]
        if source:
            where.append("source = ?")
            params.append(source)
        where_sql = " AND ".join(where)
        order_by = {
            "weight_desc": "weight_pct DESC NULLS LAST, constituent_symbol",
            "weight_asc": "weight_pct ASC NULLS LAST, constituent_symbol",
            "symbol": "constituent_symbol",
            "name": "constituent_name NULLS LAST, constituent_symbol",
        }.get(sort)
        if order_by is None:
            raise ValueError(f"Unsupported constituent sort: {sort}")
        total = int(
            self.conn.execute(
                f"SELECT COUNT(*) FROM benchmark_index_constituent WHERE {where_sql}",
                params,
            ).fetchone()[0]
        )
        rows = self.conn.execute(
            f"""
            SELECT
                index_id,
                snapshot_date,
                source,
                constituent_symbol,
                constituent_name,
                exchange_code,
                country_code,
                currency,
                sector,
                industry,
                weight_pct,
                market_cap,
                is_proxy
            FROM benchmark_index_constituent
            WHERE {where_sql}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        return Page(
            items=[
                BenchmarkConstituent(
                    index_id=row[0],
                    snapshot_date=row[1],
                    source=row[2],
                    constituent_symbol=row[3],
                    constituent_name=row[4],
                    exchange_code=row[5],
                    country_code=row[6],
                    currency=row[7],
                    sector=row[8],
                    industry=row[9],
                    weight_pct=_float_or_none(row[10]),
                    market_cap=_float_or_none(row[11]),
                    is_proxy=bool(row[12]),
                )
                for row in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    def exposures(
        self,
        index_id: str,
        snapshot_date: date | None = None,
        dimension_type: str | None = None,
    ) -> list[BenchmarkExposure]:
        self._require_benchmark(index_id)
        snap_date = snapshot_date or self._latest_exposure_snapshot_date(index_id)
        if snap_date is None:
            return []
        where = ["UPPER(index_id) = UPPER(?)", "snapshot_date = ?"]
        params: list[Any] = [index_id, snap_date]
        if dimension_type:
            where.append("dimension_type = ?")
            params.append(dimension_type)
        rows = self.conn.execute(
            f"""
            SELECT index_id, snapshot_date, dimension_type, dimension_value, weight_pct, source, source_type, is_proxy
            FROM benchmark_index_exposure_snapshot
            WHERE {" AND ".join(where)}
            ORDER BY dimension_type, weight_pct DESC, dimension_value
            """,
            params,
        ).fetchall()
        return [
            BenchmarkExposure(
                index_id=row[0],
                snapshot_date=row[1],
                dimension_type=row[2],
                dimension_value=row[3],
                weight_pct=float(row[4]),
                source=row[5],
                source_type=row[6],
                is_proxy=bool(row[7]),
            )
            for row in rows
        ]

    def default_for_asset(self, asset_id: str) -> BenchmarkDefaultResponse:
        repo = AnalyticsRepository(self.conn)
        benchmark = repo.default_benchmark_for_asset(asset_id)
        return BenchmarkDefaultResponse(
            subject_type="asset",
            subject_id=asset_id.upper().strip(),
            benchmark_index_id=benchmark,
            reason="asset country/currency metadata and available benchmark prices",
            fallback_used=benchmark is None,
        )

    def default_for_portfolio(self, portfolio_id: int) -> BenchmarkDefaultResponse:
        PortfolioApiService(self.conn).get_portfolio(portfolio_id)
        repo = AnalyticsRepository(self.conn)
        positions = self._weighted_portfolio_positions(repo, portfolio_id)
        benchmark = repo.default_benchmark_for_portfolio(positions)
        return BenchmarkDefaultResponse(
            subject_type="portfolio",
            subject_id=str(portfolio_id),
            benchmark_index_id=benchmark,
            reason="dominant portfolio country/currency exposure and available benchmark prices",
            fallback_used=benchmark is None or not positions,
        )

    def seed(self, scope: str) -> dict[str, int | str]:
        service = create_index_ingestion_service(self.conn)
        if scope == "core":
            count = service.seed_core_universe()
        elif scope == "non_core":
            count = service.seed_sector_industry_universe()
        elif scope == "all":
            count = service.seed_all_universes()
        else:
            raise ValueError(f"Unsupported benchmark seed scope: {scope}")
        return {"scope": scope, "seeded_count": count}

    def refresh_benchmark(
        self,
        index_id: str,
        job_type: str,
        lookback_days: int = 10,
        interval: str = "5min",
        comparison_index_id: str = "SP500",
    ) -> dict[str, Any]:
        self._require_benchmark(index_id)
        service = create_index_ingestion_service(self.conn)
        end = date.today()
        start = end - timedelta(days=lookback_days)
        if job_type == "daily_price":
            row_count = service.ingest_daily_prices(index_id, start, end)
        elif job_type == "intraday_price":
            row_count = service.ingest_intraday_prices(index_id, interval)
        elif job_type == "composition":
            row_count = service.ingest_composition(index_id, end)
        elif job_type == "metrics":
            row_count = service.compute_daily_metrics(index_id)
        elif job_type == "relative_metrics":
            row_count = service.compute_relative_metrics(index_id, comparison_index_id)
        else:
            raise ValueError(f"Unsupported benchmark refresh job type: {job_type}")
        return {
            "index_id": index_id,
            "job_type": job_type,
            "target_count": 1,
            "row_count": row_count,
        }

    def refresh_benchmarks(
        self,
        category: str,
        job_type: str,
        lookback_days: int = 10,
        interval: str = "5min",
    ) -> dict[str, Any]:
        scheduler = create_index_scheduler(self.conn)
        service = scheduler.service
        end = date.today()
        start = end - timedelta(days=lookback_days)

        if job_type == "relative_metrics":
            result = scheduler.run_relative_metrics_against_sp500()
        elif category == "all":
            result = self._run_all_refresh(service, job_type, start, end, interval)
        elif category == "non_core":
            result = self._run_non_core_refresh(scheduler, job_type, lookback_days, interval)
        elif category == "core_geo":
            result = self._run_core_refresh(scheduler, job_type, lookback_days, interval)
        elif category in {"sector", "industry", "theme"}:
            result = self._run_category_refresh(service, category, job_type, start, end, interval)
        else:
            raise ValueError(f"Unsupported benchmark refresh category: {category}")
        return CommandApiService.action_result(result)

    def _run_core_refresh(self, scheduler, job_type: str, lookback_days: int, interval: str):
        if job_type == "daily_price":
            return scheduler.run_core_daily_refresh(lookback_days=lookback_days)
        if job_type == "intraday_price":
            return scheduler.run_core_intraday_refresh(interval=interval)
        if job_type == "composition":
            return scheduler.run_core_composition_refresh()
        if job_type == "metrics":
            count = scheduler.service.compute_core_metrics()
            return {"job_type": "core_metrics", "target_count": scheduler._count_indices_by_category("core_geo"), "row_count": count}
        raise ValueError(f"Unsupported benchmark refresh job type: {job_type}")

    def _run_non_core_refresh(self, scheduler, job_type: str, lookback_days: int, interval: str):
        if job_type == "daily_price":
            return scheduler.run_non_core_daily_refresh(lookback_days=lookback_days)
        if job_type == "intraday_price":
            return scheduler.run_non_core_intraday_refresh(interval=interval)
        if job_type == "composition":
            return scheduler.run_non_core_composition_refresh()
        if job_type == "metrics":
            count = scheduler.service.compute_non_core_metrics()
            return {"job_type": "non_core_metrics", "target_count": scheduler._count_non_core_indices(), "row_count": count}
        raise ValueError(f"Unsupported benchmark refresh job type: {job_type}")

    def _run_category_refresh(
        self,
        service,
        category: str,
        job_type: str,
        start: date,
        end: date,
        interval: str,
    ) -> dict[str, Any]:
        target_count = self._count_category(category)
        if job_type == "daily_price":
            row_count = service.ingest_daily_prices_for_category(category, start, end)
            service.compute_metrics_for_category(category)
        elif job_type == "intraday_price":
            row_count = service.ingest_intraday_prices_for_category(category, interval)
        elif job_type == "composition":
            row_count = service.ingest_composition_for_category(category, end, continue_on_error=True)
        elif job_type == "metrics":
            row_count = service.compute_metrics_for_category(category)
        else:
            raise ValueError(f"Unsupported benchmark refresh job type: {job_type}")
        return {"job_type": f"{category}_{job_type}", "target_count": target_count, "row_count": row_count}

    def _run_all_refresh(
        self,
        service,
        job_type: str,
        start: date,
        end: date,
        interval: str,
    ) -> dict[str, Any]:
        target_count = self._count_all_active()
        if job_type == "daily_price":
            row_count = 0
            for category in ("core_geo", "sector", "industry", "theme"):
                row_count += service.ingest_daily_prices_for_category(category, start, end)
                service.compute_metrics_for_category(category)
        elif job_type == "intraday_price":
            row_count = 0
            for category in ("core_geo", "sector", "industry", "theme"):
                row_count += service.ingest_intraday_prices_for_category(category, interval)
        elif job_type == "composition":
            row_count = 0
            for category in ("core_geo", "sector", "industry", "theme"):
                row_count += service.ingest_composition_for_category(category, end, continue_on_error=True)
        elif job_type == "metrics":
            row_count = 0
            for category in ("core_geo", "sector", "industry", "theme"):
                row_count += service.compute_metrics_for_category(category)
        else:
            raise ValueError(f"Unsupported benchmark refresh job type: {job_type}")
        return {"job_type": f"all_{job_type}", "target_count": target_count, "row_count": row_count}

    def _summary_from_row(self, row) -> BenchmarkIndexSummary:
        return BenchmarkIndexSummary(
            index_id=row[0],
            index_name=row[1],
            index_family=row[2],
            index_category=row[3],
            region=row[4],
            country_code=row[5],
            currency=row[6],
            is_core=bool(row[7]),
            is_active=bool(row[8]),
            notes=row[9],
            latest_metric_date=row[10],
            latest_close=_float_or_none(row[11]),
            return_1d=_float_or_none(row[12]),
            return_21d=_float_or_none(row[13]),
            return_252d=_float_or_none(row[14]),
            volatility_252d_ann=_float_or_none(row[15]),
            latest_composition_date=row[16],
            constituent_count=int(row[17]) if row[17] is not None else None,
            composition_quality=row[18],
            daily_price_last_success_at=row[19],
            composition_last_success_at=row[20],
            last_error=row[21],
        )

    def _get_summary(self, index_id: str) -> BenchmarkIndexSummary | None:
        rows = self.list_benchmarks(q=index_id, is_active=None, limit=500)
        for row in rows:
            if row.index_id.upper() == index_id.upper().strip():
                return row
        return None

    def _require_benchmark(self, index_id: str) -> None:
        if self._get_summary(index_id) is None:
            raise LookupError(f"Benchmark not found: {index_id}")

    def _latest_snapshot_date(self, index_id: str) -> date | None:
        row = self.conn.execute(
            """
            SELECT MAX(snapshot_date)
            FROM benchmark_index_composition_snapshot
            WHERE UPPER(index_id) = UPPER(?)
            """,
            [index_id],
        ).fetchone()
        return row[0] if row else None

    def _latest_exposure_snapshot_date(self, index_id: str) -> date | None:
        row = self.conn.execute(
            """
            SELECT MAX(snapshot_date)
            FROM benchmark_index_exposure_snapshot
            WHERE UPPER(index_id) = UPPER(?)
            """,
            [index_id],
        ).fetchone()
        return row[0] if row else None

    def _weighted_portfolio_positions(
        self,
        repo: AnalyticsRepository,
        portfolio_id: int,
    ) -> list[PositionAnalytics]:
        positions: list[PositionAnalytics] = []
        total_value = 0.0
        for _portfolio_id, asset_id, qty, book_cost in repo.portfolio_positions(portfolio_id):
            latest_price = repo.latest_price(asset_id)
            market_value = qty * latest_price if latest_price is not None else None
            if market_value is not None:
                total_value += market_value
            positions.append(
                PositionAnalytics(
                    portfolio_id=portfolio_id,
                    asset_id=asset_id,
                    qty=qty,
                    book_cost=book_cost,
                    latest_price=latest_price,
                    market_value=market_value,
                    weight=None,
                    unrealized_gain=market_value - book_cost if market_value is not None else None,
                )
            )
        if total_value <= 0:
            return positions
        return [
            PositionAnalytics(
                portfolio_id=item.portfolio_id,
                asset_id=item.asset_id,
                qty=item.qty,
                book_cost=item.book_cost,
                latest_price=item.latest_price,
                market_value=item.market_value,
                weight=item.market_value / total_value if item.market_value is not None else None,
                unrealized_gain=item.unrealized_gain,
            )
            for item in positions
        ]

    def _count_category(self, category: str) -> int:
        return int(
            self.conn.execute(
                """
                SELECT COUNT(*)
                FROM benchmark_index
                WHERE index_category = ?
                  AND is_active = TRUE
                """,
                [category],
            ).fetchone()[0]
        )

    def _count_all_active(self) -> int:
        return int(
            self.conn.execute(
                """
                SELECT COUNT(*)
                FROM benchmark_index
                WHERE is_active = TRUE
                """
            ).fetchone()[0]
        )


_ENRICHED_ASSET_JOIN = """
LEFT JOIN asset cdr_underlying ON UPPER(cdr_underlying.asset_id) = UPPER(
        CASE
            WHEN POSITION('.' IN COALESCE(a.symbol, a.asset_id)) > 0
                THEN SPLIT_PART(COALESCE(a.symbol, a.asset_id), '.', 1)
            ELSE ''
        END
    )
    AND cdr_underlying.asset_id <> a.asset_id
    AND (
        LOWER(COALESCE(a.asset_subtype, '')) LIKE '%cdr%'
        OR LOWER(COALESCE(a.name, '')) LIKE '%depositary receipt%'
        OR LOWER(COALESCE(a.description, '')) LIKE '%depositary receipt%'
        OR LOWER(COALESCE(a.name, '')) LIKE '% cdr%'
        OR LOWER(COALESCE(a.description, '')) LIKE '% cdr%'
        OR (
            POSITION('.' IN COALESCE(a.symbol, a.asset_id)) > 0
            AND (
                a.sector IS NULL
                OR a.industry IS NULL
                OR a.country IS NULL
                OR UPPER(a.country) = 'CA'
            )
        )
    )
"""


_CDR_CLASSIFICATION_OVERRIDES = {
    "AAPL": {"sector": "Technology", "industry": "Consumer Electronics", "country": "US"},
    "AMD": {"sector": "Technology", "industry": "Semiconductors", "country": "US"},
    "AMZN": {"sector": "Consumer Cyclical", "industry": "Internet Retail", "country": "US"},
    "ANET": {"sector": "Technology", "industry": "Computer Hardware", "country": "US"},
    "ASML": {"sector": "Technology", "industry": "Semiconductors", "country": "NL"},
    "AVGO": {"sector": "Technology", "industry": "Semiconductors", "country": "US"},
    "GEV": {"sector": "Industrials", "industry": "Electrical Equipment & Parts", "country": "US"},
    "GOOG": {"sector": "Communication Services", "industry": "Internet Content & Information", "country": "US"},
    "ISRG": {"sector": "Healthcare", "industry": "Medical Instruments & Supplies", "country": "US"},
    "LLY": {"sector": "Healthcare", "industry": "Medical - Pharmaceuticals", "country": "US"},
    "META": {"sector": "Communication Services", "industry": "Internet Content & Information", "country": "US"},
    "MSFT": {"sector": "Technology", "industry": "Software - Infrastructure", "country": "US"},
    "MU": {"sector": "Technology", "industry": "Semiconductors", "country": "US"},
    "NOW": {"sector": "Technology", "industry": "Software - Application", "country": "US"},
    "NVDA": {"sector": "Technology", "industry": "Semiconductors", "country": "US"},
    "SPGI": {"sector": "Financial Services", "industry": "Financial Data & Stock Exchanges", "country": "US"},
    "TSLA": {"sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "country": "US"},
    "VISA": {"sector": "Financial Services", "industry": "Credit Services", "country": "US"},
}

_KNOWN_CDR_UNDERLYING_NAMES = {
    "AAPL": "Apple Inc.",
    "AMD": "Advanced Micro Devices, Inc.",
    "AMZN": "Amazon.com, Inc.",
    "ANET": "Arista Networks, Inc.",
    "ASML": "ASML Holding N.V.",
    "AVGO": "Broadcom Inc.",
    "GEV": "GE Vernova Inc.",
    "GOOG": "Alphabet Inc.",
    "ISRG": "Intuitive Surgical, Inc.",
    "LLY": "Eli Lilly and Company",
    "META": "Meta Platforms, Inc.",
    "MSFT": "Microsoft Corporation",
    "MU": "Micron Technology, Inc.",
    "NOW": "ServiceNow, Inc.",
    "NVDA": "NVIDIA Corporation",
    "SPGI": "S&P Global Inc.",
    "TSLA": "Tesla, Inc.",
    "VISA": "Visa Inc.",
}

_CDR_SYMBOL_ALIASES = {
    "NOWS": "NOW",
}


class PortfolioApiService:
    def __init__(self, conn) -> None:
        self.conn = conn

    def list_portfolios(self) -> list[PortfolioSummary]:
        rows = self.conn.execute(
            f"""
            WITH holdings AS ({_HOLDINGS_SQL}),
            latest_prices AS (
                SELECT asset_id, COALESCE(adj_close, close) AS price
                FROM asset_quote_daily
                QUALIFY ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY date DESC) = 1
            ),
            latest_broker_positions AS (
                SELECT
                    provider,
                    provider_account_id,
                    provider_position_id,
                    MAX(as_of_date) AS as_of_date
                FROM broker_position_snapshot
                GROUP BY provider, provider_account_id, provider_position_id
            ),
            broker_prices AS (
                SELECT
                    pm.portfolio_id,
                    pm.asset_id,
                    SUM(ps.market_value) / NULLIF(SUM(ps.quantity), 0) AS price
                FROM broker_portfolio_position_map pm
                JOIN latest_broker_positions latest
                  ON latest.provider = pm.provider
                 AND latest.provider_account_id = pm.provider_account_id
                 AND latest.provider_position_id = pm.provider_position_id
                JOIN broker_position_snapshot ps
                  ON ps.provider = latest.provider
                 AND ps.provider_account_id = latest.provider_account_id
                 AND ps.provider_position_id = latest.provider_position_id
                 AND ps.as_of_date = latest.as_of_date
                GROUP BY pm.portfolio_id, pm.asset_id
            ),
            totals AS (
                SELECT
                    h.portfolio_id,
                    COUNT(*) FILTER (WHERE h.quantity <> 0) AS position_count,
                    COALESCE(SUM(h.book_cost) FILTER (WHERE h.quantity <> 0), 0) AS book_cost,
                    COALESCE(
                        SUM(COALESCE(h.quantity * lp.price, h.quantity * bp.price, h.book_cost))
                            FILTER (WHERE h.quantity <> 0),
                        0
                    ) AS market_value
                FROM holdings h
                LEFT JOIN latest_prices lp ON lp.asset_id = h.asset_id
                LEFT JOIN broker_prices bp
                  ON bp.portfolio_id = h.portfolio_id
                 AND bp.asset_id = h.asset_id
                GROUP BY h.portfolio_id
            )
            SELECT
                p.portfolio_id,
                p.portfolio_name,
                p.base_ccy,
                p.created_at,
                p.updated_at,
                COALESCE(t.position_count, 0),
                COALESCE(t.market_value, 0),
                COALESCE(t.book_cost, 0)
            FROM portfolio p
            LEFT JOIN totals t ON t.portfolio_id = p.portfolio_id
            ORDER BY p.portfolio_id
            """
        ).fetchall()
        return [self._portfolio_summary(row) for row in rows]

    def aggregate_portfolio(self) -> PortfolioSummary:
        portfolios = self.list_portfolios()
        if not portfolios:
            raise LookupError("No portfolios found.")
        market_value = sum(item.market_value for item in portfolios)
        book_cost = sum(item.book_cost for item in portfolios)
        return PortfolioSummary(
            portfolio_id=0,
            name="All portfolios",
            base_ccy="CAD",
            created_at=min(item.created_at for item in portfolios),
            updated_at=max(item.updated_at for item in portfolios),
            position_count=sum(item.position_count for item in portfolios),
            market_value=market_value,
            book_cost=book_cost,
            unrealized_gain=market_value - book_cost if market_value else None,
            projected_value=sum(
                item.projected_value for item in portfolios if item.projected_value is not None
            )
            or None,
            projected_value_low=sum(
                item.projected_value_low
                for item in portfolios
                if item.projected_value_low is not None
            )
            or None,
            projected_value_high=sum(
                item.projected_value_high
                for item in portfolios
                if item.projected_value_high is not None
            )
            or None,
            projected_horizon_years=max(
                (
                    item.projected_horizon_years
                    for item in portfolios
                    if item.projected_horizon_years is not None
                ),
                default=None,
            ),
        )

    def get_portfolio(self, portfolio_id: int) -> PortfolioSummary:
        for portfolio in self.list_portfolios():
            if portfolio.portfolio_id == portfolio_id:
                return portfolio
        raise LookupError(f"Portfolio not found: {portfolio_id}")

    def create_portfolio(self, request: PortfolioCreate) -> PortfolioSummary:
        name = request.name.strip()
        if not name:
            raise ValueError("Portfolio name is required.")
        if self.conn.execute(
            "SELECT 1 FROM portfolio WHERE portfolio_name = ?",
            [name],
        ).fetchone():
            raise FileExistsError(f"Portfolio already exists: {name}")
        row = self.conn.execute(
            """
            INSERT INTO portfolio(portfolio_id, portfolio_name, base_ccy)
            SELECT COALESCE(MAX(portfolio_id), 0) + 1, ?, UPPER(?)
            FROM portfolio
            RETURNING portfolio_id
            """,
            [name, request.base_ccy],
        ).fetchone()
        return self.get_portfolio(int(row[0]))

    def update_portfolio(self, portfolio_id: int, request: PortfolioUpdate) -> PortfolioSummary:
        self.get_portfolio(portfolio_id)
        name = request.name.strip()
        if not name:
            raise ValueError("Portfolio name is required.")
        if self.conn.execute(
            """
            SELECT 1
            FROM portfolio
            WHERE portfolio_id <> ?
              AND portfolio_name = ?
            """,
            [portfolio_id, name],
        ).fetchone():
            raise FileExistsError(f"Portfolio already exists: {name}")
        self.conn.execute(
            """
            UPDATE portfolio
            SET portfolio_name = ?,
                updated_at = now()
            WHERE portfolio_id = ?
            """,
            [name, portfolio_id],
        )
        return self.get_portfolio(portfolio_id)

    def delete_portfolio(self, portfolio_id: int) -> dict[str, int]:
        self.get_portfolio(portfolio_id)
        self.conn.execute("UPDATE broker_account SET portfolio_id = NULL WHERE portfolio_id = ?", [portfolio_id])
        self.conn.execute("DELETE FROM broker_portfolio_position_map WHERE portfolio_id = ?", [portfolio_id])
        self.conn.execute("DELETE FROM broker_portfolio_txn_map WHERE portfolio_id = ?", [portfolio_id])
        self.conn.execute("DELETE FROM position WHERE portfolio_id = ?", [portfolio_id])
        self.conn.execute("DELETE FROM portfolio_ticker WHERE portfolio_id = ?", [portfolio_id])
        self.conn.execute("DELETE FROM txn WHERE portfolio_id = ?", [portfolio_id])
        self.conn.execute("DELETE FROM portfolio WHERE portfolio_id = ?", [portfolio_id])
        return {"portfolio_id": portfolio_id}

    def delete_position(self, portfolio_id: int, asset_id: str) -> dict[str, int | str]:
        self.get_portfolio(portfolio_id)
        asset_id = asset_id.upper().strip()
        existing = self.conn.execute(
            f"""
            WITH holdings AS ({_HOLDINGS_SQL})
            SELECT 1
            FROM holdings
            WHERE portfolio_id = ?
              AND UPPER(asset_id) = ?
              AND quantity <> 0
            """,
            [portfolio_id, asset_id],
        ).fetchone()
        if existing is None:
            raise LookupError(f"Holding not found in portfolio {portfolio_id}: {asset_id}")

        broker_rows = int(
            self.conn.execute(
                """
                SELECT COUNT(*)
                FROM broker_portfolio_position_map
                WHERE portfolio_id = ?
                  AND UPPER(asset_id) = ?
                """,
                [portfolio_id, asset_id],
            ).fetchone()[0]
        )
        txn_rows = self.conn.execute(
            """
            DELETE FROM txn
            WHERE portfolio_id = ?
              AND UPPER(asset_id) = ?
            RETURNING txn_id
            """,
            [portfolio_id, asset_id],
        ).fetchall()
        position_rows = self.conn.execute(
            """
            DELETE FROM position
            WHERE portfolio_id = ?
              AND UPPER(asset_id) = ?
            RETURNING asset_id
            """,
            [portfolio_id, asset_id],
        ).fetchall()
        broker_map_rows = self.conn.execute(
            """
            DELETE FROM broker_portfolio_position_map
            WHERE portfolio_id = ?
              AND UPPER(asset_id) = ?
            RETURNING asset_id
            """,
            [portfolio_id, asset_id],
        ).fetchall()
        self.conn.execute(
            """
            DELETE FROM portfolio_ticker
            WHERE portfolio_id = ?
              AND UPPER(asset_id) = ?
            """,
            [portfolio_id, asset_id],
        )
        return {
            "portfolio_id": portfolio_id,
            "asset_id": asset_id,
            "deleted_transactions": len(txn_rows),
            "deleted_positions": len(position_rows),
            "deleted_broker_mappings": len(broker_map_rows),
            "broker_linked": broker_rows > 0,
        }

    def list_positions(self, portfolio_id: int | None = None) -> list[PositionSummary]:
        if portfolio_id is not None:
            self.get_portfolio(portfolio_id)
            where = "WHERE portfolio_id = ?"
            params: list[object] = [portfolio_id, portfolio_id, portfolio_id]
        else:
            where = ""
            params = []
        rows = self.conn.execute(
            f"""
            WITH portfolio_holdings AS ({_HOLDINGS_SQL}),
            holdings AS (
                SELECT asset_id, SUM(quantity) AS quantity, SUM(book_cost) AS book_cost
                FROM portfolio_holdings
                {where}
                GROUP BY asset_id
                HAVING SUM(quantity) <> 0
            ),
            broker_links AS (
                SELECT
                    asset_id,
                    COUNT(DISTINCT provider_account_id) AS broker_account_count
                FROM broker_portfolio_position_map
                {where}
                GROUP BY asset_id
            ),
            latest_prices AS (
                SELECT asset_id, COALESCE(adj_close, close) AS price
                FROM asset_quote_daily
                QUALIFY ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY date DESC) = 1
            ),
            latest_broker_positions AS (
                SELECT
                    provider,
                    provider_account_id,
                    provider_position_id,
                    MAX(as_of_date) AS as_of_date
                FROM broker_position_snapshot
                GROUP BY provider, provider_account_id, provider_position_id
            ),
            broker_prices AS (
                SELECT
                    pm.asset_id,
                    SUM(ps.market_value) / NULLIF(SUM(ps.quantity), 0) AS price
                FROM broker_portfolio_position_map pm
                JOIN latest_broker_positions latest
                  ON latest.provider = pm.provider
                 AND latest.provider_account_id = pm.provider_account_id
                 AND latest.provider_position_id = pm.provider_position_id
                JOIN broker_position_snapshot ps
                  ON ps.provider = latest.provider
                 AND ps.provider_account_id = latest.provider_account_id
                 AND ps.provider_position_id = latest.provider_position_id
                 AND ps.as_of_date = latest.as_of_date
                {where}
                GROUP BY pm.asset_id
            ),
            valued AS (
                SELECT
                h.*,
                a.symbol,
                a.name,
                a.asset_type,
                CASE WHEN cdr_underlying.asset_id IS NOT NULL
                    THEN COALESCE(cdr_underlying.sector, a.sector)
                    ELSE a.sector
                END AS sector,
                CASE WHEN cdr_underlying.asset_id IS NOT NULL
                    THEN COALESCE(cdr_underlying.industry, a.industry)
                    ELSE a.industry
                END AS industry,
                CASE WHEN cdr_underlying.asset_id IS NOT NULL
                    THEN COALESCE(cdr_underlying.country, a.country)
                    ELSE a.country
                END AS country,
                a.ccy,
                COALESCE(bl.broker_account_count, 0) AS broker_account_count,
                COALESCE(lp.price, bp.price) AS price,
                COALESCE(h.quantity * lp.price, h.quantity * bp.price, h.book_cost) AS market_value
                FROM holdings h
                JOIN asset a ON a.asset_id = h.asset_id
                {_ENRICHED_ASSET_JOIN}
                LEFT JOIN latest_prices lp ON lp.asset_id = h.asset_id
                LEFT JOIN broker_prices bp ON bp.asset_id = h.asset_id
                LEFT JOIN broker_links bl ON bl.asset_id = h.asset_id
            )
            SELECT
                asset_id,
                COALESCE(symbol, asset_id),
                name,
                asset_type,
                sector,
                industry,
                country,
                ccy,
                broker_account_count,
                quantity,
                book_cost,
                price,
                market_value,
                market_value - book_cost,
                CASE
                    WHEN SUM(market_value) OVER () = 0 THEN NULL
                    ELSE market_value / SUM(market_value) OVER ()
                END
            FROM valued
            ORDER BY market_value DESC NULLS LAST, asset_id
            """,
            params,
        ).fetchall()
        return [self._position_summary(row) for row in rows]

    def _position_summary(self, row) -> PositionSummary:
        classification = _cdr_classification_override(
            asset_id=row[0],
            symbol=row[1],
            name=row[2],
            sector=row[4],
            industry=row[5],
            country=row[6],
        )
        return PositionSummary(
            asset_id=row[0],
            symbol=row[1],
            name=row[2],
            asset_type=row[3],
            sector=classification["sector"],
            industry=classification["industry"],
            country=classification["country"],
            currency=row[7],
            quantity=float(row[9]),
            book_cost=float(row[10]),
            latest_price=_float_or_none(row[11]),
            market_value=_float_or_none(row[12]),
            unrealized_gain=_float_or_none(row[13]),
            total_return_percent=_ratio_or_none(row[13], row[10]),
            weight=_float_or_none(row[14]),
            broker_linked=int(row[8]) > 0,
            broker_account_count=int(row[8]),
        )

    def list_asset_holdings(self, asset_id: str) -> list[AssetHoldingSummary]:
        asset_id = asset_id.upper().strip()
        rows = self.conn.execute(
            f"""
            WITH portfolio_holdings AS ({_HOLDINGS_SQL}),
            holdings AS (
                SELECT
                    h.portfolio_id,
                    p.portfolio_name,
                    h.asset_id,
                    SUM(h.quantity) AS quantity,
                    SUM(h.book_cost) AS book_cost
                FROM portfolio_holdings h
                JOIN portfolio p ON p.portfolio_id = h.portfolio_id
                WHERE UPPER(h.asset_id) = ?
                GROUP BY h.portfolio_id, p.portfolio_name, h.asset_id
                HAVING SUM(h.quantity) <> 0
            ),
            broker_links AS (
                SELECT
                    portfolio_id,
                    asset_id,
                    COUNT(DISTINCT provider_account_id) AS broker_account_count
                FROM broker_portfolio_position_map
                WHERE UPPER(asset_id) = ?
                GROUP BY portfolio_id, asset_id
            ),
            latest_prices AS (
                SELECT asset_id, COALESCE(adj_close, close) AS price
                FROM asset_quote_daily
                QUALIFY ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY date DESC) = 1
            ),
            latest_broker_positions AS (
                SELECT
                    provider,
                    provider_account_id,
                    provider_position_id,
                    MAX(as_of_date) AS as_of_date
                FROM broker_position_snapshot
                GROUP BY provider, provider_account_id, provider_position_id
            ),
            broker_prices AS (
                SELECT
                    pm.portfolio_id,
                    pm.asset_id,
                    SUM(ps.market_value) / NULLIF(SUM(ps.quantity), 0) AS price
                FROM broker_portfolio_position_map pm
                JOIN latest_broker_positions latest
                  ON latest.provider = pm.provider
                 AND latest.provider_account_id = pm.provider_account_id
                 AND latest.provider_position_id = pm.provider_position_id
                JOIN broker_position_snapshot ps
                  ON ps.provider = latest.provider
                 AND ps.provider_account_id = latest.provider_account_id
                 AND ps.provider_position_id = latest.provider_position_id
                 AND ps.as_of_date = latest.as_of_date
                WHERE UPPER(pm.asset_id) = ?
                GROUP BY pm.portfolio_id, pm.asset_id
            ),
            valued AS (
                SELECT
                    h.portfolio_id,
                    h.portfolio_name,
                    h.asset_id,
                    h.quantity,
                    h.book_cost,
                    COALESCE(a.symbol, a.asset_id) AS symbol,
                    a.name,
                    a.asset_type,
                    CASE WHEN cdr_underlying.asset_id IS NOT NULL
                        THEN COALESCE(cdr_underlying.sector, a.sector)
                        ELSE a.sector
                    END AS sector,
                    CASE WHEN cdr_underlying.asset_id IS NOT NULL
                        THEN COALESCE(cdr_underlying.industry, a.industry)
                        ELSE a.industry
                    END AS industry,
                    CASE WHEN cdr_underlying.asset_id IS NOT NULL
                        THEN COALESCE(cdr_underlying.country, a.country)
                        ELSE a.country
                    END AS country,
                    a.ccy,
                    COALESCE(bl.broker_account_count, 0) AS broker_account_count,
                    COALESCE(lp.price, bp.price) AS price,
                    COALESCE(h.quantity * lp.price, h.quantity * bp.price, h.book_cost) AS market_value
                FROM holdings h
                JOIN asset a ON a.asset_id = h.asset_id
                {_ENRICHED_ASSET_JOIN}
                LEFT JOIN latest_prices lp ON lp.asset_id = h.asset_id
                LEFT JOIN broker_prices bp
                  ON bp.portfolio_id = h.portfolio_id
                 AND bp.asset_id = h.asset_id
                LEFT JOIN broker_links bl
                  ON bl.portfolio_id = h.portfolio_id
                 AND bl.asset_id = h.asset_id
            )
            SELECT
                portfolio_id,
                portfolio_name,
                asset_id,
                symbol,
                name,
                asset_type,
                sector,
                industry,
                country,
                ccy,
                broker_account_count,
                quantity,
                book_cost,
                price,
                market_value,
                market_value - book_cost
            FROM valued
            ORDER BY portfolio_name, portfolio_id
            """,
            [asset_id, asset_id, asset_id],
        ).fetchall()

        holdings: list[AssetHoldingSummary] = []
        for row in rows:
            classification = _cdr_classification_override(
                asset_id=row[2],
                symbol=row[3],
                name=row[4],
                sector=row[6],
                industry=row[7],
                country=row[8],
            )
            unrealized_gain = _float_or_none(row[15])
            book_cost = float(row[12])
            holdings.append(
                AssetHoldingSummary(
                    portfolio_id=int(row[0]),
                    portfolio_name=row[1],
                    asset_id=row[2],
                    symbol=row[3],
                    name=row[4],
                    asset_type=row[5],
                    sector=classification["sector"],
                    industry=classification["industry"],
                    country=classification["country"],
                    currency=row[9],
                    quantity=float(row[11]),
                    book_cost=book_cost,
                    latest_price=_float_or_none(row[13]),
                    market_value=_float_or_none(row[14]),
                    unrealized_gain=unrealized_gain,
                    total_return_percent=_ratio_or_none(unrealized_gain, book_cost),
                    weight=None,
                    broker_linked=int(row[10]) > 0,
                    broker_account_count=int(row[10]),
                )
            )
        return holdings

    def list_asset_activity(self, asset_id: str, limit: int, offset: int) -> Page[AssetActivitySummary]:
        asset_id = asset_id.upper().strip()
        rows = self.conn.execute(
            """
            SELECT *
            FROM (
                SELECT
                    'broker' AS source,
                    bt.provider,
                    bt.provider_account_id,
                    bt.provider_transaction_id,
                    CAST(NULL AS BIGINT) AS txn_id,
                    ba.portfolio_id,
                    p.portfolio_name,
                    CAST(bt.trade_date AS TIMESTAMP) AS activity_time,
                    bt.txn_type,
                    COALESCE(bt.asset_id, bt.symbol) AS activity_asset_id,
                    COALESCE(bt.symbol, bt.asset_id) AS symbol,
                    bt.quantity,
                    bt.price,
                    bt.currency,
                    bt.amount
                FROM broker_transaction bt
                LEFT JOIN broker_account ba
                  ON ba.provider = bt.provider
                 AND ba.provider_account_id = bt.provider_account_id
                LEFT JOIN portfolio p ON p.portfolio_id = ba.portfolio_id
                WHERE UPPER(COALESCE(bt.asset_id, bt.symbol)) = ?
                UNION ALL
                SELECT
                    'local' AS source,
                    CAST(NULL AS TEXT) AS provider,
                    CAST(NULL AS TEXT) AS provider_account_id,
                    CAST(NULL AS TEXT) AS provider_transaction_id,
                    t.txn_id,
                    t.portfolio_id,
                    p.portfolio_name,
                    t.time_stamp AS activity_time,
                    t.txn_type,
                    t.asset_id AS activity_asset_id,
                    COALESCE(a.symbol, t.asset_id) AS symbol,
                    t.qty,
                    t.price,
                    t.ccy,
                    t.cash_amt
                FROM txn t
                JOIN portfolio p ON p.portfolio_id = t.portfolio_id
                LEFT JOIN asset a ON a.asset_id = t.asset_id
                LEFT JOIN broker_portfolio_txn_map tm ON tm.txn_id = t.txn_id
                WHERE UPPER(t.asset_id) = ?
                  AND tm.txn_id IS NULL
            ) activity
            ORDER BY activity_time DESC, COALESCE(provider_transaction_id, CAST(txn_id AS TEXT)) DESC
            LIMIT ? OFFSET ?
            """,
            [asset_id, asset_id, limit, offset],
        ).fetchall()
        total = int(
            self.conn.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT provider_transaction_id
                    FROM broker_transaction
                    WHERE UPPER(COALESCE(asset_id, symbol)) = ?
                    UNION ALL
                    SELECT CAST(t.txn_id AS TEXT)
                    FROM txn t
                    LEFT JOIN broker_portfolio_txn_map tm ON tm.txn_id = t.txn_id
                    WHERE UPPER(t.asset_id) = ?
                      AND tm.txn_id IS NULL
                ) activity
                """,
                [asset_id, asset_id],
            ).fetchone()[0]
        )
        items = [
            AssetActivitySummary(
                source=row[0],
                provider=row[1],
                provider_account_id=row[2],
                provider_transaction_id=row[3],
                transaction_id=int(row[4]) if row[4] is not None else None,
                portfolio_id=int(row[5]) if row[5] is not None else None,
                portfolio_name=row[6],
                timestamp=row[7],
                transaction_type=row[8],
                asset_id=str(row[9]).upper(),
                symbol=str(row[10]).upper(),
                quantity=_float_or_none(row[11]),
                price=_float_or_none(row[12]),
                currency=row[13],
                cash_amount=_float_or_none(row[14]),
            )
            for row in rows
        ]
        return Page(items=items, total=total, limit=limit, offset=offset)

    def list_transactions(self, portfolio_id: int | None, limit: int, offset: int) -> Page[TransactionSummary]:
        where = ""
        params: list[object] = []
        if portfolio_id is not None:
            self.get_portfolio(portfolio_id)
            where = "WHERE portfolio_id = ?"
            params.append(portfolio_id)
        total = int(
            self.conn.execute(
                f"SELECT COUNT(*) FROM txn {where}",
                params,
            ).fetchone()[0]
        )
        rows = self.conn.execute(
            f"""
            SELECT
                txn_id,
                portfolio_id,
                time_stamp,
                txn_type,
                asset_id,
                qty,
                price,
                ccy,
                cash_amt,
                fee_amt,
                batch_id
            FROM txn
            {where}
            ORDER BY time_stamp DESC, txn_id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        items = [
            TransactionSummary(
                transaction_id=int(row[0]),
                portfolio_id=int(row[1]),
                timestamp=row[2],
                transaction_type=row[3],
                asset_id=row[4],
                quantity=_float_or_none(row[5]),
                price=_float_or_none(row[6]),
                currency=row[7],
                cash_amount=_float_or_none(row[8]),
                fee_amount=_float_or_none(row[9]),
                batch_id=int(row[10]),
            )
            for row in rows
        ]
        return Page(items=items, total=total, limit=limit, offset=offset)

    def analytics(self, portfolio_id: int, benchmark_index_id: str | None = None):
        self.get_portfolio(portfolio_id)
        report = AnalyticsEngine(AnalyticsRepository(self.conn)).portfolio_report(
            portfolio_id=portfolio_id,
            benchmark_index_id=benchmark_index_id,
        )
        return analytics_report_payload(report)

    def overview_updates(self) -> OverviewUpdatesResponse:
        portfolios = self.list_portfolios()
        total_market_value = sum(item.market_value for item in portfolios)
        position_count = sum(item.position_count for item in portfolios)
        mover_rows = self.conn.execute(
            f"""
            WITH portfolio_holdings AS ({_HOLDINGS_SQL}),
            holdings AS (
                SELECT asset_id, SUM(quantity) AS quantity, SUM(book_cost) AS book_cost
                FROM portfolio_holdings
                GROUP BY asset_id
                HAVING SUM(quantity) <> 0
            ),
            ranked_prices AS (
                SELECT
                    asset_id,
                    date,
                    COALESCE(adj_close, close) AS price,
                    ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY date DESC) AS price_rank
                FROM asset_quote_daily
                WHERE COALESCE(adj_close, close) IS NOT NULL
            ),
            latest AS (
                SELECT asset_id, price
                FROM ranked_prices
                WHERE price_rank = 1
            ),
            previous AS (
                SELECT asset_id, price
                FROM ranked_prices
                WHERE price_rank = 2
            ),
            valued AS (
                SELECT
                    h.asset_id,
                    COALESCE(a.symbol, h.asset_id) AS symbol,
                    a.name,
                    l.price AS latest_price,
                    p.price AS previous_price,
                    l.price - p.price AS price_change,
                    CASE WHEN p.price IS NULL OR p.price = 0 THEN NULL ELSE (l.price - p.price) / p.price END AS change_percent,
                    COALESCE(h.quantity * l.price, h.book_cost) AS market_value
                FROM holdings h
                JOIN asset a ON a.asset_id = h.asset_id
                JOIN latest l ON l.asset_id = h.asset_id
                JOIN previous p ON p.asset_id = h.asset_id
            )
            SELECT
                asset_id,
                symbol,
                name,
                latest_price,
                previous_price,
                price_change,
                change_percent,
                market_value
            FROM valued
            ORDER BY ABS(COALESCE(change_percent, 0)) DESC, market_value DESC NULLS LAST
            LIMIT 8
            """
        ).fetchall()
        news_rows = self.conn.execute(
            """
            SELECT
                a.title,
                a.provider,
                a.published_at,
                a.url,
                m.asset_id,
                COALESCE(asset.symbol, m.ticker),
                NULL AS sentiment
            FROM news_article a
            LEFT JOIN news_article_asset_mention m ON m.article_id = a.article_id
            LEFT JOIN asset ON asset.asset_id = m.asset_id
            ORDER BY a.published_at DESC NULLS LAST, a.article_id DESC
            LIMIT 8
            """
        ).fetchall()
        return OverviewUpdatesResponse(
            total_market_value=total_market_value,
            position_count=position_count,
            mover_count=len(mover_rows),
            news_count=len(news_rows),
            price_movers=[
                PriceMoverResponse(
                    asset_id=row[0],
                    symbol=row[1],
                    name=row[2],
                    latest_price=_float_or_none(row[3]),
                    previous_price=_float_or_none(row[4]),
                    change=_float_or_none(row[5]),
                    change_percent=_float_or_none(row[6]),
                    market_value=_float_or_none(row[7]),
                    weight=(float(row[7]) / total_market_value) if total_market_value else None,
                )
                for row in mover_rows
            ],
            news=[
                NewsItemResponse(
                    title=row[0],
                    provider=row[1],
                    published_at=row[2],
                    url=row[3],
                    asset_id=row[4],
                    symbol=row[5],
                    sentiment=row[6],
                )
                for row in news_rows
            ],
        )

    def _portfolio_summary(self, row) -> PortfolioSummary:
        market_value = float(row[6])
        book_cost = float(row[7])
        projection = self._portfolio_projection(int(row[0]))
        return PortfolioSummary(
            portfolio_id=int(row[0]),
            name=row[1],
            base_ccy=row[2],
            created_at=row[3],
            updated_at=row[4],
            position_count=int(row[5]),
            market_value=market_value,
            book_cost=book_cost,
            unrealized_gain=market_value - book_cost if market_value else None,
            projected_value=projection.get("projected_value"),
            projected_value_low=projection.get("projected_value_low"),
            projected_value_high=projection.get("projected_value_high"),
            projected_horizon_years=projection.get("projected_horizon_years"),
        )

    def _portfolio_projection(self, portfolio_id: int) -> dict[str, float | int | None]:
        try:
            report = AnalyticsEngine(AnalyticsRepository(self.conn)).portfolio_report(portfolio_id)
        except Exception:
            return {}
        simulation = report.forecast.simulation
        if simulation is None:
            return {}
        return {
            "projected_value": _float_or_none(simulation.p50_value)
            or _float_or_none(simulation.expected_value),
            "projected_value_low": _float_or_none(simulation.p10_value),
            "projected_value_high": _float_or_none(simulation.p90_value),
            "projected_horizon_years": simulation.horizon_years,
        }


class AssetApiService:
    def __init__(self, conn) -> None:
        self.conn = conn

    def get_asset(self, asset_id: str) -> AssetDetail:
        asset_id = asset_id.upper().strip()
        row = self.conn.execute(
            """
            SELECT
                {_ENRICHED_ASSET_SELECT},
                (
                    SELECT COALESCE(q.adj_close, q.close)
                    FROM asset_quote_daily q
                    WHERE q.asset_id = a.asset_id
                    ORDER BY q.date DESC
                    LIMIT 1
                )
            FROM asset a
            {_ENRICHED_ASSET_JOIN}
            WHERE a.asset_id = ?
            """.format(
                _ENRICHED_ASSET_SELECT=_ENRICHED_ASSET_SELECT,
                _ENRICHED_ASSET_JOIN=_ENRICHED_ASSET_JOIN,
            ),
            [asset_id],
        ).fetchone()
        if row is None:
            fallback = _known_underlying_asset_detail(asset_id)
            if fallback is not None:
                return fallback
            raise LookupError(f"Asset not found: {asset_id}")
        classification = _cdr_classification_override(
            asset_id=row[0],
            symbol=row[1],
            name=row[6],
            sector=row[8],
            industry=row[9],
            country=row[10],
        )
        underlying_asset_id = _cdr_underlying_asset_id(row[0], row[1], row[6])
        return AssetDetail(
            asset_id=row[0],
            symbol=row[1],
            is_cdr=underlying_asset_id is not None,
            underlying_asset_id=underlying_asset_id,
            exchange_code=row[2],
            asset_type=row[3],
            asset_subtype=row[4],
            currency=row[5],
            name=row[6],
            description=row[7],
            sector=classification["sector"],
            industry=classification["industry"],
            country=classification["country"],
            region=row[11],
            size=row[12],
            market_cap=_float_or_none(row[13]),
            shares_outstanding=_float_or_none(row[14]),
            market_beta=_float_or_none(row[15]),
            latest_price=_float_or_none(row[16]),
        )

    def price_history(self, asset_id: str, limit: int) -> list[PricePointResponse]:
        self.get_asset(asset_id)
        rows = self.conn.execute(
            """
            SELECT date, COALESCE(adj_close, close)
            FROM (
                SELECT date, adj_close, close
                FROM asset_quote_daily
                WHERE asset_id = ?
                  AND COALESCE(adj_close, close) IS NOT NULL
                ORDER BY date DESC
                LIMIT ?
            )
            ORDER BY date
            """,
            [asset_id.upper().strip(), limit],
        ).fetchall()
        return [PricePointResponse(date=row[0], close=float(row[1])) for row in rows]

    def analytics(self, asset_id: str, benchmark_index_id: str | None = None):
        asset = self.get_asset(asset_id)
        report = AnalyticsEngine(AnalyticsRepository(self.conn)).asset_report(
            asset_id=asset.asset_id,
            benchmark_index_id=benchmark_index_id,
        )
        return analytics_report_payload(report)


class ComparisonApiService:
    def __init__(self, conn) -> None:
        self.conn = conn

    def compare(
        self,
        left_asset_id: str,
        right_asset_id: str | None = None,
        benchmark_index_id: str | None = None,
    ) -> ComparisonResponse:
        left = self.asset_profile(left_asset_id)
        right = self.asset_profile(right_asset_id) if right_asset_id else None
        benchmark = self.benchmark_profile(benchmark_index_id) if benchmark_index_id else None
        return ComparisonResponse(
            left=left,
            right=right,
            benchmark=benchmark,
            insights=self._insights(left, right, benchmark),
        )

    def asset_profile(self, asset_id: str) -> ComparisonAssetProfile:
        asset = AssetApiService(self.conn).get_asset(asset_id)
        prices = self._prices(asset.asset_id)
        latest_price = prices[0][1] if prices else asset.latest_price
        statements = self._income_statements(asset.asset_id)
        latest_statement = statements[0] if statements else {}
        eps = _first_number(latest_statement, "eps", "epsdiluted", "dilutedEPS", "eps_actual")
        revenue = _first_number(latest_statement, "revenue", "totalRevenue", "revenue_actual")
        net_income = _first_number(latest_statement, "netIncome", "net_income", "netIncomeCommonStockholders")
        pe_ratio = latest_price / eps if latest_price is not None and eps and eps > 0 else None
        price_to_sales = (
            asset.market_cap / revenue
            if asset.market_cap is not None and revenue is not None and revenue > 0
            else None
        )
        valuation = self._valuation_context(asset.asset_id, asset.sector, asset.industry, pe_ratio)
        return ComparisonAssetProfile(
            asset_id=asset.asset_id,
            symbol=asset.symbol,
            name=asset.name,
            sector=asset.sector,
            industry=asset.industry,
            country=asset.country,
            currency=asset.currency,
            latest_price=latest_price,
            market_cap=asset.market_cap,
            market_beta=asset.market_beta,
            returns=ComparisonReturns(
                return_1d=_period_return(prices, 1),
                return_5d=_period_return(prices, 5),
                return_21d=_period_return(prices, 21),
                return_252d=_period_return(prices, 252),
            ),
            fundamentals=ComparisonFundamentals(
                revenue=revenue,
                net_income=net_income,
                eps=eps,
                pe_ratio=pe_ratio,
                price_to_sales=price_to_sales,
            ),
            valuation=valuation,
        )

    def benchmark_profile(self, index_id: str) -> BenchmarkComparisonProfile:
        row = self.conn.execute(
            """
            SELECT
                b.index_id,
                b.index_name,
                b.index_category,
                b.currency,
                m.return_1d,
                m.return_21d,
                m.return_252d,
                m.volatility_252d_ann
            FROM benchmark_index b
            LEFT JOIN benchmark_index_daily_metric m ON m.index_id = b.index_id
            WHERE UPPER(b.index_id) = UPPER(?)
            QUALIFY ROW_NUMBER() OVER (PARTITION BY b.index_id ORDER BY m.metric_date DESC NULLS LAST) = 1
            """,
            [index_id.strip()],
        ).fetchone()
        if row is None:
            raise LookupError(f"Benchmark not found: {index_id}")
        return BenchmarkComparisonProfile(
            index_id=row[0],
            name=row[1],
            category=row[2],
            currency=row[3],
            return_1d=_float_or_none(row[4]),
            return_21d=_float_or_none(row[5]),
            return_252d=_float_or_none(row[6]),
            volatility_252d=_float_or_none(row[7]),
        )

    def _prices(self, asset_id: str) -> list[tuple[Any, float]]:
        rows = self.conn.execute(
            """
            SELECT date, COALESCE(adj_close, close)
            FROM asset_quote_daily
            WHERE asset_id = ?
              AND COALESCE(adj_close, close) IS NOT NULL
            ORDER BY date DESC
            LIMIT 260
            """,
            [asset_id],
        ).fetchall()
        return [(row[0], float(row[1])) for row in rows]

    def _income_statements(self, asset_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT period_end_date, data_json
            FROM financial_statement
            WHERE asset_id = ?
              AND statement_type = 'income'
            ORDER BY period_end_date DESC NULLS LAST, year DESC, quarter DESC
            """,
            [asset_id],
        ).fetchall()
        statements: list[dict[str, Any]] = []
        for period_end, payload in rows:
            data = _json_dict(payload)
            if data:
                data["_period_end_date"] = period_end
                statements.append(data)
        return statements

    def _valuation_context(
        self,
        asset_id: str,
        sector: str | None,
        industry: str | None,
        current_pe: float | None,
    ) -> ValuationContext:
        historical_average = self._historical_pe_average(asset_id)
        sector_average = self._peer_pe_average(asset_id, "sector", sector)
        industry_average = self._peer_pe_average(asset_id, "industry", industry)
        return ValuationContext(
            historical_pe_average=historical_average,
            historical_pe_discount=_relative_gap(current_pe, historical_average),
            sector_pe_average=sector_average,
            sector_pe_premium=_relative_gap(current_pe, sector_average),
            industry_pe_average=industry_average,
            industry_pe_premium=_relative_gap(current_pe, industry_average),
        )

    def _historical_pe_average(self, asset_id: str) -> float | None:
        values: list[float] = []
        for statement in self._income_statements(asset_id):
            eps = _first_number(statement, "eps", "epsdiluted", "dilutedEPS", "eps_actual")
            period_end = statement.get("_period_end_date")
            if eps is None or eps <= 0 or period_end is None:
                continue
            price_row = self.conn.execute(
                """
                SELECT COALESCE(adj_close, close)
                FROM asset_quote_daily
                WHERE asset_id = ?
                  AND date <= ?
                  AND COALESCE(adj_close, close) IS NOT NULL
                ORDER BY date DESC
                LIMIT 1
                """,
                [asset_id, period_end],
            ).fetchone()
            if price_row:
                values.append(float(price_row[0]) / eps)
        return sum(values) / len(values) if values else None

    def _peer_pe_average(self, asset_id: str, field: str, value: str | None) -> float | None:
        if not value:
            return None
        rows = self.conn.execute(
            f"""
            SELECT a.asset_id
            FROM asset a
            WHERE a.{field} = ?
              AND a.asset_id <> ?
            ORDER BY a.asset_id
            """,
            [value, asset_id],
        ).fetchall()
        ratios = [ratio for ratio in (self._current_pe(row[0]) for row in rows) if ratio is not None]
        return sum(ratios) / len(ratios) if ratios else None

    def _current_pe(self, asset_id: str) -> float | None:
        prices = self._prices(asset_id)
        latest_price = prices[0][1] if prices else None
        statements = self._income_statements(asset_id)
        eps = _first_number(statements[0], "eps", "epsdiluted", "dilutedEPS", "eps_actual") if statements else None
        return latest_price / eps if latest_price is not None and eps and eps > 0 else None

    def _insights(
        self,
        left: ComparisonAssetProfile,
        right: ComparisonAssetProfile | None,
        benchmark: BenchmarkComparisonProfile | None,
    ) -> list[str]:
        insights: list[str] = []
        discount = left.valuation.historical_pe_discount
        if discount is not None:
            direction = "below" if discount < 0 else "above"
            insights.append(f"{left.symbol} trades {abs(discount) * 100:.1f}% {direction} its historical P/E average.")
        sector_gap = left.valuation.sector_pe_premium
        if sector_gap is not None and left.sector:
            direction = "above" if sector_gap > 0 else "below"
            insights.append(f"{left.symbol} trades {abs(sector_gap) * 100:.1f}% {direction} the {left.sector} peer average.")
        if right and left.returns.return_21d is not None and right.returns.return_21d is not None:
            gap = left.returns.return_21d - right.returns.return_21d
            direction = "outperformed" if gap >= 0 else "underperformed"
            insights.append(f"{left.symbol} {direction} {right.symbol} by {abs(gap) * 100:.1f}% over 21 trading days.")
        if benchmark and left.returns.return_252d is not None and benchmark.return_252d is not None:
            gap = left.returns.return_252d - benchmark.return_252d
            direction = "beat" if gap >= 0 else "lagged"
            insights.append(f"{left.symbol} {direction} {benchmark.index_id} by {abs(gap) * 100:.1f}% over 252 trading days.")
        return insights


class CommandApiService(BrokerCommands, IngestionCommands):
    """Reuse command orchestration without coupling HTTP routes to the CLI manager."""

    def __init__(self, conn) -> None:
        self.conn = conn

    def broker_connections(self) -> list[BrokerConnectionResponse]:
        return [
            BrokerConnectionResponse(
                provider=item.provider,
                connection_id=item.connection_id,
                provider_connection_id=item.provider_connection_id,
                institution_name=item.institution_name,
                status=item.status,
            )
            for item in BrokerSyncRepository(self.conn).list_connections()
        ]

    def broker_account_responses(self) -> list[BrokerAccountResponse]:
        position_values = self._broker_account_position_values()
        responses: list[BrokerAccountResponse] = []
        for item in self.broker_accounts():
            if not _is_visible_broker_account(item.raw_payload):
                continue
            position_value, position_currency = position_values.get(
                item.provider_account_id,
                (None, None),
            )
            currency = item.currency or _currency_from_raw_account(item.raw_payload) or position_currency
            responses.append(
                BrokerAccountResponse(
                    provider=item.provider,
                    provider_account_id=item.provider_account_id,
                    provider_connection_id=item.provider_connection_id,
                    account_name=item.account_name,
                    account_type=item.account_type,
                    currency=_valid_currency(currency),
                    balance=self._account_display_balance(
                        item.balance,
                        position_value,
                    ),
                    portfolio_id=item.portfolio_id,
                )
            )
        return responses

    def _broker_account_position_values(self) -> dict[str, tuple[float | None, str | None]]:
        rows = self.conn.execute(
            """
            WITH latest_positions AS (
                SELECT
                    provider,
                    provider_account_id,
                    provider_position_id,
                    MAX(as_of_date) AS as_of_date
                FROM broker_position_snapshot
                GROUP BY provider, provider_account_id, provider_position_id
            )
            SELECT
                p.provider_account_id,
                SUM(p.market_value) FILTER (WHERE p.market_value IS NOT NULL) AS market_value,
                MAX(p.currency) FILTER (WHERE p.currency IS NOT NULL) AS currency
            FROM broker_position_snapshot p
            JOIN latest_positions latest
              ON latest.provider = p.provider
             AND latest.provider_account_id = p.provider_account_id
             AND latest.provider_position_id = p.provider_position_id
             AND latest.as_of_date = p.as_of_date
            WHERE p.provider = ?
            GROUP BY p.provider_account_id
            """,
            [SNAPTRADE_PROVIDER],
        ).fetchall()
        return {row[0]: (_float_or_none(row[1]), row[2]) for row in rows}

    @staticmethod
    def _account_display_balance(
        account_balance: float | None,
        position_value: float | None,
    ) -> float | None:
        if position_value is not None and (account_balance is None or account_balance == 0):
            return position_value
        return account_balance

    def register_broker_user(self, user_key: str) -> BrokerUserResponse:
        user = self.broker_register_snaptrade_user(user_key)
        return BrokerUserResponse(
            provider=user.provider,
            user_key=user.user_key,
            provider_user_id=user.provider_user_id,
            status=user.status,
        )

    def save_existing_broker_user(
        self,
        user_key: str,
        provider_user_id: str,
        user_secret: str,
    ) -> BrokerUserResponse:
        user = BrokerUser(
            provider=SNAPTRADE_PROVIDER,
            user_key=user_key.strip(),
            provider_user_id=provider_user_id.strip(),
            user_secret=user_secret.strip(),
            status="active",
        )
        if not user.user_key or not user.provider_user_id or not user.user_secret:
            raise ValueError("User key, provider user ID, and user secret are required.")
        repo, cipher = self._broker_repo_and_cipher()
        repo.upsert_broker_user(user, cipher)
        return BrokerUserResponse(
            provider=user.provider,
            user_key=user.user_key,
            provider_user_id=user.provider_user_id,
            status=user.status,
        )

    def ingestion_jobs(self, status: str | None, domain: str | None, limit: int):
        statuses = [status] if status else None
        rows = self.list_ingestion_jobs(statuses=statuses, domain=domain, limit=limit)
        return [
            IngestionJobResponse(
                job_id=int(row[0]),
                asset_id=row[1],
                domain=row[2],
                job_type=row[3],
                dataset=row[4],
                status=row[5],
                priority=int(row[6]),
                requested_start_date=row[7],
                requested_end_date=row[8],
                attempt_count=int(row[9]),
                error_message=row[10],
                created_at=row[11],
                updated_at=row[12],
            )
            for row in rows
        ]

    def retry_failed_ingestion_jobs(self, domain: str | None, max_jobs: int) -> int:
        where = ["status = 'failed'"]
        params: list[object] = []
        if domain:
            where.append("domain = ?")
            params.append(domain)
        params.append(max_jobs)
        rows = self.conn.execute(
            f"""
            UPDATE ingestion_job
            SET
                status = 'pending',
                error_message = NULL,
                updated_at = now()
            WHERE job_id IN (
                SELECT job_id
                FROM ingestion_job
                WHERE {" AND ".join(where)}
                ORDER BY updated_at ASC, job_id ASC
                LIMIT ?
            )
            RETURNING job_id
            """,
            params,
        ).fetchall()
        return len(rows)

    @staticmethod
    def action_result(value) -> dict:
        if hasattr(value, "__dataclass_fields__"):
            return asdict(value)
        if isinstance(value, dict):
            return value
        return {"count": value} if isinstance(value, int) else {"value": value}


def _float_or_none(value) -> float | None:
    return float(value) if value is not None else None


def _ratio_or_none(numerator, denominator) -> float | None:
    numerator = _float_or_none(numerator)
    denominator = _float_or_none(denominator)
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _cdr_classification_override(
    *,
    asset_id: str,
    symbol: str,
    name: str | None,
    sector: str | None,
    industry: str | None,
    country: str | None,
) -> dict[str, str | None]:
    base_symbol = _cdr_base_symbol(asset_id, symbol, name)
    override = _CDR_CLASSIFICATION_OVERRIDES.get(base_symbol)
    if not override:
        return {"sector": sector, "industry": industry, "country": country}
    return {
        "sector": sector or override["sector"],
        "industry": industry or override["industry"],
        "country": override["country"] if country is None or country.upper() == "CA" else country,
    }


def _cdr_base_symbol(asset_id: str, symbol: str, name: str | None) -> str:
    candidate = symbol or asset_id
    base = candidate.split(".", maxsplit=1)[0].upper()
    base = _CDR_SYMBOL_ALIASES.get(base, base)
    if base in _CDR_CLASSIFICATION_OVERRIDES and _looks_like_cdr_listing(asset_id, symbol, name):
        return base
    text = f"{asset_id} {symbol} {name or ''}".lower()
    if "cdr" not in text and "depositary receipt" not in text:
        return ""
    return base


def _looks_like_cdr_listing(asset_id: str, symbol: str, name: str | None) -> bool:
    text = f"{asset_id} {symbol} {name or ''}".lower()
    if "cdr" in text or "depositary receipt" in text or "depository receipt" in text:
        return True
    return (symbol or asset_id).upper().endswith(".TO")


def _cdr_underlying_asset_id(asset_id: str, symbol: str, name: str | None) -> str | None:
    base_symbol = _cdr_base_symbol(asset_id, symbol, name)
    return base_symbol or None


def _known_underlying_asset_detail(asset_id: str) -> AssetDetail | None:
    classification = _CDR_CLASSIFICATION_OVERRIDES.get(asset_id)
    if classification is None:
        return None
    return AssetDetail(
        asset_id=asset_id,
        symbol=asset_id,
        is_cdr=False,
        underlying_asset_id=None,
        exchange_code=None,
        asset_type="stock",
        asset_subtype=None,
        currency="USD",
        name=_KNOWN_CDR_UNDERLYING_NAMES.get(asset_id),
        description=None,
        sector=classification["sector"],
        industry=classification["industry"],
        country=classification["country"],
        region=None,
        size=None,
        market_cap=None,
        shares_outstanding=None,
        market_beta=None,
        latest_price=None,
    )


def _json_dict(value) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _first_number(values: dict[str, Any], *keys: str) -> float | None:
    lower_values = {key.lower(): value for key, value in values.items()}
    for key in keys:
        value = values.get(key)
        if value is None:
            value = lower_values.get(key.lower())
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            continue
    return None


def _period_return(prices: list[tuple[Any, float]], periods: int) -> float | None:
    if len(prices) <= periods:
        return None
    latest = prices[0][1]
    previous = prices[periods][1]
    if previous == 0:
        return None
    return latest / previous - 1


def _relative_gap(value: float | None, comparison: float | None) -> float | None:
    if value is None or comparison is None or comparison == 0:
        return None
    return value / comparison - 1


def _currency_from_raw_account(raw_payload: dict) -> str | None:
    balance = raw_payload.get("balance")
    if not isinstance(balance, dict):
        return None
    total = balance.get("total")
    if isinstance(total, dict):
        currency = total.get("currency")
        if currency:
            return str(currency)
    currency = balance.get("currency")
    return str(currency) if currency else None


def _is_visible_broker_account(raw_payload: dict) -> bool:
    status = str(raw_payload.get("status", "")).strip().lower()
    if status in {"archived", "closed", "disabled", "inactive"}:
        return False
    if raw_payload.get("closed") is True or raw_payload.get("disabled") is True:
        return False
    return True


def _valid_currency(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text if len(text) == 3 and text.isalpha() else None
