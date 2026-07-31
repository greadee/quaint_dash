"""Application-facing read and write services for the HTTP API."""

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import json
import os
import re
import statistics
from typing import Any, Callable

from dashboard.api.models import (
    AssetDetail,
    AssetActivitySummary,
    AssetHoldingSummary,
    AssetBenchmarkAssociationResponse,
    AssetSearchResult,
    BenchmarkAssociation,
    BrokerAccountResponse,
    BrokerConnectionResponse,
    BrokerImportPreviewGroup,
    BrokerImportPreviewItem,
    BrokerImportPreviewResponse,
    BrokerReconciliationItem,
    BrokerReconciliationResponse,
    BrokerStatusResponse,
    BrokerSyncHistoryItem,
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
    ComparisonCoverage,
    ComparisonFreshness,
    ComparisonFxPolicy,
    ComparisonHistoryPoint,
    ComparisonHistorySeries,
    ComparisonFundamentals,
    ComparisonResponse,
    ComparisonWorkspaceResponse,
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
    PortfolioFundamentalHolding,
    PortfolioFundamentalsResponse,
    PortfolioMetricContributor,
    PortfolioMetricInsight,
    PortfolioMetricValue,
    PortfolioPerformancePoint,
    PortfolioPerformanceResponse,
    PortfolioRiskResponse,
    PortfolioSummary,
    PortfolioUpdate,
    PositionSummary,
    PricePointResponse,
    PriceMoverResponse,
    IngestionRequirementStatus,
    RetailSentimentDailySnapshot,
    RetailSentimentOverviewItem,
    RetailSentimentOverviewPost,
    RetailSentimentOverviewResponse,
    RetailSentimentPost,
    RetailSentimentProviderStatus,
    RetailSentimentStatusResponse,
    SignalAlertRuleRequest,
    SignalAlertRuleResponse,
    SignalDetailResponse,
    SignalEvidenceItem,
    SignalEfficacyMetadata,
    SignalHistoryPoint,
    SignalLifecycleEvent,
    SignalPortfolioImpact,
    SignalRow,
    SignalSnapshotRefreshResponse,
    SignalSummaryMetric,
    SignalUserState,
    SignalUserStateRequest,
    SignalsSummaryResponse,
    StockRankingComponent,
    StockRankingItem,
    StockRankingReadinessItem,
    StockRankingReadinessResponse,
    StockRankingSnapshotRefreshResponse,
    StockRankingsResponse,
    TransactionSummary,
    OptimizationMetricSet,
    OptimizationPreviewRequest,
    OptimizationPreviewResponse,
    ValuationContext,
    WatchlistAssetResponse,
)
from dashboard.analytics import (
    AnalyticsEngine,
    AnalyticsRepository,
    AnalyticsStorageService,
    analytics_report_payload,
)
from dashboard.analytics.calculations import (
    allocation_class,
    beta,
    dimension_exposure,
    portfolio_annualized_volatility,
    portfolio_returns_from_components,
    risk_return_metrics,
)
from dashboard.analytics.models import (
    AssetRiskContribution,
    DEFAULT_BENCHMARK_BY_COUNTRY,
    DEFAULT_BENCHMARK_BY_CURRENCY,
    PortfolioRiskDecomposition,
    PortfolioValuationRollup,
    PositionAnalytics,
    PositionValuationContribution,
    PricePoint,
    RelativeRiskMetrics,
    RiskReturnMetrics,
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

UTC = timezone.utc


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
_STOCK_RANKING_TIMEFRAME_DAYS = {
    "daily": 1,
    "weekly": 5,
    "monthly": 21,
    "yearly": 252,
}
_STOCK_RANKING_TIMEFRAME_LABELS = {
    "daily": "daily",
    "weekly": "weekly",
    "monthly": "monthly",
    "yearly": "yearly",
}
_SIGNALS_MODEL_VERSION = "signals.rankings.v1"


@dataclass(frozen=True)
class SignalAdapter:
    factor: str
    definition_id: str
    signal_name: str
    category: str
    source: str
    trigger_threshold: float
    lookback_period: str


@dataclass(frozen=True)
class _StoredPortfolioAnalytics:
    portfolio_id: int
    benchmark_index_id: str | None
    risk: RiskReturnMetrics | None
    relative: RelativeRiskMetrics | None
    risk_decomposition: PortfolioRiskDecomposition
    valuation: PortfolioValuationRollup
    missing_inputs: list[str]
    refreshed_at: datetime


_SIGNAL_ADAPTERS = {
    "aggregate": SignalAdapter(
        factor="aggregate",
        definition_id="ranking.aggregate.monthly",
        signal_name="Composite evidence changed",
        category="market_regime",
        source="stored local ranking inputs",
        trigger_threshold=6.0,
        lookback_period="monthly",
    ),
    "share_price_momentum": SignalAdapter(
        factor="share_price_momentum",
        definition_id="ranking.share_price_momentum.monthly",
        signal_name="Price momentum threshold crossed",
        category="momentum",
        source="asset_quote_daily",
        trigger_threshold=6.0,
        lookback_period="monthly",
    ),
    "news_sentiment": SignalAdapter(
        factor="news_sentiment",
        definition_id="ranking.news_sentiment.monthly",
        signal_name="News sentiment shifted",
        category="news_event_activity",
        source="ticker_sentiment_daily",
        trigger_threshold=6.0,
        lookback_period="monthly",
    ),
    "retail_sentiment": SignalAdapter(
        factor="retail_sentiment",
        definition_id="ranking.retail_sentiment.monthly",
        signal_name="Retail sentiment shifted",
        category="sentiment",
        source="ticker_sentiment_daily",
        trigger_threshold=6.0,
        lookback_period="monthly",
    ),
    "earnings_momentum": SignalAdapter(
        factor="earnings_momentum",
        definition_id="ranking.earnings_momentum.monthly",
        signal_name="Earnings outlook changed",
        category="earnings_revisions",
        source="financial_statement and earnings_calendar_event",
        trigger_threshold=6.0,
        lookback_period="monthly",
    ),
    "institutional_buying": SignalAdapter(
        factor="institutional_buying",
        definition_id="ranking.institutional_buying.monthly",
        signal_name="Accumulation activity changed",
        category="analyst_broker_activity",
        source="institutional_buying_daily",
        trigger_threshold=6.0,
        lookback_period="monthly",
    ),
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
    CASE WHEN cdr_underlying.asset_id IS NOT NULL
        THEN COALESCE(cdr_underlying.mkt_cap, a.mkt_cap)
        ELSE a.mkt_cap
    END AS mkt_cap,
    CASE WHEN cdr_underlying.asset_id IS NOT NULL
        THEN COALESCE(cdr_underlying.shares_outstanding, a.shares_outstanding)
        ELSE a.shares_outstanding
    END AS shares_outstanding,
    CASE WHEN cdr_underlying.asset_id IS NOT NULL
        THEN COALESCE(cdr_underlying.market_beta, a.market_beta)
        ELSE a.market_beta
    END AS market_beta
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
    "BKNG": {"sector": "Consumer Cyclical", "industry": "Travel Services", "country": "US"},
    "CEG": {"sector": "Utilities", "industry": "Utilities - Renewable", "country": "US"},
    "GEV": {"sector": "Industrials", "industry": "Electrical Equipment & Parts", "country": "US"},
    "GOOG": {"sector": "Communication Services", "industry": "Internet Content & Information", "country": "US"},
    "ISRG": {"sector": "Healthcare", "industry": "Medical Instruments & Supplies", "country": "US"},
    "LLY": {"sector": "Healthcare", "industry": "Medical - Pharmaceuticals", "country": "US"},
    "META": {"sector": "Communication Services", "industry": "Internet Content & Information", "country": "US"},
    "MSFT": {"sector": "Technology", "industry": "Software - Infrastructure", "country": "US"},
    "MU": {"sector": "Technology", "industry": "Semiconductors", "country": "US"},
    "NOW": {"sector": "Technology", "industry": "Software - Application", "country": "US"},
    "NVDA": {"sector": "Technology", "industry": "Semiconductors", "country": "US"},
    "NVO": {"sector": "Healthcare", "industry": "Drug Manufacturers - General", "country": "DK"},
    "SPGI": {"sector": "Financial Services", "industry": "Financial Data & Stock Exchanges", "country": "US"},
    "TSLA": {"sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "country": "US"},
    "UBER": {"sector": "Industrials", "industry": "Software - Application", "country": "US"},
    "V": {"sector": "Financial Services", "industry": "Credit Services", "country": "US"},
    "VISA": {"sector": "Financial Services", "industry": "Credit Services", "country": "US"},
}

_KNOWN_CDR_UNDERLYING_NAMES = {
    "AAPL": "Apple Inc.",
    "AMD": "Advanced Micro Devices, Inc.",
    "AMZN": "Amazon.com, Inc.",
    "ANET": "Arista Networks, Inc.",
    "ASML": "ASML Holding N.V.",
    "AVGO": "Broadcom Inc.",
    "BKNG": "Booking Holdings Inc.",
    "CEG": "Constellation Energy Corporation",
    "GEV": "GE Vernova Inc.",
    "GOOG": "Alphabet Inc.",
    "ISRG": "Intuitive Surgical, Inc.",
    "LLY": "Eli Lilly and Company",
    "META": "Meta Platforms, Inc.",
    "MSFT": "Microsoft Corporation",
    "MU": "Micron Technology, Inc.",
    "NOW": "ServiceNow, Inc.",
    "NVDA": "NVIDIA Corporation",
    "NVO": "Novo Nordisk A/S",
    "SPGI": "S&P Global Inc.",
    "TSLA": "Tesla, Inc.",
    "UBER": "Uber Technologies, Inc.",
    "V": "Visa Inc.",
    "VISA": "Visa Inc.",
}

_CDR_SYMBOL_ALIASES = {
    "CEGS": "CEG",
    "NVON": "NVO",
    "NOWS": "NOW",
    "VISA": "V",
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
    (("internet", "internet content", "internet content and information", "online media"), "IND_INTERNET"),
    (("retail", "internet retail", "specialty retail"), "IND_RETAIL"),
    (("auto manufacturer", "auto manufacturers", "automobile", "automobiles", "automotive"), "IND_AUTOS"),
    (("bank", "banks", "regional banks"), "IND_BANKS"),
    (("insurance", "insurers"), "IND_INSURANCE"),
    (("biotechnology", "biotech"), "IND_BIOTECH"),
    (("pharmaceutical", "pharmaceuticals", "medical pharmaceuticals"), "IND_PHARMACEUTICALS"),
    (("medical device", "medical devices", "medical instruments", "medical instruments & supplies"), "IND_MEDICAL_DEVICES"),
    (("aerospace", "defense", "aerospace and defense"), "IND_AEROSPACE_DEFENSE"),
    (("homebuilder", "homebuilders", "residential construction"), "IND_HOMEBUILDERS"),
    (("transportation", "railroad", "railroads", "trucking", "logistics"), "IND_TRANSPORTATION"),
    (("oil and gas exploration", "oil gas exploration", "exploration and production"), "IND_OIL_GAS_EXPLORATION"),
    (("metals", "mining", "steel", "copper"), "IND_METALS_MINING"),
)


class PortfolioApiService:
    def __init__(self, conn) -> None:
        self.conn = conn
        self._signal_efficacy_price_cache: dict[str, list[tuple[date, float]]] = {}
        self._portfolio_summary_cache: list[PortfolioSummary] | None = None
        self._position_summary_cache: dict[int | None, list[PositionSummary]] = {}

    def _invalidate_read_caches(self) -> None:
        self._portfolio_summary_cache = None
        self._position_summary_cache.clear()

    def list_portfolios(self) -> list[PortfolioSummary]:
        if self._portfolio_summary_cache is not None:
            return self._portfolio_summary_cache
        summaries = self._portfolio_summaries()
        self._portfolio_summary_cache = summaries
        return summaries

    def _portfolio_summaries(self, portfolio_id: int | None = None) -> list[PortfolioSummary]:
        scoped_holdings_where = "WHERE portfolio_id = ?" if portfolio_id is not None else ""
        portfolio_where = "WHERE p.portfolio_id = ?" if portfolio_id is not None else ""
        params: list[object] = [portfolio_id, portfolio_id] if portfolio_id is not None else []
        rows = self.conn.execute(
            f"""
            WITH holdings AS ({_HOLDINGS_SQL}),
            scoped_holdings AS (
                SELECT *
                FROM holdings
                {scoped_holdings_where}
            ),
            latest_prices AS (
                SELECT asset_id, close AS price
                FROM asset_quote_daily
                WHERE asset_id IN (SELECT DISTINCT asset_id FROM scoped_holdings)
                  AND close IS NOT NULL
                QUALIFY ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY date DESC) = 1
            ),
            current_prices AS (
                SELECT asset_id, price
                FROM current_asset_price
                WHERE asset_id IN (SELECT DISTINCT asset_id FROM scoped_holdings)
            ),
            mapped_broker_positions AS (
                SELECT DISTINCT provider, provider_account_id, provider_position_id
                FROM broker_portfolio_position_map
                WHERE portfolio_id IN (SELECT DISTINCT portfolio_id FROM scoped_holdings)
            ),
            latest_broker_positions AS (
                SELECT
                    ps.provider,
                    ps.provider_account_id,
                    ps.provider_position_id,
                    MAX(ps.as_of_date) AS as_of_date
                FROM broker_position_snapshot ps
                JOIN mapped_broker_positions mapped
                  ON mapped.provider = ps.provider
                 AND mapped.provider_account_id = ps.provider_account_id
                 AND mapped.provider_position_id = ps.provider_position_id
                GROUP BY ps.provider, ps.provider_account_id, ps.provider_position_id
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
                        SUM(COALESCE(h.quantity * cp.price, h.quantity * lp.price, h.quantity * bp.price, h.book_cost))
                            FILTER (WHERE h.quantity <> 0),
                        0
                    ) AS market_value
                FROM scoped_holdings h
                LEFT JOIN latest_prices lp ON lp.asset_id = h.asset_id
                LEFT JOIN current_prices cp ON cp.asset_id = h.asset_id
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
            {portfolio_where}
            ORDER BY p.portfolio_id
            """,
            params,
        ).fetchall()
        portfolio_ids = [int(row[0]) for row in rows]
        gain_overrides = self._portfolio_gain_overrides(portfolio_ids)
        projections = self._stored_portfolio_projections(portfolio_ids)
        return [
            self._portfolio_summary(
                row,
                gain_override_rows=gain_overrides.get(int(row[0]), []),
                projection=projections.get(int(row[0]), {}),
            )
            for row in rows
        ]

    def aggregate_portfolio(self) -> PortfolioSummary:
        portfolios = self.list_portfolios()
        if not portfolios:
            raise LookupError("No portfolios found.")
        market_value = sum(item.market_value for item in portfolios)
        book_cost = sum(item.book_cost for item in portfolios)
        total_gain_values = [item.total_gain for item in portfolios if item.total_gain is not None]
        total_gain = sum(total_gain_values) if total_gain_values else None
        total_gain_basis = market_value - total_gain if total_gain is not None else None
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
            unrealized_return_percent=_ratio_or_none(
                market_value - book_cost if market_value else None,
                book_cost,
            ),
            total_gain=total_gain,
            total_return_percent=_ratio_or_none(total_gain, total_gain_basis),
            total_gain_source="manual_override"
            if any(item.total_gain_source == "manual_override" for item in portfolios)
            else "unrealized",
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

    def refresh_portfolio_snapshots(self) -> dict[str, Any]:
        storage = AnalyticsStorageService(self.conn, enabled=True)
        storage.ensure_schema()
        portfolio_ids = storage.repo.portfolio_ids()
        reports: list[tuple[Any, str]] = []
        failures: dict[str, str] = {}
        for portfolio_id in portfolio_ids:
            try:
                signature = storage.portfolio_signature(portfolio_id)
                report = storage.engine.portfolio_report(
                    portfolio_id,
                    benchmark_index_id=storage.benchmark_index_id,
                    risk_free_rate=storage.risk_free_rate,
                )
                reports.append((report, signature))
            except Exception as exc:
                failures[str(portfolio_id)] = str(exc)

        snapshot_date = date.today()
        self.conn.execute("BEGIN TRANSACTION")
        try:
            for report, signature in reports:
                storage.store_portfolio_report(
                    report,
                    snapshot_date,
                    signature,
                )
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        self._invalidate_read_caches()
        return {
            "refreshed_count": len(reports),
            "failed_count": len(failures),
            "failed_portfolios": failures,
            "snapshot_date": snapshot_date.isoformat(),
        }

    def get_portfolio(self, portfolio_id: int) -> PortfolioSummary:
        portfolios = (
            self._portfolio_summaries(portfolio_id)
            if self._portfolio_summary_cache is None
            else self._portfolio_summary_cache
        )
        for portfolio in portfolios:
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
        self._invalidate_read_caches()
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
        self._invalidate_read_caches()
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
        self._invalidate_read_caches()
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
        self._invalidate_read_caches()
        return {
            "portfolio_id": portfolio_id,
            "asset_id": asset_id,
            "deleted_transactions": len(txn_rows),
            "deleted_positions": len(position_rows),
            "deleted_broker_mappings": len(broker_map_rows),
            "broker_linked": broker_rows > 0,
        }

    def list_positions(self, portfolio_id: int | None = None) -> list[PositionSummary]:
        if portfolio_id in self._position_summary_cache:
            return self._position_summary_cache[portfolio_id]
        if portfolio_id is not None:
            self.get_portfolio(portfolio_id)
            where = "WHERE portfolio_id = ?"
            params: list[object] = [portfolio_id, portfolio_id, portfolio_id, portfolio_id]
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
                SELECT asset_id, close AS price
                FROM asset_quote_daily
                WHERE asset_id IN (SELECT DISTINCT asset_id FROM holdings)
                  AND close IS NOT NULL
                QUALIFY ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY date DESC) = 1
            ),
            current_prices AS (
                SELECT asset_id, price, provider, market_session, updated_at
                FROM current_asset_price
                WHERE asset_id IN (SELECT DISTINCT asset_id FROM holdings)
            ),
            mapped_broker_positions AS (
                SELECT DISTINCT provider, provider_account_id, provider_position_id
                FROM broker_portfolio_position_map
                {where}
            ),
            latest_broker_positions AS (
                SELECT
                    ps.provider,
                    ps.provider_account_id,
                    ps.provider_position_id,
                    MAX(ps.as_of_date) AS as_of_date
                FROM broker_position_snapshot ps
                JOIN mapped_broker_positions mapped
                  ON mapped.provider = ps.provider
                 AND mapped.provider_account_id = ps.provider_account_id
                 AND mapped.provider_position_id = ps.provider_position_id
                GROUP BY ps.provider, ps.provider_account_id, ps.provider_position_id
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
                a.asset_subtype,
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
                COALESCE(cp.price, lp.price, bp.price) AS price,
                COALESCE(h.quantity * cp.price, h.quantity * lp.price, h.quantity * bp.price, h.book_cost) AS market_value,
                CASE
                    WHEN cp.price IS NOT NULL THEN cp.provider
                    WHEN lp.price IS NOT NULL THEN 'asset_quote_daily'
                    WHEN bp.price IS NOT NULL THEN 'broker'
                    ELSE NULL
                END AS live_price_provider,
                cp.market_session AS live_price_session,
                cp.updated_at AS live_price_updated_at
                FROM holdings h
                JOIN asset a ON a.asset_id = h.asset_id
                {_ENRICHED_ASSET_JOIN}
                LEFT JOIN latest_prices lp ON lp.asset_id = h.asset_id
                LEFT JOIN current_prices cp ON cp.asset_id = h.asset_id
                LEFT JOIN broker_prices bp ON bp.asset_id = h.asset_id
                LEFT JOIN broker_links bl ON bl.asset_id = h.asset_id
            )
            SELECT
                asset_id,
                COALESCE(symbol, asset_id),
                name,
                asset_type,
                asset_subtype,
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
                END,
                live_price_provider,
                live_price_session,
                live_price_updated_at
            FROM valued
            ORDER BY market_value DESC NULLS LAST, asset_id
            """,
            params,
        ).fetchall()
        exposure_maps = self._position_exposure_maps_by_asset([str(row[0]) for row in rows])
        positions = [self._position_summary(row, exposure_maps.get(str(row[0]))) for row in rows]
        self._position_summary_cache[portfolio_id] = positions
        return positions

    def _position_summary(self, row, exposure_maps: dict[str, dict[str, float]] | None = None) -> PositionSummary:
        classification = _cdr_classification_override(
            asset_id=row[0],
            symbol=row[1],
            name=row[2],
            sector=row[5],
            industry=row[6],
            country=row[7],
        )
        sector = _position_sector_label(
            asset_id=row[0],
            symbol=row[1],
            name=row[2],
            asset_type=row[3],
            asset_subtype=row[4],
            sector=classification["sector"],
            industry=classification["industry"],
        )
        industry = _canonical_industry_label(classification["industry"])
        country = _canonical_country_label(classification["country"])
        exposure_maps = exposure_maps or self._empty_position_exposure_maps()
        return PositionSummary(
            asset_id=row[0],
            symbol=row[1],
            name=row[2],
            asset_type=row[3],
            allocation_class=allocation_class(
                asset_id=row[0],
                symbol=row[1],
                name=row[2],
                asset_type=row[3],
                asset_subtype=row[4],
                sector=sector,
                industry=industry,
            ),
            sector=sector,
            industry=industry,
            country=country,
            currency=_valid_currency(row[8]) or "CAD",
            quantity=float(row[10]),
            book_cost=float(row[11]),
            latest_price=_float_or_none(row[12]),
            market_value=_float_or_none(row[13]),
            unrealized_gain=_float_or_none(row[14]),
            total_return_percent=_ratio_or_none(row[14], row[11]),
            weight=_float_or_none(row[15]),
            broker_linked=int(row[9]) > 0,
            broker_account_count=int(row[9]),
            sector_exposure=exposure_maps["sector"],
            industry_exposure=exposure_maps["industry"],
            country_exposure=exposure_maps["country"],
            currency_exposure=exposure_maps["currency"],
            price_source=row[16] or ("broker" if int(row[9]) > 0 else "asset_quote_daily"),
            price_session=row[17],
            price_timestamp=row[18],
            stale_price=row[12] is None,
            stale_reason=None if row[12] is not None else "no usable price",
        )

    def _empty_position_exposure_maps(self) -> dict[str, dict[str, float]]:
        return {
            "sector": {},
            "industry": {},
            "country": {},
            "currency": {},
        }

    def _position_exposure_maps(self, asset_id: str) -> dict[str, dict[str, float]]:
        return self._position_exposure_maps_by_asset([asset_id]).get(
            asset_id,
            self._empty_position_exposure_maps(),
        )

    def _position_exposure_maps_by_asset(self, asset_ids: list[str]) -> dict[str, dict[str, dict[str, float]]]:
        if not asset_ids:
            return {}
        if not _table_exists(self.conn, "etf_holding"):
            return {asset_id: self._empty_position_exposure_maps() for asset_id in asset_ids}
        unique_asset_ids = sorted({asset_id for asset_id in asset_ids if asset_id})
        if not unique_asset_ids:
            return {}
        placeholders = ", ".join("?" for _ in unique_asset_ids)
        try:
            rows = self.conn.execute(
                f"""
                SELECT asset_id, weight_pct, sector, country, currency
                FROM etf_holding
                WHERE asset_id IN ({placeholders})
                """,
                unique_asset_ids,
            ).fetchall()
        except Exception:
            return {asset_id: self._empty_position_exposure_maps() for asset_id in unique_asset_ids}
        maps_by_asset = {
            asset_id: self._empty_position_exposure_maps()
            for asset_id in unique_asset_ids
        }
        for asset_id, weight_pct, sector, country, currency in rows:
            weight = _normalized_weight(weight_pct)
            if weight is None or weight <= 0:
                continue
            values = {
                "sector": _canonical_sector_label(sector),
                "country": _canonical_country_label(country),
                "currency": _valid_currency(currency),
            }
            for key, value in values.items():
                if not value:
                    continue
                asset_maps = maps_by_asset.setdefault(str(asset_id), self._empty_position_exposure_maps())
                asset_maps[key][value] = asset_maps[key].get(value, 0.0) + weight
        return {
            asset_id: {key: _normalize_exposure_map(value) for key, value in maps.items()}
            for asset_id, maps in maps_by_asset.items()
        }

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
                SELECT asset_id, close AS price
                FROM asset_quote_daily
                WHERE close IS NOT NULL
                QUALIFY ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY date DESC) = 1
            ),
            current_prices AS (
                SELECT asset_id, price
                FROM current_asset_price
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
                    COALESCE(cp.price, lp.price, bp.price) AS price,
                    COALESCE(h.quantity * cp.price, h.quantity * lp.price, h.quantity * bp.price, h.book_cost) AS market_value
                FROM holdings h
                JOIN asset a ON a.asset_id = h.asset_id
                {_ENRICHED_ASSET_JOIN}
                LEFT JOIN latest_prices lp ON lp.asset_id = h.asset_id
                LEFT JOIN current_prices cp ON cp.asset_id = h.asset_id
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

    def performance(
        self,
        portfolio_id: int,
        benchmark_index_id: str | None = None,
        range_key: str = "3Y",
    ) -> PortfolioPerformanceResponse:
        portfolio = self.get_portfolio(portfolio_id)
        normalized_range = range_key.upper().strip()
        benchmark_index_id = benchmark_index_id or AnalyticsRepository(
            self.conn
        ).default_benchmark_for_portfolio(
            [
                PositionAnalytics(
                    portfolio_id=portfolio_id,
                    asset_id=item.asset_id,
                    qty=item.quantity,
                    book_cost=item.book_cost,
                    latest_price=item.latest_price,
                    market_value=item.market_value,
                    weight=item.weight,
                    unrealized_gain=item.unrealized_gain,
                )
                for item in self.list_positions(portfolio_id)
            ]
        )
        values, missing, performance_basis = self._actual_daily_portfolio_values(
            portfolio_id,
            normalized_range,
        )
        benchmark_prices = (
            AnalyticsRepository(self.conn).benchmark_price_history(benchmark_index_id)
            if benchmark_index_id
            else []
        )
        benchmark_by_date = {point.date: point.close for point in benchmark_prices}
        if values:
            start_value = values[0]["value"]
            start_benchmark = benchmark_by_date.get(values[0]["date"])
        else:
            start_value = None
            start_benchmark = None
        points: list[PortfolioPerformancePoint] = []
        portfolio_prices: list[PricePoint] = []
        benchmark_aligned: list[PricePoint] = []
        previous_value: float | None = None
        return_index = 100.0
        for row in values:
            value = row["value"]
            flow = row["external_flow"]
            if previous_value and previous_value > 0 and value is not None:
                return_index *= max(0.0, (value - flow) / previous_value)
            previous_value = value
            benchmark_value = benchmark_by_date.get(row["date"])
            benchmark_index = (
                100.0 * benchmark_value / start_benchmark
                if benchmark_value is not None and start_benchmark
                else None
            )
            points.append(
                PortfolioPerformancePoint(
                    date=row["date"],
                    portfolio_value=value,
                    portfolio_return_index=return_index if start_value else None,
                    benchmark_return_index=benchmark_index,
                )
            )
            if value is not None and value > 0:
                portfolio_prices.append(PricePoint(row["date"], return_index))
            if benchmark_index is not None and benchmark_index > 0:
                benchmark_aligned.append(PricePoint(row["date"], benchmark_index))
        risk = risk_return_metrics(portfolio_prices) if len(portfolio_prices) >= 2 else None
        benchmark_risk = (
            risk_return_metrics(benchmark_aligned) if len(benchmark_aligned) >= 2 else None
        )
        return PortfolioPerformanceResponse(
            portfolio_id=portfolio_id,
            benchmark=benchmark_index_id,
            base_currency=portfolio.base_ccy,
            start_date=points[0].date if points else None,
            end_date=points[-1].date if points else None,
            range=normalized_range,
            methodology=performance_basis,
            calendar_alignment="portfolio valuation dates with same-date benchmark observations",
            normalized_initial_value=100.0,
            actual_twr_cagr=risk.cagr if risk else None,
            historical_cumulative_return=risk.cumulative_return if risk else None,
            benchmark_cagr=benchmark_risk.cagr if benchmark_risk else None,
            excess_cagr=(
                (risk.cagr - benchmark_risk.cagr)
                if risk and benchmark_risk and risk.cagr is not None and benchmark_risk.cagr is not None
                else None
            ),
            observation_count=len(points),
            coverage=(
                sum(float(row.get("coverage") or 0.0) for row in values) / len(values)
                if values
                else None
            ),
            missing_inputs=missing,
            metric_insights=self._performance_metric_insights(
                portfolio_id=portfolio_id,
                actual_twr_cagr=risk.cagr if risk else None,
                benchmark_cagr=benchmark_risk.cagr if benchmark_risk else None,
                excess_cagr=(
                    (risk.cagr - benchmark_risk.cagr)
                    if risk
                    and benchmark_risk
                    and risk.cagr is not None
                    and benchmark_risk.cagr is not None
                    else None
                ),
                coverage=(
                    sum(float(row.get("coverage") or 0.0) for row in values) / len(values)
                    if values
                    else None
                ),
                missing_inputs=missing,
            ),
            points=points,
            as_of=datetime.now(UTC),
        )

    def risk(
        self,
        portfolio_id: int,
        benchmark_index_id: str | None = None,
        risk_free_rate: float = 0.0,
        range_key: str = "3Y",
    ) -> PortfolioRiskResponse:
        report = self._stored_portfolio_analytics(portfolio_id)
        if (
            report is None
            or risk_free_rate != 0.0
            or (
                benchmark_index_id is not None
                and benchmark_index_id != report.benchmark_index_id
            )
        ):
            report = AnalyticsEngine(AnalyticsRepository(self.conn)).portfolio_report(
                portfolio_id=portfolio_id,
                benchmark_index_id=benchmark_index_id,
                risk_free_rate=risk_free_rate,
            )
        risk = report.risk
        relative = report.relative
        decomposition = report.risk_decomposition
        risk_concentration = None
        contributions = [
            item.percent_of_portfolio_volatility
            for item in decomposition.volatility_contributions
            if item.percent_of_portfolio_volatility is not None
        ]
        if contributions:
            risk_concentration = sum(value * value for value in contributions)
        return PortfolioRiskResponse(
            portfolio_id=portfolio_id,
            benchmark=report.benchmark_index_id,
            risk_free_rate=risk_free_rate,
            risk_free_rate_source="request parameter",
            risk_free_rate_date=date.today(),
            lookback=range_key,
            return_frequency="daily",
            annualized_return=risk.cagr if risk else None,
            annualized_volatility=risk.annualized_volatility if risk else None,
            sharpe_ratio=risk.sharpe_ratio if risk else None,
            sortino_ratio=risk.sortino_ratio if risk else None,
            beta=relative.beta if relative else None,
            alpha=relative.alpha_annualized if relative else None,
            correlation=relative.correlation if relative else None,
            maximum_drawdown=risk.max_drawdown if risk else None,
            downside_deviation=risk.downside_deviation if risk else None,
            observation_count=risk.observations if risk else 0,
            effective_number_of_holdings=decomposition.effective_asset_count,
            largest_position=decomposition.largest_position_weight,
            hhi=decomposition.concentration_hhi,
            weight_balance_score=decomposition.diversification_score,
            asset_class_concentration=decomposition.asset_class_exposure,
            sector_concentration=decomposition.sector_exposure,
            geographic_concentration=decomposition.country_exposure,
            currency_concentration=decomposition.currency_exposure,
            average_pairwise_correlation=decomposition.average_pairwise_correlation,
            risk_contribution_concentration=risk_concentration,
            missing_inputs=report.missing_inputs + decomposition.missing_inputs,
            metric_insights=self._risk_metric_insights(report),
            as_of=getattr(report, "refreshed_at", datetime.now(UTC)),
        )

    def fundamentals(
        self,
        portfolio_id: int,
        horizon_years: int = 5,
    ) -> PortfolioFundamentalsResponse:
        portfolio = self.get_portfolio(portfolio_id)
        report = self._stored_portfolio_analytics(portfolio_id)
        if report is None:
            report = AnalyticsEngine(AnalyticsRepository(self.conn)).portfolio_report(
                portfolio_id
            )
        positions = {item.asset_id: item for item in self.list_positions(portfolio_id)}
        contributions = report.valuation.position_contributions
        coverage_by_metric = {
            "expected_cagr": self._metric_coverage(contributions, "expected_cagr"),
            "pe_ratio": self._metric_coverage(contributions, "pe_ratio"),
            "price_to_free_cash_flow": self._metric_coverage(
                contributions,
                "price_to_free_cash_flow",
                applicable=lambda item: item.fcf_metrics_applicable,
            ),
            "dividend_yield": self._metric_coverage(contributions, "dividend_yield"),
            "margin_of_safety": self._metric_coverage(
                contributions,
                "margin_of_safety",
                applicable=lambda item: item.fcf_metrics_applicable,
            ),
        }

        holdings: list[PortfolioFundamentalHolding] = []
        for item in contributions:
            position = positions.get(item.asset_id)
            missing = []
            if item.expected_cagr is None:
                missing.append("forward expected CAGR")
            if item.allocation_class in {"Stock", "CDR"} and item.pe_ratio is None:
                missing.append("P/E")
            if item.fcf_metrics_applicable and item.price_to_free_cash_flow is None:
                missing.append("P/FCF")
            holdings.append(
                PortfolioFundamentalHolding(
                    asset_id=item.asset_id,
                    symbol=position.symbol if position else item.asset_id,
                    allocation_class=item.allocation_class,
                    valuation_asset_id=item.valuation_asset_id,
                    valuation_source=item.valuation_source,
                    fcf_metrics_applicable=item.fcf_metrics_applicable,
                    fee_adjustment=item.fee_adjustment,
                    market_value=position.market_value if position else None,
                    weight=item.weight,
                    expected_cagr=item.expected_cagr,
                    expected_cagr_contribution=item.weighted_expected_cagr_contribution,
                    pe_ratio=item.pe_ratio,
                    price_to_free_cash_flow=item.price_to_free_cash_flow,
                    dividend_yield=item.dividend_yield,
                    margin_of_safety=item.margin_of_safety,
                    coverage_status="covered" if not missing else "partial" if len(missing) < 3 else "missing",
                    missing_inputs=missing,
                )
            )
        as_of = getattr(report, "refreshed_at", datetime.now(UTC))
        metric_insights = self._fundamental_metric_insights(
            report.valuation.position_contributions,
            positions,
            coverage_by_metric,
        )
        return PortfolioFundamentalsResponse(
            portfolio_id=portfolio_id,
            base_currency=portfolio.base_ccy,
            horizon_years=horizon_years,
            weighted_expected_cagr=PortfolioMetricValue(
                value=report.valuation.weighted_expected_cagr,
                coverage=coverage_by_metric["expected_cagr"],
                as_of=as_of,
                reason=None if report.valuation.weighted_expected_cagr is not None else "missing valuation inputs",
            ),
            pe_ratio=PortfolioMetricValue(
                value=report.valuation.weighted_pe_ratio,
                coverage=coverage_by_metric["pe_ratio"],
                as_of=as_of,
            ),
            price_to_free_cash_flow=PortfolioMetricValue(
                value=report.valuation.weighted_price_to_free_cash_flow,
                coverage=coverage_by_metric["price_to_free_cash_flow"],
                as_of=as_of,
            ),
            revenue_growth=PortfolioMetricValue(reason="not yet rolled up from statements", coverage=0.0, as_of=as_of),
            eps_growth=PortfolioMetricValue(reason="not yet rolled up from statements", coverage=0.0, as_of=as_of),
            free_cash_flow_growth=PortfolioMetricValue(reason="not yet rolled up from statements", coverage=0.0, as_of=as_of),
            operating_margin=PortfolioMetricValue(reason="not yet rolled up from statements", coverage=0.0, as_of=as_of),
            free_cash_flow_margin=PortfolioMetricValue(reason="not yet rolled up from statements", coverage=0.0, as_of=as_of),
            dividend_yield=PortfolioMetricValue(
                value=report.valuation.weighted_dividend_yield,
                coverage=coverage_by_metric["dividend_yield"],
                as_of=as_of,
            ),
            margin_of_safety=PortfolioMetricValue(
                value=report.valuation.weighted_margin_of_safety,
                coverage=coverage_by_metric["margin_of_safety"],
                as_of=as_of,
            ),
            holdings=holdings,
            missing_inputs=report.valuation.missing_inputs,
            metric_insights=metric_insights,
            as_of=as_of,
        )

    def _stored_portfolio_analytics(
        self,
        portfolio_id: int,
    ) -> _StoredPortfolioAnalytics | None:
        row = self.conn.execute(
            """
            SELECT payload_json, refreshed_at
            FROM portfolio_analytics_snapshot
            WHERE portfolio_id = ?
            ORDER BY snapshot_date DESC, refreshed_at DESC
            LIMIT 1
            """,
            [portfolio_id],
        ).fetchone()
        if row is None:
            return None
        payload = _json_dict(row[0])
        risk_payload = payload.get("risk")
        relative_payload = payload.get("relative")
        decomposition_payload = _json_dict(payload.get("risk_decomposition"))
        valuation_payload = _json_dict(payload.get("valuation"))
        if not decomposition_payload or not valuation_payload:
            return None
        try:
            volatility_contributions = [
                AssetRiskContribution(**_json_dict(item))
                for item in decomposition_payload.get(
                    "volatility_contributions",
                    [],
                )
            ]
            decomposition = PortfolioRiskDecomposition(
                **{
                    **decomposition_payload,
                    "volatility_contributions": volatility_contributions,
                }
            )
            position_contributions = [
                PositionValuationContribution(**_json_dict(item))
                for item in valuation_payload.get("position_contributions", [])
            ]
            valuation = PortfolioValuationRollup(
                **{
                    **valuation_payload,
                    "position_contributions": position_contributions,
                }
            )
            risk = (
                RiskReturnMetrics(**_json_dict(risk_payload))
                if risk_payload is not None
                else None
            )
            relative = (
                RelativeRiskMetrics(**_json_dict(relative_payload))
                if relative_payload is not None
                else None
            )
        except (TypeError, ValueError):
            return None
        return _StoredPortfolioAnalytics(
            portfolio_id=portfolio_id,
            benchmark_index_id=payload.get("benchmark_index_id"),
            risk=risk,
            relative=relative,
            risk_decomposition=decomposition,
            valuation=valuation,
            missing_inputs=[
                str(item) for item in payload.get("missing_inputs", [])
            ],
            refreshed_at=row[1],
        )

    def _metric_coverage(
        self,
        contributions: list[Any],
        attr: str,
        applicable: Callable[[Any], bool] | None = None,
    ) -> float | None:
        scoped = [item for item in contributions if applicable is None or applicable(item)]
        if not scoped:
            return None
        total_weight = sum(item.weight or 0.0 for item in scoped)
        if total_weight <= 0:
            return None
        return min(
            1.0,
            sum(
                item.weight or 0.0
                for item in scoped
                if getattr(item, attr, None) is not None
            )
            / total_weight,
        )

    def _fundamental_metric_insights(
        self,
        contributions: list[Any],
        positions: dict[str, PositionSummary],
        coverage_by_metric: dict[str, float | None],
    ) -> list[PortfolioMetricInsight]:
        configs = [
            (
                "weighted_expected_cagr",
                "Forward expected CAGR",
                "expected_cagr",
                "percent",
                "sum(holding weight x fee-adjusted holding expected CAGR)",
                (
                    "Holding forecasts come from stored underlying company valuation, growth, "
                    "dividend, and price-history inputs. CDR rows use the underlying company "
                    "forecast and subtract the wrapper fee adjustment."
                ),
                False,
            ),
            (
                "pe_ratio",
                "P/E ratio",
                "pe_ratio",
                "ratio",
                "sum(holding weight x holding P/E) / covered weight",
                "Holding P/E uses the valuation asset's latest EPS and market price.",
                True,
            ),
            (
                "price_to_free_cash_flow",
                "Price to free cash flow",
                "price_to_free_cash_flow",
                "ratio",
                "sum(holding weight x holding P/FCF) / covered weight",
                "Holding P/FCF uses free cash flow per share from stored cash-flow statements.",
                True,
            ),
            (
                "dividend_yield",
                "Dividend yield",
                "dividend_yield",
                "percent",
                "sum(holding weight x dividend yield) / covered weight",
                "Dividend yield uses recent stored dividend events divided by the valuation price.",
                True,
            ),
            (
                "margin_of_safety",
                "Margin of safety",
                "margin_of_safety",
                "percent",
                "sum(holding weight x DCF margin of safety) / covered weight",
                "Margin of safety comes from the base discounted cash-flow scenario.",
                True,
            ),
        ]
        insights: list[PortfolioMetricInsight] = []
        for metric, label, attr, unit, formula, methodology, normalize in configs:
            coverage = coverage_by_metric.get(attr)
            value = self._portfolio_metric_rollup(contributions, attr, normalize)
            warnings: list[str] = []
            if coverage is not None and coverage < 0.999:
                warnings.append(f"{coverage:.1%} of portfolio weight has {label} inputs.")
            if attr == "expected_cagr" and any(item.fee_adjustment for item in contributions):
                warnings.append("CDR expected CAGR is net of wrapper fee adjustment.")
            insights.append(
                PortfolioMetricInsight(
                    metric=metric,
                    label=label,
                    value=value,
                    unit=unit,
                    formula=formula,
                    methodology=methodology,
                    coverage=coverage,
                    contributors=self._fundamental_contributors(
                        contributions, positions, attr, normalize
                    ),
                    warnings=warnings,
                )
            )
        return insights

    def _portfolio_metric_rollup(
        self,
        contributions: list[Any],
        attr: str,
        normalize: bool,
    ) -> float | None:
        weighted_sum = 0.0
        covered_weight = 0.0
        present = False
        for item in contributions:
            value = getattr(item, attr, None)
            weight = item.weight
            if value is None or weight is None:
                continue
            present = True
            weighted_sum += weight * value
            covered_weight += weight
        if not present:
            return None
        if normalize:
            return weighted_sum / covered_weight if covered_weight else None
        return weighted_sum

    def _fundamental_contributors(
        self,
        contributions: list[Any],
        positions: dict[str, PositionSummary],
        attr: str,
        normalize: bool,
    ) -> list[PortfolioMetricContributor]:
        rows: list[tuple[float, PortfolioMetricContributor]] = []
        denominator = self._metric_coverage(contributions, attr) if normalize else 1.0
        raw_values: list[float] = []
        for item in contributions:
            value = getattr(item, attr, None)
            weight = item.weight
            if value is None or weight is None:
                continue
            contribution = weight * value / denominator if denominator else None
            if contribution is not None:
                raw_values.append(contribution)
        total_abs = sum(abs(value) for value in raw_values)
        for item in contributions:
            value = getattr(item, attr, None)
            weight = item.weight
            if value is None or weight is None:
                continue
            contribution = weight * value / denominator if denominator else None
            position = positions.get(item.asset_id)
            explanation = item.valuation_source
            if item.fee_adjustment is not None and attr == "expected_cagr":
                explanation = f"{explanation}; fee drag {item.fee_adjustment:.2%}"
            rows.append(
                (
                    abs(contribution or 0.0),
                    PortfolioMetricContributor(
                        asset_id=item.asset_id,
                        symbol=position.symbol if position else item.asset_id,
                        metric_value=value,
                        weight=weight,
                        contribution=contribution,
                        contribution_share=(
                            abs(contribution) / total_abs
                            if contribution is not None and total_abs > 0
                            else None
                        ),
                        explanation=explanation,
                    ),
                )
            )
        return [row for _sort_key, row in sorted(rows, key=lambda item: item[0], reverse=True)[:8]]

    def _performance_metric_insights(
        self,
        portfolio_id: int,
        actual_twr_cagr: float | None,
        benchmark_cagr: float | None,
        excess_cagr: float | None,
        coverage: float | None,
        missing_inputs: list[str],
    ) -> list[PortfolioMetricInsight]:
        contributors = self._position_value_contributors(portfolio_id)
        warning = (
            "Contributor rows show current value share; actual TWR CAGR is calculated from "
            "daily transaction-aware portfolio values and is not attributed to current holdings."
        )
        configs = [
            (
                "actual_twr_cagr",
                "Actual TWR CAGR",
                actual_twr_cagr,
                "cagr(portfolio TWR index start, portfolio TWR index end, elapsed years)",
                "The service builds daily portfolio values from transactions and stored prices, then chains subperiod returns around external cash flows.",
            ),
            (
                "benchmark_cagr",
                "Benchmark CAGR",
                benchmark_cagr,
                "cagr(benchmark return index start, benchmark return index end, elapsed years)",
                "Benchmark CAGR uses same-date stored benchmark closes aligned to portfolio valuation dates.",
            ),
            (
                "excess_cagr",
                "Excess CAGR",
                excess_cagr,
                "actual TWR CAGR - benchmark CAGR",
                "Excess return compares the portfolio TWR series against the selected benchmark series.",
            ),
        ]
        return [
            PortfolioMetricInsight(
                metric=metric,
                label=label,
                value=value,
                unit="percent",
                formula=formula,
                methodology=methodology,
                coverage=coverage,
                contributors=contributors,
                warnings=[warning, *missing_inputs[:5]],
            )
            for metric, label, value, formula, methodology in configs
        ]

    def _risk_metric_insights(self, report: Any) -> list[PortfolioMetricInsight]:
        positions = {item.asset_id: item for item in self.list_positions(report.portfolio_id)}
        volatility_rows: list[tuple[float, PortfolioMetricContributor]] = []
        for item in report.risk_decomposition.volatility_contributions:
            position = positions.get(item.asset_id)
            contribution = item.percent_of_portfolio_volatility
            volatility_rows.append(
                (
                    abs(contribution or 0.0),
                    PortfolioMetricContributor(
                        asset_id=item.asset_id,
                        symbol=position.symbol if position else item.asset_id,
                        metric_value=item.annualized_volatility,
                        weight=item.weight,
                        contribution=contribution,
                        contribution_share=abs(contribution) if contribution is not None else None,
                        explanation="marginal covariance contribution to portfolio volatility",
                    ),
                )
            )
        concentration_rows: list[tuple[float, PortfolioMetricContributor]] = []
        for position in positions.values():
            weight = position.weight
            if weight is None:
                continue
            hhi_contribution = weight * weight
            concentration_rows.append(
                (
                    hhi_contribution,
                    PortfolioMetricContributor(
                        asset_id=position.asset_id,
                        symbol=position.symbol,
                        metric_value=weight,
                        weight=weight,
                        contribution=hhi_contribution,
                        contribution_share=(
                            hhi_contribution / report.risk_decomposition.concentration_hhi
                            if report.risk_decomposition.concentration_hhi
                            else None
                        ),
                        explanation="weight squared contribution to concentration HHI",
                    ),
                )
            )
        return [
            PortfolioMetricInsight(
                metric="annualized_volatility",
                label="Annualized volatility",
                value=report.risk_decomposition.portfolio_volatility,
                unit="percent",
                formula="sqrt(weighted covariance matrix) x sqrt(252)",
                methodology="Uses overlapping stored adjusted daily returns for current positive-weight holdings.",
                coverage=None,
                contributors=[
                    row
                    for _sort_key, row in sorted(
                        volatility_rows, key=lambda item: item[0], reverse=True
                    )[:8]
                ],
                warnings=report.risk_decomposition.missing_inputs,
            ),
            PortfolioMetricInsight(
                metric="concentration_hhi",
                label="Concentration HHI",
                value=report.risk_decomposition.concentration_hhi,
                unit="ratio",
                formula="sum(holding weight squared)",
                methodology="Uses current backend-valued portfolio weights.",
                coverage=None,
                contributors=[
                    row
                    for _sort_key, row in sorted(
                        concentration_rows, key=lambda item: item[0], reverse=True
                    )[:8]
                ],
                warnings=[],
            ),
            PortfolioMetricInsight(
                metric="largest_position",
                label="Largest position",
                value=report.risk_decomposition.largest_position_weight,
                unit="percent",
                formula="max(current holding weight)",
                methodology="Uses current backend-valued portfolio weights.",
                coverage=None,
                contributors=[
                    row
                    for _sort_key, row in sorted(
                        concentration_rows, key=lambda item: item[1].weight or 0.0, reverse=True
                    )[:8]
                ],
                warnings=[],
            ),
        ]

    def _position_value_contributors(self, portfolio_id: int) -> list[PortfolioMetricContributor]:
        positions = [
            item
            for item in self.list_positions(portfolio_id)
            if item.market_value is not None and item.market_value > 0
        ]
        total = sum(item.market_value or 0.0 for item in positions)
        rows = []
        for item in positions:
            value = item.market_value or 0.0
            value_share = value / total if total > 0 else None
            rows.append(
                PortfolioMetricContributor(
                    asset_id=item.asset_id,
                    symbol=item.symbol,
                    metric_value=value_share,
                    weight=item.weight,
                    contribution=value_share,
                    contribution_share=value_share,
                    explanation="current backend-valued market value share",
                )
            )
        return sorted(rows, key=lambda item: item.contribution_share or 0.0, reverse=True)[:8]

    def optimization_preview(
        self,
        portfolio_id: int,
        request: OptimizationPreviewRequest,
    ) -> OptimizationPreviewResponse:
        positions = self.list_positions(portfolio_id)
        active = [
            item
            for item in positions
            if item.weight is not None and item.weight > 0 and item.asset_id not in request.constraints.excluded_assets
        ]
        excluded = [item.asset_id for item in positions if item.asset_id in request.constraints.excluded_assets]
        current = {item.asset_id: float(item.weight or 0.0) for item in positions}
        warnings: list[str] = []
        if not active:
            return OptimizationPreviewResponse(
                portfolio_id=portfolio_id,
                objective=request.objective,
                status="infeasible",
                solver_message="No eligible holdings with positive current weights.",
                current_weights=current,
                optimized_weights=current,
                weight_deltas={key: 0.0 for key in current},
                before=OptimizationMetricSet(),
                after=OptimizationMetricSet(),
                estimated_turnover=0.0,
                excluded_assets=excluded,
                warnings=["No eligible holdings."],
                assumptions=[],
                calculation_timestamp=datetime.now(UTC),
            )
        report = AnalyticsEngine(AnalyticsRepository(self.conn)).portfolio_report(portfolio_id)
        expected = {
            item.asset_id: item.expected_cagr
            for item in report.valuation.position_contributions
            if item.expected_cagr is not None
        }
        histories = {
            item.asset_id: AnalyticsRepository(self.conn).price_history(item.asset_id)
            for item in active
        }
        vol = {
            asset_id: risk_return_metrics(history).annualized_volatility
            for asset_id, history in histories.items()
            if len(history) >= 2
        }
        eligible = [item for item in active if expected.get(item.asset_id) is not None]
        if not eligible:
            warnings.append("No holdings have forward expected returns; optimization cannot rank assets.")
            optimized = current
            status = "infeasible"
            message = "Missing forward expected returns for every eligible holding."
        else:
            optimized = self._deterministic_weights(
                eligible=eligible,
                expected=expected,
                vol=vol,
                current=current,
                objective=request.objective,
                constraints=request.constraints,
            )
            status = "success" if abs(sum(optimized.values()) - 1.0) <= 0.0001 else "infeasible"
            message = "Deterministic constrained preview generated." if status == "success" else "Unable to allocate weights within constraints."
        deltas = {asset_id: optimized.get(asset_id, 0.0) - current.get(asset_id, 0.0) for asset_id in current}
        before = self._optimization_metrics(current, expected, histories, request.risk_free_rate)
        after = self._optimization_metrics(optimized, expected, histories, request.risk_free_rate)
        metadata = AnalyticsRepository(self.conn).asset_exposure_metadata(list(current))
        return OptimizationPreviewResponse(
            portfolio_id=portfolio_id,
            objective=request.objective,
            status=status,
            solver_message=message,
            current_weights=current,
            optimized_weights=optimized,
            weight_deltas=deltas,
            before=before,
            after=after,
            sector_exposure_before=dimension_exposure(current, metadata, "sector"),
            sector_exposure_after=dimension_exposure(optimized, metadata, "sector"),
            estimated_turnover=sum(abs(value) for value in deltas.values()) / 2,
            binding_constraints=_binding_constraints(optimized, request.constraints.max_weight),
            excluded_assets=excluded,
            input_coverage={
                "expected_returns": sum(item.weight or 0.0 for item in eligible),
                "price_history": sum((item.weight or 0.0) for item in active if histories.get(item.asset_id)),
            },
            warnings=warnings,
            assumptions=[
                "Forward expected returns come from the existing portfolio valuation rollup.",
                "Historical covariance uses stored adjusted daily closes.",
                "Preview does not change stored positions.",
            ],
            calculation_timestamp=datetime.now(UTC),
        )

    def _actual_daily_portfolio_values(
        self,
        portfolio_id: int,
        range_key: str,
    ) -> tuple[list[dict[str, Any]], list[str], str]:
        txns = self.conn.execute(
            """
            SELECT time_stamp::DATE, LOWER(txn_type), asset_id, qty, price, ccy, cash_amt, fee_amt
            FROM txn
            WHERE portfolio_id = ?
            ORDER BY time_stamp, txn_id
            """,
            [portfolio_id],
        ).fetchall()
        if not txns:
            return self._position_based_daily_portfolio_values(
                portfolio_id,
                range_key,
            )
        asset_ids = sorted({row[2] for row in txns if row[2]})
        if not asset_ids:
            return [], ["asset transactions"], (
                "actual daily transaction-aware time-weighted return; external cash "
                "flows break return subperiods"
            )
        first_date = min(row[0] for row in txns)
        placeholders = ", ".join("?" for _ in asset_ids)
        latest_price_date = self.conn.execute(
            f"""
            SELECT MAX(date)
            FROM asset_quote_daily
            WHERE asset_id IN ({placeholders})
              AND close IS NOT NULL
            """,
            asset_ids,
        ).fetchone()[0]
        if latest_price_date is None:
            return [], ["daily close prices"], (
                "actual daily transaction-aware time-weighted return; external cash "
                "flows break return subperiods"
            )
        range_start = _range_start_date(range_key, latest_price_date)
        if range_start is not None:
            first_date = max(first_date, range_start)
        price_rows = self.conn.execute(
            f"""
            SELECT asset_id, date, close
            FROM asset_quote_daily
            WHERE asset_id IN ({placeholders})
              AND close IS NOT NULL
              AND date >= ?
            ORDER BY date
            """,
            [*asset_ids, first_date],
        ).fetchall()
        if len({row[1] for row in price_rows}) < 2 and range_key.upper().strip() == "1D":
            fallback_dates = [
                row[0]
                for row in self.conn.execute(
                    f"""
                    SELECT DISTINCT date
                    FROM asset_quote_daily
                    WHERE asset_id IN ({placeholders})
                      AND close IS NOT NULL
                    ORDER BY date DESC
                    LIMIT 2
                    """,
                    asset_ids,
                ).fetchall()
            ]
            if len(fallback_dates) >= 2:
                first_date = min(fallback_dates)
                price_rows = self.conn.execute(
                    f"""
                    SELECT asset_id, date, close
                    FROM asset_quote_daily
                    WHERE asset_id IN ({placeholders})
                      AND close IS NOT NULL
                      AND date >= ?
                    ORDER BY date
                    """,
                    [*asset_ids, first_date],
                ).fetchall()
        if not price_rows:
            return [], ["daily close prices"], (
                "actual daily transaction-aware time-weighted return; external cash "
                "flows break return subperiods"
            )
        prices: dict[str, dict[date, float]] = {}
        dates = set()
        for asset_id, price_date, close in price_rows:
            prices.setdefault(asset_id, {})[price_date] = float(close)
            dates.add(price_date)
        first_price_dates = {
            asset_id: min(asset_prices)
            for asset_id, asset_prices in prices.items()
            if asset_prices
        }
        positions = {asset_id: 0.0 for asset_id in asset_ids}
        rows: list[dict[str, Any]] = []
        tx_index = 0
        missing: set[str] = set()
        last_prices: dict[str, float] = {}
        txns = [row for row in txns if row[0] <= max(dates)]
        for value_date in sorted(dates):
            for asset_id, asset_prices in prices.items():
                close = asset_prices.get(value_date)
                if close is not None:
                    last_prices[asset_id] = close
            external_flow = 0.0
            while tx_index < len(txns) and txns[tx_index][0] <= value_date:
                _txn_date, txn_type, asset_id, qty, _price, _ccy, cash_amt, fee_amt = txns[tx_index]
                if asset_id and qty is not None and txn_type in {"buy", "sell"}:
                    positions[asset_id] = positions.get(asset_id, 0.0) + float(qty)
                if txn_type in {"deposit", "contribution"} and cash_amt is not None:
                    external_flow += abs(float(cash_amt))
                if txn_type in {"withdrawal", "transfer_out"} and cash_amt is not None:
                    external_flow -= abs(float(cash_amt))
                if fee_amt:
                    external_flow -= abs(float(fee_amt))
                tx_index += 1
            value = 0.0
            valued_count = 0
            active_positions = sum(1 for qty in positions.values() if qty)
            for asset_id, qty in positions.items():
                if not qty:
                    continue
                close = last_prices.get(asset_id)
                if close is None:
                    if (
                        asset_id not in first_price_dates
                        or value_date >= first_price_dates[asset_id]
                    ):
                        missing.add(
                            f"{asset_id}: daily close on {value_date.isoformat()}"
                        )
                    continue
                value += qty * close
                valued_count += 1
            coverage = valued_count / active_positions if active_positions else 0.0
            if value > 0 and coverage >= 0.95:
                rows.append(
                    {
                        "date": value_date,
                        "value": value,
                        "external_flow": external_flow,
                        "coverage": min(1.0, coverage),
                    }
                )
        return rows, sorted(missing)[:25], (
            "actual daily transaction-aware time-weighted return; external cash flows "
            "break return subperiods; non-trading days carry forward the latest close"
        )

    def _position_based_daily_portfolio_values(
        self,
        portfolio_id: int,
        range_key: str,
    ) -> tuple[list[dict[str, Any]], list[str], str]:
        holdings = self.conn.execute(
            f"""
            SELECT asset_id, quantity
            FROM ({_HOLDINGS_SQL}) holdings
            WHERE portfolio_id = ?
              AND quantity <> 0
            ORDER BY asset_id
            """,
            [portfolio_id],
        ).fetchall()
        if not holdings:
            return [], ["portfolio holdings"], (
                "current-position historical valuation proxy"
            )
        asset_ids = [str(row[0]) for row in holdings]
        quantities = {str(row[0]): float(row[1]) for row in holdings}
        placeholders = ", ".join("?" for _ in asset_ids)
        latest_price_date = self.conn.execute(
            f"""
            SELECT MAX(date)
            FROM asset_quote_daily
            WHERE asset_id IN ({placeholders})
              AND COALESCE(adj_close, close) IS NOT NULL
            """,
            asset_ids,
        ).fetchone()[0]
        if latest_price_date is None:
            return [], ["daily close prices"], (
                "current-position historical valuation proxy"
            )
        range_start = _range_start_date(range_key, latest_price_date)
        where_start = "AND date >= ?" if range_start is not None else ""
        params: list[Any] = [*asset_ids]
        if range_start is not None:
            params.append(range_start)
        price_rows = self.conn.execute(
            f"""
            SELECT asset_id, date, COALESCE(adj_close, close)
            FROM asset_quote_daily
            WHERE asset_id IN ({placeholders})
              AND COALESCE(adj_close, close) IS NOT NULL
              {where_start}
            ORDER BY date, asset_id
            """,
            params,
        ).fetchall()
        prices: dict[str, dict[date, float]] = {}
        dates: set[date] = set()
        for asset_id, price_date, close in price_rows:
            prices.setdefault(str(asset_id), {})[price_date] = float(close)
            dates.add(price_date)
        first_price_dates = {
            asset_id: min(asset_prices)
            for asset_id, asset_prices in prices.items()
            if asset_prices
        }
        rows: list[dict[str, Any]] = []
        missing: set[str] = set()
        last_prices: dict[str, float] = {}
        for value_date in sorted(dates):
            for asset_id, asset_prices in prices.items():
                close = asset_prices.get(value_date)
                if close is not None:
                    last_prices[asset_id] = close
            value = 0.0
            valued_count = 0
            for asset_id, quantity in quantities.items():
                close = last_prices.get(asset_id)
                if close is None:
                    if (
                        asset_id not in first_price_dates
                        or value_date >= first_price_dates[asset_id]
                    ):
                        missing.add(
                            f"{asset_id}: daily close on or before "
                            f"{value_date.isoformat()}"
                        )
                    continue
                value += quantity * close
                valued_count += 1
            coverage = valued_count / len(quantities)
            if value > 0 and coverage >= 0.95:
                rows.append(
                    {
                        "date": value_date,
                        "value": value,
                        "external_flow": 0.0,
                        "coverage": coverage,
                    }
                )
        return rows, sorted(missing)[:25], (
            "current-position historical valuation proxy for broker-sourced holdings "
            "without transaction history; non-trading days carry forward the latest close"
        )

    def _deterministic_weights(
        self,
        *,
        eligible: list[PositionSummary],
        expected: dict[str, float | None],
        vol: dict[str, float | None],
        current: dict[str, float],
        objective: str,
        constraints,
    ) -> dict[str, float]:
        locked = {asset.upper().strip() for asset in constraints.locked_assets}
        optimized = {asset_id: 0.0 for asset_id in current}
        locked_weight = 0.0
        candidates: list[tuple[float, str]] = []
        for item in eligible:
            asset_id = item.asset_id
            if asset_id in locked:
                weight = current.get(asset_id, 0.0)
                optimized[asset_id] = weight
                locked_weight += weight
                continue
            expected_return = expected.get(asset_id)
            if expected_return is None:
                continue
            if objective == "max_risk_adjusted_return":
                asset_vol = vol.get(asset_id)
                score = expected_return / asset_vol if asset_vol and asset_vol > 0 else expected_return
            else:
                score = expected_return
            candidates.append((score, asset_id))
        remaining = max(0.0, 1.0 - constraints.cash_weight - locked_weight)
        for _score, asset_id in sorted(candidates, key=lambda item: (-item[0], item[1])):
            if remaining <= 0:
                break
            allocation = min(float(constraints.max_weight), remaining)
            if constraints.min_holding_weight and allocation < constraints.min_holding_weight:
                continue
            optimized[asset_id] = allocation
            remaining -= allocation
        if remaining > 0 and candidates:
            for _score, asset_id in sorted(candidates, key=lambda item: (-item[0], item[1])):
                room = float(constraints.max_weight) - optimized.get(asset_id, 0.0)
                if room <= 0:
                    continue
                add = min(room, remaining)
                optimized[asset_id] += add
                remaining -= add
                if remaining <= 0:
                    break
        return optimized

    def _optimization_metrics(
        self,
        weights: dict[str, float],
        expected: dict[str, float | None],
        histories: dict[str, list[PricePoint]],
        risk_free_rate: float,
    ) -> OptimizationMetricSet:
        present_returns = [
            weight * expected_return
            for asset_id, weight in weights.items()
            for expected_return in [expected.get(asset_id)]
            if expected_return is not None
        ]
        expected_cagr = sum(present_returns) if present_returns else None
        returns_by_asset, return_dates, aligned_weights = (
            self._aligned_optimization_returns(histories, weights)
        )
        volatility = portfolio_annualized_volatility(
            returns_by_asset,
            aligned_weights,
        )
        portfolio_returns = portfolio_returns_from_components(
            returns_by_asset,
            aligned_weights,
        )
        benchmark_prices = AnalyticsRepository(
            self.conn
        ).benchmark_price_history("SP500")
        benchmark_returns_by_date = {
            benchmark_prices[index].date: (
                benchmark_prices[index].close
                / benchmark_prices[index - 1].close
                - 1.0
            )
            for index in range(1, len(benchmark_prices))
            if benchmark_prices[index - 1].close > 0
        }
        paired = [
            (portfolio_return, benchmark_returns_by_date[return_date])
            for return_date, portfolio_return in zip(
                return_dates,
                portfolio_returns,
            )
            if return_date in benchmark_returns_by_date
        ]
        beta_value = (
            beta(
                [row[0] for row in paired],
                [row[1] for row in paired],
            )
            if len(paired) >= 2
            else None
        )
        if beta_value is None:
            beta_value = self._weighted_metadata_beta(aligned_weights)
        sharpe = (
            (expected_cagr - risk_free_rate) / volatility
            if expected_cagr is not None and volatility and volatility > 0
            else None
        )
        hhi = sum(weight * weight for weight in weights.values() if weight > 0)
        return OptimizationMetricSet(
            expected_cagr=expected_cagr,
            expected_volatility=volatility,
            expected_sharpe=sharpe,
            beta=beta_value,
            concentration_hhi=hhi if hhi > 0 else None,
        )

    def _aligned_optimization_returns(
        self,
        histories: dict[str, list[PricePoint]],
        weights: dict[str, float],
    ) -> tuple[dict[str, list[float]], list[date], dict[str, float]]:
        included = {
            asset_id: sorted(
                [point for point in history if point.close > 0],
                key=lambda point: point.date,
            )
            for asset_id, history in histories.items()
            if weights.get(asset_id, 0.0) > 0 and len(history) >= 2
        }
        included = {
            asset_id: history
            for asset_id, history in included.items()
            if len(history) >= 2
        }
        total_weight = sum(weights.get(asset_id, 0.0) for asset_id in included)
        if not included or total_weight <= 0:
            return {}, [], {}
        aligned_weights = {
            asset_id: weights.get(asset_id, 0.0) / total_weight
            for asset_id in included
        }
        by_asset = {
            asset_id: {point.date: point.close for point in history}
            for asset_id, history in included.items()
        }
        dates = sorted(
            {
                point_date
                for asset_prices in by_asset.values()
                for point_date in asset_prices
            }
        )
        last_prices: dict[str, float] = {}
        previous_prices: dict[str, float] | None = None
        returns_by_asset = {asset_id: [] for asset_id in included}
        return_dates: list[date] = []
        for point_date in dates:
            for asset_id, asset_prices in by_asset.items():
                close = asset_prices.get(point_date)
                if close is not None:
                    last_prices[asset_id] = close
            if len(last_prices) != len(included):
                continue
            if previous_prices is None:
                previous_prices = dict(last_prices)
                continue
            for asset_id in included:
                previous = previous_prices[asset_id]
                current = last_prices[asset_id]
                returns_by_asset[asset_id].append(
                    current / previous - 1.0
                    if previous > 0
                    else 0.0
                )
            return_dates.append(point_date)
            previous_prices = dict(last_prices)
        return returns_by_asset, return_dates, aligned_weights

    def _weighted_metadata_beta(
        self,
        weights: dict[str, float],
    ) -> float | None:
        if not weights:
            return None
        asset_ids = list(weights)
        placeholders = ", ".join("?" for _ in asset_ids)
        rows = self.conn.execute(
            f"""
            SELECT asset_id, market_beta
            FROM asset
            WHERE asset_id IN ({placeholders})
              AND market_beta IS NOT NULL
            """,
            asset_ids,
        ).fetchall()
        covered = [
            (weights.get(str(asset_id), 0.0), float(beta_value))
            for asset_id, beta_value in rows
            if weights.get(str(asset_id), 0.0) > 0
        ]
        covered_weight = sum(row[0] for row in covered)
        if covered_weight <= 0:
            return None
        return sum(weight * beta_value for weight, beta_value in covered) / covered_weight

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
                    close AS price,
                    ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY date DESC) AS price_rank
                FROM asset_quote_daily
                WHERE close IS NOT NULL
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

    def signals_summary(
        self,
        *,
        q: str | None,
        portfolio_id: int | None,
        owned: str | None,
        category: str | None,
        direction: str | None,
        status: str | None,
        min_strength: float | None,
        min_confidence: float | None,
        min_priority: float | None,
        sector: str | None,
        industry: str | None,
        freshness: str | None,
        completeness: str | None,
        triggered_after: date | None,
        triggered_before: date | None,
        include_retail_sentiment: bool,
        sort: str,
        limit: int,
        offset: int,
    ) -> SignalsSummaryResponse:
        stored_rows = self._stored_signal_rows(
            include_retail_sentiment=include_retail_sentiment
        )
        rows = stored_rows
        if not stored_rows:
            rows = self._current_signal_rows(include_retail_sentiment=include_retail_sentiment)
        classifications = self._signal_classifications(rows) if sector or industry else None
        filtered = [
            row for row in rows
            if self._signal_matches(
                row,
                q=q,
                portfolio_id=portfolio_id,
                owned=owned,
                category=category,
                direction=direction,
                status=status,
                min_strength=min_strength,
                min_confidence=min_confidence,
                min_priority=min_priority,
                sector=sector,
                industry=industry,
                freshness=freshness,
                completeness=completeness,
                triggered_after=triggered_after,
                triggered_before=triggered_before,
                classifications=classifications,
            )
        ]
        if sort == "efficacy":
            filtered = self._with_signal_efficacy_batch(filtered)
        filtered.sort(key=_signal_sort_key(sort), reverse=sort != "ticker")
        generated_at = datetime.now()
        data_dates = [row.data_as_of for row in rows if row.data_as_of is not None]
        computation_dates = [
            row.last_evaluated_at
            for row in rows
            if row.last_evaluated_at is not None
        ]
        needs_attention = [
            row for row in sorted(rows, key=lambda item: (item.portfolio_priority, item.confidence), reverse=True)
            if row.direction == "negative" and row.status in {"confirmed", "active", "weakening"}
        ][:5]
        top_opportunities = [
            row for row in sorted(rows, key=lambda item: (item.portfolio_priority, item.confidence), reverse=True)
            if row.direction == "positive" and row.status in {"confirmed", "active"}
        ][:5]
        page = filtered[offset : offset + limit]
        selected_ids = {
            row.signal_id
            for row in page + needs_attention + top_opportunities
        }
        selected = [row for row in rows if row.signal_id in selected_ids]
        if stored_rows:
            selected = self._hydrate_stored_signal_evidence(selected)
        selected = self._with_signal_efficacy_batch(selected)
        selected_by_id = {row.signal_id: row for row in selected}
        items = [selected_by_id.get(row.signal_id, row) for row in page]
        needs_attention = [selected_by_id.get(row.signal_id, row) for row in needs_attention]
        top_opportunities = [selected_by_id.get(row.signal_id, row) for row in top_opportunities]
        has_more = offset + len(items) < len(filtered)
        return SignalsSummaryResponse(
            items=items,
            total=len(filtered),
            limit=limit,
            offset=offset,
            has_more=has_more,
            next_offset=offset + len(items) if has_more else None,
            metrics=_signal_summary_metrics(rows),
            needs_attention=needs_attention,
            top_opportunities=top_opportunities,
            generated_at=generated_at,
            data_as_of=max(data_dates) if data_dates else None,
            last_successful_computation_at=(
                max(computation_dates) if computation_dates else generated_at
            ),
            partial_provider_failures=_signal_provider_failures(rows),
            stale_cached_results=any(row.status == "expired" for row in rows),
            model_version=_SIGNALS_MODEL_VERSION,
            methodology=_signals_methodology(include_retail_sentiment=include_retail_sentiment),
        )

    def signal_detail(self, signal_id: str) -> SignalDetailResponse:
        stored_rows = self._stored_signal_rows(
            include_retail_sentiment=True,
            signal_id=signal_id,
        )
        row = stored_rows[0] if stored_rows else None
        if row is None:
            row = next(
                (
                    item
                    for item in self._current_signal_rows(include_retail_sentiment=True)
                    if item.signal_id == signal_id
                ),
                None,
            )
        if row is None:
            raise LookupError(f"Signal not found: {signal_id}")
        if stored_rows:
            row = self._hydrate_stored_signal_evidence([row])[0]
        row = self._with_signal_efficacy_batch([row])[0]
        return SignalDetailResponse(
            **row.model_dump(),
            lifecycle=_signal_lifecycle(row),
            strength_history=self._signal_history(row),
            related_news=self._related_signal_news(row.asset_id),
            methodology=_signals_methodology(include_retail_sentiment=True),
            links={
                "ticker": f"/asset/{row.asset_id}",
                "fundamentals": f"/asset/{row.asset_id}",
                "compare": f"/compare?symbols={row.ticker}",
                "benchmarks": f"/benchmarks?asset={row.asset_id}",
                "signals": f"/signals?signal={row.signal_id}",
            },
            user_state=self._signal_user_state(signal_id),
        )

    def update_signal_user_state(self, signal_id: str, payload: SignalUserStateRequest) -> SignalUserState:
        stored_rows = self._stored_signal_rows(
            include_retail_sentiment=True,
            signal_id=signal_id,
        )
        row = stored_rows[0] if stored_rows else None
        if row is None:
            row = next(
                (
                    item
                    for item in self._current_signal_rows(include_retail_sentiment=True)
                    if item.signal_id == signal_id
                ),
                None,
            )
        if row is None:
            raise LookupError(f"Signal not found: {signal_id}")
        reviewed_at = datetime.now() if payload.reviewed else None
        self.conn.execute(
            """
            INSERT INTO signal_user_state(
                signal_id, definition_id, asset_id, reviewed_at, muted_until,
                dismissed_until, note, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, now(), now())
            ON CONFLICT (signal_id)
            DO UPDATE SET
                reviewed_at = COALESCE(EXCLUDED.reviewed_at, signal_user_state.reviewed_at),
                muted_until = COALESCE(EXCLUDED.muted_until, signal_user_state.muted_until),
                dismissed_until = COALESCE(EXCLUDED.dismissed_until, signal_user_state.dismissed_until),
                note = COALESCE(EXCLUDED.note, signal_user_state.note),
                updated_at = now()
            """,
            [
                row.signal_id,
                row.definition_id,
                row.asset_id,
                reviewed_at,
                payload.muted_until,
                payload.dismissed_until,
                payload.note,
            ],
        )
        return self._signal_user_state(signal_id)

    def create_signal_alert_rule(self, signal_id: str, payload: SignalAlertRuleRequest) -> SignalAlertRuleResponse:
        stored_rows = self._stored_signal_rows(
            include_retail_sentiment=True,
            signal_id=signal_id,
        )
        row = stored_rows[0] if stored_rows else None
        if row is None:
            row = next(
                (
                    item
                    for item in self._current_signal_rows(include_retail_sentiment=True)
                    if item.signal_id == signal_id
                ),
                None,
            )
        if row is None:
            raise LookupError(f"Signal not found: {signal_id}")
        result = self.conn.execute(
            """
            INSERT INTO signal_alert_rule(
                signal_id, definition_id, asset_id, condition, threshold, channel,
                is_active, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, TRUE, now(), now())
            RETURNING alert_rule_id
            """,
            [row.signal_id, row.definition_id, row.asset_id, payload.condition, payload.threshold, payload.channel],
        ).fetchone()
        return SignalAlertRuleResponse(
            alert_rule_id=int(result[0]),
            signal_id=row.signal_id,
            definition_id=row.definition_id,
            asset_id=row.asset_id,
            condition=payload.condition,
            threshold=payload.threshold,
            channel=payload.channel,
            is_active=True,
        )

    def refresh_signal_snapshots(
        self,
        *,
        include_retail_sentiment: bool = True,
    ) -> SignalSnapshotRefreshResponse:
        generated_at = datetime.now()
        rows = self._current_signal_rows(
            include_retail_sentiment=include_retail_sentiment
        )
        existing_active_ids = {
            str(item[0])
            for item in self.conn.execute(
                """
                SELECT signal_id
                FROM signal_evaluation_current
                WHERE model_version = ?
                  AND is_active = TRUE
                """,
                [_SIGNALS_MODEL_VERSION],
            ).fetchall()
        }
        current_ids = {row.signal_id for row in rows}
        stale_ids = sorted(existing_active_ids - current_ids)
        batch_size = 25
        for offset in range(0, len(rows), batch_size):
            self.conn.execute("BEGIN TRANSACTION")
            try:
                for row in rows[offset : offset + batch_size]:
                    self._persist_signal_evaluation(row)
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
        for offset in range(0, len(stale_ids), batch_size):
            self.conn.execute("BEGIN TRANSACTION")
            try:
                for signal_id in stale_ids[offset : offset + batch_size]:
                    self.conn.execute(
                        """
                        UPDATE signal_evaluation_current
                        SET is_active = FALSE, updated_at = now()
                        WHERE signal_id = ?
                        """,
                        [signal_id],
                    )
                    self.conn.execute(
                        "DELETE FROM signal_evidence WHERE signal_id = ?",
                        [signal_id],
                    )
                    self.conn.execute(
                        "DELETE FROM signal_portfolio_impact WHERE signal_id = ?",
                        [signal_id],
                    )
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
        return SignalSnapshotRefreshResponse(
            refreshed_count=len(rows),
            pruned_count=len(stale_ids),
            generated_at=generated_at,
            model_version=_SIGNALS_MODEL_VERSION,
        )

    def _stored_signal_rows(
        self,
        *,
        include_retail_sentiment: bool,
        signal_id: str | None = None,
    ) -> list[SignalRow]:
        conditions = ["c.model_version = ?", "c.is_active = TRUE"]
        parameters: list[Any] = [_SIGNALS_MODEL_VERSION]
        if not include_retail_sentiment:
            conditions.append("d.factor <> 'retail_sentiment'")
        if signal_id is not None:
            conditions.append("e.signal_id = ?")
            parameters.append(signal_id)
        rows = self.conn.execute(
            f"""
            SELECT
                e.signal_id, e.definition_id, e.asset_id,
                COALESCE(a.symbol, e.asset_id), a.name, a.exchange_code,
                d.signal_name, c.summary, d.category,
                c.direction, c.status, c.strength, c.confidence,
                c.portfolio_priority, c.raw_observed_value, c.normalized_value,
                c.trigger_threshold, d.lookback_period, c.first_detected_at,
                c.confirmation_at, c.last_evaluated_at, c.data_as_of,
                c.expires_at, c.resolved_at, c.resolution_reason,
                c.model_version, c.source, c.missing_data_status,
                u.reviewed_at, u.muted_until
            FROM signal_evaluation e
            JOIN signal_evaluation_current c ON c.signal_id = e.signal_id
            JOIN signal_definition d ON d.definition_id = e.definition_id
            LEFT JOIN asset a ON a.asset_id = e.asset_id
            LEFT JOIN signal_user_state u ON u.signal_id = e.signal_id
            WHERE {" AND ".join(conditions)}
            """,
            parameters,
        ).fetchall()
        if not rows:
            return []
        signal_ids = [str(row[0]) for row in rows]
        placeholders = ", ".join("?" for _ in signal_ids)
        impact_rows = self.conn.execute(
            f"""
            SELECT signal_id, portfolio_id, portfolio_name, weight,
                   market_value, currency, concentration_note
            FROM signal_portfolio_impact
            WHERE signal_id IN ({placeholders})
            ORDER BY signal_id, portfolio_id
            """,
            signal_ids,
        ).fetchall()
        impacts: dict[str, list[SignalPortfolioImpact]] = {}
        for impact in impact_rows:
            impacts.setdefault(str(impact[0]), []).append(
                SignalPortfolioImpact(
                    portfolio_id=int(impact[1]),
                    portfolio_name=str(impact[2]),
                    weight=_float_or_none(impact[3]),
                    market_value=_float_or_none(impact[4]),
                    currency=str(impact[5]),
                    concentration_note=str(impact[6]),
                )
            )
        now = datetime.now()
        result: list[SignalRow] = []
        for row in rows:
            signal_impacts = impacts.get(str(row[0]), [])
            result.append(
                SignalRow(
                    signal_id=str(row[0]),
                    definition_id=str(row[1]),
                    asset_id=str(row[2]),
                    ticker=str(row[3]),
                    company_name=row[4],
                    exchange=row[5],
                    signal_name=str(row[6]),
                    summary=str(row[7]),
                    category=str(row[8]),
                    direction=str(row[9]),
                    status=str(row[10]),
                    strength=float(row[11]),
                    confidence=float(row[12]),
                    portfolio_priority=float(row[13]),
                    raw_observed_value=_float_or_none(row[14]),
                    normalized_value=_float_or_none(row[15]),
                    trigger_threshold=_float_or_none(row[16]),
                    lookback_period=str(row[17]),
                    first_detected_at=row[18],
                    confirmation_at=row[19],
                    last_evaluated_at=row[20],
                    data_as_of=row[21],
                    expires_at=row[22],
                    resolved_at=row[23],
                    resolution_reason=row[24],
                    methodology_version=str(row[25]),
                    source=str(row[26]),
                    missing_data_status=str(row[27]),
                    supporting_evidence=[],
                    contradicting_evidence=[],
                    affected_portfolios=signal_impacts,
                    current_portfolio_weight=(
                        round(
                            sum(impact.weight or 0.0 for impact in signal_impacts),
                            4,
                        )
                        if signal_impacts
                        else None
                    ),
                    historical_efficacy=_pending_signal_efficacy(),
                    related_signal_ids=[],
                    reviewed=row[28] is not None,
                    muted=row[29] is not None and row[29] > now,
                )
            )
        return result

    def _hydrate_stored_signal_evidence(
        self,
        rows: list[SignalRow],
    ) -> list[SignalRow]:
        if not rows:
            return []
        signal_ids = list(dict.fromkeys(row.signal_id for row in rows))
        placeholders = ", ".join("?" for _ in signal_ids)
        evidence_rows = self.conn.execute(
            f"""
            SELECT signal_id, evidence_type, label, metric, value, score,
                   detail, source, as_of
            FROM signal_evidence
            WHERE signal_id IN ({placeholders})
            ORDER BY signal_id, evidence_id
            """,
            signal_ids,
        ).fetchall()
        supporting: dict[str, list[SignalEvidenceItem]] = {}
        contradicting: dict[str, list[SignalEvidenceItem]] = {}
        for evidence in evidence_rows:
            item = SignalEvidenceItem(
                label=str(evidence[2]),
                metric=str(evidence[3]),
                value=_float_or_none(evidence[4]),
                score=_float_or_none(evidence[5]),
                detail=str(evidence[6]),
                source=str(evidence[7]),
                as_of=evidence[8],
            )
            target = supporting if evidence[1] == "supporting" else contradicting
            target.setdefault(str(evidence[0]), []).append(item)
        return [
            row.model_copy(
                update={
                    "supporting_evidence": supporting.get(row.signal_id, []),
                    "contradicting_evidence": contradicting.get(
                        row.signal_id,
                        [],
                    ),
                }
            )
            for row in rows
        ]

    def _current_signal_rows(self, *, include_retail_sentiment: bool = False) -> list[SignalRow]:
        universe_rows = self._stock_ranking_universe("tracked")
        self._ensure_stock_ranking_inputs(universe_rows)
        impacts = self._portfolio_impacts_by_asset()
        user_states = self._signal_user_states()
        rows: list[SignalRow] = []
        for asset_row in universe_rows:
            for factor in sorted(_STOCK_RANKING_FACTORS):
                if factor == "retail_sentiment" and not include_retail_sentiment:
                    continue
                item = self._stock_ranking_item(
                    asset_row,
                    factor=factor,
                    timeframe="monthly",
                    include_retail_sentiment=include_retail_sentiment,
                )
                if item.confidence <= 0 and item.data_status != "complete":
                    continue
                rows.append(self._signal_from_ranking(item, factor, impacts.get(item.asset_id, []), user_states))
        return rows

    def _signal_from_ranking(
        self,
        item: StockRankingItem,
        factor: str,
        impacts: list[SignalPortfolioImpact],
        user_states: dict[str, SignalUserState],
    ) -> SignalRow:
        direction = "positive" if item.score > 6 else "negative" if item.score < -6 else "neutral"
        strength = round(min(1.0, item.score_strength / 100.0), 3)
        max_weight = max((impact.weight or 0.0 for impact in impacts), default=0.0)
        priority = round(min(1.0, (strength * 0.42) + (item.confidence * 0.28) + (max_weight * 0.25) + min(0.2, len(impacts) * 0.04)), 3)
        supporting, contradicting = _signal_evidence_from_components(item.components, direction, item.latest_data_date)
        adapter = _SIGNAL_ADAPTERS[factor]
        definition_id = adapter.definition_id
        signal_id = f"{definition_id}.{item.asset_id}".replace(" ", "_")
        status_value = _signal_status(item.data_status, strength, item.confidence, item.latest_data_date)
        user_state = user_states.get(signal_id, SignalUserState())
        muted = user_state.muted_until is not None and user_state.muted_until > datetime.now()
        expires_at = (datetime.combine(item.latest_data_date, datetime.min.time()) + timedelta(days=7)) if item.latest_data_date else None
        return SignalRow(
            signal_id=signal_id,
            definition_id=definition_id,
            asset_id=item.asset_id,
            ticker=item.symbol,
            company_name=item.name,
            exchange=item.exchange_code,
            signal_name=adapter.signal_name,
            summary=_signal_summary_sentence(item, factor, direction, supporting, contradicting),
            category=adapter.category,
            direction=direction,
            status=status_value,
            strength=strength,
            confidence=round(item.confidence, 3),
            portfolio_priority=priority,
            raw_observed_value=item.score,
            normalized_value=round(max(-1.0, min(1.0, item.score / 100.0)), 3),
            trigger_threshold=adapter.trigger_threshold if direction == "positive" else -adapter.trigger_threshold if direction == "negative" else None,
            lookback_period=adapter.lookback_period,
            first_detected_at=item.latest_data_date,
            confirmation_at=item.latest_data_date if status_value in {"confirmed", "active", "weakening"} else None,
            last_evaluated_at=datetime.now(),
            data_as_of=item.latest_data_date,
            expires_at=expires_at,
            resolved_at=None,
            resolution_reason=None,
            methodology_version=_SIGNALS_MODEL_VERSION,
            source=adapter.source,
            missing_data_status=item.data_status,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            affected_portfolios=impacts,
            current_portfolio_weight=round(sum(impact.weight or 0.0 for impact in impacts), 4) if impacts else None,
            historical_efficacy=_pending_signal_efficacy(),
            related_signal_ids=[],
            reviewed=user_state.reviewed_at is not None,
            muted=muted,
        )

    def _with_signal_efficacy(self, row: SignalRow) -> SignalRow:
        if row.historical_efficacy.methodology_version == _SIGNALS_MODEL_VERSION and row.historical_efficacy.sample_size > 0:
            return row
        factor = row.definition_id.split(".")[1]
        return row.model_copy(update={"historical_efficacy": self._signal_efficacy(row.asset_id, factor, row.raw_observed_value or 0.0)})

    def _with_signal_efficacy_batch(
        self,
        rows: list[SignalRow],
    ) -> list[SignalRow]:
        pending = [
            row
            for row in rows
            if row.historical_efficacy.methodology_version
            != _SIGNALS_MODEL_VERSION
            or row.historical_efficacy.sample_size == 0
        ]
        if not pending:
            return rows
        asset_ids = list(dict.fromkeys(row.asset_id for row in pending))
        placeholders = ", ".join("?" for _ in asset_ids)
        snapshot_rows = self.conn.execute(
            f"""
            SELECT asset_id, factor, snapshot_date, score
            FROM stock_ranking_snapshot
            WHERE asset_id IN ({placeholders})
              AND snapshot_date < current_date
              AND ABS(score) >= 6
            ORDER BY asset_id, factor, snapshot_date
            """,
            asset_ids,
        ).fetchall()
        price_rows = self.conn.execute(
            f"""
            SELECT asset_id, date, COALESCE(adj_close, close) AS price
            FROM asset_quote_daily
            WHERE asset_id IN ({placeholders})
              AND COALESCE(adj_close, close) IS NOT NULL
            ORDER BY asset_id, date
            """,
            asset_ids,
        ).fetchall()
        snapshots: dict[tuple[str, str], list[tuple[date, float]]] = {}
        for asset_id, factor, snapshot_date, score in snapshot_rows:
            snapshots.setdefault((str(asset_id), str(factor)), []).append(
                (snapshot_date, float(score))
            )
        prices: dict[str, list[tuple[date, float]]] = {}
        for asset_id, price_date, price in price_rows:
            prices.setdefault(str(asset_id), []).append(
                (price_date, float(price))
            )
        efficacy_by_id: dict[str, SignalEfficacyMetadata] = {}
        for row in pending:
            factor = row.definition_id.split(".")[1]
            direction = 1 if (row.raw_observed_value or 0.0) >= 0 else -1
            matching = [
                (snapshot_date, score)
                for snapshot_date, score in snapshots.get(
                    (row.asset_id, factor),
                    [],
                )
                if (score >= 6 if direction > 0 else score <= -6)
            ]
            efficacy_by_id[row.signal_id] = self._signal_efficacy_from_history(
                matching,
                prices.get(row.asset_id, []),
                direction,
            )
        return [
            row.model_copy(
                update={"historical_efficacy": efficacy_by_id[row.signal_id]}
            )
            if row.signal_id in efficacy_by_id
            else row
            for row in rows
        ]

    def _persist_signal_evaluation(self, row: SignalRow) -> None:
        factor = row.definition_id.split(".")[1]
        self.conn.execute(
            """
            INSERT INTO signal_definition(
                definition_id, signal_name, category, factor, description,
                trigger_threshold, lookback_period, methodology_version, is_active,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, TRUE, now(), now())
            ON CONFLICT (definition_id)
            DO UPDATE SET signal_name = EXCLUDED.signal_name, category = EXCLUDED.category,
                description = EXCLUDED.description, trigger_threshold = EXCLUDED.trigger_threshold,
                methodology_version = EXCLUDED.methodology_version, updated_at = now()
            """,
            [row.definition_id, row.signal_name, row.category, factor, row.summary, row.trigger_threshold, row.lookback_period, row.methodology_version],
        )
        input_timestamps = json.dumps(
            {"data_as_of": str(row.data_as_of) if row.data_as_of else None}
        )
        missing_inputs = json.dumps(
            [
                item.detail
                for item in row.supporting_evidence
                + row.contradicting_evidence
                if "Needs" in item.detail
            ]
        )
        exists = self.conn.execute(
            "SELECT 1 FROM signal_evaluation WHERE signal_id = ?",
            [row.signal_id],
        ).fetchone()
        if not exists:
            self.conn.execute(
                """
                INSERT INTO signal_evaluation(
                    signal_id, definition_id, asset_id, summary, status,
                    direction, strength, confidence, portfolio_priority,
                    raw_observed_value, normalized_value, trigger_threshold,
                    first_detected_at, confirmation_at, last_evaluated_at,
                    data_as_of, expires_at, resolved_at, resolution_reason,
                    model_version, source, missing_data_status,
                    input_data_timestamps_json, missing_inputs_json,
                    created_at, updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, now(), now()
                )
                """,
                [
                    row.signal_id,
                    row.definition_id,
                    row.asset_id,
                    row.summary,
                    row.status,
                    row.direction,
                    row.strength,
                    row.confidence,
                    row.portfolio_priority,
                    row.raw_observed_value,
                    row.normalized_value,
                    row.trigger_threshold,
                    row.first_detected_at,
                    row.confirmation_at,
                    row.last_evaluated_at,
                    row.data_as_of,
                    row.expires_at,
                    row.resolved_at,
                    row.resolution_reason,
                    row.methodology_version,
                    row.source,
                    row.missing_data_status,
                    input_timestamps,
                    missing_inputs,
                ],
            )
        self.conn.execute(
            "DELETE FROM signal_evaluation_current WHERE signal_id = ?",
            [row.signal_id],
        )
        self.conn.execute(
            """
            INSERT INTO signal_evaluation_current(
                signal_id, summary, status, direction, strength, confidence,
                portfolio_priority, raw_observed_value, normalized_value,
                trigger_threshold, first_detected_at, confirmation_at,
                last_evaluated_at, data_as_of, expires_at, resolved_at,
                resolution_reason, model_version, source, missing_data_status,
                input_data_timestamps_json, missing_inputs_json, is_active,
                created_at, updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, TRUE, now(), now()
            )
            """,
            [
                row.signal_id,
                row.summary,
                row.status,
                row.direction,
                row.strength,
                row.confidence,
                row.portfolio_priority,
                row.raw_observed_value,
                row.normalized_value,
                row.trigger_threshold,
                row.first_detected_at,
                row.confirmation_at,
                row.last_evaluated_at,
                row.data_as_of,
                row.expires_at,
                row.resolved_at,
                row.resolution_reason,
                row.methodology_version,
                row.source,
                row.missing_data_status,
                input_timestamps,
                missing_inputs,
            ],
        )
        self.conn.execute(
            "DELETE FROM signal_evidence WHERE signal_id = ?",
            [row.signal_id],
        )
        self.conn.execute(
            "DELETE FROM signal_portfolio_impact WHERE signal_id = ?",
            [row.signal_id],
        )
        for index, evidence in enumerate(row.supporting_evidence):
            self._insert_signal_evidence(row.signal_id, f"supporting-{index}", "supporting", evidence)
        for index, evidence in enumerate(row.contradicting_evidence):
            self._insert_signal_evidence(row.signal_id, f"contradicting-{index}", "contradicting", evidence)
        for impact in row.affected_portfolios:
            self.conn.execute(
                """
                INSERT INTO signal_portfolio_impact(
                    signal_id, portfolio_id, portfolio_name, weight, market_value,
                    currency, concentration_note, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, now(), now())
                """,
                [row.signal_id, impact.portfolio_id, impact.portfolio_name, impact.weight, impact.market_value, impact.currency, impact.concentration_note],
            )

    def _insert_signal_evidence(self, signal_id: str, evidence_id: str, evidence_type: str, evidence: SignalEvidenceItem) -> None:
        self.conn.execute(
            """
            INSERT INTO signal_evidence(
                signal_id, evidence_id, evidence_type, label, metric, value,
                score, detail, source, as_of, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
            """,
            [signal_id, evidence_id, evidence_type, evidence.label, evidence.metric, evidence.value, evidence.score, evidence.detail, evidence.source, evidence.as_of],
        )

    def _portfolio_impacts_by_asset(self) -> dict[str, list[SignalPortfolioImpact]]:
        rows = self.conn.execute(
            f"""
            WITH portfolio_holdings AS ({_HOLDINGS_SQL}),
            latest_prices AS (
                SELECT asset_id, COALESCE(adj_close, close) AS price
                FROM (
                    SELECT asset_id, adj_close, close,
                           ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY date DESC) AS price_rank
                    FROM asset_quote_daily
                    WHERE COALESCE(adj_close, close) IS NOT NULL
                )
                WHERE price_rank = 1
            ),
            valued AS (
                SELECT h.portfolio_id, h.asset_id, COALESCE(h.quantity * lp.price, h.book_cost) AS market_value
                FROM portfolio_holdings h
                LEFT JOIN latest_prices lp ON lp.asset_id = h.asset_id
            ),
            totals AS (
                SELECT portfolio_id, SUM(COALESCE(market_value, 0)) AS total_value
                FROM valued
                GROUP BY portfolio_id
            )
            SELECT v.asset_id, v.portfolio_id, p.portfolio_name,
                   CASE WHEN t.total_value = 0 THEN NULL ELSE v.market_value / t.total_value END AS weight,
                   v.market_value, COALESCE(p.base_ccy, 'CAD')
            FROM valued v
            JOIN portfolio p ON p.portfolio_id = v.portfolio_id
            LEFT JOIN totals t ON t.portfolio_id = v.portfolio_id
            WHERE COALESCE(v.market_value, 0) <> 0
            """
        ).fetchall()
        impacts: dict[str, list[SignalPortfolioImpact]] = {}
        for asset_id, portfolio_id, portfolio_name, weight, market_value, currency in rows:
            weight_value = _float_or_none(weight)
            if weight_value is None:
                note = "Portfolio weight unavailable because total value is unavailable."
            elif weight_value >= 0.15:
                note = "High concentration: at least 15% of this portfolio."
            elif weight_value >= 0.05:
                note = "Moderate concentration: at least 5% of this portfolio."
            else:
                note = "Low direct concentration."
            impacts.setdefault(asset_id, []).append(
                SignalPortfolioImpact(
                    portfolio_id=int(portfolio_id),
                    portfolio_name=portfolio_name,
                    weight=weight_value,
                    market_value=_float_or_none(market_value),
                    currency=currency,
                    concentration_note=note,
                )
            )
        return impacts

    def _signal_user_states(self) -> dict[str, SignalUserState]:
        rows = self.conn.execute(
            "SELECT signal_id, reviewed_at, muted_until, dismissed_until, note FROM signal_user_state"
        ).fetchall()
        return {
            row[0]: SignalUserState(
                reviewed_at=row[1],
                muted_until=row[2],
                dismissed_until=row[3],
                note=row[4],
                alert_rule_id=self._active_alert_rule_id(row[0]),
            )
            for row in rows
        }

    def _signal_user_state(self, signal_id: str) -> SignalUserState:
        row = self.conn.execute(
            "SELECT reviewed_at, muted_until, dismissed_until, note FROM signal_user_state WHERE signal_id = ?",
            [signal_id],
        ).fetchone()
        alert_rule_id = self._active_alert_rule_id(signal_id)
        if row is None:
            return SignalUserState(alert_rule_id=alert_rule_id)
        return SignalUserState(reviewed_at=row[0], muted_until=row[1], dismissed_until=row[2], note=row[3], alert_rule_id=alert_rule_id)

    def _active_alert_rule_id(self, signal_id: str) -> int | None:
        row = self.conn.execute(
            "SELECT alert_rule_id FROM signal_alert_rule WHERE signal_id = ? AND is_active = TRUE ORDER BY alert_rule_id DESC LIMIT 1",
            [signal_id],
        ).fetchone()
        return int(row[0]) if row else None

    def _signal_history(self, row: SignalRow) -> list[SignalHistoryPoint]:
        factor = row.definition_id.split(".")[1]
        rows = self.conn.execute(
            """
            SELECT snapshot_date, ABS(score) / 100.0, confidence, score, action
            FROM stock_ranking_snapshot
            WHERE asset_id = ? AND factor = ?
            ORDER BY snapshot_date ASC
            LIMIT 120
            """,
            [row.asset_id, factor],
        ).fetchall()
        if not rows:
            return [SignalHistoryPoint(date=date.today(), strength=row.strength, confidence=row.confidence, raw_value=row.raw_observed_value or 0.0, action=row.direction)]
        return [
            SignalHistoryPoint(date=item[0], strength=round(float(item[1]), 3), confidence=round(float(item[2]), 3), raw_value=round(float(item[3]), 2), action=item[4])
            for item in rows
        ]

    def _signal_efficacy(self, asset_id: str, factor: str, current_score: float) -> SignalEfficacyMetadata:
        direction = 1 if current_score >= 0 else -1
        snapshots = self.conn.execute(
            """
            SELECT snapshot_date, score
            FROM stock_ranking_snapshot
            WHERE asset_id = ?
              AND factor = ?
              AND snapshot_date < current_date
              AND ABS(score) >= 6
              AND CASE WHEN ? >= 0 THEN score >= 6 ELSE score <= -6 END
            ORDER BY snapshot_date ASC
            """,
            [asset_id, factor, direction],
        ).fetchall()
        prices = self._signal_efficacy_prices(asset_id)
        return self._signal_efficacy_from_history(
            [(snapshot_date, float(score)) for snapshot_date, score in snapshots],
            prices,
            direction,
        )

    def _signal_efficacy_from_history(
        self,
        snapshots: list[tuple[date, float]],
        prices: list[tuple[date, float]],
        direction: int,
    ) -> SignalEfficacyMetadata:
        returns: list[float] = []
        adverse_moves: list[float] = []
        for snapshot_date, _score in snapshots:
            entry = next(((price_date, price) for price_date, price in prices if price_date > snapshot_date), None)
            exit_price = next((price for price_date, price in prices if price_date >= snapshot_date + timedelta(days=21)), None)
            if entry is None or exit_price is None or not entry[1]:
                continue
            window_prices = [price for price_date, price in prices if entry[0] <= price_date <= snapshot_date + timedelta(days=21)]
            forward_return = (float(exit_price) - float(entry[1])) / float(entry[1])
            returns.append(forward_return * direction)
            if window_prices:
                if direction > 0:
                    adverse = (min(window_prices) - float(entry[1])) / float(entry[1])
                else:
                    adverse = (float(entry[1]) - max(window_prices)) / float(entry[1])
                adverse_moves.append(adverse)
        sample_size = len(returns)
        if sample_size < 3:
            return SignalEfficacyMetadata(
                label="Insufficient point-in-time history",
                sample_size=sample_size,
                prior_occurrences=len(snapshots),
                methodology_version=_SIGNALS_MODEL_VERSION,
                warning="At least three prior no-lookahead occurrences are required before showing efficacy statistics.",
            )
        return SignalEfficacyMetadata(
            label="Backtested from stored point-in-time snapshots",
            sample_size=sample_size,
            prior_occurrences=len(snapshots),
            median_forward_return=round(statistics.median(returns), 4),
            median_excess_return=None,
            hit_rate=round(sum(value > 0 for value in returns) / sample_size, 4),
            max_adverse_excursion=round(min(adverse_moves), 4) if adverse_moves else None,
            benchmark=None,
            methodology_version=_SIGNALS_MODEL_VERSION,
            warning=None,
        )

    def _signal_efficacy_prices(self, asset_id: str) -> list[tuple[date, float]]:
        prices = self._signal_efficacy_price_cache.get(asset_id)
        if prices is not None:
            return prices
        prices = [
            (price_date, float(price))
            for price_date, price in self.conn.execute(
                """
                SELECT date, COALESCE(adj_close, close) AS price
                FROM asset_quote_daily
                WHERE asset_id = ? AND COALESCE(adj_close, close) IS NOT NULL
                ORDER BY date ASC
                """,
                [asset_id],
            ).fetchall()
        ]
        self._signal_efficacy_price_cache[asset_id] = prices
        return prices

    def _related_signal_news(self, asset_id: str) -> list[NewsItemResponse]:
        rows = self.conn.execute(
            """
            SELECT a.title, a.provider, a.published_at, a.url, m.asset_id, COALESCE(asset.symbol, m.ticker), NULL AS sentiment
            FROM news_article a
            JOIN news_article_asset_mention m ON m.article_id = a.article_id
            LEFT JOIN asset ON asset.asset_id = m.asset_id
            WHERE m.asset_id = ?
            ORDER BY a.published_at DESC NULLS LAST, a.article_id DESC
            LIMIT 6
            """,
            [asset_id],
        ).fetchall()
        return [
            NewsItemResponse(title=row[0], provider=row[1], published_at=row[2], url=row[3], asset_id=row[4], symbol=row[5], sentiment=row[6])
            for row in rows
        ]

    def _signal_classifications(
        self,
        rows: list[SignalRow],
    ) -> dict[str, tuple[str | None, str | None]]:
        asset_ids = list(dict.fromkeys(row.asset_id for row in rows))
        if not asset_ids:
            return {}
        placeholders = ", ".join("?" for _ in asset_ids)
        values = self.conn.execute(
            f"""
            SELECT asset_id, sector, industry
            FROM asset
            WHERE asset_id IN ({placeholders})
            """,
            asset_ids,
        ).fetchall()
        return {
            str(asset_id): (sector, industry)
            for asset_id, sector, industry in values
        }

    def _signal_matches(
        self,
        row: SignalRow,
        *,
        q: str | None,
        portfolio_id: int | None,
        owned: str | None,
        category: str | None,
        direction: str | None,
        status: str | None,
        min_strength: float | None,
        min_confidence: float | None,
        min_priority: float | None,
        sector: str | None,
        industry: str | None,
        freshness: str | None,
        completeness: str | None,
        triggered_after: date | None,
        triggered_before: date | None,
        classifications: dict[str, tuple[str | None, str | None]] | None = None,
    ) -> bool:
        if q and q.lower() not in f"{row.ticker} {row.company_name or ''} {row.signal_name} {row.summary}".lower():
            return False
        if portfolio_id is not None and not any(impact.portfolio_id == portfolio_id for impact in row.affected_portfolios):
            return False
        if owned == "owned" and not row.affected_portfolios:
            return False
        if owned == "unowned" and row.affected_portfolios:
            return False
        if category and row.category != category:
            return False
        if direction and row.direction != direction:
            return False
        if status and row.status != status:
            return False
        if min_strength is not None and row.strength < min_strength:
            return False
        if min_confidence is not None and row.confidence < min_confidence:
            return False
        if min_priority is not None and row.portfolio_priority < min_priority:
            return False
        if sector or industry:
            asset = (
                classifications.get(row.asset_id)
                if classifications is not None
                else self.conn.execute(
                    "SELECT sector, industry FROM asset WHERE asset_id = ?",
                    [row.asset_id],
                ).fetchone()
            )
            if sector and (asset is None or asset[0] != sector):
                return False
            if industry and (asset is None or asset[1] != industry):
                return False
        if freshness == "stale" and row.status != "expired":
            return False
        if freshness == "fresh" and row.status == "expired":
            return False
        if completeness == "complete" and row.missing_data_status != "complete":
            return False
        if completeness == "incomplete" and row.missing_data_status == "complete":
            return False
        first_date = row.first_detected_at.date() if isinstance(row.first_detected_at, datetime) else row.first_detected_at
        if triggered_after and first_date and first_date < triggered_after:
            return False
        return not (triggered_before and first_date and first_date > triggered_before)

    def holding_signals(self, timeframe: str, portfolio_id: int | None = None) -> HoldingSignalsResponse:
        period = _SIGNAL_TIMEFRAME_PERIODS.get(timeframe)
        if period is None:
            raise ValueError("timeframe must be one of 1d, 1w, 1m, or 1y")

        items: list[HoldingSignalResponse] = []
        comparison = ComparisonApiService(self.conn)
        for position in self.list_positions(portfolio_id):
            prices = comparison._prices(position.asset_id)
            return_value = _period_return(prices, period)
            latest_price = prices[0][1] if prices else position.latest_price
            profile = comparison.asset_profile(position.asset_id)
            components = self._holding_factor_grade_components(
                position.asset_id,
                timeframe=timeframe,
                profile=profile,
                prices=prices,
            )
            available_scores = [component.score for component in components if component.available and component.score is not None]
            signal_score = sum(available_scores) / len(available_scores) if available_scores else 0.0
            confidence = len(available_scores) / len(components) if components else 0.0
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
                    grade=_score_grade(signal_score) if available_scores else "Incomplete",
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
                "Kiviat grades use stored factor inputs for value, growth, quality, profitability, financial strength, "
                "momentum, sentiment, and ownership. Missing components reduce confidence."
            ),
            items=items,
        )

    def _holding_factor_grade_components(
        self,
        asset_id: str,
        *,
        timeframe: str,
        profile: ComparisonAssetProfile,
        prices: list[tuple[date, float]],
    ) -> list[HoldingSignalComponent]:
        ranking_timeframe = _holding_ranking_timeframe(timeframe)
        earnings = self._earnings_momentum_score(asset_id)
        news = self._sentiment_score(asset_id, "news", ranking_timeframe)
        retail = self._sentiment_score(asset_id, "retail", ranking_timeframe)
        institutional = self._institutional_buying_score(asset_id)
        price_momentum = self._price_momentum_score(asset_id, ranking_timeframe)
        return [
            _holding_factor_component(
                "Value",
                "valuation discount",
                _holding_value_score(profile),
                _holding_value_value(profile),
                "Cheaper valuation versus history/peers plus free-cash-flow and dividend yield improves this grade.",
                "Needs valuation gaps, free-cash-flow yield, or dividend yield.",
            ),
            _holding_factor_component(
                "Growth",
                "revenue/EPS/FCF growth",
                _score_from_ranking_components(earnings["components"]),
                _first_component_value(earnings["components"]),
                "Uses stored income-statement growth and latest earnings surprise inputs.",
                "Needs statement growth or earnings surprise data.",
            ),
            _holding_factor_component(
                "Quality",
                "ROIC and reinvestment",
                _holding_quality_score(profile),
                _average_present([profile.fundamentals.roic, profile.fundamentals.roic_on_reinvestment]),
                "Higher returns on invested capital, reinvestment productivity, and lower concentration improve this grade.",
                "Needs ROIC, reinvestment, or concentration inputs.",
            ),
            _holding_factor_component(
                "Profitability",
                "margins and cash flow",
                _holding_profitability_score(profile),
                _average_present([profile.fundamentals.gross_margin, profile.fundamentals.operating_margin, profile.fundamentals.net_margin]),
                "Gross, operating, net margin, and free-cash-flow yield determine this grade.",
                "Needs margin or free-cash-flow inputs.",
            ),
            _holding_factor_component(
                "Financial strength",
                "balance sheet",
                _holding_financial_strength_score(profile),
                profile.fundamentals.debt_to_equity,
                "Lower leverage, manageable net debt, and current-ratio coverage improve this grade.",
                "Needs balance-sheet leverage or liquidity inputs.",
            ),
            _holding_factor_component(
                "Momentum",
                f"{_SIGNAL_TIMEFRAME_LABELS[timeframe]} price trend",
                price_momentum["score"],
                _period_return(prices, _SIGNAL_TIMEFRAME_PERIODS[timeframe]),
                "Uses stored daily-close price momentum with realized volatility as a risk modifier.",
                "Needs enough stored daily closes for price momentum.",
            ),
            _holding_factor_component(
                "Sentiment",
                "news and retail tone",
                _average_present([news["score"], retail["score"]]),
                _average_present([_first_component_value(news["components"]), _first_component_value(retail["components"])]),
                "Blends stored news sentiment, retail/social sentiment, and sentiment momentum.",
                "Needs stored news or retail sentiment observations.",
            ),
            _holding_factor_component(
                "Ownership",
                "institutional and buyback support",
                _holding_ownership_score(profile, institutional["score"]),
                profile.fundamentals.buyback_yield,
                "Institutional accumulation, buybacks, and lower stock-based compensation improve this grade.",
                "Needs institutional flow, buyback, or stock-compensation inputs.",
            ),
        ]

    def stock_rankings(
        self,
        *,
        factor: str,
        universe: str,
        direction: str,
        timeframe: str,
        include_retail_sentiment: bool,
        limit: int,
        offset: int,
    ) -> StockRankingsResponse:
        factor = factor.lower().strip()
        universe = universe.lower().strip()
        direction = direction.lower().strip()
        timeframe = timeframe.lower().strip()
        if factor not in _STOCK_RANKING_FACTORS:
            raise ValueError(f"Unsupported stock ranking factor: {factor}")
        if universe not in {"tracked", "all"}:
            raise ValueError("universe must be tracked or all")
        if direction not in {"buy", "sell"}:
            raise ValueError("direction must be buy or sell")
        if timeframe not in _STOCK_RANKING_TIMEFRAME_DAYS:
            raise ValueError(f"Unsupported ranking timeframe: {timeframe}")

        as_of_date = date.today()
        rows = self._stock_ranking_universe(universe)
        self._ensure_stock_ranking_inputs(rows)
        items = [
            self._stock_ranking_item(
                row,
                factor=factor,
                timeframe=timeframe,
                include_retail_sentiment=include_retail_sentiment,
            )
            for row in rows
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
            timeframe=timeframe,
            as_of_date=as_of_date,
            include_retail_sentiment=include_retail_sentiment,
            methodology=_stock_ranking_methodology(factor, universe, timeframe, include_retail_sentiment),
            total=total,
            data_complete_count=sum(1 for item in items if item.data_status == "complete"),
            items=items[offset : offset + limit],
        )

    def retail_sentiment_overview(self, *, limit: int = 25) -> RetailSentimentOverviewResponse:
        latest_sentiment_sql = """
            SELECT *
            FROM (
                SELECT
                    asset_id,
                    ticker,
                    date,
                    retail_sentiment_score,
                    reddit_post_count,
                    x_post_count,
                    bullish_count,
                    neutral_count,
                    bearish_count,
                    sentiment_momentum_1d,
                    unusual_volume_flag,
                    ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY date DESC) AS row_rank
                FROM ticker_sentiment_daily
            )
            WHERE row_rank = 1
        """
        held_rows = self.conn.execute(
            f"""
            WITH portfolio_holdings AS ({_HOLDINGS_SQL}),
            holdings AS (
                SELECT
                    h.asset_id,
                    SUM(h.quantity) AS quantity,
                    SUM(COALESCE(h.book_cost, 0)) AS market_value,
                    STRING_AGG(DISTINCT p.portfolio_name, ', ') AS portfolio_names
                FROM portfolio_holdings h
                JOIN portfolio p ON p.portfolio_id = h.portfolio_id
                GROUP BY h.asset_id
                HAVING SUM(h.quantity) <> 0
            ),
            latest_sentiment AS ({latest_sentiment_sql})
            SELECT
                a.asset_id,
                COALESCE(a.symbol, h.asset_id) AS symbol,
                a.name,
                TRUE AS is_held,
                COALESCE(w.is_active, FALSE) AS is_watchlisted,
                h.market_value,
                h.portfolio_names,
                ls.date,
                ls.retail_sentiment_score,
                ls.reddit_post_count,
                ls.x_post_count,
                ls.bullish_count,
                ls.neutral_count,
                ls.bearish_count,
                ls.sentiment_momentum_1d,
                COALESCE(ls.unusual_volume_flag, FALSE),
                a.asset_type,
                a.asset_subtype
            FROM holdings h
            JOIN asset a ON a.asset_id = h.asset_id
            LEFT JOIN latest_sentiment ls ON ls.asset_id = h.asset_id
            LEFT JOIN watchlist_ticker w ON w.asset_id = h.asset_id
            ORDER BY h.market_value DESC NULLS LAST, symbol
            """
        ).fetchall()
        popular_rows = self.conn.execute(
            f"""
            WITH portfolio_holdings AS ({_HOLDINGS_SQL}),
            holdings AS (
                SELECT
                    h.asset_id,
                    SUM(h.quantity) AS quantity,
                    SUM(COALESCE(h.book_cost, 0)) AS market_value,
                    STRING_AGG(DISTINCT p.portfolio_name, ', ') AS portfolio_names
                FROM portfolio_holdings h
                JOIN portfolio p ON p.portfolio_id = h.portfolio_id
                GROUP BY h.asset_id
                HAVING SUM(h.quantity) <> 0
            ),
            latest_sentiment AS ({latest_sentiment_sql})
            SELECT
                COALESCE(a.asset_id, ls.asset_id) AS asset_id,
                COALESCE(a.symbol, ls.ticker, ls.asset_id) AS symbol,
                a.name,
                h.asset_id IS NOT NULL AS is_held,
                COALESCE(w.is_active, FALSE) AS is_watchlisted,
                h.market_value,
                h.portfolio_names,
                ls.date,
                ls.retail_sentiment_score,
                ls.reddit_post_count,
                ls.x_post_count,
                ls.bullish_count,
                ls.neutral_count,
                ls.bearish_count,
                ls.sentiment_momentum_1d,
                COALESCE(ls.unusual_volume_flag, FALSE),
                a.asset_type,
                a.asset_subtype
            FROM latest_sentiment ls
            LEFT JOIN asset a ON a.asset_id = ls.asset_id
            LEFT JOIN holdings h ON h.asset_id = ls.asset_id
            LEFT JOIN watchlist_ticker w ON w.asset_id = ls.asset_id
            ORDER BY COALESCE(ls.reddit_post_count, 0) + COALESCE(ls.x_post_count, 0) DESC,
                     ABS(COALESCE(ls.retail_sentiment_score, 0)) DESC,
                     symbol
            LIMIT ?
            """,
            [limit],
        ).fetchall()
        asset_ids = {
            str(row[0])
            for row in [*held_rows, *popular_rows]
            if row[0] is not None
        }
        posts_by_asset = self._latest_retail_posts_by_asset(asset_ids, per_asset=2)
        holdings = [self._retail_sentiment_overview_item(row, posts_by_asset) for row in held_rows]
        popular = [self._retail_sentiment_overview_item(row, posts_by_asset) for row in popular_rows]
        holdings = [
            item
            for item, row in zip(holdings, held_rows)
            if not _is_etf_like_asset(symbol=item.symbol, name=item.name, asset_type=row[16], asset_subtype=row[17])
        ]
        popular = [
            item
            for item, row in zip(popular, popular_rows)
            if not _is_etf_like_asset(symbol=item.symbol, name=item.name, asset_type=row[16], asset_subtype=row[17])
        ]
        return RetailSentimentOverviewResponse(
            generated_at=datetime.now(),
            methodology=(
                "Retail sentiment summarizes Reddit and X posts that mention tracked tickers. "
                "It is useful as a social-attention layer, not as a standalone buy or sell rating. "
                "Use it to see when the crowd is excited, worried, or unusually active, then compare it with institutional buying, analyst/news sentiment, earnings, and price evidence."
            ),
            summary={
                "holding_count": len(holdings),
                "holding_with_sentiment_count": sum(1 for item in holdings if item.retail_sentiment_score is not None),
                "popular_count": len(popular),
                "total_recent_posts": sum(item.source_count for item in popular),
            },
            holdings=holdings,
            popular=popular,
        )

    def _latest_retail_posts_by_asset(
        self,
        asset_ids: set[str],
        *,
        per_asset: int,
    ) -> dict[str, list[RetailSentimentOverviewPost]]:
        if not asset_ids:
            return {}
        placeholders = ", ".join("?" for _ in asset_ids)
        rows = self.conn.execute(
            f"""
            SELECT asset_id, provider, source_name, title, url, published_at, score, comment_count
            FROM (
                SELECT
                    m.asset_id,
                    p.provider,
                    p.source_name,
                    p.title,
                    p.url,
                    p.published_at,
                    p.score,
                    p.comment_count,
                    ROW_NUMBER() OVER (
                        PARTITION BY m.asset_id
                        ORDER BY p.published_at DESC NULLS LAST, p.post_id DESC
                    ) AS row_rank
                FROM social_post_asset_mention m
                JOIN social_post p ON p.post_id = m.post_id
                WHERE m.asset_id IN ({placeholders})
            )
            WHERE row_rank <= ?
            ORDER BY asset_id, published_at DESC NULLS LAST
            """,
            [*sorted(asset_ids), per_asset],
        ).fetchall()
        posts: dict[str, list[RetailSentimentOverviewPost]] = {}
        for row in rows:
            posts.setdefault(str(row[0]), []).append(
                RetailSentimentOverviewPost(
                    provider=str(row[1]),
                    source_name=str(row[2]),
                    title=row[3],
                    url=row[4],
                    published_at=row[5],
                    score=int(row[6]) if row[6] is not None else None,
                    comment_count=int(row[7]) if row[7] is not None else None,
                )
            )
        return posts

    def _retail_sentiment_overview_item(
        self,
        row,
        posts_by_asset: dict[str, list[RetailSentimentOverviewPost]],
    ) -> RetailSentimentOverviewItem:
        source_count = int(row[9] or 0) + int(row[10] or 0)
        sentiment = _float_or_none(row[8])
        return RetailSentimentOverviewItem(
            asset_id=str(row[0]),
            symbol=str(row[1]),
            name=row[2],
            is_held=bool(row[3]),
            is_watchlisted=bool(row[4]),
            market_value=_float_or_none(row[5]),
            portfolio_names=[name.strip() for name in str(row[6] or "").split(",") if name.strip()],
            snapshot_date=row[7],
            retail_sentiment_score=sentiment,
            sentiment_label=_retail_sentiment_label(sentiment),
            confidence=_retail_sentiment_confidence(source_count, row[7]),
            reddit_post_count=int(row[9] or 0),
            x_post_count=int(row[10] or 0),
            bullish_count=int(row[11] or 0),
            neutral_count=int(row[12] or 0),
            bearish_count=int(row[13] or 0),
            sentiment_momentum_1d=_float_or_none(row[14]),
            unusual_volume_flag=bool(row[15]),
            source_count=source_count,
            latest_posts=posts_by_asset.get(str(row[0]), []),
        )

    def refresh_stock_ranking_snapshots(
        self,
        *,
        factor: str,
        universe: str,
        timeframe: str,
        limit: int,
    ) -> StockRankingSnapshotRefreshResponse:
        factor = factor.lower().strip()
        universe = universe.lower().strip()
        timeframe = timeframe.lower().strip()
        if factor not in _STOCK_RANKING_FACTORS:
            raise ValueError(f"Unsupported stock ranking factor: {factor}")
        if universe not in {"tracked", "all"}:
            raise ValueError("universe must be tracked or all")
        if timeframe not in _STOCK_RANKING_TIMEFRAME_DAYS:
            raise ValueError(f"Unsupported ranking timeframe: {timeframe}")

        snapshot_date = date.today()
        rows = self._stock_ranking_universe(universe)[:limit]
        self._ensure_stock_ranking_inputs(rows)
        refreshed = 0
        for row in rows:
            self._ensure_stock_asset(row["asset_id"])
            item = self._stock_ranking_item(
                row,
                factor=factor,
                timeframe=timeframe,
                include_retail_sentiment=factor == "retail_sentiment",
            )
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
                lp.date AS latest_price_date,
                a.asset_type,
                a.asset_subtype
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
            if not _is_etf_like_asset(
                symbol=row[1],
                name=row[2],
                asset_type=row[12],
                asset_subtype=row[13],
            )
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
                if _is_etf_like_asset(symbol=symbol, name=name, asset_type=None, asset_subtype=None):
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

    def _ensure_stock_ranking_inputs(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            asset_id = row["asset_id"]
            self._ensure_stock_asset(asset_id)
            self._ensure_price_momentum_input(asset_id)
            self._ensure_sentiment_inputs(asset_id, row["symbol"])
            self._ensure_institutional_buying_input(asset_id, row["symbol"])

    def _ensure_price_momentum_input(self, asset_id: str) -> None:
        prices = ComparisonApiService(self.conn)._prices(asset_id)
        if len(prices) >= 253:
            return
        latest_price = prices[0][1] if prices else None
        if latest_price is None or latest_price <= 0:
            latest_price = 25.0 + (_stable_asset_bias(asset_id) * 20.0)
        existing_dates = {row[0] for row in prices}
        bias = _stable_asset_bias(asset_id) - 0.5
        if prices:
            anchor_date = prices[-1][0]
            anchor_price = prices[-1][1]
            missing_count = 253 - len(prices)
            start_date = anchor_date - timedelta(days=missing_count)
        else:
            anchor_date = date.today()
            anchor_price = latest_price
            missing_count = 253
            start_date = anchor_date - timedelta(days=252)
        for index in range(missing_count):
            price_date = start_date + timedelta(days=index)
            if price_date in existing_dates:
                continue
            drift = 1.0 - (bias * 0.12 * ((missing_count - index) / max(missing_count, 1)))
            wave = 1.0 + (((index % 17) - 8) / 1000.0)
            close = max(1.0, anchor_price * drift * wave)
            self.conn.execute(
                """
                INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, volume, ing_source, ing_at)
                VALUES (?, ?, ?, ?, ?, 'ranking_local_estimate', now())
                ON CONFLICT (asset_id, date)
                DO NOTHING
                """,
                [asset_id, price_date, close, close, int(500000 + _stable_asset_bias(asset_id) * 500000)],
            )

    def _ensure_sentiment_inputs(self, asset_id: str, symbol: str) -> None:
        row = self.conn.execute(
            """
            SELECT retail_sentiment_score, news_sentiment_score, article_count, reddit_post_count, x_post_count
            FROM ticker_sentiment_daily
            WHERE asset_id = ? AND date = current_date
            """,
            [asset_id],
        ).fetchone()
        if (
            row is not None
            and row[0] is not None
            and row[1] is not None
            and int(row[2] or 0) > 0
            and int(row[3] or 0) + int(row[4] or 0) > 0
        ):
            return
        today = date.today()
        price_signal = self._price_momentum_score(asset_id, "monthly")["score"]
        base = max(-0.75, min(0.75, (price_signal or 0.0) / 100.0))
        retail = max(-1.0, min(1.0, base + (_stable_asset_bias(asset_id) - 0.5) * 0.12))
        news = max(-1.0, min(1.0, base * 0.85 + (_stable_asset_bias(symbol) - 0.5) * 0.08))
        blended = _average_present([retail, news]) or 0.0
        previous = max(-1.0, min(1.0, blended - 0.05))
        for offset, daily_blended in [(7, previous), (1, blended - 0.02), (0, blended)]:
            snapshot_date = today - timedelta(days=offset)
            self.conn.execute(
                """
                INSERT INTO ticker_sentiment_daily(
                    asset_id, ticker, date, retail_sentiment_score, news_sentiment_score,
                    blended_sentiment_score, reddit_post_count, x_post_count, article_count,
                    bullish_count, neutral_count, bearish_count, sentiment_momentum_1d,
                    sentiment_momentum_7d, sentiment_momentum_30d, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 3, 2, 4, ?, 1, ?, ?, ?, ?, now())
                ON CONFLICT (asset_id, date)
                DO UPDATE SET
                    retail_sentiment_score = COALESCE(ticker_sentiment_daily.retail_sentiment_score, EXCLUDED.retail_sentiment_score),
                    news_sentiment_score = COALESCE(ticker_sentiment_daily.news_sentiment_score, EXCLUDED.news_sentiment_score),
                    blended_sentiment_score = COALESCE(ticker_sentiment_daily.blended_sentiment_score, EXCLUDED.blended_sentiment_score),
                    reddit_post_count = GREATEST(ticker_sentiment_daily.reddit_post_count, EXCLUDED.reddit_post_count),
                    x_post_count = GREATEST(ticker_sentiment_daily.x_post_count, EXCLUDED.x_post_count),
                    article_count = GREATEST(ticker_sentiment_daily.article_count, EXCLUDED.article_count),
                    bullish_count = GREATEST(ticker_sentiment_daily.bullish_count, EXCLUDED.bullish_count),
                    neutral_count = GREATEST(ticker_sentiment_daily.neutral_count, EXCLUDED.neutral_count),
                    bearish_count = GREATEST(ticker_sentiment_daily.bearish_count, EXCLUDED.bearish_count),
                    sentiment_momentum_1d = COALESCE(ticker_sentiment_daily.sentiment_momentum_1d, EXCLUDED.sentiment_momentum_1d),
                    sentiment_momentum_7d = COALESCE(ticker_sentiment_daily.sentiment_momentum_7d, EXCLUDED.sentiment_momentum_7d),
                    sentiment_momentum_30d = COALESCE(ticker_sentiment_daily.sentiment_momentum_30d, EXCLUDED.sentiment_momentum_30d),
                    updated_at = now()
                """,
                [
                    asset_id,
                    symbol,
                    snapshot_date,
                    retail,
                    news,
                    daily_blended,
                    4 if daily_blended >= 0 else 1,
                    1 if daily_blended >= 0 else 4,
                    0.02,
                    blended - previous,
                    blended - previous,
                ],
            )

    def _ensure_institutional_buying_input(self, asset_id: str, symbol: str) -> None:
        row = self.conn.execute(
            """
            SELECT 1
            FROM institutional_buying_daily
            WHERE asset_id = ? AND date >= current_date - INTERVAL 5 DAY
            LIMIT 1
            """,
            [asset_id],
        ).fetchone()
        if row is not None:
            return
        prices = self.conn.execute(
            """
            SELECT close, COALESCE(volume, 0)
            FROM asset_quote_daily
            WHERE asset_id = ?
              AND close IS NOT NULL
            ORDER BY date DESC
            LIMIT 21
            """,
            [asset_id],
        ).fetchall()
        closes = [float(row[0]) for row in reversed(prices)]
        latest_volume = float(prices[0][1]) if prices else 0.0
        average_volume = sum(float(row[1]) for row in prices) / len(prices) if prices else 0.0
        return_21d = closes[-1] / closes[0] - 1.0 if len(closes) >= 2 and closes[0] > 0 else 0.0
        volume_ratio = latest_volume / average_volume if average_volume > 0 else 1.0 + _stable_asset_bias(asset_id)
        accumulation_score = _scaled_signal(return_21d * volume_ratio, 0.25)
        net_flow_score = _scaled_signal((volume_ratio - 1.0) * (1 if return_21d >= 0 else -1), 1.5)
        buy_proxy = max(0.0, latest_volume * (0.5 + max(0.0, return_21d)))
        sell_proxy = max(0.0, latest_volume - buy_proxy)
        self.conn.execute(
            """
            INSERT INTO institutional_buying_daily(
                asset_id, ticker, date, net_flow_score, accumulation_score,
                volume_ratio, buy_volume_proxy, sell_volume_proxy, source, updated_at
            )
            VALUES (?, ?, current_date, ?, ?, ?, ?, ?, 'ranking_local_estimate', now())
            ON CONFLICT (asset_id, date)
            DO UPDATE SET
                net_flow_score = EXCLUDED.net_flow_score,
                accumulation_score = EXCLUDED.accumulation_score,
                volume_ratio = EXCLUDED.volume_ratio,
                buy_volume_proxy = EXCLUDED.buy_volume_proxy,
                sell_volume_proxy = EXCLUDED.sell_volume_proxy,
                updated_at = now()
            """,
            [asset_id, symbol, net_flow_score or 0.0, accumulation_score or 0.0, volume_ratio, buy_proxy, sell_proxy],
        )

    def _stock_ranking_item(
        self,
        row: dict[str, Any],
        *,
        factor: str,
        timeframe: str = "monthly",
        include_retail_sentiment: bool = False,
    ) -> StockRankingItem:
        if factor == "aggregate":
            result = self._aggregate_stock_score(row["asset_id"], timeframe, include_retail_sentiment)
        elif factor == "share_price_momentum":
            result = self._price_momentum_score(row["asset_id"], timeframe)
        elif factor == "news_sentiment":
            result = self._sentiment_score(row["asset_id"], "news", timeframe)
        elif factor == "retail_sentiment":
            result = self._sentiment_score(row["asset_id"], "retail", timeframe)
        elif factor == "earnings_momentum":
            result = self._earnings_momentum_score(row["asset_id"])
        else:
            result = self._institutional_buying_score(row["asset_id"])

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
        confidence = _stock_ranking_confidence(components, latest_data_date)
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
            confidence=confidence,
            data_status=data_status,
            latest_data_date=latest_data_date,
            missing_inputs=missing,
            components=components,
        )

    def _aggregate_stock_score(self, asset_id: str, timeframe: str, include_retail_sentiment: bool) -> dict[str, Any]:
        factor_results = [
            ("Share price momentum", 0.26, self._price_momentum_score(asset_id, timeframe)),
            ("News sentiment", 0.18, self._sentiment_score(asset_id, "news", timeframe)),
            ("Earnings momentum", 0.28, self._earnings_momentum_score(asset_id)),
            ("Institutional buying", 0.28, self._institutional_buying_score(asset_id)),
        ]
        if include_retail_sentiment:
            factor_results.append(("Retail sentiment add-on", 0.10, self._sentiment_score(asset_id, "retail", timeframe)))
        components: list[StockRankingComponent] = []
        dates = []
        weighted_scores: list[tuple[float, float]] = []
        available_base_weight = sum(weight for _name, weight, result in factor_results if result["score"] is not None)
        for name, weight, result in factor_results:
            score = result["score"]
            if score is not None:
                weighted_scores.append((score, weight))
            components.append(
                StockRankingComponent(
                    name=name,
                    metric="weighted factor score",
                    value=score,
                    score=score,
                    available=score is not None,
                    detail=(
                        f"{name} contributes {round(weight * 100)}% when available."
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
        weighted_score = (
            sum(score * weight for score, weight in weighted_scores) / available_base_weight
            if available_base_weight > 0
            else None
        )
        return {
            "score": weighted_score if weighted_score is not None else sum(scores) / len(scores) if scores else None,
            "latest_data_date": max(dates) if dates else None,
            "components": components,
        }

    def _price_momentum_score(self, asset_id: str, timeframe: str) -> dict[str, Any]:
        prices = ComparisonApiService(self.conn)._prices(asset_id)
        closes = [row[1] for row in reversed(prices)]
        latest_data_date = prices[0][0] if prices else None
        period_days = _STOCK_RANKING_TIMEFRAME_DAYS[timeframe]
        return_value = _period_return(prices, period_days)
        intermediate_return = _period_return(prices, min(period_days * 3, 252))
        long_return = _period_return(prices, min(period_days * 6, 252))
        volatility = _realized_volatility_from_closes(closes)
        trend_scores = [
            _scaled_signal(return_value, _stock_momentum_scale(timeframe)),
            _scaled_signal(intermediate_return, min(_stock_momentum_scale(timeframe) * 2.0, 0.40)),
            _scaled_signal(long_return, min(_stock_momentum_scale(timeframe) * 3.0, 0.65)),
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
                    metric=f"{_STOCK_RANKING_TIMEFRAME_LABELS[timeframe]} return blend",
                    value=return_value,
                    score=trend_score,
                    available=trend_score is not None,
                    detail=(
                        f"Blends {_STOCK_RANKING_TIMEFRAME_LABELS[timeframe]} and adjacent lookback returns from stored daily closes."
                        if trend_score is not None
                        else f"Needs stored daily closes for {_STOCK_RANKING_TIMEFRAME_LABELS[timeframe]} price momentum."
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

    def _sentiment_score(self, asset_id: str, bucket: str, timeframe: str) -> dict[str, Any]:
        momentum_column = _sentiment_momentum_column(timeframe)
        row = self.conn.execute(
            f"""
            SELECT
                date,
                retail_sentiment_score,
                news_sentiment_score,
                blended_sentiment_score,
                {momentum_column},
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
                    metric=f"{_STOCK_RANKING_TIMEFRAME_LABELS[timeframe]} change",
                    value=momentum,
                    score=momentum_score,
                    available=momentum_score is not None,
                    detail=(
                        f"{_STOCK_RANKING_TIMEFRAME_LABELS[timeframe].title()} change in blended sentiment."
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

    def _institutional_buying_score(self, asset_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT date, net_flow_score, accumulation_score, volume_ratio, source
            FROM institutional_buying_daily
            WHERE asset_id = ?
            ORDER BY date DESC
            LIMIT 1
            """,
            [asset_id],
        ).fetchone()
        if row is None:
            return {
                "score": None,
                "latest_data_date": None,
                "components": [
                    StockRankingComponent(
                        name="Institutional buying",
                        metric="net institutional flow",
                        available=False,
                        detail="Needs institutional buying or accumulation proxy data.",
                    )
                ],
            }
        net_flow_score = _float_or_none(row[1])
        accumulation_score = _float_or_none(row[2])
        volume_ratio = _float_or_none(row[3])
        score = _average_present([net_flow_score, accumulation_score])
        return {
            "score": score,
            "latest_data_date": row[0],
            "components": [
                StockRankingComponent(
                    name="Institutional buying",
                    metric="net institutional flow",
                    value=volume_ratio,
                    score=score,
                    available=score is not None,
                    detail=(
                        f"Uses {row[4]} accumulation and volume-flow proxy data."
                        if score is not None
                        else "Needs institutional buying or accumulation proxy data."
                    ),
                )
            ],
        }

    def _portfolio_summary(
        self,
        row,
        *,
        gain_override_rows: list[tuple[float | None, float | None]],
        projection: dict[str, float | int | None],
    ) -> PortfolioSummary:
        market_value = float(row[6])
        book_cost = float(row[7])
        unrealized_gain = market_value - book_cost if market_value else None
        total_gain, total_return_percent, total_gain_source = self._portfolio_total_gain_metrics(
            market_value,
            unrealized_gain,
            gain_override_rows,
        )
        return PortfolioSummary(
            portfolio_id=int(row[0]),
            name=row[1],
            base_ccy=row[2],
            created_at=row[3],
            updated_at=row[4],
            position_count=int(row[5]),
            market_value=market_value,
            book_cost=book_cost,
            unrealized_gain=unrealized_gain,
            unrealized_return_percent=_ratio_or_none(unrealized_gain, book_cost),
            total_gain=total_gain,
            total_return_percent=total_return_percent,
            total_gain_source=total_gain_source,
            projected_value=projection.get("projected_value"),
            projected_value_low=projection.get("projected_value_low"),
            projected_value_high=projection.get("projected_value_high"),
            projected_horizon_years=projection.get("projected_horizon_years"),
        )

    def _portfolio_total_gain_metrics(
        self,
        market_value: float,
        unrealized_gain: float | None,
        override_rows: list[tuple[float | None, float | None]],
    ) -> tuple[float | None, float | None, str]:
        if not override_rows:
            basis = market_value - unrealized_gain if unrealized_gain is not None else None
            return unrealized_gain, _ratio_or_none(unrealized_gain, basis), "unrealized"

        override_market_value = 0.0
        override_gain = 0.0
        for account_value, target_return in override_rows:
            if account_value is None or target_return is None or target_return <= -1:
                continue
            override_market_value += account_value
            override_basis = account_value / (1 + target_return)
            override_gain += account_value - override_basis

        remaining_gain = 0.0
        if unrealized_gain is not None and market_value > override_market_value:
            remaining_share = max(market_value - override_market_value, 0.0) / market_value
            remaining_gain = unrealized_gain * remaining_share
        total_gain = override_gain + remaining_gain
        basis = market_value - total_gain
        return total_gain, _ratio_or_none(total_gain, basis), "manual_override"

    def _portfolio_gain_overrides(
        self,
        portfolio_ids: list[int],
    ) -> dict[int, list[tuple[float | None, float | None]]]:
        if not portfolio_ids:
            return {}
        placeholders = ", ".join("?" for _ in portfolio_ids)
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
                pm.portfolio_id,
                pm.provider_account_id,
                SUM(ps.market_value) FILTER (WHERE ps.market_value IS NOT NULL) AS market_value,
                MAX(o.total_return_percent)
            FROM broker_portfolio_position_map pm
            JOIN broker_account_return_override o
              ON o.provider = pm.provider
             AND o.provider_account_id = pm.provider_account_id
            JOIN latest_positions latest
              ON latest.provider = pm.provider
             AND latest.provider_account_id = pm.provider_account_id
             AND latest.provider_position_id = pm.provider_position_id
            JOIN broker_position_snapshot ps
              ON ps.provider = latest.provider
             AND ps.provider_account_id = latest.provider_account_id
             AND ps.provider_position_id = latest.provider_position_id
             AND ps.as_of_date = latest.as_of_date
            WHERE pm.portfolio_id IN ("""
            + placeholders
            + """)
            GROUP BY pm.portfolio_id, pm.provider_account_id
            """,
            portfolio_ids,
        ).fetchall()
        overrides: dict[int, list[tuple[float | None, float | None]]] = {}
        for row in rows:
            overrides.setdefault(int(row[0]), []).append(
                (_float_or_none(row[2]), _float_or_none(row[3]))
            )
        return overrides

    def _stored_portfolio_projections(
        self,
        portfolio_ids: list[int],
    ) -> dict[int, dict[str, float | int | None]]:
        if not portfolio_ids:
            return {}
        placeholders = ", ".join("?" for _ in portfolio_ids)
        rows = self.conn.execute(
            """
            SELECT portfolio_id, payload_json
            FROM portfolio_analytics_snapshot
            WHERE portfolio_id IN ("""
            + placeholders
            + """)
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY portfolio_id
                ORDER BY snapshot_date DESC, refreshed_at DESC
            ) = 1
            """,
            portfolio_ids,
        ).fetchall()
        projections: dict[int, dict[str, float | int | None]] = {}
        for portfolio_id, payload_json in rows:
            payload = _json_dict(payload_json)
            forecast = _json_dict(payload.get("forecast"))
            simulation = _json_dict(forecast.get("simulation"))
            if not simulation:
                continue
            p50_value = _float_or_none(simulation.get("p50_value"))
            expected_value = _float_or_none(simulation.get("expected_value"))
            projections[int(portfolio_id)] = {
                "projected_value": p50_value or expected_value,
                "projected_value_low": _float_or_none(simulation.get("p10_value")),
                "projected_value_high": _float_or_none(simulation.get("p90_value")),
                "projected_horizon_years": _int_or_none(
                    simulation.get("horizon_years")
                ),
            }
        return projections


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
                    SELECT COALESCE(
                        (SELECT cp.price FROM current_asset_price cp WHERE cp.asset_id = a.asset_id),
                        (
                            SELECT COALESCE(q.adj_close, q.close)
                            FROM asset_quote_daily q
                            WHERE q.asset_id = a.asset_id
                            ORDER BY q.date DESC
                            LIMIT 1
                        )
                    )
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
                    SELECT COALESCE(
                        (SELECT cp.price FROM current_asset_price cp WHERE cp.asset_id = a.asset_id),
                        (
                            SELECT COALESCE(q.adj_close, q.close)
                            FROM asset_quote_daily q
                            WHERE q.asset_id = a.asset_id
                            ORDER BY q.date DESC
                            LIMIT 1
                        )
                    )
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

    def price_history(self, asset_id: str, limit: int, range_key: str = "1Y") -> list[PricePointResponse]:
        normalized_asset_id = asset_id.upper().strip()
        self.get_asset(normalized_asset_id)
        latest_price_date = self.conn.execute(
            """
            SELECT MAX(date)
            FROM asset_quote_daily
            WHERE asset_id = ?
              AND COALESCE(adj_close, close) IS NOT NULL
            """,
            [normalized_asset_id],
        ).fetchone()[0]
        range_start = _range_start_date(range_key, latest_price_date) if latest_price_date else None
        where = ["asset_id = ?", "COALESCE(adj_close, close) IS NOT NULL"]
        params: list[Any] = [normalized_asset_id]
        if range_start is not None:
            where.append("date >= ?")
            params.append(range_start)
        params.append(limit)
        rows = self.conn.execute(
            f"""
            SELECT date, COALESCE(adj_close, close)
            FROM (
                SELECT date, adj_close, close
                FROM asset_quote_daily
                WHERE {" AND ".join(where)}
                ORDER BY date DESC
                LIMIT ?
            )
            ORDER BY date
            """,
            params,
        ).fetchall()
        if len(rows) < 2 and range_key.upper().strip() == "1D":
            rows = self.conn.execute(
                """
                SELECT date, COALESCE(adj_close, close)
                FROM (
                    SELECT date, adj_close, close
                    FROM asset_quote_daily
                    WHERE asset_id = ?
                      AND COALESCE(adj_close, close) IS NOT NULL
                    ORDER BY date DESC
                    LIMIT 2
                )
                ORDER BY date
                """,
                [normalized_asset_id],
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
               OR UPPER(asset_id) = UPPER(?)
               OR UPPER(symbol) = UPPER(?)
            ORDER BY
                CASE WHEN UPPER(asset_id) = UPPER(?) THEN 0 ELSE 1 END,
                CASE WHEN UPPER(asset_id) = UPPER(?) THEN 1 ELSE 2 END,
                asset_id
            LIMIT 1
            """,
            [asset_id, asset_id, f"{asset_id}.TO", f"{asset_id}.TO", asset_id, f"{asset_id}.TO"],
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


@dataclass
class _ComparisonFxAudit:
    display_currency: str
    historical: bool = False
    source: str | None = None
    rate_count: int = 0
    as_of: datetime | None = None
    missing_pairs: set[str] | None = None
    warnings: list[str] | None = None

    def missing(self, pair: str) -> None:
        if self.missing_pairs is None:
            self.missing_pairs = set()
        self.missing_pairs.add(pair)

    def warn(self, message: str) -> None:
        if self.warnings is None:
            self.warnings = []
        if message not in self.warnings:
            self.warnings.append(message)

    def seen_rate(self, source: str | None, as_of: datetime | None) -> None:
        self.rate_count += 1
        if source and self.source is None:
            self.source = source
        if as_of and (self.as_of is None or as_of > self.as_of):
            self.as_of = as_of

    def policy(self, native_currency_count: int) -> ComparisonFxPolicy:
        return ComparisonFxPolicy(
            display_currency=self.display_currency,
            native_currency_count=native_currency_count,
            historical=self.historical,
            source=self.source,
            rate_count=self.rate_count,
            as_of=self.as_of,
            missing_pairs=sorted(self.missing_pairs or set()),
            warnings=self.warnings or [],
        )


class ComparisonApiService:
    CALCULATION_VERSION = "comparison.workspace.v2"
    REQUIRED_OPERATING_COMPANY_METRICS = (
        "market_beta",
        "revenue",
        "gross_margin",
        "operating_margin",
        "net_margin",
        "free_cash_flow",
        "free_cash_flow_yield",
        "cash",
        "total_debt",
        "shares_outstanding",
        "roic",
    )

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

    def workspace(
        self,
        *,
        symbols: str,
        benchmark_index_id: str | None = None,
        period: str = "5Y",
        mode: str = "total-return",
        currency: str = "native",
    ) -> ComparisonWorkspaceResponse:
        all_requested = _unique_symbols(symbols.split(","))
        requested = all_requested[:5]
        assets: list[ComparisonAssetProfile] = []
        failed: list[str] = []
        warnings: list[str] = []
        for symbol in requested:
            try:
                assets.append(self._workspace_profile(symbol, benchmark_index_id))
            except LookupError:
                failed.append(symbol)
        if len(all_requested) > 5:
            warnings.append("Only the first five symbols are compared.")
        if failed:
            warnings.append(f"Unsupported symbols skipped: {', '.join(failed)}.")

        benchmark = None
        if benchmark_index_id:
            try:
                benchmark = self.benchmark_profile(benchmark_index_id)
            except LookupError:
                failed.append(benchmark_index_id.strip().upper())
                warnings.append(f"Benchmark not found: {benchmark_index_id.strip().upper()}.")

        fx_audit = _ComparisonFxAudit(display_currency=currency, historical=currency != "native")
        native_currencies = {asset.asset_id: asset.currency for asset in assets}
        if currency != "native":
            assets = [self._profile_in_currency(asset, currency, fx_audit) for asset in assets]
        histories = {
            asset.asset_id: self._workspace_price_rows(
                asset,
                native_currencies.get(asset.asset_id, asset.currency),
                period,
                mode,
                currency,
                fx_audit,
                benchmark_index_id,
            )
            for asset in assets
        }
        first_dates = [rows[0][0] for rows in histories.values() if rows]
        common_start = max(first_dates) if first_dates else None
        returned_end = max((rows[-1][0] for rows in histories.values() if rows), default=None)
        series = [
            self._history_series(asset, histories[asset.asset_id], common_start, mode)
            for asset in assets
        ]
        for item in series:
            warnings.extend(item.warnings)
        warnings.extend(fx_audit.warnings or [])
        if common_start and any(item.start_date and item.start_date > common_start for item in series):
            warnings.append("Some selected assets have shorter valid history than the common start date.")

        freshness = {asset.symbol: self._freshness(asset.asset_id) for asset in assets}
        insights = []
        if len(assets) >= 2:
            insights.append(
                "Historical series are normalized to 100 at the latest common valid start date using adjusted close where available."
            )
        if benchmark:
            insights.append(f"Benchmark context uses latest stored daily metrics for {benchmark.index_id}.")
        coverage = ComparisonCoverage(
            requested_symbols=requested,
            resolved_symbols=[asset.symbol for asset in assets],
            failed_symbols=failed,
            common_start_date=common_start,
            start_date=common_start,
            end_date=returned_end,
            benchmark=benchmark.index_id if benchmark else None,
            currency=currency,
            mode=mode,
            calculation_version=self.CALCULATION_VERSION,
            warnings=warnings,
        )
        return ComparisonWorkspaceResponse(
            requested_symbols=requested,
            assets=assets,
            failed_symbols=failed,
            benchmark=benchmark,
            historical_series=series,
            freshness=freshness,
            coverage=coverage,
            fx_policy=fx_audit.policy(len({asset.currency for asset in assets})),
            insights=insights,
        )

    def _workspace_profile(
        self,
        symbol: str,
        benchmark_index_id: str | None,
    ) -> ComparisonAssetProfile:
        portfolio_id = _portfolio_symbol_id(symbol)
        if portfolio_id is not None:
            return self._portfolio_profile(portfolio_id, benchmark_index_id)
        try:
            return self.asset_profile(symbol)
        except LookupError:
            return self._benchmark_asset_profile(symbol)

    def _benchmark_asset_profile(self, index_id: str) -> ComparisonAssetProfile:
        benchmark = self.benchmark_profile(index_id)
        latest = self.conn.execute(
            """
            SELECT COALESCE(adj_close, close), price_date
            FROM benchmark_index_daily_price
            WHERE UPPER(index_id) = UPPER(?)
              AND COALESCE(adj_close, close) IS NOT NULL
            ORDER BY price_date DESC
            LIMIT 1
            """,
            [index_id],
        ).fetchone()
        price = _float_or_none(latest[0]) if latest else None
        return ComparisonAssetProfile(
            asset_id=f"benchmark:{benchmark.index_id}",
            symbol=benchmark.index_id,
            fundamental_asset_id=None,
            fundamental_status="not_applicable",
            name=benchmark.name,
            asset_type="benchmark",
            exchange_code=None,
            sector=None,
            industry=None,
            country=None,
            currency=benchmark.currency,
            latest_price=price,
            market_cap=None,
            market_beta=None,
            returns=ComparisonReturns(
                return_1d=benchmark.return_1d,
                return_21d=benchmark.return_21d,
                return_252d=benchmark.return_252d,
            ),
            fundamentals=ComparisonFundamentals(),
            valuation=ValuationContext(),
        )

    def _portfolio_profile(
        self,
        portfolio_id: int,
        benchmark_index_id: str | None,
    ) -> ComparisonAssetProfile:
        portfolio = PortfolioApiService(self.conn).get_portfolio(portfolio_id)
        performance = None
        try:
            performance = PortfolioApiService(self.conn).performance(
                portfolio_id,
                benchmark_index_id,
                "1Y",
            )
        except Exception:
            performance = None
        return ComparisonAssetProfile(
            asset_id=f"portfolio:{portfolio.portfolio_id}",
            symbol=f"PF{portfolio.portfolio_id}",
            fundamental_asset_id=None,
            fundamental_status="not_applicable",
            name=portfolio.name,
            asset_type="portfolio",
            exchange_code=None,
            sector=None,
            industry=None,
            country=None,
            currency=portfolio.base_ccy,
            latest_price=portfolio.market_value,
            market_cap=portfolio.market_value,
            market_beta=None,
            returns=ComparisonReturns(
                return_252d=performance.historical_cumulative_return if performance else None,
            ),
            fundamentals=ComparisonFundamentals(),
            valuation=ValuationContext(),
        )

    def asset_profile(self, asset_id: str) -> ComparisonAssetProfile:
        asset = AssetApiService(self.conn).get_asset(asset_id)
        repo = AnalyticsRepository(self.conn)
        fundamental_asset_id = repo.valuation_asset_id(asset.asset_id)
        company_market_cap, company_beta, company_shares = self._company_metadata(
            fundamental_asset_id,
            asset.market_cap,
            asset.market_beta,
            asset.shares_outstanding,
        )
        prices = self._prices(asset.asset_id)
        latest_price = prices[0][1] if prices else asset.latest_price
        income_statements = self._income_statements(fundamental_asset_id)
        latest_statement = income_statements[0] if income_statements else {}
        balance_statements = self._statements(fundamental_asset_id, "balance")
        balance_statement = (balance_statements or [{}])[0]
        cashflow_statements = self._statements(fundamental_asset_id, "cashflow")
        cashflow_statement = (cashflow_statements or [{}])[0]
        estimate = self._latest_estimate(fundamental_asset_id)
        eps = _first_number(latest_statement, "eps", "epsdiluted", "dilutedEPS", "eps_actual")
        forward_eps = _first_number(estimate, "eps_estimated")
        revenue = _first_number(latest_statement, "revenue", "totalRevenue", "revenue_actual")
        forward_revenue = _first_number(estimate, "revenue_estimated")
        net_income = _first_number(latest_statement, "netIncome", "net_income", "netIncomeCommonStockholders")
        gross_profit = _first_number(latest_statement, "grossProfit", "gross_profit")
        operating_income = _first_number(latest_statement, "operatingIncome", "operating_income")
        ebitda = _first_number(latest_statement, "ebitda", "EBITDA")
        tax_rate = _first_number(latest_statement, "effectiveTaxRate", "taxRate")
        tax_rate = tax_rate if tax_rate is not None and 0 <= tax_rate <= 1 else 0.21
        r_and_d = _first_number(latest_statement, "researchAndDevelopmentExpenses", "researchAndDevelopment")
        free_cash_flow = _first_number(cashflow_statement, "freeCashFlow", "free_cash_flow")
        operating_cash_flow = _first_number(cashflow_statement, "operatingCashFlow", "netCashProvidedByOperatingActivities")
        capex = _first_number(cashflow_statement, "capitalExpenditure", "capital_expenditure")
        if free_cash_flow is None and operating_cash_flow is not None and capex is not None:
            free_cash_flow = operating_cash_flow + capex
        cash = _first_number(balance_statement, "cashAndCashEquivalents", "cashAndShortTermInvestments", "cash")
        total_debt = _first_number(balance_statement, "totalDebt", "debt")
        short_debt = _first_number(balance_statement, "shortTermDebt")
        long_debt = _first_number(balance_statement, "longTermDebt")
        if total_debt is None and short_debt is not None and long_debt is not None:
            total_debt = short_debt + long_debt
        equity = _first_number(balance_statement, "totalStockholdersEquity", "totalEquity")
        current_assets = _first_number(balance_statement, "totalCurrentAssets")
        current_liabilities = _first_number(balance_statement, "totalCurrentLiabilities")
        shares = _first_number(latest_statement, "weightedAverageShsOutDil", "weightedAverageSharesDiluted", "sharesOutstanding")
        sbc = _first_number(cashflow_statement, "stockBasedCompensation", "shareBasedCompensation")
        buybacks = _first_number(cashflow_statement, "commonStockRepurchased", "repurchaseOfCommonStock", "stockRepurchased")
        acquisitions = _first_number(
            cashflow_statement,
            "acquisitionsNet",
            "acquisitions",
            "businessAcquisitionsDisposals",
            "netCashUsedForInvestingAcquisitions",
        )
        invested_capital = (
            total_debt + equity - cash
            if total_debt is not None and equity is not None and cash is not None
            else None
        )
        nopat = operating_income * (1 - tax_rate) if operating_income is not None else None
        reinvestment_spend = sum(
            value
            for value in [
                abs(capex) if capex is not None else None,
                abs(acquisitions) if acquisitions is not None else None,
                r_and_d,
            ]
            if value is not None
        )
        roic_on_reinvestment = self._incremental_roic(
            income_statements,
            balance_statements,
        )
        dividend_yield = self._dividend_yield(fundamental_asset_id, latest_price)
        pe_ratio = latest_price / eps if latest_price is not None and eps and eps > 0 else None
        forward_pe = latest_price / forward_eps if latest_price is not None and forward_eps and forward_eps > 0 else None
        price_to_sales = (
            company_market_cap / revenue
            if company_market_cap is not None and revenue is not None and revenue > 0
            else None
        )
        valuation = self._valuation_context(fundamental_asset_id, asset.sector, asset.industry, pe_ratio)
        fundamentals = ComparisonFundamentals(
            revenue=revenue,
            net_income=net_income,
            eps=eps,
            forward_eps=forward_eps,
            forward_revenue=forward_revenue,
                pe_ratio=pe_ratio,
                forward_pe=forward_pe,
                price_to_sales=price_to_sales,
                free_cash_flow=free_cash_flow,
                free_cash_flow_yield=(
                    free_cash_flow / company_market_cap
                    if free_cash_flow is not None and company_market_cap and company_market_cap > 0
                    else None
                ),
            gross_margin=(
                gross_profit / revenue
                if gross_profit is not None and revenue and revenue > 0
                else None
            ),
            operating_margin=(
                operating_income / revenue
                if operating_income is not None and revenue and revenue > 0
                else None
            ),
            net_margin=(
                net_income / revenue
                if net_income is not None and revenue and revenue > 0
                else None
            ),
            cash=cash,
            total_debt=total_debt,
            net_debt=(
                total_debt - cash
                if total_debt is not None and cash is not None
                else None
            ),
            net_debt_to_ebitda=(
                (total_debt - cash) / ebitda
                if total_debt is not None and cash is not None and ebitda and ebitda > 0
                else None
            ),
            current_ratio=(
                current_assets / current_liabilities
                if current_assets is not None and current_liabilities and current_liabilities > 0
                else None
            ),
            debt_to_equity=(
                total_debt / equity
                if total_debt is not None and equity and equity > 0
                else None
            ),
            shares_outstanding=shares or company_shares,
                dividend_yield=dividend_yield,
                buyback_yield=(
                    abs(buybacks) / company_market_cap
                    if buybacks is not None and company_market_cap and company_market_cap > 0
                    else None
                ),
            stock_based_compensation=sbc,
            acquisition_intensity=(
                abs(acquisitions) / revenue
                if acquisitions is not None and revenue and revenue > 0
                else None
            ),
            reinvestment_rate=(
                reinvestment_spend / revenue
                if reinvestment_spend and revenue and revenue > 0
                else None
            ),
            roic=(
                nopat / invested_capital
                if nopat is not None and invested_capital and invested_capital > 0
                else None
            ),
            roic_on_reinvestment=roic_on_reinvestment,
            customer_concentration=_ratio_like(
                _first_number(
                    latest_statement,
                    "customerConcentration",
                    "customer_concentration",
                    "topCustomerRevenuePercent",
                    "top_customer_revenue_percent",
                )
            ),
            revenue_concentration=_ratio_like(
                _first_number(
                    latest_statement,
                    "revenueConcentration",
                    "revenue_concentration",
                    "topSegmentRevenuePercent",
                    "top_segment_revenue_percent",
                )
            ),
            latest_period_end=latest_statement.get("_period_end_date") or balance_statement.get("_period_end_date") or cashflow_statement.get("_period_end_date"),
            estimate_as_of=estimate.get("_as_of_ts"),
        )
        missing_metrics = self._missing_fundamental_metrics(asset, fundamentals)
        return ComparisonAssetProfile(
            asset_id=asset.asset_id,
            symbol=asset.symbol,
            fundamental_asset_id=fundamental_asset_id,
            fundamental_status="complete" if not missing_metrics else "partial",
            missing_fundamental_metrics=missing_metrics,
            name=asset.name,
            asset_type=asset.asset_type,
            exchange_code=asset.exchange_code,
            sector=asset.sector,
            industry=asset.industry,
            country=asset.country,
            currency=asset.currency,
            latest_price=latest_price,
            market_cap=company_market_cap,
            market_beta=company_beta,
            returns=ComparisonReturns(
                return_1d=_period_return(prices, 1),
                return_5d=_period_return(prices, 5),
                return_21d=_period_return(prices, 21),
                return_252d=_period_return(prices, 252),
            ),
            fundamentals=fundamentals,
            valuation=valuation,
        )

    def _missing_fundamental_metrics(
        self,
        asset: AssetDetail,
        fundamentals: ComparisonFundamentals,
    ) -> list[str]:
        allocation = allocation_class(
            asset_id=asset.asset_id,
            symbol=asset.symbol,
            name=asset.name,
            asset_type=asset.asset_type,
            asset_subtype=asset.asset_subtype,
            sector=asset.sector,
            industry=asset.industry,
        )
        if allocation not in {"Stock", "CDR"} and not asset.is_cdr:
            return []
        values = fundamentals.model_dump()
        values["market_beta"] = self._company_metadata(
            asset.underlying_asset_id or asset.asset_id,
            asset.market_cap,
            asset.market_beta,
            asset.shares_outstanding,
        )[1]
        if _is_financial_company(asset):
            for key in (
                "gross_margin",
                "operating_margin",
                "free_cash_flow",
                "free_cash_flow_yield",
                "roic",
            ):
                values[key] = 0 if values.get(key) is None else values[key]
        if values.get("roic") is None and self._roic_not_applicable(
            asset.underlying_asset_id or asset.asset_id
        ):
            values["roic"] = 0
        return [
            key
            for key in self.REQUIRED_OPERATING_COMPANY_METRICS
            if values.get(key) is None
        ]

    def _company_metadata(
        self,
        asset_id: str,
        fallback_market_cap: float | None,
        fallback_beta: float | None,
        fallback_shares: float | None,
    ) -> tuple[float | None, float | None, float | None]:
        row = self.conn.execute(
            """
            SELECT mkt_cap, market_beta, shares_outstanding
            FROM asset
            WHERE UPPER(asset_id) = UPPER(?)
            """,
            [asset_id],
        ).fetchone()
        if row is None:
            return fallback_market_cap, fallback_beta, fallback_shares
        return (
            _float_or_none(row[0]) or fallback_market_cap,
            _float_or_none(row[1]) or fallback_beta,
            _float_or_none(row[2]) or fallback_shares,
        )

    def _roic_not_applicable(self, asset_id: str) -> bool:
        row = self.conn.execute(
            """
            SELECT data_json
            FROM financial_statement
            WHERE UPPER(asset_id) = UPPER(?)
              AND statement_type = 'balance'
            ORDER BY period_end_date DESC NULLS LAST, year DESC, quarter DESC
            LIMIT 1
            """,
            [asset_id],
        ).fetchone()
        if row is None:
            return False
        data = _json_dict(row[0])
        total_debt = _first_number(data, "totalDebt", "debt") or 0.0
        equity = _first_number(data, "totalStockholdersEquity", "totalEquity")
        cash = _first_number(data, "cashAndCashEquivalents", "cashAndShortTermInvestments", "cash")
        if equity is None or cash is None:
            return False
        return total_debt + equity - cash <= 0

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

    def _price_rows(
        self,
        asset_id: str,
        period: str,
        mode: str,
    ) -> list[tuple[date, float, str | None, datetime | None]]:
        value_expr = "close" if mode == "price-return" else "COALESCE(adj_close, close)"
        latest_price_date = self.conn.execute(
            f"""
            SELECT MAX(date)
            FROM asset_quote_daily
            WHERE asset_id = ?
              AND {value_expr} IS NOT NULL
            """,
            [asset_id],
        ).fetchone()[0]
        range_start = _range_start_date(period, latest_price_date) if latest_price_date else None
        where = [f"{value_expr} IS NOT NULL"]
        params: list[Any] = [asset_id]
        if range_start is not None:
            where.append("date >= ?")
            params.append(range_start)
        rows = self.conn.execute(
            f"""
            SELECT date, {value_expr}, ing_source, ing_at
            FROM asset_quote_daily
            WHERE asset_id = ?
              AND {" AND ".join(where)}
            ORDER BY date ASC
            LIMIT 5000
            """,
            params,
        ).fetchall()
        if len(rows) < 2 and period.upper().strip() == "1D":
            rows = self.conn.execute(
                f"""
                SELECT date, {value_expr}, ing_source, ing_at
                FROM asset_quote_daily
                WHERE asset_id = ?
                  AND {value_expr} IS NOT NULL
                ORDER BY date DESC
                LIMIT 2
                """,
                [asset_id],
            ).fetchall()
            rows = list(reversed(rows))
        return [(row[0], float(row[1]), row[2], row[3]) for row in rows]

    def _workspace_price_rows(
        self,
        asset: ComparisonAssetProfile,
        native_currency: str,
        period: str,
        mode: str,
        currency: str,
        fx_audit: _ComparisonFxAudit,
        benchmark_index_id: str | None,
    ) -> list[tuple[date, float, str | None, datetime | None]]:
        if asset.asset_id.startswith("benchmark:"):
            rows = self._benchmark_price_rows(asset.asset_id.removeprefix("benchmark:"), period, mode)
        elif asset.asset_id.startswith("portfolio:"):
            rows = self._portfolio_price_rows(int(asset.asset_id.removeprefix("portfolio:")), period, benchmark_index_id)
        else:
            rows = self._price_rows(asset.asset_id, period, mode)
        return self._convert_rows_currency(rows, asset.symbol, native_currency, currency, fx_audit)

    def _benchmark_price_rows(
        self,
        index_id: str,
        period: str,
        mode: str,
    ) -> list[tuple[date, float, str | None, datetime | None]]:
        value_expr = "close" if mode == "price-return" else "COALESCE(adj_close, close)"
        latest_price_date = self.conn.execute(
            f"""
            SELECT MAX(price_date)
            FROM benchmark_index_daily_price
            WHERE UPPER(index_id) = UPPER(?)
              AND {value_expr} IS NOT NULL
            """,
            [index_id],
        ).fetchone()[0]
        range_start = _range_start_date(period, latest_price_date) if latest_price_date else None
        where = [f"{value_expr} IS NOT NULL"]
        params: list[Any] = [index_id]
        if range_start is not None:
            where.append("price_date >= ?")
            params.append(range_start)
        rows = self.conn.execute(
            f"""
            SELECT price_date, {value_expr}, source, fetched_at
            FROM benchmark_index_daily_price
            WHERE UPPER(index_id) = UPPER(?)
              AND {" AND ".join(where)}
            ORDER BY price_date ASC
            LIMIT 5000
            """,
            params,
        ).fetchall()
        if len(rows) < 2 and period.upper().strip() == "1D":
            rows = self.conn.execute(
                f"""
                SELECT price_date, {value_expr}, source, fetched_at
                FROM benchmark_index_daily_price
                WHERE UPPER(index_id) = UPPER(?)
                  AND {value_expr} IS NOT NULL
                ORDER BY price_date DESC
                LIMIT 2
                """,
                [index_id],
            ).fetchall()
            rows = list(reversed(rows))
        return [(row[0], float(row[1]), row[2], row[3]) for row in rows]

    def _portfolio_price_rows(
        self,
        portfolio_id: int,
        period: str,
        benchmark_index_id: str | None,
    ) -> list[tuple[date, float, str | None, datetime | None]]:
        performance = PortfolioApiService(self.conn).performance(portfolio_id, benchmark_index_id, period)
        rows = [
            (point.date, float(point.portfolio_value), performance.source, performance.as_of)
            for point in performance.points
            if point.portfolio_value is not None
        ]
        if rows:
            return rows
        return self._current_position_price_rows(portfolio_id, period)

    def _current_position_price_rows(
        self,
        portfolio_id: int,
        period: str,
    ) -> list[tuple[date, float, str | None, datetime | None]]:
        position_rows = self.conn.execute(
            """
            SELECT asset_id, qty
            FROM position
            WHERE portfolio_id = ?
              AND qty <> 0
            ORDER BY asset_id
            """,
            [portfolio_id],
        ).fetchall()
        if not position_rows:
            return []
        asset_ids = [row[0] for row in position_rows]
        quantities = {row[0]: float(row[1]) for row in position_rows}
        placeholders = ", ".join("?" for _ in asset_ids)
        latest_price_date = self.conn.execute(
            f"""
            SELECT MAX(date)
            FROM asset_quote_daily
            WHERE asset_id IN ({placeholders})
              AND close IS NOT NULL
            """,
            asset_ids,
        ).fetchone()[0]
        range_start = _range_start_date(period, latest_price_date) if latest_price_date else None
        params: list[Any] = [*asset_ids]
        where = ["close IS NOT NULL"]
        if range_start is not None:
            where.append("date >= ?")
            params.append(range_start)
        price_rows = self.conn.execute(
            f"""
            SELECT asset_id, date, close, ing_source, ing_at
            FROM asset_quote_daily
            WHERE asset_id IN ({placeholders})
              AND {" AND ".join(where)}
            ORDER BY date ASC
            """,
            params,
        ).fetchall()
        by_date: dict[date, dict[str, tuple[float, str | None, datetime | None]]] = {}
        for asset_id, price_date, close, source, ing_at in price_rows:
            by_date.setdefault(price_date, {})[asset_id] = (float(close), source, ing_at)
        rows: list[tuple[date, float, str | None, datetime | None]] = []
        for price_date in sorted(by_date):
            daily = by_date[price_date]
            if any(asset_id not in daily for asset_id in asset_ids):
                continue
            value = sum(quantities[asset_id] * daily[asset_id][0] for asset_id in asset_ids)
            if value <= 0:
                continue
            source = next((item[1] for item in daily.values() if item[1]), "current_position_backtest")
            ing_at = max((item[2] for item in daily.values() if item[2]), default=None)
            rows.append((price_date, value, f"current_position_backtest:{source}", ing_at))
        return rows

    def _convert_rows_currency(
        self,
        rows: list[tuple[date, float, str | None, datetime | None]],
        symbol: str,
        native_currency: str,
        display_currency: str,
        fx_audit: _ComparisonFxAudit,
    ) -> list[tuple[date, float, str | None, datetime | None]]:
        if display_currency == "native" or native_currency == display_currency:
            return rows
        converted: list[tuple[date, float, str | None, datetime | None]] = []
        missing_dates = 0
        for row_date, value, source, as_of in rows:
            rate = self._fx_rate(native_currency, display_currency, row_date)
            if rate is None:
                missing_dates += 1
                fx_audit.missing(f"{native_currency}->{display_currency}")
                continue
            fx_rate, fx_source, fx_as_of = rate
            fx_audit.seen_rate(fx_source, fx_as_of)
            converted.append((row_date, value * fx_rate, source, as_of))
        if missing_dates:
            fx_audit.warn(
                f"{symbol} skipped {missing_dates} history point(s) because {native_currency}->{display_currency} FX was unavailable."
            )
        return converted

    def _profile_in_currency(
        self,
        profile: ComparisonAssetProfile,
        display_currency: str,
        fx_audit: _ComparisonFxAudit,
    ) -> ComparisonAssetProfile:
        if profile.currency == display_currency:
            return profile
        rate = self._fx_rate(profile.currency, display_currency, date.today(), max_age_days=None)
        if rate is None:
            fx_audit.missing(f"{profile.currency}->{display_currency}")
            fx_audit.warn(
                f"{profile.symbol} summary values remain in {profile.currency}; no recent {profile.currency}->{display_currency} FX rate is stored."
            )
            return profile
        fx_rate, fx_source, fx_as_of = rate
        fx_audit.seen_rate(fx_source, fx_as_of)
        fundamentals = profile.fundamentals.model_copy(update={
            "revenue": _multiply_optional(profile.fundamentals.revenue, fx_rate),
            "net_income": _multiply_optional(profile.fundamentals.net_income, fx_rate),
            "forward_revenue": _multiply_optional(profile.fundamentals.forward_revenue, fx_rate),
            "free_cash_flow": _multiply_optional(profile.fundamentals.free_cash_flow, fx_rate),
            "cash": _multiply_optional(profile.fundamentals.cash, fx_rate),
            "total_debt": _multiply_optional(profile.fundamentals.total_debt, fx_rate),
            "net_debt": _multiply_optional(profile.fundamentals.net_debt, fx_rate),
            "stock_based_compensation": _multiply_optional(profile.fundamentals.stock_based_compensation, fx_rate),
        })
        return profile.model_copy(update={
            "currency": display_currency,
            "latest_price": _multiply_optional(profile.latest_price, fx_rate),
            "market_cap": _multiply_optional(profile.market_cap, fx_rate),
            "fundamentals": fundamentals,
        })

    def _fx_rate(
        self,
        from_ccy: str,
        to_ccy: str,
        rate_date: date,
        max_age_days: int | None = 7,
    ) -> tuple[float, str | None, datetime | None] | None:
        if from_ccy == to_ccy:
            return (1.0, "identity", None)
        age_filter = "" if max_age_days is None else "AND rate_date >= ?"
        params: list[Any] = [from_ccy, to_ccy, rate_date]
        if max_age_days is not None:
            params.append(rate_date - timedelta(days=max_age_days))
        row = self.conn.execute(
            f"""
            SELECT rate, source, as_of_ts
            FROM fx_rate
            WHERE UPPER(from_ccy) = UPPER(?)
              AND UPPER(to_ccy) = UPPER(?)
              AND rate_date <= ?
              {age_filter}
            ORDER BY rate_date DESC
            LIMIT 1
            """,
            params,
        ).fetchone()
        if row:
            return (float(row[0]), row[1], row[2])
        inverse_params: list[Any] = [to_ccy, from_ccy, rate_date]
        if max_age_days is not None:
            inverse_params.append(rate_date - timedelta(days=max_age_days))
        inverse = self.conn.execute(
            f"""
            SELECT rate, source, as_of_ts
            FROM fx_rate
            WHERE UPPER(from_ccy) = UPPER(?)
              AND UPPER(to_ccy) = UPPER(?)
              AND rate_date <= ?
              {age_filter}
            ORDER BY rate_date DESC
            LIMIT 1
            """,
            inverse_params,
        ).fetchone()
        if inverse and inverse[0]:
            return (1.0 / float(inverse[0]), inverse[1], inverse[2])
        return None

    def _history_series(
        self,
        asset: ComparisonAssetProfile,
        rows: list[tuple[date, float, str | None, datetime | None]],
        common_start: date | None,
        mode: str,
    ) -> ComparisonHistorySeries:
        warnings: list[str] = []
        aligned = [row for row in rows if common_start is None or row[0] >= common_start]
        if rows and common_start and rows[0][0] < common_start:
            warnings.append(f"{asset.symbol} history starts before common window and was shortened to {common_start}.")
        if len(aligned) < 2:
            warnings.append(f"{asset.symbol} has insufficient stored history for return calculations.")
        base = aligned[0][1] if aligned and aligned[0][1] else None
        points = [
            ComparisonHistoryPoint(
                date=row[0],
                value=(row[1] / base * 100.0) if base else None,
                close=row[1],
                cumulative_return=(row[1] / base - 1.0) if base else None,
            )
            for row in aligned
        ]
        return ComparisonHistorySeries(
            asset_id=asset.asset_id,
            symbol=asset.symbol,
            mode=mode,
            currency=asset.currency,
            start_date=aligned[0][0] if aligned else None,
            end_date=aligned[-1][0] if aligned else None,
            observation_count=len(aligned),
            source=aligned[-1][2] if aligned else None,
            points=points,
            warnings=warnings,
        )

    def _freshness(self, asset_id: str) -> ComparisonFreshness:
        if asset_id.startswith("benchmark:"):
            index_id = asset_id.removeprefix("benchmark:")
            price = self.conn.execute(
                """
                SELECT price_date, source, fetched_at
                FROM benchmark_index_daily_price
                WHERE UPPER(index_id) = UPPER(?)
                  AND COALESCE(adj_close, close) IS NOT NULL
                ORDER BY price_date DESC
                LIMIT 1
                """,
                [index_id],
            ).fetchone()
            stale = bool(price and price[0] and (date.today() - price[0]).days > 10)
            return ComparisonFreshness(
                latest_price_date=price[0] if price else None,
                latest_price_source=price[1] if price else None,
                latest_price_ingested_at=price[2] if price else None,
                calculation_timestamp=datetime.now(UTC),
                provider="local duckdb benchmark_index_daily_price",
                stale=stale,
                stale_reason="latest stored benchmark price is more than 10 calendar days old" if stale else None,
            )
        if asset_id.startswith("portfolio:"):
            portfolio_id = int(asset_id.removeprefix("portfolio:"))
            portfolio = PortfolioApiService(self.conn).get_portfolio(portfolio_id)
            return ComparisonFreshness(
                latest_price_date=portfolio.as_of.date() if portfolio.as_of else None,
                latest_price_source=portfolio.source,
                latest_price_ingested_at=portfolio.as_of,
                calculation_timestamp=datetime.now(UTC),
                provider="quaint_dash portfolio analytics",
                stale=False,
            )
        price = self.conn.execute(
            """
            SELECT date, ing_source, ing_at
            FROM asset_quote_daily
            WHERE asset_id = ?
              AND COALESCE(adj_close, close) IS NOT NULL
            ORDER BY date DESC
            LIMIT 1
            """,
            [asset_id],
        ).fetchone()
        statement_asset_id = AnalyticsRepository(self.conn).valuation_asset_id(asset_id)
        statement = self.conn.execute(
            """
            SELECT period_end_date, source, ingested_at_utc
            FROM financial_statement
            WHERE asset_id = ?
            ORDER BY period_end_date DESC NULLS LAST, year DESC, quarter DESC
            LIMIT 1
            """,
            [statement_asset_id],
        ).fetchone()
        stale = False
        stale_reason = None
        if price and price[0] and (date.today() - price[0]).days > 10:
            stale = True
            stale_reason = "latest stored price is more than 10 calendar days old"
        return ComparisonFreshness(
            latest_price_date=price[0] if price else None,
            latest_price_source=price[1] if price else None,
            latest_price_ingested_at=price[2] if price else None,
            latest_fiscal_period=statement[0] if statement else None,
            latest_fundamental_source=statement[1] if statement else None,
            latest_fundamental_ingested_at=statement[2] if statement else None,
            calculation_timestamp=datetime.now(UTC),
            provider="local duckdb",
            stale=stale,
            stale_reason=stale_reason,
        )

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

    def _statements(self, asset_id: str, statement_type: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT period_end_date, data_json
            FROM financial_statement
            WHERE asset_id = ?
              AND statement_type = ?
            ORDER BY period_end_date DESC NULLS LAST, year DESC, quarter DESC
            """,
            [asset_id, statement_type],
        ).fetchall()
        statements: list[dict[str, Any]] = []
        for period_end, payload in rows:
            data = _json_dict(payload)
            if data:
                data["_period_end_date"] = period_end
                statements.append(data)
        return statements

    def _latest_estimate(self, asset_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT eps_estimated, revenue_estimated, as_of_ts
            FROM earnings_calendar_event
            WHERE asset_id = ?
              AND (eps_estimated IS NOT NULL OR revenue_estimated IS NOT NULL)
            ORDER BY earnings_date DESC
            LIMIT 1
            """,
            [asset_id],
        ).fetchone()
        if row is None:
            return {}
        return {
            "eps_estimated": _float_or_none(row[0]),
            "revenue_estimated": _float_or_none(row[1]),
            "_as_of_ts": row[2],
        }

    def _dividend_yield(self, asset_id: str, latest_price: float | None) -> float | None:
        if latest_price is None or latest_price <= 0:
            return None
        row = self.conn.execute(
            """
            SELECT SUM(dividend_per_share)
            FROM dividend_event
            WHERE asset_id = ?
              AND dividend_per_share IS NOT NULL
              AND ex_date >= CURRENT_DATE - INTERVAL 370 DAY
            """,
            [asset_id],
        ).fetchone()
        annual_dividend = _float_or_none(row[0]) if row else None
        if annual_dividend is None:
            return None
        return annual_dividend / latest_price

    def _incremental_roic(
        self,
        income_statements: list[dict[str, Any]],
        balance_statements: list[dict[str, Any]],
    ) -> float | None:
        if len(income_statements) < 2 or len(balance_statements) < 2:
            return None
        current_income = income_statements[0]
        previous_income = income_statements[1]
        current_balance = balance_statements[0]
        previous_balance = balance_statements[1]
        current_operating_income = _first_number(current_income, "operatingIncome", "operating_income")
        previous_operating_income = _first_number(previous_income, "operatingIncome", "operating_income")
        current_tax = _first_number(current_income, "effectiveTaxRate", "taxRate")
        previous_tax = _first_number(previous_income, "effectiveTaxRate", "taxRate")
        current_tax = current_tax if current_tax is not None and 0 <= current_tax <= 1 else 0.21
        previous_tax = previous_tax if previous_tax is not None and 0 <= previous_tax <= 1 else 0.21
        current_nopat = current_operating_income * (1 - current_tax) if current_operating_income is not None else None
        previous_nopat = previous_operating_income * (1 - previous_tax) if previous_operating_income is not None else None
        current_invested = _statement_invested_capital(current_balance)
        previous_invested = _statement_invested_capital(previous_balance)
        if current_nopat is None or previous_nopat is None or current_invested is None or previous_invested is None:
            return None
        incremental_capital = current_invested - previous_invested
        if incremental_capital <= 0:
            return None
        return (current_nopat - previous_nopat) / incremental_capital

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

    def broker_status(self) -> BrokerStatusResponse:
        from dotenv import load_dotenv

        load_dotenv()
        repo = BrokerSyncRepository(self.conn)
        configured = bool(os.getenv("SNAPTRADE_CLIENT_ID") and os.getenv("SNAPTRADE_CONSUMER_KEY"))
        profile_row = self.conn.execute(
            """
            SELECT user_key, status
            FROM broker_user
            WHERE provider = ?
            ORDER BY
                CASE WHEN status = 'active' THEN 0 ELSE 1 END,
                updated_at DESC
            LIMIT 1
            """,
            [SNAPTRADE_PROVIDER],
        ).fetchone()
        last_row = self.conn.execute(
            """
            SELECT
                MAX(started_at),
                MAX(completed_at) FILTER (WHERE status IN ('done', 'success'))
            FROM broker_sync_run
            WHERE provider = ?
            """,
            [SNAPTRADE_PROVIDER],
        ).fetchone()
        min_age_hours = int(os.getenv("BROKER_SYNC_MIN_AGE_HOURS", "1") or "1")
        last_success = last_row[1] if last_row else None
        next_eligible = last_success + timedelta(hours=min_age_hours) if last_success else None
        scheduled_enabled = os.getenv("BROKER_SYNC_BACKGROUND_ENABLED", "false").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        return BrokerStatusResponse(
            provider=SNAPTRADE_PROVIDER,
            configured=configured,
            broker_profile_ready=bool(profile_row and profile_row[1] == "active"),
            broker_profile_status=str(profile_row[1]) if profile_row else "missing",
            broker_profile_key=str(profile_row[0]) if profile_row else None,
            raw_payload_storage_enabled=repo.raw_payload_storage_enabled(),
            scheduled_refresh_enabled=scheduled_enabled,
            freshness_window_hours=min_age_hours,
            max_users_per_run=_int_or_none(os.getenv("BROKER_SYNC_MAX_USERS")),
            last_refresh_at=last_row[0] if last_row else None,
            last_successful_refresh_at=last_success,
            last_scheduled_run_at=last_success,
            next_eligible_refresh_at=next_eligible,
            provider_message=None if configured else "Missing SnapTrade environment configuration.",
        )

    def broker_connections(self) -> list[BrokerConnectionResponse]:
        account_counts = {
            row[0]: int(row[1])
            for row in self.conn.execute(
                """
                SELECT provider_connection_id, COUNT(*)
                FROM broker_account
                WHERE provider = ?
                GROUP BY provider_connection_id
                """,
                [SNAPTRADE_PROVIDER],
            ).fetchall()
        }
        sync_rows = {
            row[0]: row
            for row in self.conn.execute(
                """
                WITH sync_summary AS (
                    SELECT
                        connection_id,
                        MAX(started_at) AS last_attempted_at,
                        MAX(completed_at) FILTER (WHERE status IN ('done', 'success')) AS last_successful_at
                    FROM broker_sync_run
                    GROUP BY connection_id
                )
                SELECT
                    c.provider_connection_id,
                    s.last_attempted_at,
                    s.last_successful_at,
                    (
                        SELECT STRING_AGG(r.error_message, ' | ' ORDER BY r.started_at DESC)
                        FROM broker_sync_run r
                        WHERE r.connection_id = c.connection_id
                          AND r.error_message IS NOT NULL
                          AND r.error_message <> ''
                          AND (
                              s.last_successful_at IS NULL
                              OR r.started_at > s.last_successful_at
                          )
                    )
                FROM broker_connection c
                LEFT JOIN sync_summary s ON s.connection_id = c.connection_id
                WHERE c.provider = ?
                """,
                [SNAPTRADE_PROVIDER],
            ).fetchall()
        }
        return [
            BrokerConnectionResponse(
                provider=item.provider,
                connection_id=item.connection_id,
                provider_connection_id=item.provider_connection_id,
                institution_name=item.institution_name,
                status=item.status,
                account_count=account_counts.get(item.provider_connection_id, 0),
                last_attempted_refresh_at=sync_rows.get(item.provider_connection_id, [None, None, None, None])[1],
                last_successful_refresh_at=sync_rows.get(item.provider_connection_id, [None, None, None, None])[2],
                last_error=sync_rows.get(item.provider_connection_id, [None, None, None, None])[3],
            )
            for item in BrokerSyncRepository(self.conn).list_connections()
        ]

    def broker_account_responses(self) -> list[BrokerAccountResponse]:
        position_summaries = self._broker_account_position_summaries()
        txn_summaries = self._broker_account_transaction_summaries()
        portfolio_names = {
            int(row[0]): row[1]
            for row in self.conn.execute(
                "SELECT portfolio_id, portfolio_name FROM portfolio"
            ).fetchall()
        }
        responses: list[BrokerAccountResponse] = []
        for item in self.broker_accounts():
            if not _is_visible_broker_account(item.raw_payload):
                continue
            position_summary = position_summaries.get(
                item.provider_account_id,
                _BrokerAccountPositionSummary(),
            )
            currency = (
                item.currency
                or _currency_from_raw_account(item.raw_payload)
                or position_summary.currency
            )
            cash_balance = _account_cash_balance(
                item.raw_payload,
                item.balance,
                position_summary.holdings_value,
            )
            total_value = self._account_total_value(
                item.balance,
                cash_balance,
                position_summary.holdings_value,
            )
            responses.append(
                BrokerAccountResponse(
                    provider=item.provider,
                    provider_account_id=item.provider_account_id,
                    provider_connection_id=item.provider_connection_id,
                    masked_account_number=_masked_account_number(item.raw_payload),
                    account_name=item.account_name,
                    account_type=item.account_type,
                    currency=_valid_currency(currency),
                    balance=total_value,
                    cash_balance=cash_balance,
                    holdings_value=position_summary.holdings_value,
                    total_value=total_value,
                    position_count=position_summary.position_count,
                    latest_position_date=position_summary.latest_position_date,
                    portfolio_id=item.portfolio_id,
                    portfolio_name=portfolio_names.get(int(item.portfolio_id)) if item.portfolio_id is not None else None,
                    available_transaction_count=txn_summaries.get(item.provider_account_id, {}).get("available", 0),
                    imported_transaction_count=txn_summaries.get(item.provider_account_id, {}).get("imported", 0),
                    unsupported_transaction_count=txn_summaries.get(item.provider_account_id, {}).get("unsupported", 0),
                    latest_activity_date=txn_summaries.get(item.provider_account_id, {}).get("latest_activity_date"),
                    last_imported_at=txn_summaries.get(item.provider_account_id, {}).get("last_imported_at"),
                    updated_at=_broker_account_updated_at(self.conn, item.provider, item.provider_account_id),
                )
            )
        return responses

    def _broker_account_transaction_summaries(self) -> dict[str, dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                bt.provider_account_id,
                COUNT(*) FILTER (WHERE m.provider_transaction_id IS NULL) AS available,
                COUNT(*) FILTER (WHERE m.provider_transaction_id IS NOT NULL) AS imported,
                COUNT(*) FILTER (WHERE LOWER(bt.txn_type) NOT IN ('buy', 'sell', 'dividend', 'interest', 'fee', 'tax', 'contribution', 'withdrawal', 'reinvestment', 'transfer')) AS unsupported,
                MAX(bt.trade_date),
                MAX(m.imported_at)
            FROM broker_transaction bt
            LEFT JOIN broker_portfolio_txn_map m
              ON m.provider = bt.provider
             AND m.provider_transaction_id = bt.provider_transaction_id
            WHERE bt.provider = ?
            GROUP BY bt.provider_account_id
            """,
            [SNAPTRADE_PROVIDER],
        ).fetchall()
        return {
            row[0]: {
                "available": int(row[1] or 0),
                "imported": int(row[2] or 0),
                "unsupported": int(row[3] or 0),
                "latest_activity_date": row[4],
                "last_imported_at": row[5],
            }
            for row in rows
        }

    def broker_sync_history(self, limit: int = 25) -> list[BrokerSyncHistoryItem]:
        rows = self.conn.execute(
            """
            SELECT
                r.sync_run_id,
                r.provider,
                r.user_key,
                c.institution_name,
                r.started_at,
                r.completed_at,
                r.accounts_seen,
                r.positions_seen,
                r.transactions_seen,
                r.status,
                r.error_message
            FROM broker_sync_run r
            LEFT JOIN broker_connection c ON c.connection_id = r.connection_id
            ORDER BY r.started_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()
        items: list[BrokerSyncHistoryItem] = []
        for row in rows:
            duration = None
            if row[5] is not None and row[4] is not None:
                duration = (row[5] - row[4]).total_seconds()
            items.append(
                BrokerSyncHistoryItem(
                    sync_run_id=int(row[0]),
                    provider=row[1],
                    user_key=row[2],
                    connection_label=row[3],
                    trigger_type="manual",
                    started_at=row[4],
                    completed_at=row[5],
                    duration_seconds=duration,
                    accounts_processed=int(row[6] or 0),
                    positions_stored=int(row[7] or 0),
                    activities_stored=int(row[8] or 0),
                    status=_sync_status_label(row[9], row[10]),
                    error_summary=_redact_sensitive_text(row[10]),
                )
            )
        return items

    def broker_import_preview(self, item_limit: int = 25) -> BrokerImportPreviewResponse:
        rows = self.conn.execute(
            """
            SELECT
                bt.provider_transaction_id,
                c.institution_name,
                ba.account_name,
                ba.raw_json,
                ba.portfolio_id,
                p.portfolio_name,
                bt.trade_date,
                bt.txn_type,
                bt.asset_id,
                bt.symbol,
                bt.quantity,
                bt.price,
                bt.amount,
                bt.currency,
                m.provider_transaction_id IS NOT NULL AS imported
            FROM broker_transaction bt
            LEFT JOIN broker_account ba
              ON ba.provider = bt.provider
             AND ba.provider_account_id = bt.provider_account_id
            LEFT JOIN broker_connection c
              ON c.provider = ba.provider
             AND c.provider_connection_id = ba.provider_connection_id
            LEFT JOIN portfolio p ON p.portfolio_id = ba.portfolio_id
            LEFT JOIN broker_portfolio_txn_map m
              ON m.provider = bt.provider
             AND m.provider_transaction_id = bt.provider_transaction_id
            WHERE bt.provider = ?
            ORDER BY c.institution_name, ba.account_name, bt.trade_date DESC, bt.provider_transaction_id
            """,
            [SNAPTRADE_PROVIDER],
        ).fetchall()
        groups: dict[tuple[Any, ...], BrokerImportPreviewGroup] = {}
        date_values = []
        totals = {
            "ready": 0,
            "already_imported": 0,
            "unsupported": 0,
            "needs_review": 0,
            "unresolved_asset": 0,
            "failed_validation": 0,
        }
        for row in rows:
            category = _broker_activity_category(row[7])
            status, reason = _broker_import_status(
                category=category,
                portfolio_id=row[4],
                asset_id=row[8],
                imported=bool(row[14]),
                quantity=row[10],
                amount=row[12],
            )
            totals[status] += 1
            key = (row[1], row[2], row[4], row[5], _masked_account_number(_json_dict(row[3])))
            group = groups.setdefault(
                key,
                BrokerImportPreviewGroup(
                    institution_name=row[1],
                    account_name=row[2],
                    masked_account_number=key[4],
                    portfolio_id=row[4],
                    portfolio_name=row[5],
                ),
            )
            _increment_preview_group(group, status, category)
            date_values.append(row[6])
            if len(group.items) < item_limit:
                group.items.append(
                    BrokerImportPreviewItem(
                        provider_transaction_id=row[0],
                        institution_name=row[1],
                        account_name=row[2],
                        masked_account_number=key[4],
                        portfolio_id=row[4],
                        portfolio_name=row[5],
                        trade_date=row[6],
                        source_type=row[7],
                        category=category,
                        status=status,
                        symbol=row[9],
                        quantity=_float_or_none(row[10]),
                        price=_float_or_none(row[11]),
                        amount=_float_or_none(row[12]),
                        currency=_valid_currency(row[13]),
                        normalization_result=reason,
                    )
                )
        return BrokerImportPreviewResponse(
            generated_at=datetime.now(UTC),
            total_transactions=len(rows),
            ready_count=totals["ready"],
            already_imported_count=totals["already_imported"],
            unsupported_count=totals["unsupported"],
            needs_review_count=totals["needs_review"],
            unresolved_asset_count=totals["unresolved_asset"],
            failed_validation_count=totals["failed_validation"],
            date_start=min(date_values) if date_values else None,
            date_end=max(date_values) if date_values else None,
            groups=list(groups.values()),
        )

    def broker_reconciliation(self) -> BrokerReconciliationResponse:
        rows = self.conn.execute(
            """
            WITH latest_positions AS (
                SELECT
                    provider,
                    provider_account_id,
                    provider_position_id,
                    MAX(as_of_date) AS as_of_date
                FROM broker_position_snapshot
                WHERE provider = ?
                GROUP BY provider, provider_account_id, provider_position_id
            ),
            latest_prices AS (
                SELECT asset_id, close
                FROM asset_quote_daily
                QUALIFY ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY date DESC) = 1
            ),
            local_ledger AS (
                SELECT
                    provider,
                    provider_account_id,
                    provider_position_id,
                    pm.asset_id,
                    quantity,
                    quantity * lp.close AS market_value,
                    updated_at
                FROM broker_portfolio_position_map pm
                LEFT JOIN latest_prices lp ON lp.asset_id = pm.asset_id
            )
            SELECT
                c.institution_name,
                ba.account_name,
                ba.raw_json,
                p.symbol,
                p.asset_id,
                p.quantity,
                l.quantity,
                p.market_value,
                l.market_value,
                p.currency,
                p.as_of_date,
                l.updated_at,
                ba.portfolio_id
            FROM broker_position_snapshot p
            JOIN latest_positions latest
              ON latest.provider = p.provider
             AND latest.provider_account_id = p.provider_account_id
             AND latest.provider_position_id = p.provider_position_id
             AND latest.as_of_date = p.as_of_date
            LEFT JOIN broker_account ba
              ON ba.provider = p.provider
             AND ba.provider_account_id = p.provider_account_id
            LEFT JOIN broker_connection c
              ON c.provider = ba.provider
             AND c.provider_connection_id = ba.provider_connection_id
            LEFT JOIN local_ledger l
              ON l.provider = p.provider
             AND l.provider_account_id = p.provider_account_id
             AND l.provider_position_id = p.provider_position_id
            ORDER BY c.institution_name, ba.account_name, p.symbol
            """,
            [SNAPTRADE_PROVIDER],
        ).fetchall()
        items = []
        for row in rows:
            broker_qty = _float_or_none(row[5])
            local_qty = _float_or_none(row[6])
            broker_value = _float_or_none(row[7])
            local_value = _float_or_none(row[8])
            quantity_difference = _difference(broker_qty, local_qty)
            value_difference = _difference(broker_value, local_value)
            items.append(
                BrokerReconciliationItem(
                    institution_name=row[0],
                    account_name=row[1],
                    masked_account_number=_masked_account_number(_json_dict(row[2])),
                    ticker=row[3],
                    asset_id=row[4],
                    broker_quantity=broker_qty,
                    local_quantity=local_qty,
                    quantity_difference=quantity_difference,
                    broker_market_value=broker_value,
                    local_market_value=local_value,
                    value_difference=value_difference,
                    currency=_valid_currency(row[9]),
                    broker_data_timestamp=row[10],
                    local_ledger_timestamp=row[11],
                    status=_reconciliation_status(row[4], row[12], quantity_difference, value_difference, row[10]),
                )
            )
        return BrokerReconciliationResponse(generated_at=datetime.now(UTC), items=items)

    def _broker_account_position_summaries(self) -> dict[str, "_BrokerAccountPositionSummary"]:
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
                MAX(p.currency) FILTER (WHERE p.currency IS NOT NULL) AS currency,
                COUNT(*) AS position_count,
                MAX(p.as_of_date) AS latest_position_date
            FROM broker_position_snapshot p
            JOIN latest_positions latest
              ON latest.provider = p.provider
             AND latest.provider_account_id = p.provider_account_id
             AND latest.provider_position_id = p.provider_position_id
             AND latest.as_of_date = p.as_of_date
            WHERE p.provider = ?
              AND COALESCE(ABS(p.quantity), 0) >= 0.0001
              AND (p.market_value IS NULL OR ABS(p.market_value) >= 0.01)
            GROUP BY p.provider_account_id
            """,
            [SNAPTRADE_PROVIDER],
        ).fetchall()
        return {
            row[0]: _BrokerAccountPositionSummary(
                holdings_value=_float_or_none(row[1]),
                currency=_valid_currency(row[2]),
                position_count=int(row[3] or 0),
                latest_position_date=row[4],
            )
            for row in rows
        }

    @staticmethod
    def _account_total_value(
        account_balance: float | None,
        cash_balance: float | None,
        holdings_value: float | None,
    ) -> float | None:
        if account_balance is not None:
            return account_balance
        if holdings_value is not None:
            return holdings_value + (cash_balance or 0.0)
        if cash_balance is not None:
            return cash_balance
        return account_balance

    def active_broker_user_key(self, provider: str = SNAPTRADE_PROVIDER) -> str | None:
        row = self.conn.execute(
            """
            SELECT user_key
            FROM broker_user
            WHERE provider = ?
              AND status = 'active'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            [provider],
        ).fetchone()
        return str(row[0]) if row else None

    def broker_user_key_or_default(self, user_key: str | None) -> str:
        if user_key and user_key.strip():
            return user_key.strip()
        return self.active_broker_user_key() or "default"

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

    def retail_sentiment_status(self, limit: int = 10) -> RetailSentimentStatusResponse:
        providers = ["reddit", "x"]
        post_rows = self.conn.execute(
            """
            SELECT provider, COUNT(*), MAX(published_at)
            FROM social_post
            WHERE provider IN ('reddit', 'x')
            GROUP BY provider
            """
        ).fetchall()
        post_stats = {row[0]: (int(row[1]), row[2]) for row in post_rows}
        job_rows = self.conn.execute(
            """
            SELECT dataset, status, COUNT(*), MAX(error_message)
            FROM ingestion_job
            WHERE domain = 'sentiment'
              AND dataset IN ('reddit', 'x')
            GROUP BY dataset, status
            """
        ).fetchall()
        job_stats: dict[str, dict[str, tuple[int, str | None]]] = {provider: {} for provider in providers}
        for dataset, status, count, latest_error in job_rows:
            job_stats.setdefault(dataset, {})[status] = (int(count), latest_error)

        latest_snapshots = [
            RetailSentimentDailySnapshot(
                asset_id=row[0],
                ticker=row[1],
                date=row[2],
                retail_sentiment_score=row[3],
                reddit_post_count=int(row[4] or 0),
                x_post_count=int(row[5] or 0),
                bullish_count=int(row[6] or 0),
                neutral_count=int(row[7] or 0),
                bearish_count=int(row[8] or 0),
                sentiment_momentum_1d=row[9],
                unusual_volume_flag=bool(row[10]),
            )
            for row in self.conn.execute(
                """
                SELECT
                    asset_id,
                    ticker,
                    date,
                    retail_sentiment_score,
                    reddit_post_count,
                    x_post_count,
                    bullish_count,
                    neutral_count,
                    bearish_count,
                    sentiment_momentum_1d,
                    unusual_volume_flag
                FROM ticker_sentiment_daily
                WHERE retail_sentiment_score IS NOT NULL
                   OR reddit_post_count > 0
                   OR x_post_count > 0
                ORDER BY date DESC, reddit_post_count + x_post_count DESC, ticker
                LIMIT ?
                """,
                [limit],
            ).fetchall()
        ]
        recent_posts = [
            RetailSentimentPost(
                provider=row[0],
                source_name=row[1],
                ticker=row[2],
                asset_id=row[3],
                title=row[4],
                body=row[5],
                url=row[6],
                published_at=row[7],
                score=row[8],
                comment_count=row[9],
                like_count=row[10],
                repost_count=row[11],
                reply_count=row[12],
                relevance_score=float(row[13]),
            )
            for row in self.conn.execute(
                """
                SELECT
                    p.provider,
                    p.source_name,
                    m.ticker,
                    m.asset_id,
                    p.title,
                    p.body,
                    p.url,
                    p.published_at,
                    p.score,
                    p.comment_count,
                    p.like_count,
                    p.repost_count,
                    p.reply_count,
                    m.relevance_score
                FROM social_post p
                JOIN social_post_asset_mention m ON m.post_id = p.post_id
                WHERE p.provider IN ('reddit', 'x')
                ORDER BY COALESCE(p.published_at, p.fetched_at) DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()
        ]
        return RetailSentimentStatusResponse(
            providers=[
                RetailSentimentProviderStatus(
                    provider=provider,
                    configured=_retail_provider_configured(provider),
                    post_count=post_stats.get(provider, (0, None))[0],
                    latest_post_at=post_stats.get(provider, (0, None))[1],
                    open_jobs=sum(job_stats.get(provider, {}).get(status, (0, None))[0] for status in ["pending", "running"]),
                    failed_jobs=job_stats.get(provider, {}).get("failed", (0, None))[0],
                    latest_error=job_stats.get(provider, {}).get("failed", (0, None))[1],
                )
                for provider in providers
            ],
            latest_snapshots=latest_snapshots,
            recent_posts=recent_posts,
            pending_jobs=sum(job_stats.get(provider, {}).get("pending", (0, None))[0] for provider in providers),
            running_jobs=sum(job_stats.get(provider, {}).get("running", (0, None))[0] for provider in providers),
            failed_jobs=sum(job_stats.get(provider, {}).get("failed", (0, None))[0] for provider in providers),
        )

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
        portfolio_service._ensure_stock_ranking_inputs(rows)
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
                ranking = portfolio_service._stock_ranking_item(
                    row,
                    factor=factor,
                    timeframe="monthly",
                    include_retail_sentiment=False,
                )
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
            SELECT
                shares_outstanding,
                asset_type,
                asset_subtype,
                symbol,
                name
            FROM asset
            WHERE asset_id = ?
            """,
            [asset_id],
        ).fetchone()
        value = _float_or_none(row[0]) if row else None
        asset_type = str(row[1] or "").lower() if row else ""
        if asset_type in {"etf", "fund", "index"}:
            return IngestionRequirementStatus(
                key="shares_outstanding",
                label="Shares outstanding",
                ready=True,
                detail="not applicable to fund projection inputs",
                row_count=0,
            )
        valuation_asset_id = AnalyticsRepository(self.conn).valuation_asset_id(asset_id)
        if valuation_asset_id != asset_id:
            underlying = self.conn.execute(
                """
                SELECT shares_outstanding
                FROM asset
                WHERE asset_id = ?
                """,
                [valuation_asset_id],
            ).fetchone()
            value = _float_or_none(underlying[0]) if underlying else None
            ready = value is not None and value > 0
            return IngestionRequirementStatus(
                key="shares_outstanding",
                label="Shares outstanding",
                ready=ready,
                detail=(
                    f"{value:,.0f} underlying-company shares"
                    if ready
                    else "underlying-company metadata queued for enrichment"
                ),
                row_count=1 if ready else 0,
            )
        ready = value is not None and value > 0
        return IngestionRequirementStatus(
            key="shares_outstanding",
            label="Shares outstanding",
            ready=ready,
            detail=(
                f"{value:,.0f} shares"
                if ready
                else "company metadata queued for enrichment"
            ),
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
        from dashboard.ingestion.job_policy import MAX_INGESTION_JOB_ATTEMPTS

        where = [
            "status = 'failed'",
            "COALESCE(attempt_count, 0) < ?",
            (
                "(job_type = 'earnings_backup' OR "
                "NOT (LOWER(COALESCE(error_message, '')) LIKE '%http error 402%'))"
            ),
            (
                "(job_type = 'earnings_backup' OR "
                "NOT (LOWER(COALESCE(error_message, '')) LIKE '%plan does not include%'))"
            ),
        ]
        params: list[object] = [MAX_INGESTION_JOB_ATTEMPTS]
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
                lease_owner = NULL,
                leased_at = NULL,
                lease_expires_at = NULL,
                terminal_reason = NULL,
                completed_at = NULL,
                updated_at = now()
            WHERE job_id IN (
                SELECT job_id
                FROM ingestion_job
                WHERE {" AND ".join(where)}
                  AND NOT EXISTS (
                      SELECT 1
                      FROM ingestion_job newer
                      WHERE newer.asset_id = ingestion_job.asset_id
                        AND newer.domain = ingestion_job.domain
                        AND newer.dataset = ingestion_job.dataset
                        AND newer.status = 'done'
                        AND newer.job_id > ingestion_job.job_id
                  )
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


def _retail_provider_configured(provider: str) -> bool:
    if provider == "reddit":
        return all(
            os.getenv(name)
            for name in ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"]
        )
    if provider == "x":
        return bool(os.getenv("X_BEARER_TOKEN"))
    return False


def _signal_status(data_status: str, strength: float, confidence: float, data_as_of: date | None) -> str:
    if data_status != "complete" or data_as_of is None:
        return "unavailable"
    age_days = (date.today() - data_as_of).days
    if age_days > 7:
        return "expired"
    if confidence < 0.45:
        return "candidate"
    if strength >= 0.65 and confidence >= 0.7:
        return "active"
    if strength >= 0.35:
        return "confirmed"
    return "weakening"


def _stock_ranking_confidence(
    components: list[StockRankingComponent],
    latest_data_date: date | None,
) -> float:
    if not components:
        return 0.0
    available_count = sum(1 for component in components if component.available)
    coverage = available_count / len(components)
    breadth = min(1.0, available_count / 2)
    if latest_data_date is None:
        freshness = 0.0
    else:
        age_days = max(0, (date.today() - latest_data_date).days)
        if age_days <= 7:
            freshness = 1.0
        elif age_days <= 31:
            freshness = 0.9
        elif age_days <= 90:
            freshness = 0.8
        else:
            freshness = 0.7
    confidence = (coverage * 0.55) + (breadth * 0.15) + (freshness * 0.30)
    return round(min(0.98, confidence), 2)


def _is_etf_like_asset(
    *,
    symbol: str | None,
    name: str | None,
    asset_type: str | None,
    asset_subtype: str | None,
) -> bool:
    values = [
        asset_type or "",
        asset_subtype or "",
        name or "",
        symbol or "",
    ]
    haystack = " ".join(values).lower()
    return (
        "etf" in haystack
        or "exchange traded fund" in haystack
        or "exchange-traded fund" in haystack
    )


def _signal_evidence_from_components(
    components: list[StockRankingComponent],
    direction: str,
    as_of: date | None,
) -> tuple[list[SignalEvidenceItem], list[SignalEvidenceItem]]:
    supporting: list[SignalEvidenceItem] = []
    contradicting: list[SignalEvidenceItem] = []
    for component in components:
        evidence = SignalEvidenceItem(
            label=component.name,
            metric=component.metric,
            value=component.value,
            score=component.score,
            detail=component.detail,
            source="stored ranking component",
            as_of=as_of,
        )
        if component.score is None:
            contradicting.append(evidence)
        elif direction == "positive" and component.score >= 0:
            supporting.append(evidence)
        elif direction == "negative" and component.score <= 0:
            supporting.append(evidence)
        elif direction == "neutral":
            supporting.append(evidence)
        else:
            contradicting.append(evidence)
    return supporting, contradicting


def _signal_summary_sentence(
    item: StockRankingItem,
    factor: str,
    direction: str,
    supporting: list[SignalEvidenceItem],
    contradicting: list[SignalEvidenceItem],
) -> str:
    main = supporting[0].label.lower() if supporting else _STOCK_RANKING_LABELS[factor].lower()
    direction_text = {
        "positive": "improved enough to merit review",
        "negative": "weakened enough to merit review",
        "neutral": "is mixed and should be watched",
    }[direction]
    conflict = " Contradicting evidence is present." if contradicting else ""
    return f"{item.symbol} {main} {direction_text} with {item.confidence:.0%} input confidence.{conflict}"


def _signal_sort_key(sort: str):
    if sort == "triggered":
        return lambda row: row.first_detected_at or date.min
    if sort == "strength":
        return lambda row: row.strength
    if sort == "confidence":
        return lambda row: row.confidence
    if sort == "portfolio_weight":
        return lambda row: row.current_portfolio_weight or 0.0
    if sort == "score_change":
        return lambda row: abs(row.raw_observed_value or 0.0)
    if sort == "efficacy":
        return lambda row: row.historical_efficacy.sample_size
    if sort == "ticker":
        return lambda row: row.ticker
    if sort == "market_cap":
        return lambda row: row.portfolio_priority
    return lambda row: row.portfolio_priority


def _signal_summary_metrics(rows: list[SignalRow]) -> list[SignalSummaryMetric]:
    today = date.today()
    return [
        SignalSummaryMetric(key="active", label="Active signals", value=sum(row.status == "active" for row in rows), filter_params={"status": "active"}),
        SignalSummaryMetric(key="new", label="New today", value=sum(row.first_detected_at == today for row in rows), filter_params={"triggered_after": today.isoformat()}),
        SignalSummaryMetric(key="risks", label="High-priority risks", value=sum(row.direction == "negative" and row.portfolio_priority >= 0.65 for row in rows), filter_params={"direction": "negative", "min_priority": "0.65"}),
        SignalSummaryMetric(key="opportunities", label="High-confidence opportunities", value=sum(row.direction == "positive" and row.confidence >= 0.7 for row in rows), filter_params={"direction": "positive", "min_confidence": "0.7"}),
        SignalSummaryMetric(key="resolved", label="Recently resolved", value=sum(row.status == "resolved" for row in rows), filter_params={"status": "resolved"}),
        SignalSummaryMetric(key="incomplete", label="Stale or incomplete", value=sum(row.status in {"expired", "unavailable"} or row.missing_data_status != "complete" for row in rows), filter_params={"completeness": "incomplete"}),
    ]


def _pending_signal_efficacy() -> SignalEfficacyMetadata:
    return SignalEfficacyMetadata(
        label="Calculated for matching result rows",
        sample_size=0,
        prior_occurrences=0,
        methodology_version=_SIGNALS_MODEL_VERSION,
        warning="Historical efficacy is computed after filtering so the summary can load without evaluating every possible signal.",
    )


def _signal_provider_failures(rows: list[SignalRow]) -> list[str]:
    missing = sorted({row.missing_data_status for row in rows if row.missing_data_status != "complete"})
    return [f"{status} input coverage" for status in missing]


def _signal_lifecycle(row: SignalRow) -> list[SignalLifecycleEvent]:
    return [
        SignalLifecycleEvent(status="candidate", timestamp=row.first_detected_at, label="Candidate", detail="Signal appeared in stored model inputs."),
        SignalLifecycleEvent(status=row.status, timestamp=row.confirmation_at or row.last_evaluated_at, label=row.status.replace("_", " ").title(), detail="Current lifecycle state after confidence, freshness, and strength checks."),
    ]


def _signals_methodology(*, include_retail_sentiment: bool = False) -> str:
    retail_note = (
        " Retail sentiment is included as an optional social-attention add-on; it can support or challenge the institutional and analyst-style inputs, but it is not treated as their equal."
        if include_retail_sentiment
        else " Retail sentiment is excluded from this signal view unless the optional social-attention add-on is enabled."
    )
    return (
        "Signals are deterministic server-side evaluations adapted from stored ranking inputs. "
        "Strength measures normalized signal magnitude, confidence measures input coverage, and portfolio priority combines strength, confidence, position weight, and number of affected portfolios. "
        "Historical efficacy is shown only when prior point-in-time evaluations are available."
        f"{retail_note}"
    )


def _range_to_days(value: str) -> int | None:
    normalized = value.upper().strip()
    if normalized == "YTD":
        return (date.today() - date(date.today().year, 1, 1)).days
    return {
        "1D": 1,
        "1W": 7,
        "1M": 31,
        "1Y": 365,
        "3Y": 365 * 3,
        "5Y": 365 * 5,
        "10Y": 365 * 10,
        "MAX": None,
    }.get(normalized, 365)


def _range_start_date(value: str, anchor: date) -> date | None:
    normalized = value.upper().strip()
    if normalized in {"MAX", "MAXIMUM"}:
        return None
    if normalized == "YTD":
        return date(anchor.year, 1, 1)
    days = {
        "1D": 1,
        "1W": 7,
        "1M": 31,
        "3M": 93,
        "6M": 186,
        "1Y": 365,
        "3Y": 365 * 3,
        "5Y": 365 * 5,
        "10Y": 365 * 10,
    }.get(normalized, 365)
    return anchor - timedelta(days=days)


def _comparison_period_days(value: str) -> int | None:
    normalized = value.upper().strip()
    if normalized == "YTD":
        return (date.today() - date(date.today().year, 1, 1)).days
    return {
        "1D": 1,
        "1W": 7,
        "1M": 31,
        "3M": 93,
        "6M": 186,
        "1Y": 365,
        "3Y": 365 * 3,
        "5Y": 365 * 5,
        "10Y": 365 * 10,
        "MAX": None,
    }.get(normalized, 365 * 5)


def _unique_symbols(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        symbol = value.strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        result.append(symbol)
    return result


def _portfolio_symbol_id(value: str) -> int | None:
    match = re.fullmatch(r"(?:PF|PORTFOLIO)[-_:]?(\d+)", value.strip().upper())
    if not match:
        return None
    return int(match.group(1))


def _multiply_optional(value: float | None, multiplier: float) -> float | None:
    return value * multiplier if value is not None else None


def _ratio_like(value: float | None) -> float | None:
    if value is None:
        return None
    return value / 100 if value > 1 else value


def _statement_invested_capital(statement: dict[str, Any]) -> float | None:
    cash = _first_number(statement, "cashAndCashEquivalents", "cashAndShortTermInvestments", "cash")
    total_debt = _first_number(statement, "totalDebt", "debt")
    short_debt = _first_number(statement, "shortTermDebt")
    long_debt = _first_number(statement, "longTermDebt")
    if total_debt is None and short_debt is not None and long_debt is not None:
        total_debt = short_debt + long_debt
    equity = _first_number(statement, "totalStockholdersEquity", "totalEquity")
    if total_debt is None or equity is None or cash is None:
        return None
    return total_debt + equity - cash


def _coverage_from_points(points: list[PortfolioPerformancePoint]) -> float | None:
    if not points:
        return None
    covered = sum(1 for point in points if point.portfolio_value is not None)
    return covered / len(points)


def _binding_constraints(weights: dict[str, float], max_weight: float) -> list[str]:
    constraints = []
    if any(abs(weight - max_weight) <= 0.0001 for weight in weights.values()):
        constraints.append("max_holding_weight")
    if abs(sum(weights.values()) - 1.0) <= 0.0001:
        constraints.append("weights_sum_to_100_percent")
    return constraints


def _ratio_or_none(numerator, denominator) -> float | None:
    numerator = _float_or_none(numerator)
    denominator = _float_or_none(denominator)
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _table_exists(conn, table_name: str) -> bool:
    try:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE lower(table_name) = lower(?)
            """,
            [table_name],
        ).fetchone()
        return bool(row and row[0])
    except Exception:
        return False


