from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TickerSubscription:
    asset_id: str
    symbol: str
    exchange_code: str | None
    source_scope: str


class TickerUniverseRepository:
    """
    Shared source of ticker lists used by ingestion.

    New code should read portfolio and watchlist tickers from portfolio_ticker
    and watchlist_ticker. Fallbacks keep older tests and partially migrated
    databases working until the schema has been initialized.
    """

    def __init__(self, conn) -> None:
        self.conn = conn

    def portfolio_asset_ids(self) -> list[str]:
        if self._table_exists("portfolio_ticker"):
            return self._asset_ids_from_portfolio_ticker()

        if self._table_exists("position"):
            return self._asset_ids_from_position()

        return []

    def watchlist_asset_ids(self) -> list[str]:
        if self._table_exists("watchlist_ticker"):
            return self._asset_ids_from_watchlist_ticker()

        if self._table_exists("watchlist_asset"):
            return self._asset_ids_from_watchlist_asset()

        return []

    def ingestible_asset_ids(
        self,
        include_watchlist: bool = True,
        asset_types: tuple[str, ...] | None = None,
    ) -> list[str]:
        asset_ids = set(self.portfolio_asset_ids())

        if include_watchlist:
            asset_ids.update(self.watchlist_asset_ids())

        if not asset_ids:
            asset_ids.update(self._tracked_asset_ids())

        if not asset_ids:
            return []

        ordered = sorted(asset_ids)
        if asset_types is None or not self._has_column("asset", "asset_type"):
            return ordered

        placeholders = ", ".join("?" for _ in ordered)
        type_placeholders = ", ".join("?" for _ in asset_types)
        rows = self.conn.execute(
            f"""
            SELECT asset_id
            FROM asset
            WHERE asset_id IN ({placeholders})
              AND COALESCE(asset_type, 'stock') IN ({type_placeholders})
            ORDER BY asset_id
            """,
            [*ordered, *asset_types],
        ).fetchall()

        return [row[0] for row in rows]

    def sync_portfolio_tickers_from_positions(self) -> int:
        if not self._table_exists("portfolio_ticker") or not self._table_exists("position"):
            return 0

        quantity_column = self._quantity_column()
        if quantity_column is None:
            return 0

        self.conn.execute(
            f"""
            INSERT INTO portfolio_ticker (
                portfolio_id,
                asset_id,
                is_active,
                source,
                created_at,
                updated_at
            )
            SELECT DISTINCT
                portfolio_id,
                asset_id,
                TRUE,
                'position',
                now(),
                now()
            FROM position
            WHERE asset_id IS NOT NULL
              AND COALESCE({quantity_column}, 0) <> 0
            ON CONFLICT (portfolio_id, asset_id)
            DO UPDATE SET
                is_active = TRUE,
                updated_at = now()
            """
        )
        self.conn.execute(
            f"""
            UPDATE portfolio_ticker pt
            SET is_active = FALSE,
                updated_at = now()
            WHERE NOT EXISTS (
                SELECT 1
                FROM position p
                WHERE p.portfolio_id = pt.portfolio_id
                  AND p.asset_id = pt.asset_id
                  AND p.asset_id IS NOT NULL
                  AND COALESCE(p.{quantity_column}, 0) <> 0
            )
            """
        )

        row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM portfolio_ticker
            WHERE is_active = TRUE
            """
        ).fetchone()
        return int(row[0])

    def stream_subscriptions(
        self,
        include_portfolios: bool = True,
        include_watchlist: bool = False,
    ) -> list[TickerSubscription]:
        subscriptions: dict[str, TickerSubscription] = {}

        scopes: list[tuple[str, list[str]]] = []
        if include_portfolios:
            scopes.append(("portfolio", self.portfolio_asset_ids()))
        if include_watchlist:
            scopes.append(("watchlist", self.watchlist_asset_ids()))

        for scope, asset_ids in scopes:
            for asset_id, symbol, exchange_code, asset_subtype, name, description in self._asset_symbol_rows(asset_ids):
                subscriptions.setdefault(
                    symbol,
                    TickerSubscription(
                        asset_id=asset_id,
                        symbol=symbol,
                        exchange_code=exchange_code,
                        source_scope=scope,
                    ),
                )
                underlying = _cdr_underlying_symbol(
                    asset_id=asset_id,
                    symbol=symbol,
                    asset_subtype=asset_subtype,
                    name=name,
                    description=description,
                )
                if underlying and underlying != symbol:
                    subscriptions.setdefault(
                        underlying,
                        TickerSubscription(
                            asset_id=underlying,
                            symbol=underlying,
                            exchange_code=None,
                            source_scope=f"{scope}_underlying",
                        ),
                    )

        return sorted(subscriptions.values(), key=lambda item: item.symbol)

    def _asset_ids_from_portfolio_ticker(self) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT asset_id
            FROM portfolio_ticker
            WHERE is_active = TRUE
            ORDER BY asset_id
            """
        ).fetchall()
        return [row[0] for row in rows]

    def _asset_ids_from_watchlist_ticker(self) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT asset_id
            FROM watchlist_ticker
            WHERE is_active = TRUE
            ORDER BY asset_id
            """
        ).fetchall()
        return [row[0] for row in rows]

    def _asset_ids_from_position(self) -> list[str]:
        quantity_column = self._quantity_column()
        if quantity_column is None:
            return []

        rows = self.conn.execute(
            f"""
            SELECT DISTINCT asset_id
            FROM position
            WHERE asset_id IS NOT NULL
              AND COALESCE({quantity_column}, 0) <> 0
            ORDER BY asset_id
            """
        ).fetchall()
        return [row[0] for row in rows]

    def _asset_ids_from_watchlist_asset(self) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT asset_id
            FROM watchlist_asset
            WHERE is_active = TRUE
            ORDER BY asset_id
            """
        ).fetchall()
        return [row[0] for row in rows]

    def _tracked_asset_ids(self) -> list[str]:
        if not self._has_column("asset", "track"):
            return []

        rows = self.conn.execute(
            """
            SELECT asset_id
            FROM asset
            WHERE track = TRUE
            ORDER BY asset_id
            """
        ).fetchall()
        return [row[0] for row in rows]

    def _asset_symbol_rows(
        self,
        asset_ids: list[str],
    ) -> list[tuple[str, str, str | None, str | None, str | None, str | None]]:
        if not asset_ids:
            return []

        placeholders = ", ".join("?" for _ in asset_ids)
        symbol_expr = "COALESCE(symbol, asset_id)" if self._has_column("asset", "symbol") else "asset_id"
        exchange_expr = "exchange_code" if self._has_column("asset", "exchange_code") else "NULL"
        subtype_expr = "asset_subtype" if self._has_column("asset", "asset_subtype") else "NULL"
        name_expr = "name" if self._has_column("asset", "name") else "NULL"
        description_expr = "description" if self._has_column("asset", "description") else "NULL"

        rows = self.conn.execute(
            f"""
            SELECT
                asset_id,
                {symbol_expr} AS symbol,
                {exchange_expr} AS exchange_code,
                {subtype_expr} AS asset_subtype,
                {name_expr} AS name,
                {description_expr} AS description
            FROM asset
            WHERE asset_id IN ({placeholders})
            ORDER BY symbol
            """,
            asset_ids,
        ).fetchall()

        return [(row[0], row[1], row[2], row[3], row[4], row[5]) for row in rows]

    def _quantity_column(self) -> str | None:
        if self._has_column("position", "qty"):
            return "qty"
        if self._has_column("position", "quantity"):
            return "quantity"
        return None

    def _table_exists(self, table_name: str) -> bool:
        row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_name = ?
            """,
            [table_name],
        ).fetchone()
        return bool(row and row[0])

    def _has_column(self, table_name: str, column_name: str) -> bool:
        if not self._table_exists(table_name):
            return False

        rows = self.conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
        return any(row[1] == column_name for row in rows)


_CDR_SYMBOL_ALIASES = {
    "NOWS": "NOW",
}


def _cdr_underlying_symbol(
    *,
    asset_id: str,
    symbol: str,
    asset_subtype: str | None,
    name: str | None,
    description: str | None,
) -> str | None:
    text = " ".join(
        str(value or "")
        for value in (asset_id, symbol, asset_subtype, name, description)
    ).lower()
    if "cdr" not in text and "depositary receipt" not in text and "depository receipt" not in text:
        return None

    base = (symbol or asset_id).split(".", maxsplit=1)[0].upper()
    return _CDR_SYMBOL_ALIASES.get(base, base) or None
