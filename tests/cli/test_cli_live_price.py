from dashboard.models.cli_view import DashboardView


class FakeStreamingManager:
    def __init__(self):
        self.calls = []

    def run_live_price_stream(self, include_watchlist=False, enable_extended_hours=True):
        self.calls.append((include_watchlist, enable_extended_hours))


def test_live_price_stream_cli_dispatches_options(capsys):
    manager = FakeStreamingManager()
    view = DashboardView(manager)

    view.handle_input("live-price-stream --include-watchlist --no-extended-hours")

    assert manager.calls == [(True, False)]
    output = capsys.readouterr().out
    assert "Starting live price stream." in output
    assert "Watchlist streaming enabled." in output
    assert "Extended-hours streaming disabled." in output
