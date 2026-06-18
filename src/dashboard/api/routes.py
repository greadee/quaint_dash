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
    BenchmarkSeedRequest,
    BrokerAccountMappingRequest,
    BrokerAccountResponse,
    BrokerConnectionResponse,
    BrokerExistingUserCreate,
    BrokerImportRequest,
    BrokerPortalRequest,
    BrokerPortalResponse,
    BrokerSyncRequest,
    BrokerUserCreate,
    BrokerUserResponse,
    ComparisonResponse,
    IngestionJobResponse,
    IngestionBackgroundStatusResponse,
    IngestionReadinessResponse,
    IngestionRetryFailedRequest,
    IngestionRunRequest,
    IngestionScheduleRequest,
    OverviewUpdatesResponse,
    Page,
    PortfolioCreate,
    PortfolioSummary,
    PortfolioUpdate,
    PositionSummary,
    PricePointResponse,
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


@router.get("/rankings/stocks", response_model=StockRankingsResponse)
def stock_rankings(
    factor: str = Query(
        default="aggregate",
        pattern="^(aggregate|share_price_momentum|news_sentiment|retail_sentiment|earnings_momentum|institutional_buying)$",
    ),
    universe: str = Query(default="tracked", pattern="^(tracked|all)$"),
    direction: str = Query(default="buy", pattern="^(buy|sell)$"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    conn=Depends(get_connection),
):
    return PortfolioApiService(conn).stock_rankings(
        factor=factor,
        universe=universe,
        direction=direction,
        limit=limit,
        offset=offset,
    )


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
    conn=Depends(get_connection),
):
    return AssetApiService(conn).price_history(asset_id, limit)


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
    url = CommandApiService(conn).broker_snaptrade_portal(
        payload.user_key,
        broker=payload.broker,
        reconnect=payload.reconnect,
    )
    return BrokerPortalResponse(url=url)


@router.post("/brokers/snaptrade/sync", response_model=ActionResult)
def broker_sync(payload: BrokerSyncRequest, request: Request, conn=Depends(get_connection)):
    with request.app.state.write_lock:
        result = CommandApiService(conn).broker_snaptrade_sync(payload.user_key)
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
