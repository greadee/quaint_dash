"""Project synced broker transactions into local portfolios."""

from __future__ import annotations

import ast
from dataclasses import dataclass, replace
from datetime import datetime, time
import json
from typing import Any


@dataclass(frozen=True, slots=True)
class BrokerPortfolioImportResult:
    provider: str
    imported_transactions: int
    skipped_transactions: int
    batch_id: int | None


@dataclass(frozen=True, slots=True)
class BrokerPortfolioProjectionResult:
    provider: str
    provider_account_id: str
    portfolio_id: int
    upserted_positions: int
    skipped_positions: int


class BrokerPortfolioIntegrationService:
    def __init__(self, conn) -> None:
        self.conn = conn

    def import_mapped_transactions(
        self,
        provider: str = "snaptrade",
        portfolio_id: int | None = None,
    ) -> BrokerPortfolioImportResult:
        rows = self._pending_rows(provider, portfolio_id)
        if not rows:
            if self.recalculate_projected_book_costs(provider, portfolio_id):
                self._refresh_positions()
            return BrokerPortfolioImportResult(
                provider=provider,
                imported_transactions=0,
                skipped_transactions=0,
                batch_id=None,
            )

        batch_id = self._create_batch()
        imported = 0
        skipped = 0
        for row in rows:
            normalized = _normalize_broker_transaction(row)
            if normalized is None:
                skipped += 1
                continue
            self._ensure_asset(normalized)
            txn_id = self._insert_txn(normalized, batch_id)
            self._insert_mapping(normalized, txn_id)
            imported += 1

        self.conn.execute(
            """
            DELETE FROM import_batch
            WHERE batch_id = ?
              AND NOT EXISTS (SELECT 1 FROM txn WHERE batch_id = ?)
            """,
            [batch_id, batch_id],
        )
        self.recalculate_projected_book_costs(provider, portfolio_id)
        self._refresh_positions()
        return BrokerPortfolioImportResult(
            provider=provider,
            imported_transactions=imported,
            skipped_transactions=skipped,
            batch_id=batch_id if imported else None,
        )

    def project_account_positions(
        self,
        provider_account_id: str,
        portfolio_id: int,
        provider: str = "snaptrade",
    ) -> BrokerPortfolioProjectionResult:
        rows = self._latest_position_rows(provider, provider_account_id)
        self.conn.execute(
            """
            DELETE FROM broker_portfolio_position_map
            WHERE provider = ?
              AND provider_account_id = ?
            """,
            [provider, provider_account_id],
        )

        upserted = 0
        skipped = 0
        for row in rows:
            normalized = _normalize_broker_position(row, portfolio_id)
            if normalized is None:
                skipped += 1
                continue
            normalized = replace(
                normalized,
                book_cost=self._projected_book_cost(normalized),
            )
            self._ensure_position_asset(normalized)
            self._insert_position_mapping(normalized)
            upserted += 1

        self._refresh_positions()
        return BrokerPortfolioProjectionResult(
            provider=provider,
            provider_account_id=provider_account_id,
            portfolio_id=portfolio_id,
            upserted_positions=upserted,
            skipped_positions=skipped,
        )

    def recalculate_projected_book_costs(
        self,
        provider: str = "snaptrade",
        portfolio_id: int | None = None,
    ) -> int:
        where = ["provider = ?"]
        params: list[object] = [provider]
        if portfolio_id is not None:
            where.append("portfolio_id = ?")
            params.append(portfolio_id)
        rows = self.conn.execute(
            f"""
            SELECT
                provider,
                provider_account_id,
                provider_position_id,
                portfolio_id,
                asset_id,
                quantity,
                book_cost,
                currency
            FROM broker_portfolio_position_map
            WHERE {" AND ".join(where)}
            """,
            params,
        ).fetchall()
        updated = 0
        for row in rows:
            position = _NormalizedBrokerPosition(
                provider=row[0],
                provider_account_id=row[1],
                provider_position_id=row[2],
                portfolio_id=int(row[3]),
                asset_id=row[4],
                description=None,
                quantity=float(row[5]),
                book_cost=float(row[6]),
                currency=row[7],
            )
            book_cost = self._projected_book_cost(position)
            if abs(book_cost - position.book_cost) < 0.0001:
                continue
            self.conn.execute(
                """
                UPDATE broker_portfolio_position_map
                SET book_cost = ?,
                    updated_at = now()
                WHERE provider = ?
                  AND provider_account_id = ?
                  AND provider_position_id = ?
                """,
                [
                    book_cost,
                    position.provider,
                    position.provider_account_id,
                    position.provider_position_id,
                ],
            )
            updated += 1
        return updated

    def _latest_position_rows(self, provider: str, provider_account_id: str) -> list[tuple]:
        return self.conn.execute(
            """
            WITH latest_positions AS (
                SELECT
                    provider,
                    provider_account_id,
                    provider_position_id,
                    MAX(as_of_date) AS as_of_date
                FROM broker_position_snapshot
                WHERE provider = ?
                  AND provider_account_id = ?
                GROUP BY provider, provider_account_id, provider_position_id
            )
            SELECT
                p.provider,
                p.provider_account_id,
                p.provider_position_id,
                p.asset_id,
                p.symbol,
                p.description,
                p.quantity,
                p.market_value,
                p.currency,
                p.raw_json
            FROM broker_position_snapshot p
            JOIN latest_positions latest
              ON latest.provider = p.provider
             AND latest.provider_account_id = p.provider_account_id
             AND latest.provider_position_id = p.provider_position_id
             AND latest.as_of_date = p.as_of_date
            ORDER BY p.provider_position_id
            """,
            [provider, provider_account_id],
        ).fetchall()

    def _pending_rows(self, provider: str, portfolio_id: int | None) -> list[tuple]:
        where = [
            "bt.provider = ?",
            "ba.portfolio_id IS NOT NULL",
            "m.provider_transaction_id IS NULL",
        ]
        params: list[object] = [provider]
        if portfolio_id is not None:
            where.append("ba.portfolio_id = ?")
            params.append(portfolio_id)

        query = f"""
            SELECT
                bt.provider,
                bt.provider_transaction_id,
                bt.provider_account_id,
                ba.portfolio_id,
                bt.trade_date,
                bt.txn_type,
                bt.asset_id,
                bt.symbol,
                bt.quantity,
                bt.price,
                bt.amount,
                bt.currency
            FROM broker_transaction bt
            JOIN broker_account ba
              ON ba.provider = bt.provider
             AND ba.provider_account_id = bt.provider_account_id
            LEFT JOIN broker_portfolio_txn_map m
              ON m.provider = bt.provider
             AND m.provider_transaction_id = bt.provider_transaction_id
            WHERE {" AND ".join(where)}
            ORDER BY ba.portfolio_id, bt.trade_date, bt.provider_transaction_id
        """
        return self.conn.execute(query, params).fetchall()

    def _create_batch(self) -> int:
        row = self.conn.execute(
            """
            INSERT INTO import_batch(batch_type, import_time)
            VALUES ('broker-sync', now())
            RETURNING batch_id
            """
        ).fetchone()
        return int(row[0])

    def _ensure_asset(self, txn: "_NormalizedBrokerTxn") -> None:
        if txn.asset_id is None:
            return
        self.conn.execute(
            """
            INSERT INTO asset(asset_id, symbol, asset_type, ccy, track, created_at, updated_at)
            VALUES (?, ?, 'stock', ?, TRUE, now(), now())
            ON CONFLICT(asset_id) DO UPDATE SET
                symbol = COALESCE(asset.symbol, excluded.symbol),
                updated_at = now()
            """,
            [txn.asset_id, txn.asset_id, txn.ccy or "CAD"],
        )
        self.conn.execute(
            """
            INSERT INTO asset_metadata_sync(asset_id, source, sync_status, next_retry_at)
            VALUES (?, 'fmp', 'pending', now())
            ON CONFLICT(asset_id) DO NOTHING
            """,
            [txn.asset_id],
        )

    def _ensure_position_asset(self, position: "_NormalizedBrokerPosition") -> None:
        self.conn.execute(
            """
            INSERT INTO asset(asset_id, symbol, asset_type, ccy, name, track, created_at, updated_at)
            VALUES (?, ?, 'stock', ?, ?, TRUE, now(), now())
            ON CONFLICT(asset_id) DO UPDATE SET
                symbol = COALESCE(asset.symbol, excluded.symbol),
                name = COALESCE(asset.name, excluded.name),
                updated_at = now()
            """,
            [
                position.asset_id,
                position.asset_id,
                position.currency or "CAD",
                position.description,
            ],
        )
        self.conn.execute(
            """
            INSERT INTO asset_metadata_sync(asset_id, source, sync_status, next_retry_at)
            VALUES (?, 'fmp', 'pending', now())
            ON CONFLICT(asset_id) DO NOTHING
            """,
            [position.asset_id],
        )

    def _insert_txn(self, txn: "_NormalizedBrokerTxn", batch_id: int) -> int:
        row = self.conn.execute(
            """
            INSERT INTO txn (
                portfolio_id,
                time_stamp,
                txn_type,
                asset_id,
                qty,
                price,
                ccy,
                cash_amt,
                fee_amt,
                batch_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            RETURNING txn_id
            """,
            [
                txn.portfolio_id,
                txn.time_stamp,
                txn.txn_type,
                txn.asset_id,
                txn.qty,
                txn.price,
                txn.ccy,
                txn.cash_amt,
                batch_id,
            ],
        ).fetchone()
        return int(row[0])

    def _insert_mapping(self, txn: "_NormalizedBrokerTxn", txn_id: int) -> None:
        self.conn.execute(
            """
            INSERT INTO broker_portfolio_txn_map (
                provider,
                provider_transaction_id,
                txn_id,
                portfolio_id,
                provider_account_id,
                imported_at
            )
            VALUES (?, ?, ?, ?, ?, now())
            ON CONFLICT(provider, provider_transaction_id) DO NOTHING
            """,
            [
                txn.provider,
                txn.provider_transaction_id,
                txn_id,
                txn.portfolio_id,
                txn.provider_account_id,
            ],
        )

    def _insert_position_mapping(self, position: "_NormalizedBrokerPosition") -> None:
        self.conn.execute(
            """
            INSERT INTO broker_portfolio_position_map (
                provider,
                provider_account_id,
                provider_position_id,
                portfolio_id,
                asset_id,
                quantity,
                book_cost,
                currency,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, now())
            ON CONFLICT(provider, provider_account_id, provider_position_id)
            DO UPDATE SET
                portfolio_id = excluded.portfolio_id,
                asset_id = excluded.asset_id,
                quantity = excluded.quantity,
                book_cost = excluded.book_cost,
                currency = excluded.currency,
                updated_at = excluded.updated_at
            """,
            [
                position.provider,
                position.provider_account_id,
                position.provider_position_id,
                position.portfolio_id,
                position.asset_id,
                position.quantity,
                position.book_cost,
                position.currency,
            ],
        )

    def _projected_book_cost(self, position: "_NormalizedBrokerPosition") -> float:
        return (
            self._book_cost_from_position_snapshot(position)
            or self._book_cost_from_broker_transactions(position)
            or position.book_cost
        )

    def _book_cost_from_position_snapshot(self, position: "_NormalizedBrokerPosition") -> float | None:
        row = self.conn.execute(
            """
            SELECT raw_json
            FROM broker_position_snapshot
            WHERE provider = ?
              AND provider_account_id = ?
              AND provider_position_id = ?
            ORDER BY as_of_date DESC
            LIMIT 1
            """,
            [
                position.provider,
                position.provider_account_id,
                position.provider_position_id,
            ],
        ).fetchone()
        if row is None:
            return None
        payload = _json_payload(row[0])
        average_price = _float_or_none(_payload_value(payload, "average_purchase_price"))
        if average_price is None:
            average_price = _float_or_none(_payload_value(payload, "averagePrice"))
        if average_price is None or average_price <= 0:
            return None
        return average_price * position.quantity

    def _book_cost_from_broker_transactions(self, position: "_NormalizedBrokerPosition") -> float | None:
        rows = self.conn.execute(
            """
            SELECT
                trade_date,
                txn_type,
                asset_id,
                symbol,
                quantity,
                price,
                amount,
                raw_json
            FROM broker_transaction
            WHERE provider = ?
              AND provider_account_id = ?
            ORDER BY trade_date, provider_transaction_id
            """,
            [position.provider, position.provider_account_id],
        ).fetchall()
        quantity = 0.0
        cost = 0.0
        matched_trade_count = 0
        for row in rows:
            txn_type = _normalize_type(row[1])
            if txn_type not in {"buy", "sell"}:
                continue
            asset_id = _normalize_asset_id(row[2] or row[3])
            if asset_id != position.asset_id:
                continue
            txn_qty = _normalize_quantity(txn_type, row[4])
            payload = _json_payload(row[7])
            if txn_qty is None:
                txn_qty = _normalize_quantity(
                    txn_type,
                    _payload_value(payload, "units") or _payload_value(payload, "quantity"),
                )
            price = _float_or_none(row[5])
            amount = _float_or_none(row[6])
            if price is None:
                price = _float_or_none(
                    _payload_value(payload, "price")
                    or _payload_value(payload, "trade_price")
                    or _payload_value(payload, "execution_price")
                )
            if amount is None:
                amount = _float_or_none(
                    _payload_value(payload, "amount")
                    or _payload_value(payload, "net_amount")
                    or _payload_value(payload, "value")
                )
            if price is None and amount is not None and txn_qty not in (None, 0):
                price = abs(amount) / abs(txn_qty)
            if txn_qty is None or price is None:
                continue
            matched_trade_count += 1
            if txn_type == "buy":
                buy_qty = abs(txn_qty)
                quantity += buy_qty
                cost += buy_qty * price
                continue
            sell_qty = min(abs(txn_qty), quantity)
            if sell_qty <= 0 or quantity <= 0:
                continue
            average_cost = cost / quantity if quantity else 0.0
            quantity -= sell_qty
            cost -= average_cost * sell_qty

        if not matched_trade_count or quantity <= 0 or cost <= 0:
            return None
        average_cost = cost / quantity
        return average_cost * position.quantity

    def _refresh_positions(self) -> None:
        self.conn.execute("DELETE FROM position")
        self.conn.execute(
            """
            INSERT INTO position (portfolio_id, asset_id, qty, book_cost, created_at, updated_at)
            SELECT
                portfolio_id,
                asset_id,
                SUM(quantity) AS qty,
                SUM(book_cost) AS book_cost,
                now() AS created_at,
                now() AS updated_at
            FROM (
                SELECT
                    portfolio_id,
                    asset_id,
                    SUM(qty) AS quantity,
                    SUM(price * qty) AS book_cost
                FROM txn
                WHERE txn_type IN ('buy', 'sell')
                  AND asset_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1
                    FROM broker_portfolio_position_map mapped_positions
                    WHERE mapped_positions.portfolio_id = txn.portfolio_id
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM broker_portfolio_txn_map tm
                    JOIN broker_portfolio_position_map pm
                      ON pm.provider = tm.provider
                     AND pm.provider_account_id = tm.provider_account_id
                     AND pm.portfolio_id = txn.portfolio_id
                     AND pm.asset_id = txn.asset_id
                    WHERE tm.txn_id = txn.txn_id
                  )
                GROUP BY portfolio_id, asset_id
                UNION ALL
                SELECT
                    portfolio_id,
                    asset_id,
                    quantity,
                    book_cost
                FROM broker_portfolio_position_map
            ) holdings
            GROUP BY portfolio_id, asset_id
            HAVING SUM(quantity) <> 0
            """
        )
        try:
            from dashboard.ingestion.ticker_universe import TickerUniverseRepository

            TickerUniverseRepository(self.conn).sync_portfolio_tickers_from_positions()
        except Exception:
            pass