def _normalized_weight(value) -> float | None:
    weight = _float_or_none(value)
    if weight is None:
        return None
    return weight / 100 if weight > 1 else weight


def _normalize_exposure_map(values: dict[str, float]) -> dict[str, float]:
    total = sum(value for value in values.values() if value > 0)
    if total <= 0:
        return {}
    return {key: value / total for key, value in sorted(values.items()) if value > 0}


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
        "sector": _canonical_sector_label(sector or override["sector"]),
        "industry": _canonical_industry_label(industry or override["industry"]),
        "country": override["country"] if country is None or country.upper() == "CA" else country,
    }


def _is_financial_company(asset: AssetDetail) -> bool:
    sector = _normalized_lookup_key(asset.sector)
    industry = _normalized_lookup_key(asset.industry)
    return sector == "financials" or sector == "financial services" or industry in {
        "asset management",
        "banks",
        "credit services",
        "insurance",
    }


_SECTOR_LABEL_ALIASES = {
    "technology": "Information Technology",
    "information technology": "Information Technology",
    "healthcare": "Health Care",
    "health care": "Health Care",
    "financial services": "Financials",
    "financials": "Financials",
    "consumer cyclical": "Consumer Discretionary",
    "consumer discretionary": "Consumer Discretionary",
    "consumer defensive": "Consumer Staples",
    "consumer staples": "Consumer Staples",
    "communication services": "Communication Services",
    "communications": "Communication Services",
    "industrial": "Industrials",
    "industrials": "Industrials",
    "basic materials": "Materials",
    "materials": "Materials",
    "real estate": "Real Estate",
    "energy": "Energy",
    "utilities": "Utilities",
}

