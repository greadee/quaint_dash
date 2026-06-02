# src/dashboard/ingestion/fundamentals/subscription_service.py

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dashboard.ingestion.fundamentals.constants import DEFAULT_REFRESH_INTERVAL_DAYS
from dashboard.ingestion.fundamentals.schema import ensure_fundamental_phase1_schema


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _table_columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    return {row[1] for row in rows}


def _asset_id_column(conn) -> str:
    columns = _table_columns(conn, "asset")

    if "asset_id" in columns:
        return "asset_id"

    if "id" in columns:
        return "id"

    raise RuntimeError("Could not find asset id column. Expected asset.asset_id or asset.id.")


def _asset_ticker_column(conn) -> str:
    columns = _table_columns(conn, "asset")

    if "asset_id" in columns:
        return "asset_id"

    if "ticker" in columns:
        return "ticker"

    if "symbol" in columns:
        return "symbol"

    raise RuntimeError("Could not find asset ticker column. Expected asset.asset_id, asset.ticker, or asset.symbol.")


class FundamentalSubscriptionService:
    def __init__(self, conn):
        self.conn = conn
        ensure_fundamental_phase1_schema(conn)

    def subscribe_asset(
        self,
        asset_id: str,
        refresh_interval_days: int = DEFAULT_REFRESH_INTERVAL_DAYS,
        subscription_source: str = "manual",
    ) -> str:
        """
        Adds an asset to the monitored fundamentals list.

        Idempotent:
        - If the subscription does not exist, create it.
        - If it exists, reactivate it and update the interval.
        """

        now = _utc_now_naive()

        existing = self.conn.execute(
            """
            SELECT asset_id
            FROM fundamental_subscription
            WHERE asset_id = ?
            """,
            [asset_id],
        ).fetchone()

        if existing:
            self.conn.execute(
                """
                UPDATE fundamental_subscription
                SET
                    is_active = TRUE,
                    refresh_interval_days = ?,
                    subscription_source = ?,
                    next_refresh_at = COALESCE(next_refresh_at, ?),
                    updated_at = ?
                WHERE asset_id = ?
                """,
                [
                    refresh_interval_days,
                    subscription_source,
                    now,
                    now,
                    asset_id,
                ],
            )
        else:
            self.conn.execute(
                """
                INSERT INTO fundamental_subscription (
                    asset_id,
                    is_active,
                    refresh_interval_days,
                    next_refresh_at,
                    subscription_source,
                    created_at,
                    updated_at
                )
                VALUES (?, TRUE, ?, ?, ?, ?, ?)
                """,
                [
                    asset_id,
                    refresh_interval_days,
                    now,
                    subscription_source,
                    now,
                    now,
                ],
            )

        return asset_id

    def subscribe_ticker(
        self,
        ticker: str,
        refresh_interval_days: int = DEFAULT_REFRESH_INTERVAL_DAYS,
        subscription_source: str = "manual",
    ) -> str:
        """
        Subscribes an existing asset by ticker.

        This intentionally does not create the asset because asset creation rules
        already live elsewhere in the project.
        """

        asset_id = self.find_asset_id_by_ticker(ticker)

        if asset_id is None:
            raise ValueError(
                f"Ticker '{ticker}' does not exist in asset table. "
                "Create/import the asset before subscribing fundamentals."
            )

        return self.subscribe_asset(
            asset_id=asset_id,
            refresh_interval_days=refresh_interval_days,
            subscription_source=subscription_source,
        )

    def unsubscribe_asset(self, asset_id: str) -> None:
        now = _utc_now_naive()

        self.conn.execute(
            """
            UPDATE fundamental_subscription
            SET
                is_active = FALSE,
                updated_at = ?
            WHERE asset_id = ?
            """,
            [now, asset_id],
        )

    def unsubscribe_ticker(self, ticker: str) -> None:
        asset_id = self.find_asset_id_by_ticker(ticker)

        if asset_id is None:
            raise ValueError(f"Ticker '{ticker}' does not exist in asset table.")

        self.unsubscribe_asset(asset_id)

    def find_asset_id_by_ticker(self, ticker: str) -> str | None:
        asset_id_col = _asset_id_column(self.conn)
        ticker_col = _asset_ticker_column(self.conn)

        row = self.conn.execute(
            f"""
            SELECT {asset_id_col}
            FROM asset
            WHERE upper({ticker_col}) = upper(?)
            LIMIT 1
            """,
            [ticker],
        ).fetchone()

        if not row:
            return None

        return str(row[0])

    def list_active_subscriptions(self) -> list[dict[str, Any]]:
        asset_id_col = _asset_id_column(self.conn)
        ticker_col = _asset_ticker_column(self.conn)

        rows = self.conn.execute(
            f"""
            SELECT
                fs.asset_id,
                a.{ticker_col} AS ticker,
                fs.refresh_interval_days,
                fs.next_refresh_at,
                fs.last_refresh_attempted_at,
                fs.last_refresh_succeeded_at,
                fs.subscription_source
            FROM fundamental_subscription fs
            JOIN asset a
                ON a.{asset_id_col} = fs.asset_id
            WHERE fs.is_active = TRUE
            ORDER BY a.{ticker_col}
            """
        ).fetchall()

        return [
            {
                "asset_id": row[0],
                "ticker": row[1],
                "refresh_interval_days": row[2],
                "next_refresh_at": row[3],
                "last_refresh_attempted_at": row[4],
                "last_refresh_succeeded_at": row[5],
                "subscription_source": row[6],
            }
            for row in rows
        ]