@dataclass(frozen=True, slots=True)
class _NormalizedBrokerTxn:
    provider: str
    provider_transaction_id: str
    provider_account_id: str
    portfolio_id: int
    time_stamp: datetime
    txn_type: str
    asset_id: str | None
    qty: float | None
    price: float | None
    ccy: str | None
    cash_amt: float | None


@dataclass(frozen=True, slots=True)
class _NormalizedBrokerPosition:
    provider: str
    provider_account_id: str
    provider_position_id: str
    portfolio_id: int
    asset_id: str
    description: str | None
    quantity: float
    book_cost: float
    currency: str | None


def _normalize_broker_position(row: tuple, portfolio_id: int) -> _NormalizedBrokerPosition | None:
    (
        provider,
        provider_account_id,
        provider_position_id,
        raw_asset_id,
        raw_symbol,
        description,
        quantity,
        market_value,
        currency,
        raw_json,
    ) = row
    symbol_payload = _symbol_payload(raw_symbol)
    asset_id = _normalize_asset_id(raw_asset_id or raw_symbol)
    qty = _float_or_none(quantity)
    value = _float_or_none(market_value)
    payload = _json_payload(raw_json)
    weighting = _position_weighting(payload)
    if asset_id is None or qty is None or abs(qty) < 0.0001:
        return None
    if value is not None and abs(value) < 0.01:
        return None
    if weighting is not None and abs(weighting) < 0.0001:
        return None
    currency = _normalize_currency(currency) or _normalize_currency(_payload_value(symbol_payload, "currency"))
    return _NormalizedBrokerPosition(
        provider=str(provider),
        provider_account_id=str(provider_account_id),
        provider_position_id=str(provider_position_id),
        portfolio_id=portfolio_id,
        asset_id=asset_id,
        description=str(description or _payload_value(symbol_payload, "description") or "")
        or None,
        quantity=qty,
        book_cost=value or 0.0,
        currency=currency,
    )


