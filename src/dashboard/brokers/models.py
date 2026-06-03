"""Broker sync models for read-only account linking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class BrokerUser:
    provider: str
    user_key: str
    provider_user_id: str
    user_secret: str
    status: str = "active"


@dataclass(frozen=True, slots=True)
class BrokerConnection:
    provider: str
    provider_connection_id: str
    institution_name: str
    status: str
    connection_id: int | None = None
    provider_user_id: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BrokerAccount:
    provider: str
    provider_account_id: str
    provider_connection_id: str
    account_name: str | None
    account_type: str | None
    currency: str | None
    balance: float | None
    portfolio_id: int | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BrokerPosition:
    provider: str
    provider_account_id: str
    provider_position_id: str
    symbol: str | None
    description: str | None
    quantity: float | None
    market_value: float | None
    currency: str | None
    as_of_date: date
    asset_id: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BrokerTransaction:
    provider: str
    provider_transaction_id: str
    provider_account_id: str
    txn_type: str
    trade_date: date
    symbol: str | None = None
    asset_id: str | None = None
    quantity: float | None = None
    price: float | None = None
    amount: float | None = None
    currency: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BrokerSyncResult:
    provider: str
    connection_id: int | None
    accounts_seen: int = 0
    positions_seen: int = 0
    transactions_seen: int = 0
    status: str = "done"
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class BrokerConnectionPortal:
    provider: str
    provider_user_id: str
    redirect_uri: str
    session_id: str | None = None


class SecretCipher(Protocol):
    name: str

    def encrypt(self, plaintext: str) -> str:
        """Return encrypted text safe to store in the database."""

    def decrypt(self, ciphertext: str) -> str:
        """Return decrypted text for provider calls."""


class BrokerProvider(Protocol):
    provider_name: str

    def create_connection_portal_url(self, user: BrokerUser) -> str:
        """Create a hosted provider portal URL for account linking."""

    def list_connections(self, user: BrokerUser) -> list[BrokerConnection]:
        """List provider connections for a linked user."""

    def list_accounts(self, user: BrokerUser) -> list[BrokerAccount]:
        """List provider accounts for a linked user."""

    def list_positions(self, user: BrokerUser, account: BrokerAccount) -> list[BrokerPosition]:
        """List latest positions for one provider account."""

    def list_transactions(
        self,
        user: BrokerUser,
        account: BrokerAccount,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[BrokerTransaction]:
        """List transactions for one provider account."""

    def disconnect(self, user: BrokerUser, connection: BrokerConnection) -> None:
        """Disconnect provider access where supported."""
