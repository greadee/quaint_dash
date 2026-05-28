from __future__ import annotations

from pathlib import Path
import sys

import duckdb
import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from tests.fixtures.fixture_index import create_benchmark_index_tables  # noqa: E402
from tests.fixtures.fixture_websocket import create_live_price_tables  # noqa: E402


@pytest.fixture()
def conn():
    """
    Shared test DuckDB connection.

    Combines benchmark-index tables and live-price/websocket tables.
    """
    connection = duckdb.connect(":memory:")

    create_benchmark_index_tables(connection)
    create_live_price_tables(connection)

    yield connection

    connection.close()


@pytest.fixture()
def seeded_assets(conn):
    """
    Seed assets for live price subscription and worker-routing tests.

    AAPL and MSFT are portfolio holdings.
    NVDA is watchlist only.
    CASH has zero quantity and should not stream.
    """
    conn.execute(
        """
        INSERT OR REPLACE INTO asset(asset_id, symbol, exchange_code)
        VALUES
            ('AAPL', 'AAPL', 'XNYS'),
            ('MSFT', 'MSFT', 'XNAS'),
            ('NVDA', 'NVDA', 'XNAS'),
            ('CASH', 'CASH', NULL);
        """
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO position(position_id, portfolio_id, asset_id, quantity)
        VALUES
            ('pos-aapl', 'p1', 'AAPL', 10),
            ('pos-msft', 'p1', 'MSFT', 5),
            ('pos-cash', 'p1', 'CASH', 0);
        """
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO watchlist_asset(watchlist_asset_id, asset_id, is_active)
        VALUES
            ('wl-nvda', 'NVDA', TRUE),
            ('wl-aapl', 'AAPL', TRUE);
        """
    )

    return conn