def _normalize_broker_transaction(row: tuple) -> _NormalizedBrokerTxn | None:
    (
        provider,
        provider_transaction_id,
        provider_account_id,
        portfolio_id,
        trade_date,
        raw_type,
        raw_asset_id,
        raw_symbol,
        quantity,
        price,
        amount,
        currency,
    ) = row
    txn_type = _normalize_type(raw_type)
    asset_id = _normalize_asset_id(raw_asset_id or raw_symbol)
    qty = _normalize_quantity(txn_type, quantity)
    price = _float_or_none(price)
    cash_amt = _normalize_cash_amount(txn_type, amount, qty, price)

    if txn_type in {"buy", "sell", "dividend"} and asset_id is None:
        return None
    if txn_type in {"buy", "sell"} and (qty is None or price is None):
        return None
    if txn_type in {"contribution", "withdrawal", "interest"} and cash_amt is None:
        return None

    return _NormalizedBrokerTxn(
        provider=str(provider),
        provider_transaction_id=str(provider_transaction_id),
        provider_account_id=str(provider_account_id),
        portfolio_id=int(portfolio_id),
        time_stamp=datetime.combine(trade_date, time.min)
        if not isinstance(trade_date, datetime)
        else trade_date,
        txn_type=txn_type,
        asset_id=asset_id,
        qty=qty,
        price=price,
        ccy=str(currency).upper() if currency else None,
        cash_amt=cash_amt,
    )


