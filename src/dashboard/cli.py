"""Application entry point for the interactive dashboard CLI."""
import os

from dotenv import load_dotenv

from dashboard.db.db_conn import DB, init_db
from dashboard.models.storage import DashboardManager
from dashboard.models.cli_view import View, DashboardView


def run_startup_broker_sync(manager: DashboardManager) -> None:
    """Optionally refresh stale broker data during CLI startup."""
    load_dotenv()
    if os.getenv("BROKER_SYNC_ON_STARTUP", "").lower() not in {"1", "true", "yes", "on"}:
        return
    max_users = _int_env("BROKER_SYNC_MAX_USERS")
    min_age_hours = _int_env("BROKER_SYNC_MIN_AGE_HOURS", 24) or 24
    result = manager.broker_snaptrade_sync_due(
        max_users=max_users,
        min_age_hours=min_age_hours,
    )
    if result.users_synced:
        print(
            f"Broker sync scheduler: synced {result.users_synced} user(s), "
            f"saw {result.accounts_seen} account(s), {result.positions_seen} position(s), "
            f"and {result.transactions_seen} transaction(s)."
        )


def _int_env(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def cli_loop():
    """Start the dashboard, run startup maintenance, then enter the view loop."""
    db = DB("data/persistent_db.db")
    init_db(db)
    manager = DashboardManager(db)

    # Startup maintenance is best-effort: failed refreshes should not block the CLI.
    try:
        n = manager.refresh_due_asset_metadata(max_assets=5)
        if n:
            print(f"Auto-refreshed metadata for {n} asset(s).")
    except Exception as e:
        print(f"Metadata scheduler skipped: {e}")

    try:
        enqueued = manager.schedule_due_price_history_backfills(max_assets=3, years=10)
        processed = manager.run_price_history_backfill_jobs(max_jobs=1)
        if enqueued or processed:
            print(f"Price history scheduler: enqueued {enqueued}, processed {processed}.")
    except Exception as e:
        print(f"Price history scheduler skipped: {e}")

    try:
        n = manager.refresh_trading_calendar(market_code="all")
        if n:
            print(f"Trading calendar scheduler: refreshed {n} day(s).")
    except Exception as e:
        print(f"Trading calendar scheduler skipped: {e}")

    try:
        run_startup_broker_sync(manager)
    except Exception as e:
        print(f"Broker sync scheduler skipped: {e}")

    view: View = DashboardView(manager)

    while True:
        view.default_display()
        line = input(view.prompt_input())
        if not line:
            continue
        try:
            next_view = view.handle_input(line)
        except Exception as e:
            print(e)
            next_view = view

        if isinstance(next_view, View):
            view = next_view


def main():
    cli_loop()
