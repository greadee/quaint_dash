"""FastAPI application factory and web entry point."""

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from dashboard.api.dependencies import get_connection
from dashboard.api.models import ErrorResponse, HealthResponse
from dashboard.db.db_conn import DB, init_db

API_VERSION = "phase5.api.v1"
DEFAULT_DB_PATH = Path("data/persistent_db.db")


def create_app(db_path: str | Path = DEFAULT_DB_PATH) -> FastAPI:
    """Create an API application backed by the requested DuckDB file."""
    resolved_db_path = Path(db_path)
    db = DB(resolved_db_path)
    init_db(db)
    db.conn.close()

    app = FastAPI(
        title="Quaint Dash API",
        version=API_VERSION,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.db_path = resolved_db_path

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
        return _error_response(400, "invalid_request", str(exc))

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


app = create_app()


def main() -> None:
    """Run the local-first API server."""
    import uvicorn

    uvicorn.run("dashboard.api.app:app", host="127.0.0.1", port=8000, reload=False)
