"""FastAPI dependencies shared across API routes."""

from collections.abc import Iterator

import duckdb
from fastapi import Request


def get_connection(request: Request) -> Iterator[duckdb.DuckDBPyConnection]:
    """Borrow an independent request connection without taking the writer lock.

    Mutation routes and background workers serialize their short write sections
    with ``app.state.write_lock``. Reads rely on DuckDB's in-process MVCC so a
    provider-bound writer cannot starve health and interactive GET requests.
    Reusable pooled connections avoid both Windows file-handle churn and unsafe
    concurrent cursor use on a single DuckDB connection.
    """
    pool = request.app.state.db_connection_pool
    conn = pool.acquire()
    try:
        yield conn
    finally:
        pool.release(conn)