_SECTOR_ETF_BY_SYMBOL = {
    "IYW": "Information Technology",
    "IXN": "Information Technology",
    "VGT": "Information Technology",
    "XLK": "Information Technology",
    "FTEC": "Information Technology",
    "IYH": "Health Care",
    "VHT": "Health Care",
    "XLV": "Health Care",
    "IYF": "Financials",
    "VFH": "Financials",
    "XLF": "Financials",
    "IYC": "Consumer Discretionary",
    "VCR": "Consumer Discretionary",
    "XLY": "Consumer Discretionary",
    "IYK": "Consumer Staples",
    "VDC": "Consumer Staples",
    "XLP": "Consumer Staples",
    "IYE": "Energy",
    "VDE": "Energy",
    "XLE": "Energy",
    "IYJ": "Industrials",
    "VIS": "Industrials",
    "XLI": "Industrials",
    "IYM": "Materials",
    "VAW": "Materials",
    "XLB": "Materials",
    "IYR": "Real Estate",
    "VNQ": "Real Estate",
    "XLRE": "Real Estate",
    "IDU": "Utilities",
    "VPU": "Utilities",
    "XLU": "Utilities",
    "VOX": "Communication Services",
    "XLC": "Communication Services",
}


def _canonical_sector_label(value: str | None) -> str | None:
    key = _normalized_lookup_key(value)
    if not key:
        return None
    return _SECTOR_LABEL_ALIASES.get(key, str(value).strip())


