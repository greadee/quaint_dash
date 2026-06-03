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
from dashboard.brokers.snaptrade import SnapTradeConfig, SnapTradeProvider, compute_snaptrade_signature
from dashboard.db.db_conn import DB, init_db
from dashboard.models.cli_view import DashboardView
from dashboard.models.storage import DashboardManager


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


def test_snaptrade_signature_uses_canonical_payload_shape():
    signature = compute_snaptrade_signature(
        "/snapTrade/registerUser?clientId=PASSIVTEST&timestamp=1635790389",
        "consumer-secret",
        {"userId": "new_user_123"},
    )

    assert signature == "wUENeeVmQN4WyUeaYZ+3Hxt/mOmsegJ8mJGUPxcieFA="


def test_snaptrade_provider_registers_user_and_creates_read_only_portal():
    session = FakeSnapTradeSession(
        [
            {"userId": "local-user", "userSecret": "generated-secret"},
            {"redirectURI": "https://app.snaptrade.com/portal", "sessionId": "session-1"},
        ]
    )
    provider = SnapTradeProvider(
        SnapTradeConfig(
            client_id="client-id",
            consumer_key="consumer-key",
            base_url="https://api.test/api/v1",
        ),
        session=session,
        clock=lambda: 1_635_790_389,
    )

    user = provider.register_user("local-user")
    portal = provider.create_connection_portal(user, broker="WEALTHSIMPLE")

    assert user.provider_user_id == "local-user"
    assert user.user_secret == "generated-secret"
    assert portal.redirect_uri == "https://app.snaptrade.com/portal"
    assert len(session.calls) == 2
    register_call, portal_call = session.calls
    assert register_call["url"] == "https://api.test/api/v1/snapTrade/registerUser"
    assert register_call["json"] == {"userId": "local-user"}
    assert register_call["headers"]["Signature"]
    assert portal_call["url"] == "https://api.test/api/v1/snapTrade/login"
    assert portal_call["json"]["connectionType"] == "read"
    assert portal_call["json"]["broker"] == "WEALTHSIMPLE"
    assert ("userSecret", "generated-secret") in portal_call["params"]


def test_broker_cli_prints_snaptrade_read_only_portal(tmp_path, capsys):
    db = DB(str(tmp_path / "broker_cli.db"))
    init_db(db)
    manager = DashboardManager(db)
    view = DashboardView(manager)

    def fake_portal(
        user_key,
        broker=None,
        custom_redirect=None,
        immediate_redirect=False,
        register_if_missing=False,
    ):
        assert user_key == "default"
        assert broker == "WEALTHSIMPLE"
        assert register_if_missing is True
        return type(
            "Portal",
            (),
            {
                "redirect_uri": "https://app.snaptrade.com/portal",
                "session_id": "session-1",
            },
        )()

    manager.broker_snaptrade_portal = fake_portal

    view.handle_input("broker snaptrade portal default --broker WEALTHSIMPLE --register-if-missing")
    out = capsys.readouterr().out

    assert "read-only connection portal URL" in out
    assert "https://app.snaptrade.com/portal" in out
    assert "session-1" in out


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


class FakeSnapTradeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict:
        return self.payload


class FakeSnapTradeSession:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return FakeSnapTradeResponse(self.responses.pop(0))