def _normalize_type(value) -> str:
    text = str(value or "").strip().lower().replace("_", " ")
    if text in {"rei", "dividend reinvestment"}:
        return "buy"
    if any(token in text for token in ("buy", "purchase")):
        return "buy"
    if any(token in text for token in ("sell", "sale")):
        return "sell"
    if "stock dividend" in text:
        return "buy"
    if "dividend" in text or text in {"div"}:
        return "dividend"
    if any(token in text for token in ("deposit", "contribution", "transfer in")):
        return "contribution"
    if any(token in text for token in ("withdraw", "transfer out")):
        return "withdrawal"
    if any(token in text for token in ("fee", "tax")):
        return "withdrawal"
    if any(token in text for token in ("interest", "cash")):
        return "interest"
    return "interest"


def _normalize_asset_id(value) -> str | None:
    if value is None:
        return None
    payload = _symbol_payload(value)
    if payload:
        symbol = _payload_value(payload, "symbol") or _payload_value(payload, "ticker")
        symbol = symbol or _payload_value(payload, "raw_symbol")
        if symbol:
            return str(symbol).strip().upper()
    text = str(value).strip().upper()
    if text.startswith("{"):
        return None
    return text or None


def _normalize_currency(value) -> str | None:
    if isinstance(value, dict):
        value = _payload_value(value, "code") or _payload_value(value, "currency")
    if value is None:
        return None
    text = str(value).strip().upper()
    return text if len(text) == 3 and text.isalpha() else None


