"""FastAPI application factory and web entry point."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from threading import RLock

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from dashboard.api.broker_background import BrokerBackgroundConfig, BrokerBackgroundWorker
from dashboard.api.data_readiness_background import DataReadinessConfig, DataReadinessWorker
from dashboard.api.dependencies import get_connection
from dashboard.api.ingestion_background import IngestionBackgroundConfig, IngestionBackgroundWorker
from dashboard.api.market_freshness_background import MarketFreshnessConfig, MarketFreshnessWorker
from dashboard.api.models import ErrorResponse, HealthResponse
from dashboard.api.routes import router
from dashboard.brokers.snaptrade import SnapTradeError
from dashboard.db.db_conn import DB, init_db
from dashboard.models.storage import DashboardManager

API_VERSION = "phase5.api.v1"
DEFAULT_DB_PATH = Path(os.getenv("DASHBOARD_DB_PATH", "data/persistent_db.db"))
DEFAULT_WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"
LOGGER = logging.getLogger(__name__)


def create_app(
    db_path: str | Path = DEFAULT_DB_PATH,
    web_dist: str | Path = DEFAULT_WEB_DIST,
) -> FastAPI:
    """Create an API application backed by the requested DuckDB file."""
    resolved_db_path = Path(db_path)
    db = DB(resolved_db_path)
    init_db(db)
    db.conn.close()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            _run_startup_broker_sync_if_enabled(app.state.db_path)
        except Exception as exc:
            LOGGER.warning("Broker sync scheduler skipped during API startup: %s", exc)
        worker = app.state.ingestion_background_worker
        market_worker = app.state.market_freshness_worker
        data_worker = app.state.data_readiness_worker
        broker_worker = app.state.broker_background_worker
        worker.start()
        market_worker.start()
        data_worker.start()
        broker_worker.start()
        try:
            yield
        finally:
            await broker_worker.stop()
            await data_worker.stop()
            await market_worker.stop()
            await worker.stop()

    app = FastAPI(
        title="Quaint Dash API",
        version=API_VERSION,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.db_path = resolved_db_path
    app.state.write_lock = RLock()
    app.state.web_dist = Path(web_dist)
    app.state.ingestion_background_worker = IngestionBackgroundWorker(
        resolved_db_path,
        app.state.write_lock,
        IngestionBackgroundConfig.from_env(),
    )
    app.state.market_freshness_worker = MarketFreshnessWorker(
        resolved_db_path,
        app.state.write_lock,
        MarketFreshnessConfig.from_env(),
    )
    app.state.data_readiness_worker = DataReadinessWorker(
        resolved_db_path,
        app.state.write_lock,
        DataReadinessConfig.from_env(),
    )
    app.state.broker_background_worker = BrokerBackgroundWorker(
        resolved_db_path,
        app.state.write_lock,
        BrokerBackgroundConfig.from_env(),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[os.getenv("DASHBOARD_WEB_DEV_ORIGIN", "http://127.0.0.1:5173")],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
        return _error_response(400, "invalid_request", str(exc))

    @app.exception_handler(LookupError)
    async def lookup_error_handler(_request: Request, exc: LookupError) -> JSONResponse:
        return _error_response(404, "not_found", str(exc))

    @app.exception_handler(FileExistsError)
    async def file_exists_error_handler(_request: Request, exc: FileExistsError) -> JSONResponse:
        return _error_response(409, "conflict", str(exc))

    @app.exception_handler(SnapTradeError)
    async def snaptrade_error_handler(_request: Request, exc: SnapTradeError) -> JSONResponse:
        return _error_response(400, "snaptrade_error", str(exc))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(422, "validation_error", "Request validation failed.", exc.errors())

    @app.get(
        "/api/v1/health",
        response_model=HealthResponse,
        responses={500: {"model": ErrorResponse}},
    )
    def health(conn=Depends(get_connection)) -> HealthResponse:
        conn.execute("SELECT 1").fetchone()
        return HealthResponse(status="ok", api_version=API_VERSION, database="connected")

    app.include_router(router)
    _mount_web_application(app)
    return app


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details=None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


def _mount_web_application(app: FastAPI) -> None:
    web_dist: Path = app.state.web_dist
    assets = web_dist / "assets"

    @app.get("/assets/{asset_path:path}", include_in_schema=False)
    def web_asset_or_asset_route(asset_path: str):
        index = web_dist / "index.html"
        requested = assets / asset_path
        if requested.is_file() and assets in requested.resolve().parents:
            return FileResponse(requested)
        if index.is_file():
            return FileResponse(index)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "web_not_built",
                    "message": "Build the React application in web/ before using the browser interface.",
                    "details": {},
                }
            },
        )

    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="web-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def web_application(full_path: str):
        if full_path.startswith("api/"):
            return _error_response(404, "not_found", "API route not found.")
        index = web_dist / "index.html"
        if index.is_file():
            requested = web_dist / full_path
            if full_path and requested.is_file() and web_dist in requested.resolve().parents:
                return FileResponse(requested)
            return FileResponse(index)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "web_not_built",
                    "message": "Build the React application in web/ before using the browser interface.",
                    "details": {},
                }
            },
        )


app = create_app()


def main() -> None:
    """Run the local-first API server."""
    import uvicorn

    host = os.getenv("DASHBOARD_API_HOST", "127.0.0.1")
    port = _int_env("DASHBOARD_API_PORT", 8000) or 8000
    uvicorn.run(app, host=host, port=port, reload=False)


def _run_startup_broker_sync_if_enabled(db_path: Path) -> None:
    """Optionally refresh stale broker data when the API server starts."""
    load_dotenv()
    if not (
        _truthy_env("BROKER_SYNC_ON_SERVER_STARTUP")
        or _truthy_env("BROKER_SYNC_ON_STARTUP")
    ):
        return

    max_users = _int_env("BROKER_SYNC_MAX_USERS")
    min_age_hours = _int_env("BROKER_SYNC_MIN_AGE_HOURS", 1) or 1
    result = _run_startup_broker_sync(
        db_path,
        max_users=max_users,
        min_age_hours=min_age_hours,
    )

    if result.users_synced:
        LOGGER.info(
            "Broker sync scheduler synced %s user(s), saw %s account(s), %s position(s), and %s transaction(s).",
            result.users_synced,
            result.accounts_seen,
            result.positions_seen,
            result.transactions_seen,
        )


def _run_startup_broker_sync(
    db_path: Path,
    max_users: int | None,
    min_age_hours: int,
):
    db = DB(db_path)
    try:
        init_db(db)
        manager = DashboardManager(db)
        return manager.broker_snaptrade_sync_due(
            max_users=max_users,
            min_age_hours=min_age_hours,
        )
    finally:
        db.conn.close()


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


if __name__ == "__main__":
    main()
