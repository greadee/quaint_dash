# tests/conftest.py

from __future__ import annotations

from pathlib import Path
import sys

import duckdb
import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from tests.fixture_index import ( 
    EmptyProvider,
    FakeConstituentProvider,
    FakeDailyPriceProvider,
    FakeIntradayProvider,
    FailingIntradayProvider,
    create_benchmark_index_tables,
    index_conn,
    insert_daily_price_rows,
    insert_daily_price_rows_fn,
    insert_test_index,
    insert_test_index_fn,
    insert_test_symbol,
    insert_test_symbol_fn,
)

from tests.fixture_websocket import (  
    create_live_price_tables,
    seeded_assets,
    websocket_conn,
)


@pytest.fixture()
def conn():
    """
    Shared test DuckDB connection.

    This combines benchmark-index tables and live-price/websocket tables so
    root-level tests can all request the same fixture name: `conn`.

    This avoids having two competing `conn` fixtures.
    """
    connection = duckdb.connect(":memory:")

    create_benchmark_index_tables(connection)
    create_live_price_tables(connection)

    yield connection

    connection.close()