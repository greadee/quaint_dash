"""Versioned HTTP API routes."""

from datetime import date
from threading import Lock

from fastapi import APIRouter, Depends, Query, Request, status

from dashboard.api.dependencies import get_connection
from dashboard.api.models import (
    ActionResult,
    AssetBenchmarkAssociationResponse,
    AssetActivitySummary,
    AssetDetail,
    AssetHoldingSummary,
    AssetSearchResult,
    BenchmarkBulkHardenRequest,
    BenchmarkBulkRefreshRequest,
    BenchmarkConstituent,
    BenchmarkDailyMetric,
    BenchmarkDefaultResponse,
    BenchmarkExposure,
    BenchmarkIndexDetail,
    BenchmarkIndexSummary,
    BenchmarkPricePoint,
    BenchmarkReadinessResponse,
    BenchmarkRefreshRequest,
    BenchmarkHardenRequest,
    BenchmarkSeedRequest,
    BrokerAccountMappingRequest,
    BrokerAccountResponse,
    BrokerConnectionResponse,
    BrokerDueRefreshRequest,
    BrokerExistingUserCreate,
    BrokerImportPreviewResponse,
    BrokerImportRequest,
    BrokerPortalRequest,
    BrokerPortalResponse,
    BrokerReconciliationResponse,
    BrokerStatusResponse,
    BrokerStorageSettingRequest,
    BrokerStorageSettingResponse,
    BrokerSyncHistoryItem,
    BrokerSyncRequest,
    BrokerUserCreate,
    BrokerUserResponse,
    ComparisonResponse,
    ComparisonWorkspaceResponse,
    DataReadinessWorkerStatusResponse,
    IngestionJobResponse,
    IngestionBackgroundStatusResponse,
    IngestionReadinessResponse,
    IngestionRetryFailedRequest,
    IngestionRunRequest,
    IngestionScheduleRequest,
    MarketFreshnessStatusResponse,
    HoldingSignalsResponse,
    OverviewUpdatesResponse,
    Page,
    PortfolioCreate,
    OptimizationPreviewRequest,
    OptimizationPreviewResponse,
    PortfolioFundamentalsResponse,
    PortfolioPerformanceResponse,
    PortfolioRiskResponse,
    PortfolioSummary,
    PortfolioUpdate,
    PositionSummary,
    PricePointResponse,
    SignalAlertRuleRequest,
    SignalAlertRuleResponse,
    SignalDetailResponse,
    SignalUserState,
    SignalUserStateRequest,
    SignalsSummaryResponse,
    StockRankingReadinessResponse,
    StockRankingSnapshotRefreshRequest,
    StockRankingSnapshotRefreshResponse,
    StockRankingsResponse,
    TransactionSummary,
    WatchlistAssetResponse,
)
from dashboard.api.services import (
    AssetApiService,
    BenchmarkApiService,
    CommandApiService,
    ComparisonApiService,
    PortfolioApiService,
)

router = APIRouter(prefix="/api/v1")


@router.get("/portfolios", response_model=list[PortfolioSummary])
def list_portfolios(conn=Depends(get_connection)):
    return PortfolioApiService(conn).list_portfolios()


@router.get("/overview/updates", response_model=OverviewUpdatesResponse)
def overview_updates(conn=Depends(get_connection)):
    return PortfolioApiService(conn).overview_updates()


