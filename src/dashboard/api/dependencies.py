"""FastAPI dependencies shared across API routes."""

from collections.abc import Iterator
from pathlib import Path

import duckdb
from fastapi import Request


def get_connection(request: Request) -> Iterator[duckdb.DuckDBPyConnection]:
    """Open and close one DuckDB connection per request."""
    db_path = Path(request.app.state.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    try:
        yield conn
    finally:
        conn.close()