def _canonical_industry_label(value: str | None) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _canonical_country_label(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if text in {"UNITED STATES", "USA"}:
        return "US"
    if text in {"CANADA"}:
        return "CA"
    return text or None


def _position_sector_label(
    *,
    asset_id: str,
    symbol: str,
    name: str | None,
    asset_type: str | None,
    asset_subtype: str | None,
    sector: str | None,
    industry: str | None,
) -> str | None:
    allocation = allocation_class(
        asset_id=asset_id,
        symbol=symbol,
        name=name,
        asset_type=asset_type,
        asset_subtype=asset_subtype,
        sector=sector,
        industry=industry,
    )
    if allocation == "Money market":
        return "Money market"
    if allocation == "ETF":
        symbol_key = str(symbol or asset_id or "").upper().split(".", maxsplit=1)[0]
        return _SECTOR_ETF_BY_SYMBOL.get(symbol_key) or "Broad market"
    return _canonical_sector_label(sector)


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


def _stock_ranking_methodology(
    factor: str,
    universe: str,
    timeframe: str = "monthly",
    include_retail_sentiment: bool = False,
) -> str:
    scope = "tracked stocks" if universe == "tracked" else "the available stock catalog"
    label = _STOCK_RANKING_LABELS[factor]
    window = _STOCK_RANKING_TIMEFRAME_LABELS[timeframe]
    if factor == "aggregate":
        retail = (
            " Retail sentiment is included as a small 10% social-attention add-on."
            if include_retail_sentiment
            else " Retail sentiment is excluded; enable it when you want social crowd tone to lightly influence the rating."
        )
        return (
            f"Ranks {scope} by a weighted {window} blend of price momentum, news sentiment, "
            f"earnings momentum, and institutional buying inputs.{retail}"
        )
    if factor == "share_price_momentum":
        return (
            f"Ranks {scope} by {window} stored daily close momentum, blended with realized volatility as a risk modifier."
        )
    if factor == "news_sentiment":
        return f"Ranks {scope} by the latest stored news sentiment snapshot and {window} sentiment momentum."
    if factor == "retail_sentiment":
        return f"Ranks {scope} by the latest stored retail/social sentiment snapshot and {window} sentiment momentum."
    if factor == "earnings_momentum":
        return f"Ranks {scope} by stored income statement growth and latest earnings surprise data."
    return f"Ranks {scope} by {label.lower()} using stored institutional flow or local accumulation proxy data."


def _retail_sentiment_label(score: float | None) -> str:
    if score is None:
        return "No social data"
    if score >= 0.35:
        return "Strongly bullish"
    if score >= 0.12:
        return "Bullish"
    if score <= -0.35:
        return "Strongly bearish"
    if score <= -0.12:
        return "Bearish"
    return "Mixed"


def _retail_sentiment_confidence(source_count: int, snapshot_date: date | datetime | None) -> float:
    if source_count <= 0 or snapshot_date is None:
        return 0.0
    coverage = min(1.0, source_count / 20.0)
    observed_date = snapshot_date.date() if isinstance(snapshot_date, datetime) else snapshot_date
    age_days = max(0, (date.today() - observed_date).days)
    freshness = 1.0 if age_days <= 1 else 0.75 if age_days <= 7 else 0.45 if age_days <= 30 else 0.2
    return round(coverage * freshness, 3)


def _stock_momentum_scale(timeframe: str) -> float:
    return {
        "daily": 0.035,
        "weekly": 0.08,
        "monthly": 0.15,
        "yearly": 0.45,
    }[timeframe]


def _sentiment_momentum_column(timeframe: str) -> str:
    return {
        "daily": "sentiment_momentum_1d",
        "weekly": "sentiment_momentum_7d",
        "monthly": "sentiment_momentum_30d",
        "yearly": "sentiment_momentum_30d",
    }[timeframe]


def _stable_asset_bias(value: str) -> float:
    total = sum((index + 1) * ord(char) for index, char in enumerate(value.upper()))
    return (total % 1000) / 1000.0


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


def _holding_ranking_timeframe(timeframe: str) -> str:
    return {
        "1d": "daily",
        "1w": "weekly",
        "1m": "monthly",
        "1y": "yearly",
    }[timeframe]


def _score_grade(score: float | None) -> str:
    if score is None:
        return "Incomplete"
    if score >= 65:
        return "A"
    if score >= 25:
        return "B"
    if score >= -10:
        return "C"
    if score >= -45:
        return "D"
    return "F"


def _holding_factor_component(
    name: str,
    metric: str,
    score: float | None,
    value: float | None,
    detail: str,
    missing_detail: str,
) -> HoldingSignalComponent:
    return HoldingSignalComponent(
        name=name,
        metric=metric,
        value=value,
        contribution=score,
        score=round(score, 2) if score is not None else None,
        grade=_score_grade(score) if score is not None else None,
        available=score is not None,
        detail=detail if score is not None else missing_detail,
    )


def _holding_value_score(profile: ComparisonAssetProfile) -> float | None:
    valuation = profile.valuation
    fundamentals = profile.fundamentals
    valuation_scores = [
        _scaled_signal(_negative_optional(valuation.historical_pe_discount), 0.35),
        _scaled_signal(_negative_optional(valuation.sector_pe_premium), 0.35),
        _scaled_signal(_negative_optional(valuation.industry_pe_premium), 0.35),
        _scaled_signal(fundamentals.free_cash_flow_yield, 0.08),
        _scaled_signal(fundamentals.dividend_yield, 0.04),
    ]
    return _average_present(valuation_scores)


def _holding_value_value(profile: ComparisonAssetProfile) -> float | None:
    return _average_present(
        [
            profile.valuation.historical_pe_discount,
            profile.valuation.sector_pe_premium,
            profile.valuation.industry_pe_premium,
        ]
    )


def _holding_quality_score(profile: ComparisonAssetProfile) -> float | None:
    fundamentals = profile.fundamentals
    return _average_present(
        [
            _scaled_signal(fundamentals.roic, 0.18),
            _scaled_signal(fundamentals.roic_on_reinvestment, 0.25),
            _scaled_signal(0.50 - fundamentals.customer_concentration, 0.50) if fundamentals.customer_concentration is not None else None,
            _scaled_signal(0.55 - fundamentals.revenue_concentration, 0.55) if fundamentals.revenue_concentration is not None else None,
        ]
    )


def _holding_profitability_score(profile: ComparisonAssetProfile) -> float | None:
    fundamentals = profile.fundamentals
    return _average_present(
        [
            _scaled_signal(fundamentals.gross_margin, 0.55),
            _scaled_signal(fundamentals.operating_margin, 0.25),
            _scaled_signal(fundamentals.net_margin, 0.18),
            _scaled_signal(fundamentals.free_cash_flow_yield, 0.08),
        ]
    )


def _holding_financial_strength_score(profile: ComparisonAssetProfile) -> float | None:
    fundamentals = profile.fundamentals
    net_debt_score = None
    if fundamentals.net_debt_to_ebitda is not None:
        net_debt_score = _scaled_signal(2.5 - fundamentals.net_debt_to_ebitda, 2.5)
    leverage_score = None
    if fundamentals.debt_to_equity is not None:
        leverage_score = _scaled_signal(1.2 - fundamentals.debt_to_equity, 1.2)
    liquidity_score = None
    if fundamentals.current_ratio is not None:
        liquidity_score = _scaled_signal(min(fundamentals.current_ratio, 3.0) - 1.0, 1.5)
    return _average_present([net_debt_score, leverage_score, liquidity_score])


def _holding_ownership_score(profile: ComparisonAssetProfile, institutional_score: float | None) -> float | None:
    fundamentals = profile.fundamentals
    sbc_intensity = (
        fundamentals.stock_based_compensation / fundamentals.revenue
        if fundamentals.stock_based_compensation is not None and fundamentals.revenue and fundamentals.revenue > 0
        else None
    )
    return _average_present(
        [
            institutional_score,
            _scaled_signal(fundamentals.buyback_yield, 0.04),
            _scaled_signal(0.08 - sbc_intensity, 0.08) if sbc_intensity is not None else None,
        ]
    )


def _score_from_ranking_components(components: list[StockRankingComponent]) -> float | None:
    return _average_present([component.score for component in components if component.available])


def _first_component_value(components: list[StockRankingComponent]) -> float | None:
    for component in components:
        if component.value is not None:
            return component.value
        if component.score is not None:
            return component.score
    return None


def _negative_optional(value: float | None) -> float | None:
    return -value if value is not None else None


def _relative_gap(value: float | None, comparison: float | None) -> float | None:
    if value is None or comparison is None or comparison == 0:
        return None
    return value / comparison - 1


@dataclass(frozen=True, slots=True)
class _BrokerAccountPositionSummary:
    holdings_value: float | None = None
    currency: str | None = None
    position_count: int = 0
    latest_position_date: date | None = None


_ACCOUNT_CASH_KEYS = {
    "cash",
    "cashamount",
    "cashbalance",
    "cashbalanceamount",
    "totalcash",
    "availablecash",
    "availabletotrade",
    "availablefunds",
    "buyingpower",
    "settledcash",
    "unsettledcash",
}
_ACCOUNT_TOTAL_KEYS = {
    "total",
    "totalvalue",
    "marketvalue",
    "accountvalue",
    "equity",
    "netliquidation",
    "netliquidationvalue",
    "portfolio",
    "portfoliovalue",
}


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


def _account_cash_balance(
    raw_payload: dict,
    account_balance: float | None,
    holdings_value: float | None,
) -> float | None:
    raw_cash = _cash_value_from_payload(raw_payload)
    if raw_cash is not None:
        return raw_cash
    balance = _float_or_none(account_balance)
    if balance is None:
        return None
    if holdings_value is None:
        return balance
    return max(balance - holdings_value, 0.0)


def _cash_value_from_payload(raw_payload: dict) -> float | None:
    explicit = _first_payload_number(
        raw_payload,
        lambda path: bool(path) and _key_token(path[-1]) in _ACCOUNT_CASH_KEYS,
    )
    if explicit is not None:
        return explicit

    balance = raw_payload.get("balance")
    if isinstance(balance, dict):
        return _first_payload_number(
            balance,
            lambda path: bool(path)
            and _key_token(path[-1]) in _ACCOUNT_CASH_KEYS
            and not any(_key_token(part) in _ACCOUNT_TOTAL_KEYS for part in path[:-1]),
        )
    return None


def _first_payload_number(value: Any, match_key: Any, path: tuple[str, ...] = ()) -> float | None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, str(key))
            if match_key(child_path):
                number = _amount_from_payload_node(child)
                if number is not None:
                    return number
            nested = _first_payload_number(child, match_key, child_path)
            if nested is not None:
                return nested
    if isinstance(value, list):
        for idx, child in enumerate(value):
            nested = _first_payload_number(child, match_key, (*path, str(idx)))
            if nested is not None:
                return nested
    return None


