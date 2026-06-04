"""CLI parser and dispatch helpers for broker sync commands."""

from __future__ import annotations

import argparse
from typing import Any


def build_broker_parser(parser_cls: type[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    parser = parser_cls(
        prog="broker",
        add_help=True,
        description="Manage read-only broker account links.",
    )
    broker_subp = parser.add_subparsers(dest="broker_provider", required=True)

    _add_storage_parser(broker_subp)
    _add_snaptrade_parser(broker_subp)
    return parser


def handle_broker_command(access: Any, ns: argparse.Namespace) -> None:
    if ns.broker_provider == "storage":
        _handle_storage_command(access, ns)
        return
    if ns.broker_provider == "snaptrade":
        _handle_snaptrade_command(access, ns)
        return
    raise ValueError(f"Unsupported broker provider: {ns.broker_provider}")


def _add_storage_parser(subparsers) -> None:
    storage = subparsers.add_parser(
        "storage",
        add_help=True,
        description="Manage optional broker raw payload storage.",
    )
    storage_subp = storage.add_subparsers(dest="storage_command", required=True)
    storage_subp.add_parser("status", add_help=True)
    storage_subp.add_parser("enable-raw", add_help=True)
    storage_subp.add_parser("disable-raw", add_help=True)


def _add_snaptrade_parser(subparsers) -> None:
    snaptrade = subparsers.add_parser(
        "snaptrade",
        add_help=True,
        description="Manage SnapTrade read-only account linking.",
    )
    snaptrade_subp = snaptrade.add_subparsers(dest="broker_command", required=True)

    register = snaptrade_subp.add_parser(
        "register-user",
        add_help=True,
        description="Register a SnapTrade user and store the generated user secret.",
    )
    register.add_argument("user_key", help="Local immutable user key.")
    register.add_argument(
        "--provider-user-id",
        dest="provider_user_id",
        default=None,
        help="Optional SnapTrade userId. Defaults to user_key.",
    )

    portal = snaptrade_subp.add_parser(
        "portal",
        add_help=True,
        description="Create a hosted SnapTrade portal URL with read-only permissions.",
    )
    portal.add_argument("user_key", help="Local immutable user key.")
    portal.add_argument(
        "--broker",
        dest="broker",
        default=None,
        help="Optional SnapTrade broker slug, such as WEALTHSIMPLE or TD.",
    )
    portal.add_argument(
        "--custom-redirect",
        dest="custom_redirect",
        default=None,
        help="Optional URL SnapTrade should redirect to after linking.",
    )
    portal.add_argument(
        "--immediate-redirect",
        dest="immediate_redirect",
        action="store_true",
        help="Redirect immediately after the portal flow completes.",
    )
    portal.add_argument(
        "--register-if-missing",
        dest="register_if_missing",
        action="store_true",
        help="Register the SnapTrade user before creating the portal if needed.",
    )
    portal.add_argument(
        "--reconnect",
        dest="reconnect",
        default=None,
        help="Disabled SnapTrade connection id to repair through the portal.",
    )

    rotate = snaptrade_subp.add_parser(
        "rotate-secret",
        add_help=True,
        description="Rotate and store a SnapTrade user secret.",
    )
    rotate.add_argument("user_key")

    unlink = snaptrade_subp.add_parser(
        "unlink-user",
        add_help=True,
        description="Mark a SnapTrade user unlinked locally, optionally deleting provider data.",
    )
    unlink.add_argument("user_key")
    unlink.add_argument("--delete-provider-user", dest="delete_provider_user", action="store_true")

    disable = snaptrade_subp.add_parser(
        "disable-connection",
        add_help=True,
        description="Force-disable a SnapTrade connection for reconnect testing.",
    )
    disable.add_argument("user_key")
    disable.add_argument("provider_connection_id")

    smoke = snaptrade_subp.add_parser(
        "smoke-test",
        add_help=True,
        description="Verify SnapTrade credentials and optional stored user without syncing data.",
    )
    smoke.add_argument("user_key", nargs="?", default=None)

    sync = snaptrade_subp.add_parser(
        "sync",
        add_help=True,
        description="Sync linked SnapTrade connections, accounts, positions, and transactions.",
    )
    sync.add_argument("user_key", help="Local immutable user key.")
    sync.add_argument("--start-date", dest="start_date", default=None)
    sync.add_argument("--end-date", dest="end_date", default=None)

    sync_due = snaptrade_subp.add_parser(
        "sync-due",
        add_help=True,
        description="Sync SnapTrade users whose latest successful sync is stale.",
    )
    sync_due.add_argument("--max-users", dest="max_users", type=int, default=None)
    sync_due.add_argument("--min-age-hours", dest="min_age_hours", type=int, default=24)
    sync_due.add_argument("--force", dest="force", action="store_true")

    snaptrade_subp.add_parser(
        "accounts",
        add_help=True,
        description="List locally stored SnapTrade broker accounts.",
    )

    map_account = snaptrade_subp.add_parser(
        "map-account",
        add_help=True,
        description="Map a stored SnapTrade account to a local portfolio.",
    )
    map_account.add_argument("provider_account_id")
    map_account.add_argument("portfolio_id", type=int)

    import_txns = snaptrade_subp.add_parser(
        "import-transactions",
        add_help=True,
        description="Import mapped SnapTrade transactions into local portfolios.",
    )
    import_txns.add_argument("--portfolio-id", dest="portfolio_id", type=int, default=None)


def _handle_storage_command(access: Any, ns: argparse.Namespace) -> None:
    if ns.storage_command == "status":
        state = "enabled" if access.broker_raw_payload_storage_enabled() else "disabled"
        print(f"Broker raw payload storage is {state}.")
        return
    if ns.storage_command == "enable-raw":
        access.set_broker_raw_payload_storage_enabled(True)
        print("Broker raw payload storage enabled.")
        return
    if ns.storage_command == "disable-raw":
        access.set_broker_raw_payload_storage_enabled(False)
        print("Broker raw payload storage disabled.")
        return
    raise ValueError(f"Unsupported broker storage command: {ns.storage_command}")


def _handle_snaptrade_command(access: Any, ns: argparse.Namespace) -> None:
    command = ns.broker_command
    if command == "register-user":
        user = access.broker_register_snaptrade_user(
            ns.user_key,
            provider_user_id=ns.provider_user_id,
        )
        print(
            "Registered SnapTrade user "
            f"{user.provider_user_id} for local broker user {user.user_key}."
        )
        return

    if command == "portal":
        portal = access.broker_snaptrade_portal(
            ns.user_key,
            broker=ns.broker,
            custom_redirect=ns.custom_redirect,
            immediate_redirect=ns.immediate_redirect,
            register_if_missing=ns.register_if_missing,
            reconnect=ns.reconnect,
        )
        print("Open this SnapTrade read-only connection portal URL:")
        print(portal.redirect_uri)
        if portal.session_id:
            print(f"Session: {portal.session_id}")
        return

    if command == "rotate-secret":
        user = access.broker_snaptrade_rotate_secret(ns.user_key)
        print(f"Rotated SnapTrade user secret for {user.user_key}.")
        return

    if command == "unlink-user":
        access.broker_snaptrade_unlink_user(
            ns.user_key,
            delete_provider_user=ns.delete_provider_user,
        )
        print(f"Unlinked SnapTrade user {ns.user_key}.")
        return

    if command == "disable-connection":
        access.broker_snaptrade_disable_connection(ns.user_key, ns.provider_connection_id)
        print(f"Disabled SnapTrade connection {ns.provider_connection_id}.")
        return

    if command == "smoke-test":
        result = access.broker_snaptrade_smoke_test(ns.user_key)
        print(
            f"SnapTrade smoke test: configured={result.configured}, "
            f"api_online={result.api_online}, user_found={result.user_found}."
        )
        print(result.message)
        return

    if command == "sync":
        result = access.broker_snaptrade_sync(
            ns.user_key,
            start_date=ns.start_date,
            end_date=ns.end_date,
        )
        print(
            f"Broker sync saw {result.connections_seen} connection(s), "
            f"{result.accounts_seen} account(s), {result.positions_seen} position(s), "
            f"and {result.transactions_seen} transaction(s)."
        )
        if result.failed_connections:
            print(f"Failed connections: {result.failed_connections}.")
        return

    if command == "sync-due":
        result = access.broker_snaptrade_sync_due(
            max_users=ns.max_users,
            min_age_hours=ns.min_age_hours,
            force=ns.force,
        )
        print(
            f"Broker due sync checked {result.users_checked} user(s) "
            f"and synced {result.users_synced} user(s)."
        )
        print(
            f"Saw {result.accounts_seen} account(s), {result.positions_seen} position(s), "
            f"and {result.transactions_seen} transaction(s)."
        )
        if result.failed_connections:
            print(f"Failed connections: {result.failed_connections}.")
        return

    if command == "accounts":
        _print_broker_accounts(access.broker_accounts("snaptrade"))
        return

    if command == "map-account":
        access.broker_map_account(
            ns.provider_account_id,
            ns.portfolio_id,
            provider="snaptrade",
        )
        print(f"Mapped SnapTrade account {ns.provider_account_id} to portfolio {ns.portfolio_id}.")
        return

    if command == "import-transactions":
        result = access.broker_import_transactions(
            provider="snaptrade",
            portfolio_id=ns.portfolio_id,
        )
        print(f"Imported {result.imported_transactions} broker transaction(s) into local portfolios.")
        if result.skipped_transactions:
            print(f"Skipped transactions: {result.skipped_transactions}.")
        if result.batch_id is not None:
            print(f"Batch: {result.batch_id}.")
        return

    raise ValueError(f"Unsupported SnapTrade broker command: {command}")


def _print_broker_accounts(accounts) -> None:
    if not accounts:
        print("No broker accounts found.")
        return
    print("| provider | account_id | name | type | currency | balance | portfolio_id |")
    for account in accounts:
        print(
            f"| {account.provider} | {account.provider_account_id} | "
            f"{account.account_name or ''} | {account.account_type or ''} | "
            f"{account.currency or ''} | {account.balance if account.balance is not None else ''} | "
            f"{account.portfolio_id if account.portfolio_id is not None else ''} |"
        )
