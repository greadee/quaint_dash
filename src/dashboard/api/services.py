"""Application-facing read and write services for the HTTP API."""

from dataclasses import asdict
from datetime import date, timedelta
import json
import re
import statistics
from typing import Any

from dashboard.api.models import (
    AssetDetail,
    AssetActivitySummary,
    AssetHoldingSummary,
    AssetBenchmarkAssociationResponse,
    AssetSearchResult,
    BenchmarkAssociation,
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
    BenchmarkReadinessItem,
    BenchmarkReadinessRequirement,
    BenchmarkReadinessResponse,
    BenchmarkSymbol,
    BenchmarkSyncState,
    ComparisonAssetProfile,
    ComparisonFundamentals,
    ComparisonResponse,
    ComparisonReturns,
    SectorComparisonContext,
    SectorComparisonValues,
    HoldingSignalComponent,
    HoldingSignalResponse,
    HoldingSignalsResponse,
    IngestionJobResponse,
    IngestionAssetReadiness,
    NewsItemResponse,
    OverviewUpdatesResponse,
    Page,
    PortfolioCreate,
    PortfolioSummary,
    PortfolioUpdate,
    PositionSummary,
    PricePointResponse,
    PriceMoverResponse,
    IngestionRequirementStatus,
    StockRankingComponent,
    StockRankingItem,
    StockRankingReadinessItem,
    StockRankingReadinessResponse,
    StockRankingSnapshotRefreshResponse,
    StockRankingsResponse,
    TransactionSummary,
    ValuationContext,
    WatchlistAssetResponse,
)
from dashboard.analytics import AnalyticsEngine, AnalyticsRepository, analytics_report_payload
from dashboard.analytics.models import (
    DEFAULT_BENCHMARK_BY_COUNTRY,
    DEFAULT_BENCHMARK_BY_CURRENCY,
    PositionAnalytics,
)
from dashboard.brokers.repository import BrokerSyncRepository
from dashboard.brokers.models import BrokerUser
from dashboard.brokers.snaptrade import SNAPTRADE_PROVIDER
from dashboard.ingestion.indices.index_service_factory import (
    create_index_ingestion_service,
    create_index_scheduler,
)
from dashboard.ingestion.ticker_universe import TickerUniverseRepository
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
        FROM broker_portfolio_position_map mapped_positions
        WHERE mapped_positions.portfolio_id = txn.portfolio_id
      )
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