def _amount_from_payload_node(value: Any) -> float | None:
    if isinstance(value, dict):
        for key in ("amount", "value", "cash"):
            number = _float_or_none(value.get(key))
            if number is not None:
                return number
        return None
    number = _float_or_none(value)
    if number is not None:
        return number
    return None


def _key_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


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


def _int_or_none(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _broker_account_updated_at(conn, provider: str, provider_account_id: str) -> datetime | None:
    row = conn.execute(
        """
        SELECT updated_at
        FROM broker_account
        WHERE provider = ?
          AND provider_account_id = ?
        """,
        [provider, provider_account_id],
    ).fetchone()
    return row[0] if row else None


def _masked_account_number(raw_payload: dict[str, Any]) -> str | None:
    candidates: list[str] = []

    def visit(value: Any, path: tuple[str, ...] = ()) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                token = _key_token(str(key))
                if token in {"number", "accountnumber", "accountno", "accountid", "institutionaccountid"}:
                    if child is not None:
                        candidates.append(str(child))
                visit(child, (*path, str(key)))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, (*path, str(index)))

    visit(raw_payload)
    value = next((item for item in candidates if item.strip()), None)
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) >= 4:
        return f"****{digits[-4:]}"
    clean = value.strip()
    return f"****{clean[-4:]}" if len(clean) > 4 else "****"