@router.get("/signals", response_model=SignalsSummaryResponse)
def signals_summary(
    q: str | None = Query(default=None, max_length=80),
    portfolio_id: int | None = Query(default=None, ge=0),
    owned: str | None = Query(default=None, pattern="^(owned|unowned)$"),
    category: str | None = Query(default=None, max_length=64),
    direction: str | None = Query(default=None, pattern="^(positive|negative|neutral)$"),
    status: str | None = Query(
        default=None,
        pattern="^(candidate|confirmed|active|weakening|resolved|invalidated|expired|unavailable)$",
    ),
    min_strength: float | None = Query(default=None, ge=0, le=1),
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    min_priority: float | None = Query(default=None, ge=0, le=1),
    sector: str | None = Query(default=None, max_length=80),
    industry: str | None = Query(default=None, max_length=120),
    freshness: str | None = Query(default=None, pattern="^(fresh|stale)$"),
    completeness: str | None = Query(default=None, pattern="^(complete|incomplete)$"),
    triggered_after: date | None = None,
    triggered_before: date | None = None,
    sort: str = Query(default="priority", pattern="^(priority|triggered|strength|confidence|portfolio_weight|score_change|efficacy|ticker|market_cap)$"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    conn=Depends(get_connection),
):
    return PortfolioApiService(conn).signals_summary(
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
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/signals/{signal_id:path}", response_model=SignalDetailResponse)
def signal_detail(signal_id: str, conn=Depends(get_connection)):
    return PortfolioApiService(conn).signal_detail(signal_id)


@router.put("/signals/{signal_id:path}/user-state", response_model=SignalUserState)
def update_signal_user_state(
    signal_id: str,
    payload: SignalUserStateRequest,
    request: Request,
    conn=Depends(get_connection),
):
    with request.app.state.write_lock:
        return PortfolioApiService(conn).update_signal_user_state(signal_id, payload)


@router.post("/signals/{signal_id:path}/alerts", response_model=SignalAlertRuleResponse)
def create_signal_alert_rule(
    signal_id: str,
    payload: SignalAlertRuleRequest,
    request: Request,
    conn=Depends(get_connection),
):
    with request.app.state.write_lock:
        return PortfolioApiService(conn).create_signal_alert_rule(signal_id, payload)


@router.get("/rankings/stocks", response_model=StockRankingsResponse)
def stock_rankings(
    factor: str = Query(
        default="aggregate",
        pattern="^(aggregate|share_price_momentum|news_sentiment|retail_sentiment|earnings_momentum|institutional_buying)$",
    ),
    universe: str = Query(default="tracked", pattern="^(tracked|all)$"),
    direction: str = Query(default="buy", pattern="^(buy|sell)$"),
    timeframe: str = Query(default="monthly", pattern="^(daily|weekly|monthly|yearly)$"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    conn=Depends(get_connection),
):
    return PortfolioApiService(conn).stock_rankings(
        factor=factor,
        universe=universe,
        direction=direction,
        timeframe=timeframe,
        limit=limit,
        offset=offset,
    )


@router.get("/holdings/signals", response_model=HoldingSignalsResponse)
def holding_signals(
    timeframe: str = Query(default="1m", pattern="^(1d|1w|1m|1y)$"),
    conn=Depends(get_connection),
):
    return PortfolioApiService(conn).holding_signals(timeframe)


@router.post("/rankings/stocks/snapshots", response_model=StockRankingSnapshotRefreshResponse)
def refresh_stock_ranking_snapshots(
    payload: StockRankingSnapshotRefreshRequest,
    request: Request,
    conn=Depends(get_connection),
):
    with request.app.state.write_lock:
        return PortfolioApiService(conn).refresh_stock_ranking_snapshots(
            factor=payload.factor,
            universe=payload.universe,
            timeframe=payload.timeframe,
            limit=payload.limit,
        )


@router.post("/watchlist/assets/{asset_id}", response_model=WatchlistAssetResponse)
def add_watchlist_asset(asset_id: str, request: Request, conn=Depends(get_connection)):
    with request.app.state.write_lock:
        return PortfolioApiService(conn).add_to_watchlist(asset_id)


@router.get("/comparison", response_model=ComparisonResponse)
def comparison(
    left: str = Query(min_length=1, max_length=32),
    right: str | None = Query(default=None, min_length=1, max_length=32),
    benchmark_index_id: str | None = Query(default=None, min_length=1, max_length=64),
    conn=Depends(get_connection),
):
    return ComparisonApiService(conn).compare(left, right, benchmark_index_id)


@router.get("/comparison/workspace", response_model=ComparisonWorkspaceResponse)
def comparison_workspace(
    symbols: str = Query(min_length=1, max_length=240),
    benchmark: str | None = Query(default=None, min_length=1, max_length=64),
    period: str = Query(default="1Y", pattern="^(1D|1W|1M|3M|6M|YTD|1Y|3Y|5Y|10Y|MAX|Max)$"),
    mode: str = Query(default="total-return", pattern="^(price-return|total-return|relative|drawdown|rolling-return|rolling-volatility)$"),
    currency: str = Query(default="native", pattern="^(native|USD|CAD)$"),
    conn=Depends(get_connection),
):
    return ComparisonApiService(conn).workspace(
        symbols=symbols,
        benchmark_index_id=benchmark,
        period=period.upper(),
        mode=mode,
        currency=currency.upper() if currency != "native" else currency,
    )


@router.get("/benchmarks", response_model=list[BenchmarkIndexSummary])
def list_benchmarks(
    q: str | None = Query(default=None, min_length=1, max_length=100),
    category: str | None = Query(default=None, max_length=32),
    region: str | None = Query(default=None, max_length=64),
    country_code: str | None = Query(default=None, min_length=2, max_length=3),
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    is_core: bool | None = None,
    is_active: bool | None = True,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    conn=Depends(get_connection),
):
    return BenchmarkApiService(conn).list_benchmarks(
        q=q,
        category=category,
        region=region,
        country_code=country_code,
        currency=currency,
        is_core=is_core,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )


@router.get("/benchmarks/defaults/asset/{asset_id}", response_model=BenchmarkDefaultResponse)
def asset_default_benchmark(asset_id: str, conn=Depends(get_connection)):
    return BenchmarkApiService(conn).default_for_asset(asset_id)


@router.get("/benchmarks/associations/asset/{asset_id}", response_model=AssetBenchmarkAssociationResponse)
def asset_benchmark_associations(asset_id: str, conn=Depends(get_connection)):
    return BenchmarkApiService(conn).associations_for_asset(asset_id)


@router.get("/benchmarks/defaults/portfolio/{portfolio_id}", response_model=BenchmarkDefaultResponse)
def portfolio_default_benchmark(portfolio_id: int, conn=Depends(get_connection)):
    return BenchmarkApiService(conn).default_for_portfolio(portfolio_id)


@router.get("/benchmarks/readiness", response_model=BenchmarkReadinessResponse)
def benchmark_readiness(
    category: str | None = Query(default=None, pattern="^(core_geo|sector|industry|theme|non_core|all)$"),
    conn=Depends(get_connection),
):
    return BenchmarkApiService(conn).readiness(category=category)


@router.post("/benchmarks/harden", response_model=ActionResult)
def benchmark_bulk_harden(
    payload: BenchmarkBulkHardenRequest,
    request: Request,
    conn=Depends(get_connection),
):
    with request.app.state.write_lock:
        result = BenchmarkApiService(conn).harden_benchmarks(
            category=payload.category,
            lookback_days=payload.lookback_days,
            include_composition=payload.include_composition,
            include_relative_metrics=payload.include_relative_metrics,
            comparison_index_id=payload.comparison_index_id,
        )
    return ActionResult(result=result)


@router.get("/benchmarks/{index_id}/readiness", response_model=BenchmarkReadinessResponse)
def benchmark_readiness_for_index(index_id: str, conn=Depends(get_connection)):
    return BenchmarkApiService(conn).readiness(index_id=index_id)


@router.get("/benchmarks/{index_id}", response_model=BenchmarkIndexDetail)
def benchmark_detail(index_id: str, conn=Depends(get_connection)):
    return BenchmarkApiService(conn).get_benchmark(index_id)


@router.get("/benchmarks/{index_id}/prices", response_model=list[BenchmarkPricePoint])
def benchmark_prices(
    index_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=365, ge=1, le=5000),
    conn=Depends(get_connection),
):
    return BenchmarkApiService(conn).prices(index_id, start_date, end_date, limit)


@router.get("/benchmarks/{index_id}/metrics", response_model=list[BenchmarkDailyMetric])
def benchmark_metrics(
    index_id: str,
    limit: int = Query(default=365, ge=1, le=5000),
    conn=Depends(get_connection),
):
    return BenchmarkApiService(conn).metrics(index_id, limit)


@router.get("/benchmarks/{index_id}/constituents", response_model=Page[BenchmarkConstituent])
def benchmark_constituents(
    index_id: str,
    snapshot_date: date | None = None,
    source: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="weight_desc", max_length=32),
    conn=Depends(get_connection),
):
    return BenchmarkApiService(conn).constituents(index_id, snapshot_date, source, limit, offset, sort)


@router.get("/benchmarks/{index_id}/exposures", response_model=list[BenchmarkExposure])
def benchmark_exposures(
    index_id: str,
    snapshot_date: date | None = None,
    dimension_type: str | None = Query(default=None, max_length=64),
    conn=Depends(get_connection),
):
    return BenchmarkApiService(conn).exposures(index_id, snapshot_date, dimension_type)


@router.post("/benchmarks/seed", response_model=ActionResult)
def benchmark_seed(payload: BenchmarkSeedRequest, request: Request, conn=Depends(get_connection)):
    with request.app.state.write_lock:
        result = BenchmarkApiService(conn).seed(payload.scope)
    return ActionResult(result=result)


@router.post("/benchmarks/{index_id}/refresh", response_model=ActionResult)
def benchmark_refresh(
    index_id: str,
    payload: BenchmarkRefreshRequest,
    request: Request,
    conn=Depends(get_connection),
):
    with request.app.state.write_lock:
        result = BenchmarkApiService(conn).refresh_benchmark(
            index_id=index_id,
            job_type=payload.job_type,
            lookback_days=payload.lookback_days,
            interval=payload.interval,
            comparison_index_id=payload.comparison_index_id,
        )
    return ActionResult(result=result)


@router.post("/benchmarks/{index_id}/harden", response_model=ActionResult)
def benchmark_harden(
    index_id: str,
    payload: BenchmarkHardenRequest,
    request: Request,
    conn=Depends(get_connection),
):
    with request.app.state.write_lock:
        result = BenchmarkApiService(conn).harden_benchmark(
            index_id=index_id,
            lookback_days=payload.lookback_days,
            include_composition=payload.include_composition,
            include_relative_metrics=payload.include_relative_metrics,
            comparison_index_id=payload.comparison_index_id,
        )
    return ActionResult(result=result)


@router.post("/benchmarks/refresh", response_model=ActionResult)
def benchmark_bulk_refresh(
    payload: BenchmarkBulkRefreshRequest,
    request: Request,
    conn=Depends(get_connection),
):
    with request.app.state.write_lock:
        result = BenchmarkApiService(conn).refresh_benchmarks(
            category=payload.category,
            job_type=payload.job_type,
            lookback_days=payload.lookback_days,
            interval=payload.interval,
        )
    return ActionResult(result=result)


@router.get("/portfolios/aggregate/overview", response_model=PortfolioSummary)
def aggregate_portfolio_overview(conn=Depends(get_connection)):
    return PortfolioApiService(conn).aggregate_portfolio()


@router.get("/portfolios/aggregate/positions", response_model=list[PositionSummary])
def aggregate_portfolio_positions(conn=Depends(get_connection)):
    return PortfolioApiService(conn).list_positions()


@router.get("/portfolios/aggregate/transactions", response_model=Page[TransactionSummary])
def aggregate_portfolio_transactions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    conn=Depends(get_connection),
):
    return PortfolioApiService(conn).list_transactions(None, limit, offset)


