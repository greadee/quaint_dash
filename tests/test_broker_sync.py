from __future__ import annotations

from datetime import date

from dashboard.brokers.models import (
    BrokerAccount,
    BrokerConnection,
    BrokerPosition,
    BrokerSyncResult,
    BrokerTransaction,
    BrokerUser,
)
from dashboard.brokers.repository import BrokerSyncRepository
from dashboard.brokers.secrets import LocalSecretCipher
from dashboard.db.db_conn import DB, init_db


def table_columns(conn, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()}


def test_init_db_creates_broker_sync_tables(tmp_path):
    db = DB(str(tmp_path / "broker_schema.db"))
    init_db(db)

    rows = db.conn.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'main'
        """
    ).fetchall()
    tables = {row[0] for row in rows}

    assert {
        "broker_user",
        "broker_connection",
        "broker_account",
        "broker_position_snapshot",
        "broker_transaction",
        "broker_sync_run",
    }.issubset(tables)
    assert "encrypted_user_secret" in table_columns(db.conn, "broker_user")
    assert "portfolio_id" in table_columns(db.conn, "broker_account")


def test_local_secret_cipher_round_trips_without_plaintext():
    cipher = LocalSecretCipher("test-key")

    encrypted = cipher.encrypt("provider-secret")

    assert encrypted != "provider-secret"
    assert cipher.decrypt(encrypted) == "provider-secret"


def test_broker_repository_persists_user_connection_account_and_sync_run(tmp_path):
    db = DB(str(tmp_path / "broker_repo.db"))
    init_db(db)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Broker')")
    repo = BrokerSyncRepository(db.conn)
    cipher = LocalSecretCipher("test-key")

    repo.upsert_broker_user(
        BrokerUser(
            provider="snaptrade",
            user_key="default",
            provider_user_id="snap-user-1",
            user_secret="snap-secret",
        ),
        cipher,
    )
    row = db.conn.execute("SELECT encrypted_user_secret FROM broker_user").fetchone()
    restored_user = repo.get_broker_user("snaptrade", "default", cipher)

    assert row[0] != "snap-secret"
    assert restored_user is not None
    assert restored_user.user_secret == "snap-secret"

    connection_id = repo.upsert_connection(
        BrokerConnection(
            provider="snaptrade",
            provider_connection_id="conn-1",
            provider_user_id="snap-user-1",
            institution_name="Wealthsimple",
            status="connected",
            raw_payload={"institution": "Wealthsimple"},
        )
    )
    repo.upsert_account(
        BrokerAccount(
            provider="snaptrade",
            provider_account_id="acct-1",
            provider_connection_id="conn-1",
            account_name="TFSA",
            account_type="registered",
            currency="CAD",
            balance=1000.0,
        )
    )
    repo.map_account_to_portfolio("snaptrade", "acct-1", 1)

    connections = repo.list_connections("snaptrade")
    accounts = repo.list_accounts("snaptrade")

    assert connections[0].connection_id == connection_id
    assert connections[0].raw_payload["institution"] == "Wealthsimple"
    assert accounts[0].portfolio_id == 1

    sync_run_id = repo.create_sync_run("snaptrade", connection_id)
    repo.finish_sync_run(
        sync_run_id,
        BrokerSyncResult(
            provider="snaptrade",
            connection_id=connection_id,
            accounts_seen=1,
            positions_seen=2,
            transactions_seen=3,
        ),
    )
    row = db.conn.execute(
        """
        SELECT status, accounts_seen, positions_seen, transactions_seen
        FROM broker_sync_run
        WHERE sync_run_id = ?
        """,
        [sync_run_id],
    ).fetchone()
    assert row == ("done", 1, 2, 3)


def test_fake_broker_provider_outputs_can_be_persisted(tmp_path):
    db = DB(str(tmp_path / "broker_fake_provider.db"))
    init_db(db)
    repo = BrokerSyncRepository(db.conn)
    provider = FakeBrokerProvider()
    user = BrokerUser("snaptrade", "default", "user-1", "secret")

    connection_id = repo.upsert_connection(provider.list_connections(user)[0])
    account = provider.list_accounts(user)[0]
    repo.upsert_account(account)
    for position in provider.list_positions(user, account):
        repo.upsert_position_snapshot(position)
    for transaction in provider.list_transactions(user, account):
        repo.upsert_transaction(transaction)

    assert connection_id == 1
    assert db.conn.execute("SELECT COUNT(*) FROM broker_account").fetchone()[0] == 1
    assert db.conn.execute("SELECT COUNT(*) FROM broker_position_snapshot").fetchone()[0] == 1
    assert db.conn.execute("SELECT COUNT(*) FROM broker_transaction").fetchone()[0] == 1


class FakeBrokerProvider:
    provider_name = "snaptrade"

    def create_connection_portal_url(self, user: BrokerUser) -> str:
        return f"https://connect.example.test/{user.provider_user_id}"

    def list_connections(self, user: BrokerUser) -> list[BrokerConnection]:
        return [
            BrokerConnection(
                provider=self.provider_name,
                provider_connection_id="conn-1",
                provider_user_id=user.provider_user_id,
                institution_name="TD Direct Investing",
                status="connected",
            )
        ]

    def list_accounts(self, user: BrokerUser) -> list[BrokerAccount]:
        return [
            BrokerAccount(
                provider=self.provider_name,
                provider_account_id="acct-1",
                provider_connection_id="conn-1",
                account_name="Margin",
                account_type="non_registered",
                currency="CAD",
                balance=5000.0,
            )
        ]

    def list_positions(self, user: BrokerUser, account: BrokerAccount) -> list[BrokerPosition]:
        return [
            BrokerPosition(
                provider=self.provider_name,
                provider_account_id=account.provider_account_id,
                provider_position_id="acct-1:AAPL",
                symbol="AAPL",
                description="Apple Inc.",
                quantity=2.0,
                market_value=400.0,
                currency="USD",
                as_of_date=date(2026, 1, 5),
            )
        ]

    def list_transactions(
        self,
        user: BrokerUser,
        account: BrokerAccount,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[BrokerTransaction]:
        return [
            BrokerTransaction(
                provider=self.provider_name,
                provider_transaction_id="txn-1",
                provider_account_id=account.provider_account_id,
                txn_type="buy",
                trade_date=date(2026, 1, 4),
                symbol="AAPL",
                quantity=2.0,
                price=200.0,
                amount=-400.0,
                currency="USD",
            )
        ]

    def disconnect(self, user: BrokerUser, connection: BrokerConnection) -> None:
        return None

