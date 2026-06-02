from __future__ import annotations

from dashboard.models.cli_view import DashboardView


class FakeManager:
    def __init__(self):
        self.calls = []

    def sentiment_refresh(self, target, source="all"):
        self.calls.append(("sentiment_refresh", target, source))
        return 2

    def run_sentiment_jobs(self, max_jobs=1):
        self.calls.append(("run_sentiment_jobs", max_jobs))
        return 1

    def sentiment_summary(self, ticker):
        self.calls.append(("sentiment_summary", ticker))
        return f"Ticker: {ticker}"

    def list_news_for_ticker(self, ticker, limit=10, days=30):
        self.calls.append(("list_news_for_ticker", ticker, limit, days))
        return []

    def list_social_for_ticker(self, ticker, limit=10, days=30):
        self.calls.append(("list_social_for_ticker", ticker, limit, days))
        return []

    def refresh_factor_snapshot(self, target):
        self.calls.append(("refresh_factor_snapshot", target))
        return 1

    def refresh_quant_rating(self, target):
        self.calls.append(("refresh_quant_rating", target))
        return 1

    def quant_summary(self, ticker):
        self.calls.append(("quant_summary", ticker))
        return f"Ticker: {ticker}"


def test_sentiment_cli_commands_dispatch_to_manager(capsys):
    manager = FakeManager()
    view = DashboardView(manager)

    view.handle_input("sentiment-refresh AMD --source reddit")
    view.handle_input("sentiment-run --max-jobs 3")
    view.handle_input("sentiment-summary AMD")
    view.handle_input("news-list AMD --limit 5 --days 7")
    view.handle_input("social-list AMD --limit 4 --days 2")
    view.handle_input("factor-refresh AMD")
    view.handle_input("quant-refresh AMD")
    view.handle_input("quant-summary AMD")

    assert manager.calls == [
        ("sentiment_refresh", "AMD", "reddit"),
        ("run_sentiment_jobs", 3),
        ("sentiment_summary", "AMD"),
        ("list_news_for_ticker", "AMD", 5, 7),
        ("list_social_for_ticker", "AMD", 4, 2),
        ("refresh_factor_snapshot", "AMD"),
        ("refresh_quant_rating", "AMD"),
        ("quant_summary", "AMD"),
    ]
    assert "Processed 1 sentiment job(s)." in capsys.readouterr().out

