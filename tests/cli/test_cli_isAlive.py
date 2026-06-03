"""root/tests/
cli smoke test
"""

from dashboard.cli import cli_loop, run_startup_broker_sync

def test_cli_isAlive(monkeypatch, capsys):
    '''
    test_cli_isAlive: test that the CLI starts and exits properly.
    Uses monkeypatch to simulate user input, and capsys to capture stdout. 
    Verfifies that the startup banner and exit message are printed.
    '''
    inputs = iter(["exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    
    try:
        cli_loop()
    except SystemExit: # allow for reading sys.out after SystemExit
        pass

    out = capsys.readouterr().out

    assert "=== Dashboard ===" in out 
    assert "Goodbye." in out


def test_startup_broker_sync_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("BROKER_SYNC_ON_STARTUP", raising=False)
    manager = FakeBrokerManager()

    run_startup_broker_sync(manager)

    assert manager.calls == []


def test_startup_broker_sync_runs_when_enabled(monkeypatch, capsys):
    monkeypatch.setenv("BROKER_SYNC_ON_STARTUP", "true")
    monkeypatch.setenv("BROKER_SYNC_MAX_USERS", "2")
    monkeypatch.setenv("BROKER_SYNC_MIN_AGE_HOURS", "6")
    manager = FakeBrokerManager()

    run_startup_broker_sync(manager)
    out = capsys.readouterr().out

    assert manager.calls == [(2, 6)]
    assert "Broker sync scheduler: synced 1 user(s)" in out


class FakeBrokerManager:
    def __init__(self):
        self.calls = []

    def broker_snaptrade_sync_due(self, max_users=None, min_age_hours=24):
        self.calls.append((max_users, min_age_hours))
        return type(
            "DueSync",
            (),
            {
                "users_synced": 1,
                "accounts_seen": 2,
                "positions_seen": 3,
                "transactions_seen": 4,
            },
        )()