@router.post("/portfolios", response_model=PortfolioSummary, status_code=status.HTTP_201_CREATED)
def create_portfolio(payload: PortfolioCreate, request: Request, conn=Depends(get_connection)):
    lock: Lock = request.app.state.write_lock
    with lock:
        return PortfolioApiService(conn).create_portfolio(payload)


@router.get("/portfolios/{portfolio_id}/overview", response_model=PortfolioSummary)
def portfolio_overview(portfolio_id: int, conn=Depends(get_connection)):
    return PortfolioApiService(conn).get_portfolio(portfolio_id)


@router.get("/portfolios/{portfolio_id}", response_model=PortfolioSummary)
def portfolio_detail(portfolio_id: int, conn=Depends(get_connection)):
    return PortfolioApiService(conn).get_portfolio(portfolio_id)


@router.patch("/portfolios/{portfolio_id}", response_model=PortfolioSummary)
def update_portfolio(
    portfolio_id: int,
    payload: PortfolioUpdate,
    request: Request,
    conn=Depends(get_connection),
):
    with request.app.state.write_lock:
        return PortfolioApiService(conn).update_portfolio(portfolio_id, payload)


@router.get("/portfolios/{portfolio_id}/positions", response_model=list[PositionSummary])
def portfolio_positions(portfolio_id: int, conn=Depends(get_connection)):
    return PortfolioApiService(conn).list_positions(portfolio_id)


