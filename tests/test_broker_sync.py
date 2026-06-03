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
from dashboard.brokers.portfolio import BrokerPortfolioIntegrationService
from dashboard.brokers.repository import BrokerSyncRepository
from dashboard.brokers.scheduler import BrokerSyncScheduler
from dashboard.brokers.secrets import LocalSecretCipher
from dashboard.brokers.snaptrade import SnapTradeConfig, SnapTradeProvider, compute_snaptrade_signature
from dashboard.brokers.sync import BrokerSyncService
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
        "broker_portfolio_txn_map",
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

    sync_run_id = repo.create_sync_run("snaptrade", connection_id, user_key="default")
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
        SELECT status, user_key, accounts_seen, positions_seen, transactions_seen
        FROM broker_sync_run
        WHERE sync_run_id = ?
        """,
        [sync_run_id],
    ).fetchone()
    assert row == ("done", "default", 1, 2, 3)


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
    portal = provider.create_connection_portal(user, broker="WEALTHSIMPLE", reconnect="auth-1")

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
    assert portal_call["json"]["reconnect"] == "auth-1"
    assert ("userSecret", "generated-secret") in portal_call["params"]


def test_snaptrade_provider_rotates_secret_deletes_user_and_disables_connection():
    session = FakeSnapTradeSession(
        [
            {"userSecret": "new-secret"},
            {"status": "deleted", "userId": "user-1"},
            {"detail": "Connection disabled"},
        ]
    )
    provider = SnapTradeProvider(
        SnapTradeConfig("client-id", "consumer-key", base_url="https://api.test/api/v1"),
        session=session,
        clock=lambda: 1_635_790_389,
    )
    user = BrokerUser("snaptrade", "default", "user-1", "old-secret")
    connection = BrokerConnection("snaptrade", "auth-1", "Wealthsimple", "connected")

    rotated = provider.rotate_user_secret(user)
    deleted = provider.delete_user(user)
    provider.disconnect(user, connection)

    assert rotated.user_secret == "new-secret"
    assert deleted["status"] == "deleted"
    assert session.calls[0]["url"] == "https://api.test/api/v1/snapTrade/resetUserSecret"
    assert session.calls[1]["url"] == "https://api.test/api/v1/snapTrade/deleteUser"
    assert session.calls[2]["url"] == "https://api.test/api/v1/authorizations/auth-1/disable"


def test_snaptrade_provider_maps_connections_accounts_positions_and_transactions():
    session = FakeSnapTradeSession(
        [
            [
                {
                    "id": "auth-1",
                    "name": "Connection-1",
                    "type": "read",
                    "disabled": False,
                    "brokerage": {"display_name": "Wealthsimple"},
                }
            ],
            [
                {
                    "id": "acct-1",
                    "name": "TFSA",
                    "type": "registered",
                    "balance": {"total": 1234.5, "currency": "CAD"},
                }
            ],
            [
                {
                    "symbol": {"symbol": "AAPL", "description": "Apple Inc."},
                    "units": 2,
                    "price": 400,
                    "currency": "USD",
                    "last_updated": "2026-01-05T12:00:00Z",
                }
            ],
            [
                {
                    "id": "act-1",
                    "type": "BUY",
                    "trade_date": "2026-01-04",
                    "symbol": {"symbol": "AAPL"},
                    "units": 2,
                    "price": 200,
                    "amount": -400,
                    "currency": "USD",
                }
            ],
        ]
    )
    provider = SnapTradeProvider(
        SnapTradeConfig("client-id", "consumer-key", base_url="https://api.test/api/v1"),
        session=session,
        clock=lambda: 1_635_790_389,
    )
    user = BrokerUser("snaptrade", "default", "user-1", "secret")

    connection = provider.list_connections(user)[0]
    account = provider.list_accounts(user, connection)[0]
    position = provider.list_positions(user, account)[0]
    transaction = provider.list_transactions(user, account, date(2026, 1, 1), date(2026, 1, 5))[0]

    assert connection.provider_connection_id == "auth-1"
    assert connection.institution_name == "Wealthsimple"
    assert account.provider_account_id == "acct-1"
    assert account.balance == 1234.5
    assert position.symbol == "AAPL"
    assert position.as_of_date == date(2026, 1, 5)
    assert transaction.provider_transaction_id == "act-1"
    assert transaction.trade_date == date(2026, 1, 4)
    activities_call = session.calls[-1]
    assert ("startDate", "2026-01-01") in activities_call["params"]
    assert ("endDate", "2026-01-05") in activities_call["params"]


def test_broker_sync_service_persists_provider_data_and_sync_run(tmp_path):
    db = DB(str(tmp_path / "broker_sync_service.db"))
    init_db(db)
    repo = BrokerSyncRepository(db.conn)
    cipher = LocalSecretCipher("test-key")
    repo.upsert_broker_user(
        BrokerUser("snaptrade", "default", "user-1", "secret"),
        cipher,
    )
    service = BrokerSyncService(repo, FakeBrokerProvider(), cipher)

    result = service.sync_user("default", start_date=date(2026, 1, 1), end_date=date(2026, 1, 5))

    assert result.connections_seen == 1
    assert result.accounts_seen == 1
    assert result.positions_seen == 1
    assert result.transactions_seen == 1
    assert result.failed_connections == 0
    assert db.conn.execute("SELECT COUNT(*) FROM broker_connection").fetchone()[0] == 1
    assert db.conn.execute("SELECT COUNT(*) FROM broker_account").fetchone()[0] == 1
    assert db.conn.execute("SELECT COUNT(*) FROM broker_position_snapshot").fetchone()[0] == 1
    assert db.conn.execute("SELECT COUNT(*) FROM broker_transaction").fetchone()[0] == 1
    assert db.conn.execute("SELECT status FROM broker_sync_run").fetchone()[0] == "done"
    assert db.conn.execute("SELECT user_key FROM broker_sync_run").fetchone()[0] == "default"


def test_broker_sync_scheduler_syncs_due_users_once_per_day(tmp_path):
    db = DB(str(tmp_path / "broker_scheduler.db"))
    init_db(db)
    repo = BrokerSyncRepository(db.conn)
    cipher = LocalSecretCipher("test-key")
    repo.upsert_broker_user(
        BrokerUser("snaptrade", "default", "user-1", "secret"),
        cipher,
    )
    scheduler = BrokerSyncScheduler(repo, FakeBrokerProvider(), cipher)

    first = scheduler.sync_due_users()
    second = scheduler.sync_due_users()

    assert first.users_checked == 1
    assert first.users_synced == 1
    assert second.users_checked == 0
    assert second.users_synced == 0
    assert db.conn.execute("SELECT COUNT(*) FROM broker_sync_run").fetchone()[0] == 1


def test_broker_sync_scheduler_force_resyncs_active_users(tmp_path):
    db = DB(str(tmp_path / "broker_scheduler_force.db"))
    init_db(db)
    repo = BrokerSyncRepository(db.conn)
    cipher = LocalSecretCipher("test-key")
    repo.upsert_broker_user(
        BrokerUser("snaptrade", "default", "user-1", "secret"),
        cipher,
    )
    scheduler = BrokerSyncScheduler(repo, FakeBrokerProvider(), cipher)
    scheduler.sync_due_users()

    forced = scheduler.sync_due_users(force=True)

    assert forced.users_checked == 1
    assert forced.users_synced == 1
    assert db.conn.execute("SELECT COUNT(*) FROM broker_sync_run").fetchone()[0] == 2


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
        reconnect=None,
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


def test_broker_manager_rotates_and_unlinks_snaptrade_user(tmp_path, monkeypatch):
    db = DB(str(tmp_path / "broker_lifecycle.db"))
    init_db(db)
    repo = BrokerSyncRepository(db.conn)
    cipher = LocalSecretCipher("test-key")
    repo.upsert_broker_user(
        BrokerUser("snaptrade", "default", "user-1", "old-secret"),
        cipher,
    )
    manager = DashboardManager(db)
    monkeypatch.setattr(manager, "_broker_secret_cipher", lambda: cipher)
    monkeypatch.setattr(
        manager,
        "_snaptrade_config",
        lambda: SnapTradeConfig("client-id", "consumer-key", base_url="https://api.test/api/v1"),
    )
    session = FakeSnapTradeSession(
        [
            {"userSecret": "new-secret"},
            {"status": "deleted", "userId": "user-1"},
        ]
    )
    monkeypatch.setattr("dashboard.brokers.snaptrade.requests.Session", lambda: session)

    rotated = manager.broker_snaptrade_rotate_secret("default")
    manager.broker_snaptrade_unlink_user("default", delete_provider_user=True)
    restored = repo.get_broker_user("snaptrade", "default", cipher)

    assert rotated.user_secret == "new-secret"
    assert restored is not None
    assert restored.status == "unlinked"
    assert restored.user_secret == "new-secret"


def test_broker_cli_lifecycle_commands(tmp_path, capsys):
    db = DB(str(tmp_path / "broker_cli_lifecycle.db"))
    init_db(db)
    manager = DashboardManager(db)
    view = DashboardView(manager)
    calls = []

    manager.broker_snaptrade_rotate_secret = lambda user_key: type(
        "User", (), {"user_key": user_key}
    )()
    manager.broker_snaptrade_unlink_user = lambda user_key, delete_provider_user=False: calls.append(
        ("unlink", user_key, delete_provider_user)
    )
    manager.broker_snaptrade_disable_connection = lambda user_key, provider_connection_id: calls.append(
        ("disable", user_key, provider_connection_id)
    )

    view.handle_input("broker snaptrade rotate-secret default")
    view.handle_input("broker snaptrade unlink-user default --delete-provider-user")
    view.handle_input("broker snaptrade disable-connection default auth-1")
    out = capsys.readouterr().out

    assert "Rotated SnapTrade user secret for default." in out
    assert "Unlinked SnapTrade user default." in out
    assert "Disabled SnapTrade connection auth-1." in out
    assert ("unlink", "default", True) in calls
    assert ("disable", "default", "auth-1") in calls


def test_broker_cli_lists_and_maps_accounts(tmp_path, capsys):
    db = DB(str(tmp_path / "broker_cli_accounts.db"))
    init_db(db)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Broker')")
    repo = BrokerSyncRepository(db.conn)
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
    manager = DashboardManager(db)
    view = DashboardView(manager)

    view.handle_input("broker snaptrade accounts")
    out = capsys.readouterr().out
    assert "acct-1" in out
    assert "TFSA" in out

    view.handle_input("broker snaptrade map-account acct-1 1")
    out = capsys.readouterr().out
    assert "Mapped SnapTrade account acct-1 to portfolio 1." in out
    assert repo.list_accounts("snaptrade")[0].portfolio_id == 1


def test_broker_portfolio_integration_imports_mapped_transactions_idempotently(tmp_path):
    db = DB(str(tmp_path / "broker_portfolio_import.db"))
    init_db(db)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Broker')")
    repo = BrokerSyncRepository(db.conn)
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
    repo.upsert_transaction(
        BrokerTransaction(
            provider="snaptrade",
            provider_transaction_id="buy-1",
            provider_account_id="acct-1",
            txn_type="BUY",
            trade_date=date(2026, 1, 4),
            symbol="AAPL",
            quantity=2.0,
            price=200.0,
            amount=-400.0,
            currency="USD",
        )
    )

    service = BrokerPortfolioIntegrationService(db.conn)
    unmapped = service.import_mapped_transactions()
    repo.map_account_to_portfolio("snaptrade", "acct-1", 1)
    first = service.import_mapped_transactions()
    second = service.import_mapped_transactions()

    assert unmapped.imported_transactions == 0
    assert first.imported_transactions == 1
    assert first.batch_id is not None
    assert second.imported_transactions == 0
    assert db.conn.execute("SELECT COUNT(*) FROM txn").fetchone()[0] == 1
    assert db.conn.execute("SELECT COUNT(*) FROM broker_portfolio_txn_map").fetchone()[0] == 1
    txn_row = db.conn.execute(
        "SELECT portfolio_id, txn_type, asset_id, qty, price, ccy, cash_amt FROM txn"
    ).fetchone()
    assert txn_row == (1, "buy", "AAPL", 2.0, 200.0, "USD", None)
    position_row = db.conn.execute(
        "SELECT portfolio_id, asset_id, qty, book_cost FROM position"
    ).fetchone()
    assert position_row == (1, "AAPL", 2.0, 400.0)


def test_broker_portfolio_integration_normalizes_sells_and_skips_bad_asset_rows(tmp_path):
    db = DB(str(tmp_path / "broker_portfolio_sell.db"))
    init_db(db)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Broker')")
    repo = BrokerSyncRepository(db.conn)
    repo.upsert_account(
        BrokerAccount(
            provider="snaptrade",
            provider_account_id="acct-1",
            provider_connection_id="conn-1",
            account_name="Margin",
            account_type="non_registered",
            currency="CAD",
            balance=1000.0,
            portfolio_id=1,
        )
    )
    repo.upsert_transaction(
        BrokerTransaction(
            provider="snaptrade",
            provider_transaction_id="sell-1",
            provider_account_id="acct-1",
            txn_type="SELL",
            trade_date=date(2026, 1, 4),
            symbol="AAPL",
            quantity=1.0,
            price=220.0,
            amount=220.0,
            currency="USD",
        )
    )
    repo.upsert_transaction(
        BrokerTransaction(
            provider="snaptrade",
            provider_transaction_id="bad-1",
            provider_account_id="acct-1",
            txn_type="BUY",
            trade_date=date(2026, 1, 4),
            quantity=1.0,
            price=100.0,
            currency="USD",
        )
    )

    result = BrokerPortfolioIntegrationService(db.conn).import_mapped_transactions()

    assert result.imported_transactions == 1
    assert result.skipped_transactions == 1
    row = db.conn.execute("SELECT txn_type, asset_id, qty, price FROM txn").fetchone()
    assert row == ("sell", "AAPL", -1.0, 220.0)


def test_broker_cli_imports_mapped_transactions(tmp_path, capsys):
    db = DB(str(tmp_path / "broker_cli_import.db"))
    init_db(db)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Broker')")
    repo = BrokerSyncRepository(db.conn)
    repo.upsert_account(
        BrokerAccount(
            provider="snaptrade",
            provider_account_id="acct-1",
            provider_connection_id="conn-1",
            account_name="TFSA",
            account_type="registered",
            currency="CAD",
            balance=1000.0,
            portfolio_id=1,
        )
    )
    repo.upsert_transaction(
        BrokerTransaction(
            provider="snaptrade",
            provider_transaction_id="buy-1",
            provider_account_id="acct-1",
            txn_type="BUY",
            trade_date=date(2026, 1, 4),
            symbol="AAPL",
            quantity=2.0,
            price=200.0,
            amount=-400.0,
            currency="USD",
        )
    )
    view = DashboardView(DashboardManager(db))

    view.handle_input("broker snaptrade import-transactions --portfolio-id 1")
    out = capsys.readouterr().out

    assert "Imported 1 broker transaction(s)" in out
    assert db.conn.execute("SELECT COUNT(*) FROM txn").fetchone()[0] == 1


def test_broker_cli_runs_due_sync(tmp_path, capsys):
    db = DB(str(tmp_path / "broker_cli_due_sync.db"))
    init_db(db)
    manager = DashboardManager(db)
    view = DashboardView(manager)

    def fake_sync_due(max_users=None, min_age_hours=24, force=False):
        assert max_users == 2
        assert min_age_hours == 1
        assert force is True
        return type(
            "DueSync",
            (),
            {
                "users_checked": 3,
                "users_synced": 2,
                "accounts_seen": 4,
                "positions_seen": 5,
                "transactions_seen": 6,
                "failed_connections": 0,
            },
        )()

    manager.broker_snaptrade_sync_due = fake_sync_due

    view.handle_input("broker snaptrade sync-due --max-users 2 --min-age-hours 1 --force")
    out = capsys.readouterr().out

    assert "checked 3 user(s) and synced 2 user(s)" in out
    assert "Saw 4 account(s), 5 position(s), and 6 transaction(s)." in out


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

    def list_accounts(
        self,
        user: BrokerUser,
        connection: BrokerConnection | None = None,
    ) -> list[BrokerAccount]:
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
    def __init__(self, payload, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self.payload


class FakeSnapTradeSession:
    def __init__(self, responses: list) -> None:
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