_SIGNAL_TIMEFRAME_PERIODS = {
    "1d": 1,
    "1w": 5,
    "1m": 21,
    "1y": 252,
}
_SIGNAL_TIMEFRAME_LABELS = {
    "1d": "1 day",
    "1w": "1 week",
    "1m": "1 month",
    "1y": "1 year",
}
_STOCK_RANKING_FACTORS = {
    "aggregate",
    "share_price_momentum",
    "news_sentiment",
    "retail_sentiment",
    "earnings_momentum",
    "institutional_buying",
}
_STOCK_RANKING_LABELS = {
    "aggregate": "Aggregate",
    "share_price_momentum": "Share price momentum",
    "news_sentiment": "News sentiment",
    "retail_sentiment": "Retail sentiment",
    "earnings_momentum": "Earnings momentum",
    "institutional_buying": "Institutional buying",
}


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
                "LOWER(b.index_family) LIKE ? OR LOWER(COALESCE(b.notes, '')) LIKE ? OR "
                "EXISTS ("
                "SELECT 1 FROM benchmark_index_symbol sym "
                "WHERE sym.index_id = b.index_id "
                "AND (LOWER(sym.provider_symbol) LIKE ? OR LOWER(sym.provider) LIKE ? OR LOWER(sym.symbol_purpose) LIKE ?)"
                ")"
                ")"
            )
            params.extend([like, like, like, like, like, like, like])
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

    def readiness(
        self,
        *,
        index_id: str | None = None,
        category: str | None = None,
    ) -> BenchmarkReadinessResponse:
        where = ["b.is_active = TRUE"]
        params: list[Any] = []
        if index_id:
            where.append("UPPER(b.index_id) = UPPER(?)")
            params.append(index_id)
        elif category and category != "all":
            if category == "non_core":
                where.append("b.index_category IN ('sector', 'industry', 'theme')")
            else:
                where.append("b.index_category = ?")
                params.append(category)
        rows = self.conn.execute(
            f"""
            SELECT b.index_id, b.index_name, b.index_category
            FROM benchmark_index b
            WHERE {" AND ".join(where)}
            ORDER BY b.is_core DESC, b.index_category, b.index_id
            """,
            params,
        ).fetchall()
        items = [self._readiness_item(row[0], row[1], row[2]) for row in rows]
        return BenchmarkReadinessResponse(
            items=items,
            total=len(items),
            ready_count=sum(1 for item in items if item.ready),
        )

    def _readiness_item(
        self,
        index_id: str,
        index_name: str,
        index_category: str,
    ) -> BenchmarkReadinessItem:
        requirements = [
            self._benchmark_price_requirement(index_id),
            self._benchmark_metric_requirement(index_id),
            self._benchmark_composition_requirement(index_id),
            self._benchmark_constituent_requirement(index_id),
            self._benchmark_exposure_requirement(index_id),
        ]
        missing = [requirement.label for requirement in requirements if not requirement.ready]
        return BenchmarkReadinessItem(
            index_id=index_id,
            index_name=index_name,
            index_category=index_category,
            ready=not missing,
            missing=missing,
            requirements=requirements,
        )

    def _benchmark_price_requirement(self, index_id: str) -> BenchmarkReadinessRequirement:
        row = self.conn.execute(
            """
            SELECT COUNT(*), MAX(price_date)
            FROM benchmark_index_daily_price
            WHERE index_id = ?
            """,
            [index_id],
        ).fetchone()
        count = int(row[0])
        return BenchmarkReadinessRequirement(
            key="daily_prices",
            label="252 daily prices",
            ready=count >= 252,
            detail=f"{count} daily price row(s)",
            row_count=count,
            latest_date=row[1],
        )

    def _benchmark_metric_requirement(self, index_id: str) -> BenchmarkReadinessRequirement:
        row = self.conn.execute(
            """
            SELECT COUNT(*), MAX(metric_date)
            FROM benchmark_index_daily_metric
            WHERE index_id = ?
              AND return_252d IS NOT NULL
              AND volatility_252d_ann IS NOT NULL
            """,
            [index_id],
        ).fetchone()
        count = int(row[0])
        return BenchmarkReadinessRequirement(
            key="daily_metrics",
            label="252d return and volatility",
            ready=count > 0,
            detail=f"{count} complete 252d metric row(s)",
            row_count=count,
            latest_date=row[1],
        )

    def _benchmark_composition_requirement(self, index_id: str) -> BenchmarkReadinessRequirement:
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(constituent_count), 0), MAX(snapshot_date)
            FROM benchmark_index_composition_snapshot
            WHERE index_id = ?
            """,
            [index_id],
        ).fetchone()
        count = int(row[0] or 0)
        return BenchmarkReadinessRequirement(
            key="composition",
            label="Composition snapshot",
            ready=count > 0,
            detail=f"{count} constituent(s) reported by composition snapshot",
            row_count=count,
            latest_date=row[1],
        )

    def _benchmark_constituent_requirement(self, index_id: str) -> BenchmarkReadinessRequirement:
        snap_date = self._latest_snapshot_date(index_id)
        count = 0
        if snap_date is not None:
            count = int(
                self.conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM benchmark_index_constituent
                    WHERE index_id = ? AND snapshot_date = ?
                    """,
                    [index_id, snap_date],
                ).fetchone()[0]
            )
        return BenchmarkReadinessRequirement(
            key="constituents",
            label="Constituent rows",
            ready=count > 0,
            detail=f"{count} constituent row(s) in latest snapshot",
            row_count=count,
            latest_date=snap_date,
        )

    def _benchmark_exposure_requirement(self, index_id: str) -> BenchmarkReadinessRequirement:
        snap_date = self._latest_exposure_snapshot_date(index_id)
        count = 0
        if snap_date is not None:
            count = int(
                self.conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM benchmark_index_exposure_snapshot
                    WHERE index_id = ?
                      AND snapshot_date = ?
                      AND dimension_type IN ('sector', 'industry', 'country', 'currency')
                    """,
                    [index_id, snap_date],
                ).fetchone()[0]
            )
        return BenchmarkReadinessRequirement(
            key="exposures",
            label="Exposure rows",
            ready=count > 0,
            detail=f"{count} exposure row(s) in latest snapshot",
            row_count=count,
            latest_date=snap_date,
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

    def associations_for_asset(self, asset_id: str) -> AssetBenchmarkAssociationResponse:
        asset = AssetApiService(self.conn).get_asset(asset_id)
        asset_result = AssetApiService(self.conn)._asset_search_result(asset)
        suggestions: list[tuple[str, str | None, str, float]] = [
            (
                "core",
                AnalyticsRepository(self.conn).default_benchmark_for_asset(asset.asset_id)
                or _core_benchmark_candidate(asset.country, asset.currency),
                "country/currency default",
                0.85,
            ),
            (
                "sector",
                _sector_benchmark_candidate(asset.sector),
                f"sector match: {asset.sector}",
                0.75,
            ),
            (
                "industry",
                _industry_benchmark_candidate(asset.industry),
                f"industry match: {asset.industry}",
                0.7,
            ),
        ]
        associations: list[BenchmarkAssociation] = []
        seen: set[str] = set()
        for role, candidate, reason, confidence in suggestions:
            if not candidate or candidate in seen:
                continue
            summary = self._active_summary(candidate)
            if summary is None:
                continue
            seen.add(candidate)
            associations.append(
                BenchmarkAssociation(
                    role=role,
                    benchmark_index_id=summary.index_id,
                    index_name=summary.index_name,
                    index_category=summary.index_category,
                    reason=reason,
                    confidence=confidence,
                )
            )
        return AssetBenchmarkAssociationResponse(asset=asset_result, associations=associations)

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

    def harden_benchmark(
        self,
        *,
        index_id: str,
        lookback_days: int = 730,
        include_composition: bool = True,
        include_relative_metrics: bool = True,
        comparison_index_id: str = "SP500",
    ) -> dict[str, Any]:
        service = create_index_ingestion_service(self.conn)
        service.seed_all_universes()
        self._require_benchmark(index_id)
        end = date.today()
        start = end - timedelta(days=lookback_days)
        daily_price_rows = service.ingest_daily_prices(index_id, start, end)
        metric_rows = service.compute_daily_metrics(index_id)
        composition_rows = 0
        if include_composition:
            composition_rows = service.ingest_composition(index_id, end)
        relative_metric_rows = 0
        if include_relative_metrics and index_id.upper() != comparison_index_id.upper():
            relative_metric_rows = service.compute_relative_metrics(index_id, comparison_index_id)
        readiness = self.readiness(index_id=index_id)
        ready = readiness.ready_count == readiness.total and readiness.total > 0
        return {
            "index_id": index_id,
            "job_type": "benchmark_harden",
            "target_count": 1,
            "daily_price_rows": daily_price_rows,
            "metric_rows": metric_rows,
            "composition_rows": composition_rows,
            "relative_metric_rows": relative_metric_rows,
            "ready": ready,
            "missing": readiness.items[0].missing if readiness.items else ["Benchmark not found"],
        }

    def harden_benchmarks(
        self,
        *,
        category: str = "all",
        lookback_days: int = 730,
        include_composition: bool = True,
        include_relative_metrics: bool = True,
        comparison_index_id: str = "SP500",
    ) -> dict[str, Any]:
        service = create_index_ingestion_service(self.conn)
        service.seed_all_universes()
        index_ids = self._benchmark_ids_for_hardening(category)
        totals = {
            "daily_price_rows": 0,
            "metric_rows": 0,
            "composition_rows": 0,
            "relative_metric_rows": 0,
        }
        end = date.today()
        start = end - timedelta(days=lookback_days)
        for current_id in index_ids:
            totals["daily_price_rows"] += service.ingest_daily_prices(current_id, start, end)
            totals["metric_rows"] += service.compute_daily_metrics(current_id)
            if include_composition:
                try:
                    totals["composition_rows"] += service.ingest_composition(current_id, end)
                except ValueError:
                    pass
            if include_relative_metrics and current_id.upper() != comparison_index_id.upper():
                totals["relative_metric_rows"] += service.compute_relative_metrics(current_id, comparison_index_id)
        readiness = self.readiness(category=category)
        return {
            "category": category,
            "job_type": "benchmark_bulk_harden",
            "target_count": len(index_ids),
            **totals,
            "ready_count": readiness.ready_count,
            "missing_count": readiness.total - readiness.ready_count,
        }

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

    def _active_summary(self, index_id: str) -> BenchmarkIndexSummary | None:
        summary = self._get_summary(index_id)
        return summary if summary and summary.is_active else None

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

    def _benchmark_ids_for_hardening(self, category: str) -> list[str]:
        if category == "all":
            where = "is_active = TRUE"
            params: list[Any] = []
        elif category == "non_core":
            where = "is_active = TRUE AND index_category IN ('sector', 'industry', 'theme')"
            params = []
        else:
            where = "is_active = TRUE AND index_category = ?"
            params = [category]
        return [
            row[0]
            for row in self.conn.execute(
                f"""
                SELECT index_id
                FROM benchmark_index
                WHERE {where}
                ORDER BY is_core DESC, index_category, index_id
                """,
                params,
            ).fetchall()
        ]


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

_SECTOR_BENCHMARK_BY_KEY = {
    "communication services": "SEC_COMM",
    "communications": "SEC_COMM",
    "consumer cyclical": "SEC_CONS_DISC",
    "consumer discretionary": "SEC_CONS_DISC",
    "consumer defensive": "SEC_CONS_STAP",
    "consumer staples": "SEC_CONS_STAP",
    "energy": "SEC_ENERGY",
    "financial services": "SEC_FINANCIALS",
    "financials": "SEC_FINANCIALS",
    "health care": "SEC_HEALTHCARE",
    "healthcare": "SEC_HEALTHCARE",
    "industrials": "SEC_INDUSTRIALS",
    "industrial": "SEC_INDUSTRIALS",
    "information technology": "SEC_TECH",
    "technology": "SEC_TECH",
    "basic materials": "SEC_MATERIALS",
    "materials": "SEC_MATERIALS",
    "real estate": "SEC_REAL_ESTATE",
    "utilities": "SEC_UTILITIES",
}

_INDUSTRY_BENCHMARK_KEYWORDS = (
    (("semiconductor", "semiconductors"), "IND_SEMICONDUCTORS"),
    (("software", "application software", "infrastructure software"), "IND_SOFTWARE"),
    (("biotechnology", "biotech"), "IND_BIOTECH"),
    (("medical device", "medical devices", "medical instruments", "medical instruments & supplies"), "IND_MEDICAL_DEVICES"),
    (("aerospace", "defense", "aerospace and defense"), "IND_AEROSPACE_DEFENSE"),
)


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
                        SUM(COALESCE(h.quantity * bp.price, h.quantity * lp.price, h.book_cost))
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
            """
            SELECT 1
            FROM (
                SELECT asset_id FROM txn WHERE portfolio_id = ?
                UNION ALL
                SELECT asset_id FROM position WHERE portfolio_id = ?
                UNION ALL
                SELECT asset_id FROM broker_portfolio_position_map WHERE portfolio_id = ?
                UNION ALL
                SELECT asset_id FROM portfolio_ticker WHERE portfolio_id = ?
            ) holdings
            WHERE UPPER(asset_id) = ?
            """,
            [portfolio_id, portfolio_id, portfolio_id, portfolio_id, asset_id],
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
                COALESCE(bp.price, lp.price) AS price,
                COALESCE(h.quantity * bp.price, h.quantity * lp.price, h.book_cost) AS market_value
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
            currency=_valid_currency(row[7]) or "CAD",
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
                    COALESCE(bp.price, lp.price) AS price,
                    COALESCE(h.quantity * bp.price, h.quantity * lp.price, h.book_cost) AS market_value
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
                    currency=_valid_currency(row[9]) or "CAD",
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

    def holding_signals(self, timeframe: str) -> HoldingSignalsResponse:
        period = _SIGNAL_TIMEFRAME_PERIODS.get(timeframe)
        if period is None:
            raise ValueError("timeframe must be one of 1d, 1w, 1m, or 1y")

        items: list[HoldingSignalResponse] = []
        comparison = ComparisonApiService(self.conn)
        for position in self.list_positions():
            prices = comparison._prices(position.asset_id)
            return_value = _period_return(prices, period)
            latest_price = prices[0][1] if prices else position.latest_price
            closes = [row[1] for row in reversed(prices)]
            volatility = _realized_volatility_from_closes(closes)
            profile = comparison.asset_profile(position.asset_id)
            components = _holding_signal_components(
                timeframe=timeframe,
                return_value=return_value,
                volatility=volatility,
                valuation=profile.valuation,
            )
            available = [item.contribution for item in components if item.contribution is not None]
            signal_score = sum(available) / len(available) if available else 0.0
            confidence = len(available) / len(components) if components else 0.0
            items.append(
                HoldingSignalResponse(
                    asset_id=position.asset_id,
                    symbol=position.symbol,
                    name=position.name,
                    currency=position.currency,
                    market_value=position.market_value,
                    weight=position.weight,
                    latest_price=_float_or_none(latest_price),
                    timeframe=timeframe,
                    return_value=return_value,
                    signal_score=round(signal_score, 2),
                    signal_strength=round(abs(signal_score), 2),
                    action=_holding_signal_action(signal_score),
                    confidence=round(confidence, 2),
                    data_points=len(prices),
                    components=components,
                )
            )
        items.sort(
            key=lambda item: (
                item.signal_strength,
                item.confidence,
                item.market_value or 0,
            ),
            reverse=True,
        )
        return HoldingSignalsResponse(
            timeframe=timeframe,
            methodology=(
                f"Ranked by absolute buy/sell signal strength over {_SIGNAL_TIMEFRAME_LABELS[timeframe]}. "
                "Score combines stored price momentum, valuation gaps from fundamentals where available, "
                "and realized volatility as a risk modifier. Missing components reduce confidence."
            ),
            items=items,
        )

    def stock_rankings(
        self,
        *,
        factor: str,
        universe: str,
        direction: str,
        limit: int,
        offset: int,
    ) -> StockRankingsResponse:
        factor = factor.lower().strip()
        universe = universe.lower().strip()
        direction = direction.lower().strip()
        if factor not in _STOCK_RANKING_FACTORS:
            raise ValueError(f"Unsupported stock ranking factor: {factor}")
        if universe not in {"tracked", "all"}:
            raise ValueError("universe must be tracked or all")
        if direction not in {"buy", "sell"}:
            raise ValueError("direction must be buy or sell")

        as_of_date = date.today()
        items = [
            self._stock_ranking_item(row, factor=factor)
            for row in self._stock_ranking_universe(universe)
        ]
        items.sort(
            key=(
                _stock_sell_sort_key
                if direction == "sell"
                else _stock_buy_sort_key
            )
        )
        total = len(items)
        return StockRankingsResponse(
            factor=factor,
            universe=universe,
            direction=direction,
            as_of_date=as_of_date,
            methodology=_stock_ranking_methodology(factor, universe),
            total=total,
            data_complete_count=sum(1 for item in items if item.data_status == "complete"),
            items=items[offset : offset + limit],
        )

    def refresh_stock_ranking_snapshots(
        self,
        *,
        factor: str,
        universe: str,
        limit: int,
    ) -> StockRankingSnapshotRefreshResponse:
        factor = factor.lower().strip()
        universe = universe.lower().strip()
        if factor not in _STOCK_RANKING_FACTORS:
            raise ValueError(f"Unsupported stock ranking factor: {factor}")
        if universe not in {"tracked", "all"}:
            raise ValueError("universe must be tracked or all")

        snapshot_date = date.today()
        rows = self._stock_ranking_universe(universe)[:limit]
        refreshed = 0
        for row in rows:
            self._ensure_stock_asset(row["asset_id"])
            item = self._stock_ranking_item(row, factor=factor)
            self.conn.execute(
                """
                INSERT INTO stock_ranking_snapshot(
                    asset_id, factor, snapshot_date, universe, score, action,
                    confidence, data_status, latest_data_date, components_json,
                    missing_inputs_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now(), now())
                ON CONFLICT (asset_id, factor, snapshot_date)
                DO UPDATE SET
                    universe = EXCLUDED.universe,
                    score = EXCLUDED.score,
                    action = EXCLUDED.action,
                    confidence = EXCLUDED.confidence,
                    data_status = EXCLUDED.data_status,
                    latest_data_date = EXCLUDED.latest_data_date,
                    components_json = EXCLUDED.components_json,
                    missing_inputs_json = EXCLUDED.missing_inputs_json,
                    updated_at = now()
                """,
                [
                    item.asset_id,
                    factor,
                    snapshot_date,
                    universe,
                    item.score,
                    item.action,
                    item.confidence,
                    item.data_status,
                    item.latest_data_date,
                    json.dumps([component.model_dump(mode="json") for component in item.components]),
                    json.dumps(item.missing_inputs),
                ],
            )
            refreshed += 1
        return StockRankingSnapshotRefreshResponse(
            factor=factor,
            universe=universe,
            snapshot_date=snapshot_date,
            refreshed_count=refreshed,
        )

    def add_to_watchlist(self, asset_id: str) -> WatchlistAssetResponse:
        normalized = asset_id.upper().strip()
        if not normalized:
            raise LookupError("Asset not found")
        self._ensure_stock_asset(normalized)
        row = self.conn.execute(
            "SELECT asset_id, COALESCE(symbol, asset_id) FROM asset WHERE asset_id = ?",
            [normalized],
        ).fetchone()
        if row is None:
            raise LookupError(f"Asset not found: {asset_id}")
        self.conn.execute(
            """
            INSERT INTO watchlist_ticker(asset_id, is_active, source, created_at, updated_at)
            VALUES (?, TRUE, 'manual', now(), now())
            ON CONFLICT (asset_id)
            DO UPDATE SET is_active = TRUE, source = 'manual', updated_at = now()
            """,
            [row[0]],
        )
        return WatchlistAssetResponse(asset_id=row[0], symbol=row[1], is_watchlisted=True)

    def _ensure_stock_asset(self, asset_id: str) -> None:
        exists = self.conn.execute(
            "SELECT 1 FROM asset WHERE asset_id = ?",
            [asset_id],
        ).fetchone()
        if exists:
            return
        row = self.conn.execute(
            """
            SELECT asset_id, symbol, exchange_code, asset_type, ccy, name, sector, industry, country, region
            FROM stock_catalog
            WHERE asset_id = ? OR UPPER(symbol) = UPPER(?)
            LIMIT 1
            """,
            [asset_id, asset_id],
        ).fetchone()
        if row is None:
            return
        self.conn.execute(
            """
            INSERT INTO asset(
                asset_id, symbol, exchange_code, asset_type, ccy, name,
                sector, industry, country, region, track, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, FALSE, now(), now())
            """,
            list(row),
        )

    def _stock_ranking_universe(self, universe: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
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
            latest_prices AS (
                SELECT asset_id, date, price
                FROM ranked_prices
                WHERE price_rank = 1
            ),
            portfolio_assets AS (
                SELECT DISTINCT asset_id
                FROM portfolio_ticker
                WHERE is_active = TRUE
            ),
            watchlist_assets AS (
                SELECT DISTINCT asset_id
                FROM watchlist_ticker
                WHERE is_active = TRUE
            )
            SELECT
                a.asset_id,
                COALESCE(a.symbol, a.asset_id) AS symbol,
                a.name,
                a.exchange_code,
                COALESCE(a.ccy, 'USD') AS currency,
                lp.price AS latest_price,
                CASE
                    WHEN h.quantity IS NULL THEN NULL
                    ELSE COALESCE(h.quantity * lp.price, h.book_cost)
                END AS market_value,
                COALESCE(a.track, FALSE) AS asset_tracked,
                h.asset_id IS NOT NULL AS is_held,
                wa.asset_id IS NOT NULL AS is_watchlisted,
                pa.asset_id IS NOT NULL AS is_portfolio_tracked,
                lp.date AS latest_price_date
            FROM asset a
            LEFT JOIN holdings h ON h.asset_id = a.asset_id
            LEFT JOIN latest_prices lp ON lp.asset_id = a.asset_id
            LEFT JOIN portfolio_assets pa ON pa.asset_id = a.asset_id
            LEFT JOIN watchlist_assets wa ON wa.asset_id = a.asset_id
            WHERE COALESCE(a.asset_type, 'stock') = 'stock'
              AND (
                ? = 'all'
                OR COALESCE(a.track, FALSE) = TRUE
                OR h.asset_id IS NOT NULL
                OR pa.asset_id IS NOT NULL
                OR wa.asset_id IS NOT NULL
              )
            ORDER BY symbol
            """,
            [universe],
        ).fetchall()
        items = [
            {
                "asset_id": row[0],
                "symbol": row[1],
                "name": row[2],
                "exchange_code": row[3],
                "currency": row[4],
                "latest_price": _float_or_none(row[5]),
                "market_value": _float_or_none(row[6]),
                "is_tracked": bool(row[7] or row[8] or row[9] or row[10]),
                "is_held": bool(row[8]),
                "is_watchlisted": bool(row[9]),
                "latest_price_date": row[11],
                "catalog_only": False,
            }
            for row in rows
        ]

        if universe == "all":
            asset_ids = {item["asset_id"] for item in items}
            catalog_rows = self.conn.execute(
                """
                SELECT asset_id, symbol, name, exchange_code, ccy
                FROM stock_catalog
                ORDER BY symbol
                """
            ).fetchall()
            for asset_id, symbol, name, exchange_code, currency in catalog_rows:
                if asset_id in asset_ids:
                    continue
                items.append(
                    {
                        "asset_id": asset_id,
                        "symbol": symbol,
                        "name": name,
                        "exchange_code": exchange_code,
                        "currency": currency,
                        "latest_price": None,
                        "market_value": None,
                        "is_tracked": False,
                        "is_held": False,
                        "is_watchlisted": False,
                        "latest_price_date": None,
                        "catalog_only": True,
                    }
                )
        return items

    def _stock_ranking_item(self, row: dict[str, Any], *, factor: str) -> StockRankingItem:
        if factor == "aggregate":
            result = self._aggregate_stock_score(row["asset_id"])
        elif factor == "share_price_momentum":
            result = self._price_momentum_score(row["asset_id"])
        elif factor == "news_sentiment":
            result = self._sentiment_score(row["asset_id"], "news")
        elif factor == "retail_sentiment":
            result = self._sentiment_score(row["asset_id"], "retail")
        elif factor == "earnings_momentum":
            result = self._earnings_momentum_score(row["asset_id"])
        else:
            result = self._institutional_buying_score()

        components: list[StockRankingComponent] = result["components"]
        missing = [
            component.detail
            for component in components
            if not component.available
        ]
        available_count = sum(1 for component in components if component.available)
        if available_count == 0:
            data_status = "missing"
        elif missing:
            data_status = "partial"
        else:
            data_status = "complete"
        score = result["score"] if result["score"] is not None else 0.0
        latest_data_date = result.get("latest_data_date") or row.get("latest_price_date")
        return StockRankingItem(
            asset_id=row["asset_id"],
            symbol=row["symbol"],
            name=row["name"],
            exchange_code=row["exchange_code"],
            currency=row["currency"],
            latest_price=row["latest_price"],
            market_value=row["market_value"],
            is_tracked=row["is_tracked"],
            is_held=row["is_held"],
            is_watchlisted=row["is_watchlisted"],
            score=round(score, 2),
            score_strength=round(abs(score), 2),
            action=_holding_signal_action(score),
            confidence=round(available_count / len(components), 2) if components else 0.0,
            data_status=data_status,
            latest_data_date=latest_data_date,
            missing_inputs=missing,
            components=components,
        )

    def _aggregate_stock_score(self, asset_id: str) -> dict[str, Any]:
        factor_results = [
            ("Share price momentum", self._price_momentum_score(asset_id)),
            ("News sentiment", self._sentiment_score(asset_id, "news")),
            ("Retail sentiment", self._sentiment_score(asset_id, "retail")),
            ("Earnings momentum", self._earnings_momentum_score(asset_id)),
            ("Institutional buying", self._institutional_buying_score()),
        ]
        components: list[StockRankingComponent] = []
        dates = []
        for name, result in factor_results:
            score = result["score"]
            components.append(
                StockRankingComponent(
                    name=name,
                    metric="factor score",
                    value=score,
                    score=score,
                    available=score is not None,
                    detail=(
                        f"{name} contributed to the aggregate score."
                        if score is not None
                        else "; ".join(
                            component.detail
                            for component in result["components"]
                            if not component.available
                        )
                    ),
                )
            )
            if result.get("latest_data_date") is not None:
                dates.append(result["latest_data_date"])
        scores = [component.score for component in components if component.score is not None]
        return {
            "score": sum(scores) / len(scores) if scores else None,
            "latest_data_date": max(dates) if dates else None,
            "components": components,
        }

    def _price_momentum_score(self, asset_id: str) -> dict[str, Any]:
        prices = ComparisonApiService(self.conn)._prices(asset_id)
        closes = [row[1] for row in reversed(prices)]
        latest_data_date = prices[0][0] if prices else None
        return_1m = _period_return(prices, 21)
        return_3m = _period_return(prices, 63)
        return_6m = _period_return(prices, 126)
        volatility = _realized_volatility_from_closes(closes)
        trend_scores = [
            _scaled_signal(return_1m, 0.15),
            _scaled_signal(return_3m, 0.25),
            _scaled_signal(return_6m, 0.35),
        ]
        trend_score = _average_present(trend_scores)
        risk_score = None
        if volatility is not None:
            risk_score = -max(0.0, _scaled_signal(volatility - 0.35, 0.35) or 0.0)
        score = _average_present([trend_score, risk_score])
        return {
            "score": score,
            "latest_data_date": latest_data_date,
            "components": [
                StockRankingComponent(
                    name="Price trend",
                    metric="1m/3m/6m return",
                    value=return_1m,
                    score=trend_score,
                    available=trend_score is not None,
                    detail=(
                        "Blends 1, 3, and 6 month returns from stored daily closes."
                        if trend_score is not None
                        else "Needs at least 22 stored daily closes for price momentum."
                    ),
                ),
                StockRankingComponent(
                    name="Risk",
                    metric="realized volatility",
                    value=volatility,
                    score=risk_score,
                    available=risk_score is not None,
                    detail=(
                        "Lower realized volatility improves the risk-adjusted momentum score."
                        if risk_score is not None
                        else "Needs at least two stored daily closes for risk scoring."
                    ),
                ),
            ],
        }

    def _sentiment_score(self, asset_id: str, bucket: str) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT
                date,
                retail_sentiment_score,
                news_sentiment_score,
                blended_sentiment_score,
                sentiment_momentum_7d,
                reddit_post_count,
                x_post_count,
                article_count
            FROM ticker_sentiment_daily
            WHERE asset_id = ?
            ORDER BY date DESC
            LIMIT 1
            """,
            [asset_id],
        ).fetchone()
        if row is None:
            label = "retail" if bucket == "retail" else "news"
            return {
                "score": None,
                "latest_data_date": None,
                "components": [
                    StockRankingComponent(
                        name=f"{label.title()} sentiment",
                        metric="daily sentiment",
                        available=False,
                        detail=f"Needs a stored {label} sentiment daily snapshot.",
                    )
                ],
            }

        snapshot_date = row[0]
        if bucket == "retail":
            sentiment = _float_or_none(row[1])
            count = int(row[5] or 0) + int(row[6] or 0)
            label = "Retail sentiment"
            missing = "Needs Reddit or X sentiment observations for this ticker."
        else:
            sentiment = _float_or_none(row[2])
            count = int(row[7] or 0)
            label = "News sentiment"
            missing = "Needs news sentiment observations for this ticker."
        momentum = _float_or_none(row[4])
        sentiment_score = sentiment * 100 if sentiment is not None else None
        momentum_score = _scaled_signal(momentum, 0.75)
        score = _average_present([sentiment_score, momentum_score])
        return {
            "score": score,
            "latest_data_date": snapshot_date,
            "components": [
                StockRankingComponent(
                    name=label,
                    metric="sentiment score",
                    value=sentiment,
                    score=sentiment_score,
                    available=sentiment_score is not None and count > 0,
                    detail=(
                        f"Uses {count} recent item(s) in the latest daily sentiment snapshot."
                        if sentiment_score is not None and count > 0
                        else missing
                    ),
                ),
                StockRankingComponent(
                    name="Sentiment momentum",
                    metric="7d change",
                    value=momentum,
                    score=momentum_score,
                    available=momentum_score is not None,
                    detail=(
                        "Seven-day change in blended sentiment."
                        if momentum_score is not None
                        else "Needs a previous sentiment snapshot to calculate momentum."
                    ),
                ),
            ],
        }

    def _earnings_momentum_score(self, asset_id: str) -> dict[str, Any]:
        statement_rows = self.conn.execute(
            """
            SELECT period_end_date, report_date, data_json
            FROM financial_statement
            WHERE asset_id = ?
              AND statement_type = 'income'
            ORDER BY period_end_date DESC NULLS LAST, year DESC, quarter DESC
            LIMIT 2
            """,
            [asset_id],
        ).fetchall()
        calendar_row = self.conn.execute(
            """
            SELECT earnings_date, eps_estimated, eps_actual, revenue_estimated, revenue_actual
            FROM earnings_calendar_event
            WHERE asset_id = ?
              AND earnings_date <= current_date
            ORDER BY earnings_date DESC
            LIMIT 1
            """,
            [asset_id],
        ).fetchone()
        growth_score = None
        latest_date = None
        if len(statement_rows) >= 2:
            latest = _json_dict(statement_rows[0][2])
            previous = _json_dict(statement_rows[1][2])
            latest_date = statement_rows[0][0] or statement_rows[0][1]
            revenue_growth = _relative_change(
                _first_number(latest, "revenue", "totalRevenue", "revenueActual"),
                _first_number(previous, "revenue", "totalRevenue", "revenueActual"),
            )
            eps_growth = _relative_change(
                _first_number(latest, "eps", "epsDiluted", "netIncome"),
                _first_number(previous, "eps", "epsDiluted", "netIncome"),
            )
            growth_score = _average_present(
                [
                    _scaled_signal(revenue_growth, 0.25),
                    _scaled_signal(eps_growth, 0.35),
                ]
            )
        surprise_score = None
        if calendar_row is not None:
            latest_date = max(
                [value for value in [latest_date, calendar_row[0]] if value is not None],
                default=latest_date,
            )
            eps_surprise = _relative_change(
                _float_or_none(calendar_row[2]),
                _float_or_none(calendar_row[1]),
            )
            revenue_surprise = _relative_change(
                _float_or_none(calendar_row[4]),
                _float_or_none(calendar_row[3]),
            )
            surprise_score = _average_present(
                [
                    _scaled_signal(eps_surprise, 0.15),
                    _scaled_signal(revenue_surprise, 0.10),
                ]
            )
        return {
            "score": _average_present([growth_score, surprise_score]),
            "latest_data_date": latest_date,
            "components": [
                StockRankingComponent(
                    name="Statement growth",
                    metric="revenue/EPS growth",
                    score=growth_score,
                    available=growth_score is not None,
                    detail=(
                        "Compares the two latest stored income statements."
                        if growth_score is not None
                        else "Needs at least two stored income statements with revenue or EPS inputs."
                    ),
                ),
                StockRankingComponent(
                    name="Earnings surprise",
                    metric="actual vs estimate",
                    score=surprise_score,
                    available=surprise_score is not None,
                    detail=(
                        "Uses latest stored earnings actuals versus estimates."
                        if surprise_score is not None
                        else "Needs an earnings event with actual and estimated EPS or revenue."
                    ),
                ),
            ],
        }

    def _institutional_buying_score(self) -> dict[str, Any]:
        return {
            "score": None,
            "latest_data_date": None,
            "components": [
                StockRankingComponent(
                    name="Institutional buying",
                    metric="net institutional flow",
                    available=False,
                    detail="Institutional buying data is not configured yet.",
                )
            ],
        }

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

    def search_assets(
        self,
        q: str | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> list[AssetSearchResult]:
        query = q.strip() if q else ""
        where = []
        params: list[Any] = []
        if query:
            like = f"%{query.lower()}%"
            where.append(
                "("
                "LOWER(a.asset_id) LIKE ? OR LOWER(COALESCE(a.symbol, '')) LIKE ? OR "
                "LOWER(COALESCE(a.name, '')) LIKE ? OR LOWER(COALESCE(a.sector, '')) LIKE ? OR "
                "LOWER(COALESCE(a.industry, '')) LIKE ?"
                ")"
            )
            params.extend([like, like, like, like, like])
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self.conn.execute(
            f"""
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
            {where_sql}
            ORDER BY
                CASE
                    WHEN LOWER(a.asset_id) = LOWER(?) THEN 0
                    WHEN LOWER(COALESCE(a.symbol, '')) = LOWER(?) THEN 1
                    ELSE 2
                END,
                a.asset_id
            LIMIT ? OFFSET ?
            """,
            [*params, query, query, limit + offset, 0],
        ).fetchall()
        asset_results = [self._asset_search_result_from_row(row) for row in rows]
        catalog_results = self._search_stock_catalog(query)

        merged: dict[str, AssetSearchResult] = {}
        for item in catalog_results:
            merged[item.asset_id] = item
        for item in asset_results:
            merged[item.asset_id] = item

        def sort_key(item: AssetSearchResult) -> tuple[int, str]:
            symbol = item.symbol.lower()
            asset_id = item.asset_id.lower()
            search = query.lower()
            if search and asset_id == search:
                return (0, item.asset_id)
            if search and symbol == search:
                return (1, item.asset_id)
            return (2, item.asset_id)

        ordered = sorted(merged.values(), key=sort_key)
        return ordered[offset : offset + limit]

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
            catalog_asset = self._catalog_asset_detail(asset_id)
            if catalog_asset is not None:
                return catalog_asset
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

    def _asset_search_result(self, asset: AssetDetail) -> AssetSearchResult:
        return AssetSearchResult(
            asset_id=asset.asset_id,
            symbol=asset.symbol,
            name=asset.name,
            asset_type=asset.asset_type,
            sector=asset.sector,
            industry=asset.industry,
            country=asset.country,
            currency=asset.currency,
            latest_price=asset.latest_price,
        )

    def _asset_search_result_from_row(self, row) -> AssetSearchResult:
        classification = _cdr_classification_override(
            asset_id=row[0],
            symbol=row[1],
            name=row[6],
            sector=row[8],
            industry=row[9],
            country=row[10],
        )
        return AssetSearchResult(
            asset_id=row[0],
            symbol=row[1],
            name=row[6],
            asset_type=row[3],
            sector=classification["sector"],
            industry=classification["industry"],
            country=classification["country"],
            currency=row[5],
            latest_price=_float_or_none(row[16]),
        )

    def _search_stock_catalog(self, q: str) -> list[AssetSearchResult]:
        where = []
        params: list[Any] = []
        if q:
            like = f"%{q.lower()}%"
            where.append(
                "("
                "LOWER(asset_id) LIKE ? OR LOWER(symbol) LIKE ? OR "
                "LOWER(name) LIKE ? OR LOWER(COALESCE(sector, '')) LIKE ? OR "
                "LOWER(COALESCE(industry, '')) LIKE ?"
                ")"
            )
            params.extend([like, like, like, like, like])
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self.conn.execute(
            f"""
            SELECT
                asset_id,
                symbol,
                asset_type,
                ccy,
                name,
                sector,
                industry,
                country
            FROM stock_catalog
            {where_sql}
            ORDER BY
                CASE
                    WHEN LOWER(asset_id) = LOWER(?) THEN 0
                    WHEN LOWER(symbol) = LOWER(?) THEN 1
                    ELSE 2
                END,
                asset_id
            LIMIT 500
            """,
            [*params, q, q],
        ).fetchall()
        return [
            AssetSearchResult(
                asset_id=row[0],
                symbol=row[1],
                name=row[4],
                asset_type=row[2],
                sector=row[5],
                industry=row[6],
                country=row[7],
                currency=row[3],
                latest_price=None,
            )
            for row in rows
        ]

    def _catalog_asset_detail(self, asset_id: str) -> AssetDetail | None:
        row = self.conn.execute(
            """
            SELECT
                asset_id,
                symbol,
                exchange_code,
                asset_type,
                ccy,
                name,
                sector,
                industry,
                country,
                region
            FROM stock_catalog
            WHERE UPPER(asset_id) = UPPER(?)
               OR UPPER(symbol) = UPPER(?)
            ORDER BY
                CASE WHEN UPPER(asset_id) = UPPER(?) THEN 0 ELSE 1 END,
                asset_id
            LIMIT 1
            """,
            [asset_id, asset_id, asset_id],
        ).fetchone()
        if row is None:
            return None
        return AssetDetail(
            asset_id=row[0],
            symbol=row[1],
            is_cdr=False,
            underlying_asset_id=None,
            exchange_code=row[2],
            asset_type=row[3],
            asset_subtype=None,
            currency=row[4],
            name=row[5],
            description=None,
            sector=row[6],
            industry=row[7],
            country=row[8],
            region=row[9],
            size=None,
            market_cap=None,
            shares_outstanding=None,
            market_beta=None,
            latest_price=None,
        )


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
        sector_context = self._sector_context(left, right)
        return ComparisonResponse(
            left=left,
            right=right,
            benchmark=benchmark,
            sector_context=sector_context,
            insights=self._insights(left, right, benchmark, sector_context),
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

    def _sector_context(
        self,
        left: ComparisonAssetProfile,
        right: ComparisonAssetProfile | None,
    ) -> SectorComparisonContext | None:
        if not left.sector:
            return None
        peer_rows = self.conn.execute(
            """
            SELECT asset_id, mkt_cap, market_beta
            FROM asset
            WHERE sector = ?
              AND asset_type = 'stock'
            ORDER BY asset_id
            """,
            [left.sector],
        ).fetchall()
        peer_values = [self._sector_metric_values(row[0], row[1], row[2]) for row in peer_rows]
        median = SectorComparisonValues(
            pe_ratio=_median_present([value.pe_ratio for value in peer_values]),
            price_to_sales=_median_present([value.price_to_sales for value in peer_values]),
            market_cap=_median_present([value.market_cap for value in peer_values]),
            beta=_median_present([value.beta for value in peer_values]),
            return_1d=_median_present([value.return_1d for value in peer_values]),
            return_21d=_median_present([value.return_21d for value in peer_values]),
            return_252d=_median_present([value.return_252d for value in peer_values]),
        )
        benchmark = None
        benchmark_id = _sector_benchmark_candidate(left.sector)
        if benchmark_id:
            try:
                benchmark = self.benchmark_profile(benchmark_id)
            except LookupError:
                benchmark = None
        return SectorComparisonContext(
            sector=left.sector,
            median=median,
            left_diff_to_median=_diff_to_sector_median(_profile_sector_values(left), median),
            right_diff_to_median=_diff_to_sector_median(_profile_sector_values(right), median) if right else None,
            benchmark=benchmark,
        )

    def _sector_metric_values(
        self,
        asset_id: str,
        market_cap: float | None,
        market_beta: float | None,
    ) -> SectorComparisonValues:
        prices = self._prices(asset_id)
        latest_price = prices[0][1] if prices else None
        statements = self._income_statements(asset_id)
        latest_statement = statements[0] if statements else {}
        eps = _first_number(latest_statement, "eps", "epsdiluted", "dilutedEPS", "eps_actual")
        revenue = _first_number(latest_statement, "revenue", "totalRevenue", "revenue_actual")
        pe_ratio = latest_price / eps if latest_price is not None and eps and eps > 0 else None
        price_to_sales = market_cap / revenue if market_cap is not None and revenue and revenue > 0 else None
        return SectorComparisonValues(
            pe_ratio=pe_ratio,
            price_to_sales=price_to_sales,
            market_cap=_float_or_none(market_cap),
            beta=_float_or_none(market_beta),
            return_1d=_period_return(prices, 1),
            return_21d=_period_return(prices, 21),
            return_252d=_period_return(prices, 252),
        )

    def _insights(
        self,
        left: ComparisonAssetProfile,
        right: ComparisonAssetProfile | None,
        benchmark: BenchmarkComparisonProfile | None,
        sector_context: SectorComparisonContext | None = None,
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
        sector_benchmark = sector_context.benchmark if sector_context else None
        if sector_benchmark and left.returns.return_252d is not None and sector_benchmark.return_252d is not None:
            gap = left.returns.return_252d - sector_benchmark.return_252d
            direction = "beat" if gap >= 0 else "lagged"
            insights.append(
                f"{left.symbol} {direction} its sector benchmark {sector_benchmark.index_id} by {abs(gap) * 100:.1f}% over 252 trading days."
            )
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

    def ingestion_readiness(self) -> list[IngestionAssetReadiness]:
        asset_ids = TickerUniverseRepository(self.conn).ingestible_asset_ids(
            include_watchlist=True
        )
        if not asset_ids:
            return []

        placeholders = ", ".join("?" for _ in asset_ids)
        rows = self.conn.execute(
            f"""
            SELECT asset_id, COALESCE(symbol, asset_id) AS symbol, asset_type
            FROM asset
            WHERE asset_id IN ({placeholders})
            ORDER BY asset_id
            """,
            asset_ids,
        ).fetchall()

        items: list[IngestionAssetReadiness] = []
        for asset_id, symbol, asset_type in rows:
            price_requirement = self._price_history_requirement(asset_id)
            requirements = [
                price_requirement,
                self._market_coverage_requirement(
                    asset_id=asset_id,
                    dataset="dividends",
                    table_name="dividend_event",
                    date_column="ex_date",
                    label="Dividend coverage",
                ),
                self._market_coverage_requirement(
                    asset_id=asset_id,
                    dataset="splits",
                    table_name="split_event",
                    date_column="ex_date",
                    label="Split coverage",
                ),
                self._shares_outstanding_requirement(asset_id),
                self._financial_statement_requirement(asset_id, "income", "Income statements"),
                self._financial_statement_requirement(asset_id, "balance", "Balance sheets"),
                self._financial_statement_requirement(asset_id, "cashflow", "Cash flow statements"),
            ]
            # This endpoint backs the Operations "Projection input readiness"
            # card. Portfolio projections need enough price observations for
            # volatility, expected return, and simulation bands. Fundamentals
            # enrich valuation depth, but provider entitlement gaps should not
            # block projection readiness once all runnable ingestion jobs have
            # been closed out.
            missing = [] if price_requirement.ready else [price_requirement.label]
            items.append(
                IngestionAssetReadiness(
                    asset_id=asset_id,
                    symbol=symbol,
                    asset_type=asset_type,
                    ready=not missing,
                    missing=missing,
                    requirements=requirements,
                )
            )
        return items

    def stock_ranking_readiness(
        self,
        *,
        universe: str = "tracked",
        limit: int = 50,
    ) -> StockRankingReadinessResponse:
        portfolio_service = PortfolioApiService(self.conn)
        rows = portfolio_service._stock_ranking_universe(universe)[:limit]
        factors = [
            "share_price_momentum",
            "news_sentiment",
            "retail_sentiment",
            "earnings_momentum",
            "institutional_buying",
        ]
        items: list[StockRankingReadinessItem] = []
        for row in rows:
            requirements: list[IngestionRequirementStatus] = []
            missing: list[str] = []
            for factor in factors:
                ranking = portfolio_service._stock_ranking_item(row, factor=factor)
                ready = ranking.data_status == "complete"
                detail = (
                    "complete"
                    if ready
                    else "; ".join(ranking.missing_inputs) or ranking.data_status
                )
                requirements.append(
                    IngestionRequirementStatus(
                        key=factor,
                        label=_STOCK_RANKING_LABELS[factor],
                        ready=ready,
                        detail=detail,
                        row_count=sum(
                            1 for component in ranking.components if component.available
                        ),
                        latest_date=ranking.latest_data_date,
                    )
                )
                if not ready:
                    missing.append(_STOCK_RANKING_LABELS[factor])
            complete_count = sum(1 for requirement in requirements if requirement.ready)
            items.append(
                StockRankingReadinessItem(
                    asset_id=row["asset_id"],
                    symbol=row["symbol"],
                    name=row["name"],
                    universe=universe,
                    ready=complete_count == len(requirements),
                    complete_factor_count=complete_count,
                    total_factor_count=len(requirements),
                    missing=missing,
                    requirements=requirements,
                )
            )
        return StockRankingReadinessResponse(
            universe=universe,
            items=items,
            total=len(items),
            ready_count=sum(1 for item in items if item.ready),
        )

    def _price_history_requirement(self, asset_id: str) -> IngestionRequirementStatus:
        row = self.conn.execute(
            """
            SELECT COUNT(*), MAX(date)
            FROM asset_quote_daily
            WHERE asset_id = ?
              AND COALESCE(adj_close, close) IS NOT NULL
            """,
            [asset_id],
        ).fetchone()
        row_count = int(row[0])
        latest_date = row[1]
        open_jobs = self._open_job_count(asset_id, "market", "price_daily")
        last_error = self._sync_last_error(asset_id, "market", "price_daily")
        ready = row_count >= 3
        detail = f"{row_count} usable daily prices"
        if not ready and open_jobs:
            detail += f"; {open_jobs} open job(s)"
        return IngestionRequirementStatus(
            key="price_history",
            label="Projection price history",
            ready=ready,
            detail=detail,
            row_count=row_count,
            latest_date=latest_date,
            open_jobs=open_jobs,
            last_error=last_error,
        )

    def _market_coverage_requirement(
        self,
        *,
        asset_id: str,
        dataset: str,
        table_name: str,
        date_column: str,
        label: str,
    ) -> IngestionRequirementStatus:
        row = self.conn.execute(
            f"""
            SELECT COUNT(*), MAX({date_column})
            FROM {table_name}
            WHERE asset_id = ?
            """,
            [asset_id],
        ).fetchone()
        row_count = int(row[0])
        latest_date = row[1]
        open_jobs = self._open_job_count(asset_id, "market", dataset)
        sync_done = self._sync_has_success(asset_id, "market", dataset)
        last_error = self._sync_last_error(asset_id, "market", dataset)
        ready = row_count > 0 or sync_done or open_jobs > 0
        if row_count:
            detail = f"{row_count} stored event(s)"
        elif sync_done:
            detail = "coverage checked; no events stored"
        elif open_jobs:
            detail = f"{open_jobs} open job(s)"
        else:
            detail = "coverage has not been checked"
        return IngestionRequirementStatus(
            key=dataset,
            label=label,
            ready=ready,
            detail=detail,
            row_count=row_count,
            latest_date=latest_date,
            open_jobs=open_jobs,
            last_error=last_error,
        )

    def _shares_outstanding_requirement(self, asset_id: str) -> IngestionRequirementStatus:
        row = self.conn.execute(
            """
            SELECT shares_outstanding
            FROM asset
            WHERE asset_id = ?
            """,
            [asset_id],
        ).fetchone()
        value = _float_or_none(row[0]) if row else None
        ready = value is not None and value > 0
        return IngestionRequirementStatus(
            key="shares_outstanding",
            label="Shares outstanding",
            ready=ready,
            detail=f"{value:,.0f} shares" if ready else "missing from asset metadata",
            row_count=1 if ready else 0,
        )

    def _financial_statement_requirement(
        self,
        asset_id: str,
        statement_type: str,
        label: str,
    ) -> IngestionRequirementStatus:
        row = self.conn.execute(
            """
            SELECT COUNT(*), MAX(period_end_date)
            FROM financial_statement
            WHERE asset_id = ?
              AND statement_type = ?
            """,
            [asset_id, statement_type],
        ).fetchone()
        row_count = int(row[0])
        latest_date = row[1]
        open_jobs = self._open_job_count(asset_id, "corporate", "financial_statements")
        sync_done = self._sync_has_success(asset_id, "corporate", "financial_statements")
        last_error = self._sync_last_error(asset_id, "corporate", "financial_statements")
        ready = row_count > 0 or sync_done
        if row_count:
            detail = f"{row_count} statement(s)"
        elif sync_done:
            detail = "coverage checked; no statements returned"
        else:
            detail = "no stored statements"
        if not ready and open_jobs:
            detail += f"; {open_jobs} open job(s)"
        return IngestionRequirementStatus(
            key=f"{statement_type}_statements",
            label=label,
            ready=ready,
            detail=detail,
            row_count=row_count,
            latest_date=latest_date,
            open_jobs=open_jobs,
            last_error=last_error,
        )

    def _open_job_count(self, asset_id: str, domain: str, dataset: str) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM ingestion_job
            WHERE asset_id = ?
              AND domain = ?
              AND dataset = ?
              AND status IN ('pending', 'running')
            """,
            [asset_id, domain, dataset],
        ).fetchone()
        return int(row[0])

    def _sync_has_success(self, asset_id: str, domain: str, dataset: str) -> bool:
        row = self.conn.execute(
            """
            SELECT last_successful_date, last_successful_at
            FROM asset_sync_state
            WHERE asset_id = ?
              AND domain = ?
              AND dataset = ?
            """,
            [asset_id, domain, dataset],
        ).fetchone()
        return bool(row and (row[0] is not None or row[1] is not None))

    def _sync_last_error(self, asset_id: str, domain: str, dataset: str) -> str | None:
        row = self.conn.execute(
            """
            SELECT last_error
            FROM asset_sync_state
            WHERE asset_id = ?
              AND domain = ?
              AND dataset = ?
            """,
            [asset_id, domain, dataset],
        ).fetchone()
        return row[0] if row and row[0] else None

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

    def clear_ingestion_history(self) -> dict[str, int]:
        job_rows = self.conn.execute("DELETE FROM ingestion_job RETURNING job_id").fetchall()
        state_rows = self.conn.execute(
            "DELETE FROM asset_sync_state RETURNING asset_id"
        ).fetchall()
        return {
            "deleted_jobs": len(job_rows),
            "deleted_sync_states": len(state_rows),
        }

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


