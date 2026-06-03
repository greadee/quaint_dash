"""DuckDB repository for read-only broker sync state."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from dashboard.brokers.models import (
    BrokerAccount,
    BrokerConnection,
    BrokerPosition,
    BrokerSyncResult,
    BrokerTransaction,
    BrokerUser,
    SecretCipher,
)


class BrokerSyncRepository:
    def __init__(self, conn) -> None:
        self.conn = conn

    def raw_payload_storage_enabled(self) -> bool:
        row = self.conn.execute(
            """
            SELECT config_value
            FROM broker_storage_config
            WHERE config_key = 'raw_payloads_enabled'
            """
        ).fetchone()
        return not row or str(row[0]).lower() == "true"

    def set_raw_payload_storage_enabled(self, enabled: bool) -> None:
        self.conn.execute(
            """
            INSERT INTO broker_storage_config(config_key, config_value, updated_at)
            VALUES ('raw_payloads_enabled', ?, now())
            ON CONFLICT(config_key) DO UPDATE SET
                config_value = excluded.config_value,
                updated_at = now()
            """,
            ["true" if enabled else "false"],
        )

    def _raw_json(self, value: dict[str, Any]) -> str:
        return _json_dumps(value) if self.raw_payload_storage_enabled() else "{}"

    def upsert_broker_user(
        self,
        user: BrokerUser,
        cipher: SecretCipher,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO broker_user (
                provider,
                user_key,
                provider_user_id,
                encrypted_user_secret,
                secret_cipher,
                status,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, now())
            ON CONFLICT(provider, user_key) DO UPDATE SET
                provider_user_id = excluded.provider_user_id,
                encrypted_user_secret = excluded.encrypted_user_secret,
                secret_cipher = excluded.secret_cipher,
                status = excluded.status,
                updated_at = now()
            """,
            [
                user.provider,
                user.user_key,
                user.provider_user_id,
                cipher.encrypt(user.user_secret),
                cipher.name,
                user.status,
            ],
        )

    def get_broker_user(
        self,
        provider: str,
        user_key: str,
        cipher: SecretCipher,
    ) -> BrokerUser | None:
        row = self.conn.execute(
            """
            SELECT provider, user_key, provider_user_id, encrypted_user_secret, status
            FROM broker_user
            WHERE provider = ?
              AND user_key = ?
            """,
            [provider, user_key],
        ).fetchone()
        if row is None:
            return None
        return BrokerUser(
            provider=row[0],
            user_key=row[1],
            provider_user_id=row[2],
            user_secret=cipher.decrypt(row[3]),
            status=row[4],
        )

    def list_broker_users(
        self,
        provider: str,
        cipher: SecretCipher,
        status: str = "active",
    ) -> list[BrokerUser]:
        rows = self.conn.execute(
            """
            SELECT provider, user_key, provider_user_id, encrypted_user_secret, status
            FROM broker_user
            WHERE provider = ?
              AND status = ?
            ORDER BY user_key
            """,
            [provider, status],
        ).fetchall()
        return [
            BrokerUser(
                provider=row[0],
                user_key=row[1],
                provider_user_id=row[2],
                user_secret=cipher.decrypt(row[3]),
                status=row[4],
            )
            for row in rows
        ]

    def update_broker_user_status(self, provider: str, user_key: str, status: str) -> None:
        self.conn.execute(
            """
            UPDATE broker_user
            SET status = ?,
                updated_at = now()
            WHERE provider = ?
              AND user_key = ?
            """,
            [status, provider, user_key],
        )

    def update_connection_status(
        self,
        provider: str,
        provider_connection_id: str,
        status: str,
    ) -> None:
        self.conn.execute(
            """
            UPDATE broker_connection
            SET status = ?,
                updated_at = now()
            WHERE provider = ?
              AND provider_connection_id = ?
            """,
            [status, provider, provider_connection_id],
        )

    def due_broker_users(
        self,
        provider: str,
        cipher: SecretCipher,
        stale_before: datetime,
    ) -> list[BrokerUser]:
        rows = self.conn.execute(
            """
            SELECT
                u.provider,
                u.user_key,
                u.provider_user_id,
                u.encrypted_user_secret,
                u.status,
                MAX(r.completed_at) AS last_completed_at
            FROM broker_user u
            LEFT JOIN broker_sync_run r
              ON r.provider = u.provider
             AND r.user_key = u.user_key
             AND r.status = 'done'
            WHERE u.provider = ?
              AND u.status = 'active'
            GROUP BY
                u.provider,
                u.user_key,
                u.provider_user_id,
                u.encrypted_user_secret,
                u.status
            HAVING last_completed_at IS NULL
                OR last_completed_at < ?
            ORDER BY u.user_key
            """,
            [provider, stale_before],
        ).fetchall()
        return [
            BrokerUser(
                provider=row[0],
                user_key=row[1],
                provider_user_id=row[2],
                user_secret=cipher.decrypt(row[3]),
                status=row[4],
            )
            for row in rows
        ]

    def upsert_connection(self, connection: BrokerConnection) -> int:
        self.conn.execute(
            """
            INSERT INTO broker_connection (
                provider,
                provider_connection_id,
                provider_user_id,
                institution_name,
                status,
                raw_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, now())
            ON CONFLICT(provider, provider_connection_id) DO UPDATE SET
                provider_user_id = excluded.provider_user_id,
                institution_name = excluded.institution_name,
                status = excluded.status,
                raw_json = excluded.raw_json,
                updated_at = now()
            """,
            [
                connection.provider,
                connection.provider_connection_id,
                connection.provider_user_id,
                connection.institution_name,
                connection.status,
                self._raw_json(connection.raw_payload),
            ],
        )
        row = self.conn.execute(
            """
            SELECT connection_id
            FROM broker_connection
            WHERE provider = ?
              AND provider_connection_id = ?
            """,
            [connection.provider, connection.provider_connection_id],
        ).fetchone()
        return int(row[0])

    def list_connections(self, provider: str | None = None) -> list[BrokerConnection]:
        where = ""
        params: list[Any] = []
        if provider is not None:
            where = "WHERE provider = ?"
            params.append(provider)
        rows = self.conn.execute(
            f"""
            SELECT
                connection_id,
                provider,
                provider_connection_id,
                provider_user_id,
                institution_name,
                status,
                raw_json
            FROM broker_connection
            {where}
            ORDER BY institution_name, connection_id
            """,
            params,
        ).fetchall()
        return [
            BrokerConnection(
                connection_id=int(row[0]),
                provider=row[1],
                provider_connection_id=row[2],
                provider_user_id=row[3],
                institution_name=row[4],
                status=row[5],
                raw_payload=_json_loads(row[6]),
            )
            for row in rows
        ]

    def upsert_account(self, account: BrokerAccount) -> None:
        self.conn.execute(
            """
            INSERT INTO broker_account (
                provider,
                provider_account_id,
                provider_connection_id,
                account_name,
                account_type,
                currency,
                balance,
                portfolio_id,
                raw_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, now())
            ON CONFLICT(provider, provider_account_id) DO UPDATE SET
                provider_connection_id = excluded.provider_connection_id,
                account_name = excluded.account_name,
                account_type = excluded.account_type,
                currency = excluded.currency,
                balance = excluded.balance,
                portfolio_id = COALESCE(excluded.portfolio_id, broker_account.portfolio_id),
                raw_json = excluded.raw_json,
                updated_at = now()
            """,
            [
                account.provider,
                account.provider_account_id,
                account.provider_connection_id,
                account.account_name,
                account.account_type,
                account.currency,
                account.balance,
                account.portfolio_id,
                self._raw_json(account.raw_payload),
            ],
        )

    def map_account_to_portfolio(self, provider: str, provider_account_id: str, portfolio_id: int) -> None:
        self.conn.execute(
            """
            UPDATE broker_account
            SET portfolio_id = ?,
                updated_at = now()
            WHERE provider = ?
              AND provider_account_id = ?
            """,
            [portfolio_id, provider, provider_account_id],
        )

    def list_accounts(self, provider: str | None = None) -> list[BrokerAccount]:
        where = ""
        params: list[Any] = []
        if provider is not None:
            where = "WHERE provider = ?"
            params.append(provider)
        rows = self.conn.execute(
            f"""
            SELECT
                provider,
                provider_account_id,
                provider_connection_id,
                account_name,
                account_type,
                currency,
                balance,
                portfolio_id,
                raw_json
            FROM broker_account
            {where}
            ORDER BY account_name, provider_account_id
            """,
            params,
        ).fetchall()
        return [
            BrokerAccount(
                provider=row[0],
                provider_account_id=row[1],
                provider_connection_id=row[2],
                account_name=row[3],
                account_type=row[4],
                currency=row[5],
                balance=row[6],
                portfolio_id=row[7],
                raw_payload=_json_loads(row[8]),
            )
            for row in rows
        ]

    def upsert_position_snapshot(self, position: BrokerPosition) -> None:
        self.conn.execute(
            """
            INSERT INTO broker_position_snapshot (
                provider,
                provider_account_id,
                provider_position_id,
                as_of_date,
                asset_id,
                symbol,
                description,
                quantity,
                market_value,
                currency,
                raw_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
            ON CONFLICT(provider, provider_account_id, provider_position_id, as_of_date)
            DO UPDATE SET
                asset_id = excluded.asset_id,
                symbol = excluded.symbol,
                description = excluded.description,
                quantity = excluded.quantity,
                market_value = excluded.market_value,
                currency = excluded.currency,
                raw_json = excluded.raw_json,
                updated_at = now()
            """,
            [
                position.provider,
                position.provider_account_id,
                position.provider_position_id,
                position.as_of_date,
                position.asset_id,
                position.symbol,
                position.description,
                position.quantity,
                position.market_value,
                position.currency,
                self._raw_json(position.raw_payload),
            ],
        )

    def upsert_transaction(self, transaction: BrokerTransaction) -> None:
        self.conn.execute(
            """
            INSERT INTO broker_transaction (
                provider,
                provider_transaction_id,
                provider_account_id,
                trade_date,
                txn_type,
                asset_id,
                symbol,
                quantity,
                price,
                amount,
                currency,
                raw_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
            ON CONFLICT(provider, provider_transaction_id) DO UPDATE SET
                provider_account_id = excluded.provider_account_id,
                trade_date = excluded.trade_date,
                txn_type = excluded.txn_type,
                asset_id = excluded.asset_id,
                symbol = excluded.symbol,
                quantity = excluded.quantity,
                price = excluded.price,
                amount = excluded.amount,
                currency = excluded.currency,
                raw_json = excluded.raw_json,
                updated_at = now()
            """,
            [
                transaction.provider,
                transaction.provider_transaction_id,
                transaction.provider_account_id,
                transaction.trade_date,
                transaction.txn_type,
                transaction.asset_id,
                transaction.symbol,
                transaction.quantity,
                transaction.price,
                transaction.amount,
                transaction.currency,
                self._raw_json(transaction.raw_payload),
            ],
        )

    def create_sync_run(
        self,
        provider: str,
        connection_id: int | None = None,
        user_key: str | None = None,
    ) -> int:
        row = self.conn.execute("SELECT nextval('seq_broker_sync_run_id')").fetchone()
        sync_run_id = int(row[0])
        self.conn.execute(
            """
            INSERT INTO broker_sync_run(
                sync_run_id,
                provider,
                user_key,
                connection_id,
                status,
                started_at
            )
            VALUES (?, ?, ?, ?, 'running', ?)
            """,
            [sync_run_id, provider, user_key, connection_id, datetime.now()],
        )
        return sync_run_id

    def finish_sync_run(self, sync_run_id: int, result: BrokerSyncResult) -> None:
        self.conn.execute(
            """
            UPDATE broker_sync_run
            SET status = ?,
                completed_at = ?,
                accounts_seen = ?,
                positions_seen = ?,
                transactions_seen = ?,
                error_message = ?
            WHERE sync_run_id = ?
            """,
            [
                result.status,
                datetime.now(),
                result.accounts_seen,
                result.positions_seen,
                result.transactions_seen,
                result.error_message,
                sync_run_id,
            ],
        )


def _json_dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True)


def _json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {}