@router.get("/portfolios/{portfolio_id}/transactions", response_model=Page[TransactionSummary])
def portfolio_transactions(
    portfolio_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    conn=Depends(get_connection),
):
    return PortfolioApiService(conn).list_transactions(portfolio_id, limit, offset)


@router.get("/portfolios/{portfolio_id}/analytics")
def portfolio_analytics(
    portfolio_id: int,
    benchmark_index_id: str | None = None,
    conn=Depends(get_connection),
):
    return PortfolioApiService(conn).analytics(portfolio_id, benchmark_index_id)


@router.get("/portfolios/{portfolio_id}/performance", response_model=PortfolioPerformanceResponse)
def portfolio_performance(
    portfolio_id: int,
    benchmark: str | None = Query(default=None, min_length=1, max_length=64),
    range: str = Query(default="1Y", pattern="^(1D|1W|1M|YTD|1Y|5Y|Max|MAX)$"),
    conn=Depends(get_connection),
):
    return PortfolioApiService(conn).performance(portfolio_id, benchmark, range.upper())


@router.get("/portfolios/{portfolio_id}/risk", response_model=PortfolioRiskResponse)
def portfolio_risk(
    portfolio_id: int,
    benchmark: str | None = Query(default=None, min_length=1, max_length=64),
    risk_free_rate: float = Query(default=0.0, ge=-0.05, le=0.25),
    lookback: str = Query(default="1Y", pattern="^(1D|1W|1M|YTD|1Y|5Y|Max|MAX)$"),
    conn=Depends(get_connection),
):
    return PortfolioApiService(conn).risk(portfolio_id, benchmark, risk_free_rate, lookback.upper())