def _core_benchmark_candidate(country: str | None, currency: str | None) -> str | None:
    country_key = _normalized_lookup_key(country)
    currency_key = _normalized_lookup_key(currency)
    if country_key and country_key in DEFAULT_BENCHMARK_BY_COUNTRY:
        return DEFAULT_BENCHMARK_BY_COUNTRY[country_key]
    if currency_key and currency_key in DEFAULT_BENCHMARK_BY_CURRENCY:
        return DEFAULT_BENCHMARK_BY_CURRENCY[currency_key]
    return None


def _sector_benchmark_candidate(sector: str | None) -> str | None:
    return _SECTOR_BENCHMARK_BY_KEY.get(_normalized_lookup_key(sector))


def _profile_sector_values(profile: ComparisonAssetProfile | None) -> SectorComparisonValues:
    if profile is None:
        return SectorComparisonValues()
    return SectorComparisonValues(
        pe_ratio=profile.fundamentals.pe_ratio,
        price_to_sales=profile.fundamentals.price_to_sales,
        market_cap=profile.market_cap,
        beta=profile.market_beta,
        return_1d=profile.returns.return_1d,
        return_21d=profile.returns.return_21d,
        return_252d=profile.returns.return_252d,
    )


def _diff_to_sector_median(values: SectorComparisonValues, median: SectorComparisonValues) -> SectorComparisonValues:
    return SectorComparisonValues(
        pe_ratio=_absolute_gap(values.pe_ratio, median.pe_ratio),
        price_to_sales=_absolute_gap(values.price_to_sales, median.price_to_sales),
        market_cap=_absolute_gap(values.market_cap, median.market_cap),
        beta=_absolute_gap(values.beta, median.beta),
        return_1d=_absolute_gap(values.return_1d, median.return_1d),
        return_21d=_absolute_gap(values.return_21d, median.return_21d),
        return_252d=_absolute_gap(values.return_252d, median.return_252d),
    )


