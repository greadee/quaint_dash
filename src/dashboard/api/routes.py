"""Versioned HTTP API routes."""

from threading import Lock

from fastapi import APIRouter, Depends, Query, Request, status

from dashboard.api.dependencies import get_connection
from dashboard.api.models import (
    ActionResult,
    AssetDetail,
    AssetHoldingSummary,
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
    TransactionSummary,
)
from dashboard.api.services import AssetApiService, CommandApiService, ComparisonApiService, PortfolioApiService

router = APIRouter(prefix="/api/v1")


@router.get("/portfolios", response_model=list[PortfolioSummary])
def list_portfolios(conn=Depends(get_connection)):
    return PortfolioApiService(conn).list_portfolios()


@router.get("/overview/updates", response_model=OverviewUpdatesResponse)
def overview_updates(conn=Depends(get_connection)):
    return PortfolioApiService(conn).overview_updates()


@router.get("/comparison", response_model=ComparisonResponse)
def comparison(
    left: str = Query(min_length=1, max_length=32),
    right: str | None = Query(default=None, min_length=1, max_length=32),
    benchmark_index_id: str | None = Query(default=None, min_length=1, max_length=64),
    conn=Depends(get_connection),
):
    return ComparisonApiService(conn).compare(left, right, benchmark_index_id)


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