@router.get("/portfolios/{portfolio_id}/fundamentals", response_model=PortfolioFundamentalsResponse)
def portfolio_fundamentals(
    portfolio_id: int,
    horizon_years: int = Query(default=5, ge=3, le=10),
    conn=Depends(get_connection),
):
    return PortfolioApiService(conn).fundamentals(portfolio_id, horizon_years)


@router.post(
    "/portfolios/{portfolio_id}/optimization/preview",
    response_model=OptimizationPreviewResponse,
)
def portfolio_optimization_preview(
    portfolio_id: int,
    payload: OptimizationPreviewRequest,
    conn=Depends(get_connection),
):
    return PortfolioApiService(conn).optimization_preview(portfolio_id, payload)


@router.delete("/portfolios/{portfolio_id}", response_model=ActionResult)
def delete_portfolio(portfolio_id: int, request: Request, conn=Depends(get_connection)):
    with request.app.state.write_lock:
        result = PortfolioApiService(conn).delete_portfolio(portfolio_id)
    return ActionResult(result=result)


@router.delete("/portfolios/{portfolio_id}/positions/{asset_id}", response_model=ActionResult)
def delete_portfolio_position(
    portfolio_id: int,
    asset_id: str,
    request: Request,
    conn=Depends(get_connection),
):
    with request.app.state.write_lock:
        result = PortfolioApiService(conn).delete_position(portfolio_id, asset_id)
    return ActionResult(result=result)