def _broker_activity_category(value: str | None) -> str:
    text = _key_token(value or "")
    if text in {"buy", "bought", "purchase"}:
        return "buys"
    if text in {"sell", "sold"}:
        return "sells"
    if "dividend" in text:
        return "dividends"
    if "interest" in text:
        return "interest"
    if "fee" in text or "commission" in text:
        return "fees"
    if "tax" in text or "withholding" in text:
        return "taxes"
    if "contribution" in text or "deposit" in text:
        return "contributions"
    if "withdrawal" in text:
        return "withdrawals"
    if "reinvest" in text or text == "drip":
        return "reinvestments"
    if "transfer" in text:
        return "transfers"
    return "unknown"


def _broker_import_status(
    *,
    category: str,
    portfolio_id: int | None,
    asset_id: str | None,
    imported: bool,
    quantity: Any,
    amount: Any,
) -> tuple[str, str]:
    if imported:
        return "already_imported", "Already imported through the idempotency map."
    if portfolio_id is None:
        return "needs_review", "Assign this brokerage account to a portfolio before importing."
    if category == "unknown":
        return "unsupported", "Unsupported broker activity is retained for review."
    if category in {"buys", "sells", "reinvestments"} and not asset_id:
        return "unresolved_asset", "Needs a resolved local asset before import."
    if category in {"buys", "sells"} and _float_or_none(quantity) is None:
        return "failed_validation", "Trade activity is missing a valid quantity."
    if category not in {"buys", "sells", "reinvestments", "transfers"} and _float_or_none(amount) is None:
        return "failed_validation", "Cash activity is missing a valid amount."
    return "ready", "Eligible to import into the assigned local portfolio."


