"""Versioned HTTP API routes."""

from threading import Lock

from fastapi import APIRouter, Depends, Query, Request, status

from dashboard.api.dependencies import get_connection
from dashboard.api.models import (
    AssetDetail,
    Page,
    PortfolioCreate,
    PortfolioSummary,
    PositionSummary,
    PricePointResponse,
    TransactionSummary,
)
from dashboard.api.services import AssetApiService, PortfolioApiService

router = APIRouter(prefix="/api/v1")


@router.get("/portfolios", response_model=list[PortfolioSummary])
def list_portfolios(conn=Depends(get_connection)):
    return PortfolioApiService(conn).list_portfolios()


@router.post("/portfolios", response_model=PortfolioSummary, status_code=status.HTTP_201_CREATED)
def create_portfolio(payload: PortfolioCreate, request: Request, conn=Depends(get_connection)):
    lock: Lock = request.app.state.write_lock
    with lock:
        return PortfolioApiService(conn).create_portfolio(payload)


@router.get("/portfolios/{portfolio_id}/overview", response_model=PortfolioSummary)
def portfolio_overview(portfolio_id: int, conn=Depends(get_connection)):
    return PortfolioApiService(conn).get_portfolio(portfolio_id)


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