@router.get("/assets/{asset_id}/holdings", response_model=list[AssetHoldingSummary])
def asset_holdings(asset_id: str, conn=Depends(get_connection)):
    return PortfolioApiService(conn).list_asset_holdings(asset_id)


@router.get("/assets/{asset_id}/activity", response_model=Page[AssetActivitySummary])
def asset_activity(
    asset_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    conn=Depends(get_connection),
):
    return PortfolioApiService(conn).list_asset_activity(asset_id, limit, offset)


@router.get("/assets", response_model=list[AssetSearchResult])
def search_assets(
    q: str | None = Query(default=None, min_length=1, max_length=100),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    conn=Depends(get_connection),
):
    return AssetApiService(conn).search_assets(q=q, limit=limit, offset=offset)


@router.get("/assets/{asset_id}", response_model=AssetDetail)
def asset_detail(asset_id: str, conn=Depends(get_connection)):
    return AssetApiService(conn).get_asset(asset_id)


@router.get("/assets/{asset_id}/prices", response_model=list[PricePointResponse])
def asset_prices(
    asset_id: str,
    limit: int = Query(default=365, ge=1, le=5000),
    range: str = Query(default="1Y", pattern="^(1D|1W|1M|YTD|1Y|5Y|Max|MAX)$"),
    conn=Depends(get_connection),
):
    return AssetApiService(conn).price_history(asset_id, limit, range.upper())


@router.get("/assets/{asset_id}/analytics")
def asset_analytics(
    asset_id: str,
    benchmark_index_id: str | None = None,
    conn=Depends(get_connection),
):
    return AssetApiService(conn).analytics(asset_id, benchmark_index_id)


@router.get("/brokers/connections", response_model=list[BrokerConnectionResponse])
def broker_connections(conn=Depends(get_connection)):
    return CommandApiService(conn).broker_connections()


@router.get("/brokers/accounts", response_model=list[BrokerAccountResponse])
def broker_accounts(conn=Depends(get_connection)):
    return CommandApiService(conn).broker_account_responses()


@router.get("/brokers/status", response_model=BrokerStatusResponse)
def broker_status(conn=Depends(get_connection)):
    return CommandApiService(conn).broker_status()


@router.get("/brokers/import-preview", response_model=BrokerImportPreviewResponse)
def broker_import_preview(conn=Depends(get_connection)):
    return CommandApiService(conn).broker_import_preview()


@router.get("/brokers/reconciliation", response_model=BrokerReconciliationResponse)
def broker_reconciliation(conn=Depends(get_connection)):
    return CommandApiService(conn).broker_reconciliation()


@router.get("/brokers/sync-history", response_model=list[BrokerSyncHistoryItem])
def broker_sync_history(limit: int = Query(default=25, ge=1, le=200), conn=Depends(get_connection)):
    return CommandApiService(conn).broker_sync_history(limit=limit)


@router.post("/brokers/snaptrade/users", response_model=BrokerUserResponse)
def register_broker_user(payload: BrokerUserCreate, request: Request, conn=Depends(get_connection)):
    with request.app.state.write_lock:
        return CommandApiService(conn).register_broker_user(payload.user_key)


@router.post("/brokers/snaptrade/existing-user", response_model=BrokerUserResponse)
def save_existing_broker_user(
    payload: BrokerExistingUserCreate,
    request: Request,
    conn=Depends(get_connection),
):
    with request.app.state.write_lock:
        return CommandApiService(conn).save_existing_broker_user(
            payload.user_key,
            payload.provider_user_id,
            payload.user_secret,
        )


@router.post("/brokers/snaptrade/portal", response_model=BrokerPortalResponse)
def broker_portal(payload: BrokerPortalRequest, conn=Depends(get_connection)):
    service = CommandApiService(conn)
    url = service.broker_snaptrade_portal(
        service.broker_user_key_or_default(payload.user_key),
        broker=payload.broker,
        reconnect=payload.reconnect,
        register_if_missing=True,
    )
    return BrokerPortalResponse(url=url)


