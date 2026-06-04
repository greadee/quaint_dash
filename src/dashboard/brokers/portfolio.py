"""Project synced broker transactions into local portfolios."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time


@dataclass(frozen=True, slots=True)
class BrokerPortfolioImportResult:
    provider: str
    imported_transactions: int
    skipped_transactions: int
    batch_id: int | None


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
        self._refresh_positions()
        return BrokerPortfolioImportResult(
            provider=provider,
            imported_transactions=imported,
            skipped_transactions=skipped,
            batch_id=batch_id if imported else None,
        )

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

    def _refresh_positions(self) -> None:
        from dashboard.db import queries as qry

        self.conn.execute(qry.UPDATE_POSITIONS)
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
    text = str(value).strip().upper()
    return text or None


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
