"""Broker account sync orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from dashboard.brokers.models import (
    BrokerProvider,
    BrokerSyncResult,
    BrokerUser,
    SecretCipher,
)
from dashboard.brokers.repository import BrokerSyncRepository


@dataclass(frozen=True, slots=True)
class BrokerSyncSummary:
    provider: str
    user_key: str
    connections_seen: int
    accounts_seen: int
    positions_seen: int
    transactions_seen: int
    failed_connections: int = 0


class BrokerSyncService:
    def __init__(
        self,
        repo: BrokerSyncRepository,
        provider: BrokerProvider,
        cipher: SecretCipher,
    ) -> None:
        self.repo = repo
        self.provider = provider
        self.cipher = cipher

    def sync_user(
        self,
        user_key: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> BrokerSyncSummary:
        user = self.repo.get_broker_user(self.provider.provider_name, user_key, self.cipher)
        if user is None:
            raise ValueError(f"No broker user found for {self.provider.provider_name}:{user_key}.")
        return self.sync_existing_user(user, start_date=start_date, end_date=end_date)

    def sync_existing_user(
        self,
        user: BrokerUser,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> BrokerSyncSummary:
        connections = self.provider.list_connections(user)
        accounts_seen = 0
        positions_seen = 0
        transactions_seen = 0
        failed_connections = 0

        for connection in connections:
            connection_id = self.repo.upsert_connection(connection)
            sync_run_id = self.repo.create_sync_run(self.provider.provider_name, connection_id)
            run_accounts = 0
            run_positions = 0
            run_transactions = 0
            try:
                accounts = self.provider.list_accounts(user, connection)
                for account in accounts:
                    self.repo.upsert_account(account)
                    run_accounts += 1
                    for position in self.provider.list_positions(user, account):
                        self.repo.upsert_position_snapshot(position)
                        run_positions += 1
                    for transaction in self.provider.list_transactions(
                        user,
                        account,
                        start_date=start_date,
                        end_date=end_date,
                    ):
                        self.repo.upsert_transaction(transaction)
                        run_transactions += 1
                self.repo.finish_sync_run(
                    sync_run_id,
                    BrokerSyncResult(
                        provider=self.provider.provider_name,
                        connection_id=connection_id,
                        accounts_seen=run_accounts,
                        positions_seen=run_positions,
                        transactions_seen=run_transactions,
                    ),
                )
            except Exception as exc:
                failed_connections += 1
                self.repo.finish_sync_run(
                    sync_run_id,
                    BrokerSyncResult(
                        provider=self.provider.provider_name,
                        connection_id=connection_id,
                        accounts_seen=run_accounts,
                        positions_seen=run_positions,
                        transactions_seen=run_transactions,
                        status="failed",
                        error_message=str(exc),
                    ),
                )
                continue

            accounts_seen += run_accounts
            positions_seen += run_positions
            transactions_seen += run_transactions

        return BrokerSyncSummary(
            provider=self.provider.provider_name,
            user_key=user.user_key,
            connections_seen=len(connections),
            accounts_seen=accounts_seen,
            positions_seen=positions_seen,
            transactions_seen=transactions_seen,
            failed_connections=failed_connections,
        )