@router.post("/brokers/snaptrade/sync", response_model=ActionResult)
def broker_sync(payload: BrokerSyncRequest, request: Request, conn=Depends(get_connection)):
    with request.app.state.write_lock:
        service = CommandApiService(conn)
        result = service.broker_snaptrade_sync(service.broker_user_key_or_default(payload.user_key))
    return ActionResult(result=CommandApiService.action_result(result))


@router.post("/brokers/snaptrade/sync-due", response_model=ActionResult)
def broker_sync_due(payload: BrokerDueRefreshRequest, request: Request, conn=Depends(get_connection)):
    with request.app.state.write_lock:
        result = CommandApiService(conn).broker_snaptrade_sync_due(
            max_users=payload.max_users,
            min_age_hours=payload.min_age_hours,
            force=payload.force,
        )
    return ActionResult(result=CommandApiService.action_result(result))


@router.post("/brokers/snaptrade/smoke-test", response_model=ActionResult)
def broker_smoke_test(request: Request, conn=Depends(get_connection)):
    with request.app.state.write_lock:
        service = CommandApiService(conn)
        result = service.broker_snaptrade_smoke_test(service.broker_user_key_or_default(None))
    return ActionResult(result=CommandApiService.action_result(result))


@router.post("/brokers/accounts/{account_id}/mapping", response_model=ActionResult)
def broker_account_mapping(
    account_id: str,
    payload: BrokerAccountMappingRequest,
    request: Request,
    conn=Depends(get_connection),
):
    with request.app.state.write_lock:
        result = CommandApiService(conn).broker_map_account(account_id, payload.portfolio_id)
    return ActionResult(result=CommandApiService.action_result(result))


@router.post("/brokers/import-transactions", response_model=ActionResult)
def broker_import(
    payload: BrokerImportRequest,
    request: Request,
    conn=Depends(get_connection),
):
    with request.app.state.write_lock:
        result = CommandApiService(conn).broker_import_transactions(portfolio_id=payload.portfolio_id)
    return ActionResult(result=CommandApiService.action_result(result))


@router.put("/brokers/settings/raw-payload-storage", response_model=BrokerStorageSettingResponse)
def broker_raw_payload_storage(
    payload: BrokerStorageSettingRequest,
    request: Request,
    conn=Depends(get_connection),
):
    with request.app.state.write_lock:
        service = CommandApiService(conn)
        service.set_broker_raw_payload_storage_enabled(payload.enabled)
        return BrokerStorageSettingResponse(
            raw_payload_storage_enabled=service.broker_raw_payload_storage_enabled(),
        )


@router.get("/ingestion/jobs", response_model=list[IngestionJobResponse])
def ingestion_jobs(
    job_status: str | None = Query(default=None, alias="status"),
    domain: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    conn=Depends(get_connection),
):
    return CommandApiService(conn).ingestion_jobs(job_status, domain, limit)


@router.delete("/ingestion/jobs", response_model=ActionResult)
def ingestion_clear_history(request: Request, conn=Depends(get_connection)):
    with request.app.state.write_lock:
        result = CommandApiService(conn).clear_ingestion_history()
    return ActionResult(result=result)


@router.get("/ingestion/background/status", response_model=IngestionBackgroundStatusResponse)
def ingestion_background_status(request: Request):
    return request.app.state.ingestion_background_worker.status()


@router.post("/ingestion/background/start", response_model=ActionResult)
async def ingestion_background_start(request: Request):
    request.app.state.ingestion_background_worker.enable()
    return ActionResult(result=request.app.state.ingestion_background_worker.status())


@router.post("/ingestion/background/stop", response_model=ActionResult)
async def ingestion_background_stop(request: Request):
    await request.app.state.ingestion_background_worker.disable()
    return ActionResult(result=request.app.state.ingestion_background_worker.status())


@router.post("/ingestion/background/tick", response_model=ActionResult)
async def ingestion_background_tick(request: Request):
    result = await request.app.state.ingestion_background_worker.tick()
    return ActionResult(result=result)


