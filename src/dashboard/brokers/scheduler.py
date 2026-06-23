"""Broker sync scheduling helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from dashboard.brokers.models import BrokerProvider, SecretCipher
from dashboard.brokers.repository import BrokerSyncRepository
from dashboard.brokers.sync import BrokerSyncService, BrokerSyncSummary


@dataclass(frozen=True, slots=True)
class BrokerDueSyncResult:
    provider: str
    users_checked: int
    users_synced: int
    summaries: list[BrokerSyncSummary]

    @property
    def accounts_seen(self) -> int:
        return sum(summary.accounts_seen for summary in self.summaries)

    @property
    def positions_seen(self) -> int:
        return sum(summary.positions_seen for summary in self.summaries)

    @property
    def transactions_seen(self) -> int:
        return sum(summary.transactions_seen for summary in self.summaries)

    @property
    def failed_connections(self) -> int:
        return sum(summary.failed_connections for summary in self.summaries)


class BrokerSyncScheduler:
    def __init__(
        self,
        repo: BrokerSyncRepository,
        provider: BrokerProvider,
        cipher: SecretCipher,
        now_fn=datetime.now,
    ) -> None:
        self.repo = repo
        self.provider = provider
        self.cipher = cipher
        self.now_fn = now_fn

    def sync_due_users(
        self,
        max_users: int | None = None,
        min_age_hours: int = 1,
        force: bool = False,
    ) -> BrokerDueSyncResult:
        if force:
            users = self.repo.list_broker_users(self.provider.provider_name, self.cipher)
        else:
            stale_before = self.now_fn() - timedelta(hours=min_age_hours)
            users = self.repo.due_broker_users(
                self.provider.provider_name,
                self.cipher,
                stale_before,
            )

        selected = users if max_users is None else users[:max_users]
        service = BrokerSyncService(self.repo, self.provider, self.cipher)
        summaries = [service.sync_existing_user(user) for user in selected]
        return BrokerDueSyncResult(
            provider=self.provider.provider_name,
            users_checked=len(users),
            users_synced=len(summaries),
            summaries=summaries,
        )
