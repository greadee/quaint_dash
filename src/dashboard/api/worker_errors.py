"""Map adapter exceptions to application diagnostic codes without exposing their contents."""

import duckdb

from dashboard.db.db_conn import DatabaseInUseError
from dashboard.ingestion.rate_limits import RateLimitExceeded


def classify_worker_error(exc: Exception, phase: str) -> str:
    message = str(exc).lower()
    if isinstance(exc, DatabaseInUseError) or (
        isinstance(exc, duckdb.IOException)
        and any(marker in message for marker in (
            "could not set lock", "conflicting lock", "used by another process",
            "database is locked", "already open in",
        ))
    ):
        return "database_lock"
    if phase == "schedule" and isinstance(
        exc, (duckdb.BinderException, duckdb.ParserException, duckdb.CatalogException)
    ):
        return "scheduler_query"
    if isinstance(exc, RateLimitExceeded) or any(marker in message for marker in (
        "rate limit exceeded", "http error 429", "status code 429", "too many requests",
    )):
        return "provider_rate_limit"
    if any(marker in message for marker in (
        "provider missing", "missing credentials", "api_key is required", "api_key not found",
        "http error 401", "http error 402", "http error 403", "subscription does not",
    )):
        return "provider_configuration"
    return "unexpected"