@router.get("/market/freshness/status", response_model=MarketFreshnessStatusResponse)
def market_freshness_status(request: Request):
    return request.app.state.market_freshness_worker.status()


@router.post("/market/freshness/start", response_model=ActionResult)
async def market_freshness_start(request: Request):
    request.app.state.market_freshness_worker.enable()
    return ActionResult(result=request.app.state.market_freshness_worker.status())


@router.post("/market/freshness/stop", response_model=ActionResult)
async def market_freshness_stop(request: Request):
    await request.app.state.market_freshness_worker.disable()
    return ActionResult(result=request.app.state.market_freshness_worker.status())


@router.post("/market/freshness/tick", response_model=ActionResult)
async def market_freshness_tick(request: Request):
    result = await request.app.state.market_freshness_worker.tick()
    return ActionResult(result=result)


@router.get("/data/readiness/status", response_model=DataReadinessWorkerStatusResponse)
def data_readiness_status(request: Request):
    return request.app.state.data_readiness_worker.status()


@router.post("/data/readiness/start", response_model=ActionResult)
async def data_readiness_start(request: Request):
    request.app.state.data_readiness_worker.enable()
    return ActionResult(result=request.app.state.data_readiness_worker.status())


@router.post("/data/readiness/stop", response_model=ActionResult)
async def data_readiness_stop(request: Request):
    await request.app.state.data_readiness_worker.disable()
    return ActionResult(result=request.app.state.data_readiness_worker.status())


@router.post("/data/readiness/tick", response_model=ActionResult)
async def data_readiness_tick(request: Request):
    result = await request.app.state.data_readiness_worker.tick()
    return ActionResult(result=result)


@router.get("/ingestion/readiness", response_model=IngestionReadinessResponse)
def ingestion_readiness(conn=Depends(get_connection)):
    items = CommandApiService(conn).ingestion_readiness()
    return IngestionReadinessResponse(
        items=items,
        total=len(items),
        ready_count=sum(1 for item in items if item.ready),
    )


@router.get("/ingestion/ranking-readiness", response_model=StockRankingReadinessResponse)
def ingestion_ranking_readiness(
    universe: str = Query(default="tracked", pattern="^(tracked|all)$"),
    limit: int = Query(default=50, ge=1, le=200),
    conn=Depends(get_connection),
):
    return CommandApiService(conn).stock_ranking_readiness(universe=universe, limit=limit)


@router.post("/ingestion/schedule", response_model=ActionResult)
def ingestion_schedule(
    payload: IngestionScheduleRequest,
    request: Request,
    conn=Depends(get_connection),
):
    with request.app.state.write_lock:
        count = CommandApiService(conn).schedule_ingestion_jobs(
            pipeline=payload.pipeline,
            asset_id=payload.asset_id,
            max_assets=payload.max_assets,
            years=payload.years,
            prices_only=payload.prices_only,
            ranking_factor=payload.ranking_factor,
            ranking_universe=payload.ranking_universe,
            ranking_timeframe=payload.ranking_timeframe,
            missing_only=payload.missing_only,
            stale_only=payload.stale_only,
        )
    return ActionResult(result={"scheduled_jobs": count})


@router.post("/ingestion/run", response_model=ActionResult)
def ingestion_run(payload: IngestionRunRequest, request: Request, conn=Depends(get_connection)):
    with request.app.state.write_lock:
        count = CommandApiService(conn).run_ingestion_jobs(
            domain=payload.domain,
            max_jobs=payload.max_jobs,
        )
    return ActionResult(result={"completed_jobs": count})


@router.post("/ingestion/retry-failed", response_model=ActionResult)
def ingestion_retry_failed(
    payload: IngestionRetryFailedRequest,
    request: Request,
    conn=Depends(get_connection),
):
    with request.app.state.write_lock:
        count = CommandApiService(conn).retry_failed_ingestion_jobs(
            domain=payload.domain,
            max_jobs=payload.max_jobs,
        )
    return ActionResult(result={"retried_jobs": count})