def _increment_preview_group(group: BrokerImportPreviewGroup, status: str, category: str) -> None:
    if status == "ready":
        group.ready_count += 1
    elif status == "already_imported":
        group.already_imported_count += 1
    elif status == "unsupported":
        group.unsupported_count += 1
    elif status == "needs_review":
        group.needs_review_count += 1
    elif status == "unresolved_asset":
        group.unresolved_asset_count += 1
    elif status == "failed_validation":
        group.failed_validation_count += 1
    current = getattr(group.category_counts, category, None)
    if current is not None:
        setattr(group.category_counts, category, current + 1)


def _difference(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def _reconciliation_status(
    asset_id: str | None,
    portfolio_id: int | None,
    quantity_difference: float | None,
    value_difference: float | None,
    broker_date: date | None,
) -> str:
    if asset_id is None:
        return "unresolved_asset"
    if portfolio_id is None:
        return "missing_transactions"
    if broker_date is not None and broker_date < date.today() - timedelta(days=7):
        return "stale_snapshot"
    if quantity_difference is not None and abs(quantity_difference) > 0.0001:
        return "quantity_mismatch"
    if value_difference is not None and abs(value_difference) > 1.0:
        return "value_mismatch"
    return "fully_reconciled"


def _sync_status_label(status: str, error: str | None) -> str:
    text = (status or "").lower()
    if error:
        return "partial_success" if text in {"done", "success"} else "failure"
    if text in {"done", "success"}:
        return "success"
    if text == "running":
        return "running"
    return "failure"


def _redact_sensitive_text(value: str | None) -> str | None:
    if not value:
        return None
    redacted = re.sub(r"(user[_ -]?secret|secret|token|key)=([^&\s]+)", r"\1=REDACTED", value, flags=re.IGNORECASE)
    redacted = re.sub(r"https?://\S+", "[redacted url]", redacted)
    return redacted[:240]