def _symbol_payload(value) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    text = str(value).strip()
    if not text.startswith("{"):
        return {}
    normalized = (
        text.replace(": TRUE", ": True")
        .replace(": FALSE", ": False")
        .replace(": NONE", ": None")
    )
    try:
        payload = ast.literal_eval(normalized)
    except (SyntaxError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _json_payload(value) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    try:
        payload = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _payload_value(payload: dict[str, Any], key: str) -> Any:
    if key in payload:
        value = payload[key]
    elif key.upper() in payload:
        value = payload[key.upper()]
    elif key.lower() in payload:
        value = payload[key.lower()]
    else:
        return None
    if isinstance(value, dict):
        return _payload_value(value, "code") or _payload_value(value, "symbol")
    return value


def _position_weighting(payload: dict[str, Any]) -> float | None:
    for key in (
        "weight",
        "weighting",
        "weight_percent",
        "weightPercentage",
        "allocation",
        "allocation_percent",
        "portfolio_weight",
        "portfolioWeight",
        "percentage",
    ):
        value = _payload_value(payload, key)
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip().removesuffix("%")
        parsed = _float_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _normalize_quantity(txn_type: str, value) -> float | None:
    qty = _float_or_none(value)
    if qty is None:
        return None
    if txn_type == "sell":
        return -abs(qty)
    return abs(qty)


def _normalize_cash_amount(txn_type: str, amount, qty: float | None, price: float | None) -> float | None:
    if txn_type in {"buy", "sell"}:
        return None
    cash_amt = _float_or_none(amount)
    if cash_amt is not None:
        if txn_type == "withdrawal":
            return -abs(cash_amt)
        if txn_type in {"contribution", "dividend", "interest"}:
            return abs(cash_amt)
        return cash_amt
    if txn_type == "dividend" and qty is not None and price is not None:
        return abs(qty * price)
    return None


def _float_or_none(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
