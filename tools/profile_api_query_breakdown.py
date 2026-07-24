"""Profile frontend GET endpoints with a reused read-only DuckDB cursor.

This diagnostic separates the one-time DuckDB file-open cost from endpoint SQL,
Python transformation, validation, and JSON serialization work. It intentionally
does not start the API lifespan, schedulers, or provider refresh jobs.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

import duckdb
import requests
import urllib.request
import yfinance
from fastapi import Request
from fastapi.testclient import TestClient

from dashboard.api.app import app
from dashboard.api.dependencies import get_connection

DB_PATH = Path("data/persistent_db.db")

ENDPOINTS = [
    ("health", "/api/v1/health"),
    ("overview", "/api/v1/overview/updates"),
    ("portfolios", "/api/v1/portfolios"),
    ("portfolio aggregate", "/api/v1/portfolios/aggregate/overview"),
    ("aggregate positions", "/api/v1/portfolios/aggregate/positions"),
    ("portfolio detail", "/api/v1/portfolios/3"),
    ("portfolio positions", "/api/v1/portfolios/3/positions"),
    ("portfolio performance", "/api/v1/portfolios/3/performance?range=1Y"),
    ("portfolio risk", "/api/v1/portfolios/3/risk?lookback=1Y&risk_free_rate=0"),
    ("portfolio fundamentals", "/api/v1/portfolios/3/fundamentals?horizon_years=5"),
    ("portfolio transactions", "/api/v1/portfolios/3/transactions?limit=25&offset=0"),
    ("portfolio news", "/api/v1/portfolios/3/news?limit=5&offset=0&sort=relevance"),
    ("holding signals", "/api/v1/holdings/signals?timeframe=1m&portfolio_id=3"),
    ("assets", "/api/v1/assets?limit=25"),
    ("asset detail", "/api/v1/assets/AAPL"),
    ("asset prices", "/api/v1/assets/AAPL/prices?limit=5000&range=1Y"),
    ("asset analytics", "/api/v1/assets/AAPL/analytics"),
    ("asset business strength", "/api/v1/assets/AAPL/business-strength"),
    ("asset news", "/api/v1/assets/AAPL/news?limit=10&offset=0&sort=recency"),
    ("asset holdings", "/api/v1/assets/AAPL/holdings"),
    ("asset activity", "/api/v1/assets/AAPL/activity?limit=20&offset=0"),
    ("news feed", "/api/v1/news"),
    ("news providers", "/api/v1/news/providers"),
    ("news categories", "/api/v1/news/categories"),
    ("retail sentiment", "/api/v1/retail-sentiment?limit=30"),
    (
        "stock rankings",
        "/api/v1/rankings/stocks?factor=aggregate&universe=tracked&direction=buy"
        "&timeframe=monthly&include_retail_sentiment=false&limit=25&offset=0",
    ),
    ("signals", "/api/v1/signals"),
    (
        "signal detail",
        "/api/v1/signals/ranking.institutional_buying.monthly.META.TO",
    ),
    ("comparison", "/api/v1/comparison/workspace?symbols=AAPL%2CMSFT&period=1Y"),
    ("asset benchmark associations", "/api/v1/benchmarks/associations/asset/AAPL"),
    ("benchmarks", "/api/v1/benchmarks?is_active=true&limit=500"),
    ("benchmark detail", "/api/v1/benchmarks/SP500"),
    ("benchmark prices", "/api/v1/benchmarks/SP500/prices?limit=1400"),
    ("benchmark metrics", "/api/v1/benchmarks/SP500/metrics?limit=365"),
    ("benchmark constituents", "/api/v1/benchmarks/SP500/constituents?limit=100&offset=0"),
    ("benchmark exposures", "/api/v1/benchmarks/SP500/exposures"),
    ("broker status", "/api/v1/brokers/status"),
    ("broker connections", "/api/v1/brokers/connections"),
    ("broker accounts", "/api/v1/brokers/accounts"),
    ("broker import preview", "/api/v1/brokers/import-preview?item_limit=25"),
    ("broker reconciliation", "/api/v1/brokers/reconciliation"),
    ("broker sync history", "/api/v1/brokers/sync-history"),
    ("ingestion jobs", "/api/v1/ingestion/jobs?limit=100"),
    ("retail sentiment status", "/api/v1/ingestion/retail-sentiment/status?limit=10"),
    ("ingestion readiness", "/api/v1/ingestion/readiness"),
    ("ranking readiness", "/api/v1/ingestion/ranking-readiness?universe=tracked&limit=50"),
    ("streaming status", "/api/v1/market/streaming/status"),
]


@dataclass
class QueryTrace:
    sql: str
    duration_ms: float
    rows_loaded: int | None = None


@dataclass
class RequestTrace:
    path: str
    cursor_acquire_ms: float
    queries: list[QueryTrace] = field(default_factory=list)


class TracedConnection:
    def __init__(self, conn: duckdb.DuckDBPyConnection, trace: RequestTrace):
        self._conn = conn
        self._trace = trace
        self._active_query: QueryTrace | None = None

    def execute(self, query: str, parameters: Any = None):
        started = time.perf_counter()
        if parameters is None:
            self._conn.execute(query)
        else:
            self._conn.execute(query, parameters)
        item = QueryTrace(
            sql=_normalize_sql(query),
            duration_ms=_milliseconds_since(started),
        )
        self._trace.queries.append(item)
        self._active_query = item
        return self

    def executemany(self, query: str, parameters: Any):
        started = time.perf_counter()
        self._conn.executemany(query, parameters)
        item = QueryTrace(
            sql=_normalize_sql(query),
            duration_ms=_milliseconds_since(started),
        )
        self._trace.queries.append(item)
        self._active_query = item
        return self

    def fetchall(self):
        rows = self._conn.fetchall()
        if self._active_query is not None:
            self._active_query.rows_loaded = len(rows)
        return rows

    def fetchone(self):
        row = self._conn.fetchone()
        if self._active_query is not None:
            self._active_query.rows_loaded = 0 if row is None else 1
        return row

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


def _normalize_sql(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip()


def _milliseconds_since(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def main() -> None:
    base_started = time.perf_counter()
    base_connection = duckdb.connect(str(DB_PATH), read_only=True)
    base_open_ms = _milliseconds_since(base_started)
    completed_traces: list[RequestTrace] = []
    provider_attempts: list[dict[str, str]] = []

    def traced_connection(request: Request):
        cursor_started = time.perf_counter()
        cursor = base_connection.cursor()
        trace = RequestTrace(
            path=request.url.path,
            cursor_acquire_ms=_milliseconds_since(cursor_started),
        )
        try:
            yield TracedConnection(cursor, trace)
        finally:
            cursor.close()
            completed_traces.append(trace)

    def block_requests(session, method, url, *args, **kwargs):
        provider_attempts.append({"library": "requests", "method": method, "url": str(url)})
        raise RuntimeError(f"External provider call blocked during GET audit: {method} {url}")

    def block_urlopen(url, *args, **kwargs):
        provider_attempts.append({"library": "urllib", "method": "GET", "url": str(url)})
        raise RuntimeError(f"External provider call blocked during GET audit: {url}")

    def block_yfinance(*args, **kwargs):
        provider_attempts.append({"library": "yfinance", "method": "CALL", "url": "provider"})
        raise RuntimeError("External yfinance call blocked during GET audit")

    app.dependency_overrides[get_connection] = traced_connection
    client = TestClient(app)
    results = []
    try:
        with (
            patch.object(requests.sessions.Session, "request", block_requests),
            patch.object(urllib.request, "urlopen", block_urlopen),
            patch.object(yfinance, "download", block_yfinance),
            patch.object(yfinance, "Ticker", block_yfinance),
        ):
            for name, path in ENDPOINTS:
                before = len(completed_traces)
                started = time.perf_counter()
                response = client.get(path)
                total_ms = _milliseconds_since(started)
                trace = completed_traces[-1] if len(completed_traces) > before else None
                query_ms = round(sum(item.duration_ms for item in trace.queries), 3) if trace else 0
                results.append(
                    {
                        "name": name,
                        "path": path,
                        "status": response.status_code,
                        "total_ms_with_reused_cursor": total_ms,
                        "cursor_acquire_ms": trace.cursor_acquire_ms if trace else 0,
                        "query_count": len(trace.queries) if trace else 0,
                        "database_execute_ms": query_ms,
                        "transform_validation_serialization_ms": round(max(0, total_ms - query_ms), 3),
                        "payload_bytes": len(response.content),
                        "rows_loaded_observed": sum(
                            item.rows_loaded or 0 for item in (trace.queries if trace else [])
                        ),
                        "queries": [item.__dict__ for item in (trace.queries if trace else [])],
                    }
                )
    finally:
        app.dependency_overrides.clear()
        base_connection.close()

    print(
        json.dumps(
            {
                "generated_at_epoch": time.time(),
                "database": str(DB_PATH),
                "database_bytes": DB_PATH.stat().st_size,
                "one_time_base_connection_open_ms": base_open_ms,
                "provider_attempts": provider_attempts,
                "results": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