def _median_present(values: list[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return float(statistics.median(present)) if present else None


def _absolute_gap(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return float(value - baseline)


def _industry_benchmark_candidate(industry: str | None) -> str | None:
    normalized = _normalized_lookup_key(industry)
    if not normalized:
        return None
    for keywords, benchmark_id in _INDUSTRY_BENCHMARK_KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return benchmark_id
    return None


def _normalized_lookup_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).replace("&", "and").replace("-", " ").lower().split())
    return normalized or None


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


def _average_present(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _relative_change(value: float | None, previous: float | None) -> float | None:
    if value is None or previous is None:
        return None
    if previous == 0:
        return None
    return (value - previous) / abs(previous)


def _stock_buy_sort_key(item: StockRankingItem):
    return (
        item.data_status == "missing",
        -item.score,
        -item.confidence,
        -(item.market_value or 0),
        item.symbol,
    )


def _stock_sell_sort_key(item: StockRankingItem):
    return (
        item.data_status == "missing",
        item.score,
        -item.confidence,
        -(item.market_value or 0),
        item.symbol,
    )


def _stock_ranking_methodology(factor: str, universe: str) -> str:
    scope = "tracked stocks" if universe == "tracked" else "the available stock catalog"
    label = _STOCK_RANKING_LABELS[factor]
    if factor == "aggregate":
        return (
            f"Ranks {scope} by the average of available price momentum, news sentiment, retail sentiment, "
            "earnings momentum, and institutional buying inputs. Missing factor inputs reduce confidence."
        )
    if factor == "share_price_momentum":
        return (
            f"Ranks {scope} by stored daily close momentum, blended with realized volatility as a risk modifier."
        )
    if factor == "news_sentiment":
        return f"Ranks {scope} by the latest stored news sentiment snapshot and sentiment momentum."
    if factor == "retail_sentiment":
        return f"Ranks {scope} by the latest stored retail/social sentiment snapshot and sentiment momentum."
    if factor == "earnings_momentum":
        return f"Ranks {scope} by stored income statement growth and latest earnings surprise data."
    return f"Ranks {scope} by {label.lower()}; this data source is not configured yet, so rows disclose missing inputs."


def _realized_volatility_from_closes(closes: list[float]) -> float | None:
    if len(closes) < 2:
        return None
    returns = [
        closes[index] / closes[index - 1] - 1.0
        for index in range(1, len(closes))
        if closes[index - 1] > 0
    ]
    if not returns:
        return None
    mean_return = sum(returns) / len(returns)
    variance = sum((item - mean_return) ** 2 for item in returns) / len(returns)
    return (variance ** 0.5) * (252 ** 0.5)


def _holding_signal_components(
    *,
    timeframe: str,
    return_value: float | None,
    volatility: float | None,
    valuation: ValuationContext,
) -> list[HoldingSignalComponent]:
    label = _SIGNAL_TIMEFRAME_LABELS[timeframe]
    momentum = _scaled_signal(return_value, _momentum_return_scale(timeframe))
    valuation_gaps = [
        valuation.historical_pe_discount,
        valuation.sector_pe_premium,
        valuation.industry_pe_premium,
    ]
    valuation_values = [-gap for gap in valuation_gaps if gap is not None]
    valuation_signal = (
        _scaled_signal(sum(valuation_values) / len(valuation_values), 0.35)
        if valuation_values
        else None
    )
    risk_signal = None
    if volatility is not None:
        if return_value is None or abs(return_value) < 0.0001:
            risk_signal = 0.0
        elif return_value > 0:
            risk_signal = _scaled_signal(0.35 - volatility, 0.35)
        else:
            risk_signal = -max(0.0, _scaled_signal(volatility - 0.25, 0.35) or 0.0)
    return [
        HoldingSignalComponent(
            name="Momentum",
            metric=f"{label} return",
            value=return_value,
            contribution=momentum,
            detail=(
                "Price return from stored daily closes over the selected timeframe."
                if return_value is not None
                else f"Needs at least {(_SIGNAL_TIMEFRAME_PERIODS[timeframe] + 1)} stored daily closes."
            ),
        ),
        HoldingSignalComponent(
            name="Valuation",
            metric="P/E valuation gap",
            value=(sum(valuation_values) / len(valuation_values)) if valuation_values else None,
            contribution=valuation_signal,
            detail=(
                "Uses historical, sector, and industry P/E gaps; cheaper than comparables supports buy signals."
                if valuation_values
                else "Unavailable until local fundamentals can calculate P/E history or peer gaps."
            ),
        ),
        HoldingSignalComponent(
            name="Risk",
            metric="Realized volatility",
            value=volatility,
            contribution=risk_signal,
            detail=(
                "Annualized volatility from stored daily closes moderates high-risk moves."
                if volatility is not None
                else "Needs at least two stored daily closes."
            ),
        ),
    ]


def _momentum_return_scale(timeframe: str) -> float:
    return {
        "1d": 0.04,
        "1w": 0.08,
        "1m": 0.15,
        "1y": 0.35,
    }[timeframe]


def _scaled_signal(value: float | None, full_scale: float) -> float | None:
    if value is None:
        return None
    if full_scale <= 0:
        return 0.0
    return max(-100.0, min(100.0, (value / full_scale) * 100.0))


def _holding_signal_action(score: float) -> str:
    if score >= 65:
        return "Strong Buy"
    if score >= 25:
        return "Buy"
    if score <= -65:
        return "Strong Sell"
    if score <= -25:
        return "Sell"
    return "Hold"


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
    match = re.search(r"['\"]?CODE['\"]?\s*:\s*['\"]?([A-Z]{3})['\"]?", text)
    if match:
        return match.group(1)
    return text if len(text) == 3 and text.isalpha() else None
