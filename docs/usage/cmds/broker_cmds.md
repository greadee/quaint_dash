# Broker Commands

Broker commands are available from the dashboard view. Phase 4 broker sync is read-only and currently uses SnapTrade.

## Environment

Broker linking requires SnapTrade credentials and a local encryption key:

```
SNAPTRADE_CLIENT_ID=<client id>
SNAPTRADE_CONSUMER_KEY=<consumer key>
QUAINT_BROKER_SECRET_KEY=<local encryption key>
```

Optional:

```
SNAPTRADE_BASE_URL=https://api.snaptrade.com/api/v1
SNAPTRADE_TIMEOUT_SECONDS=20
SNAPTRADE_ACTIVITY_PAGE_LIMIT=1000
BROKER_SYNC_ON_STARTUP=false
BROKER_SYNC_MAX_USERS=
BROKER_SYNC_MIN_AGE_HOURS=24
```

When `BROKER_SYNC_ON_STARTUP=true`, dashboard startup runs `broker snaptrade sync-due` behavior automatically. This refreshes provider-side broker data only; it does not import transactions into portfolios.

## Broker Storage

```
broker storage status
broker storage enable-raw
broker storage disable-raw
```

Controls whether raw provider payload JSON is retained in broker sync tables.

- Raw payload storage is enabled by default.
- Disabling raw storage keeps normalized broker records needed for sync, mapping, and imports.
- Disabling raw storage does not delete previously stored raw payloads.

## Register User

```
broker snaptrade register-user <user-key> [--provider-user-id id]
```

Registers a SnapTrade user and stores the generated user secret locally in encrypted form.

- `user-key` should be stable and immutable.
- `--provider-user-id` can override the SnapTrade `userId`; when omitted, `user-key` is used.

## Smoke Test Credentials

```
broker snaptrade smoke-test [user-key]
```

Checks whether SnapTrade credentials can reach the API status endpoint. When `user-key` is provided, also checks whether that local broker user exists.

This command does not open a portal, sync data, map accounts, or import transactions.

## Create Read-Only Portal URL

```
broker snaptrade portal <user-key> [--broker slug] [--custom-redirect url] [--immediate-redirect] [--register-if-missing] [--reconnect connection-id]
```

Creates a SnapTrade hosted connection portal URL with read-only permissions.

- `--broker` optionally directs the portal to a specific broker slug.
- `--reconnect` opens the portal in repair mode for a disabled connection.
- `--register-if-missing` registers the SnapTrade user before creating the portal if no stored user exists.
- The application does not collect broker credentials.
- The application does not request trading permissions.

## Rotate User Secret

```
broker snaptrade rotate-secret <user-key>
```

Rotates the SnapTrade user secret and stores the replacement locally in encrypted form.

## Unlink User

```
broker snaptrade unlink-user <user-key> [--delete-provider-user]
```

Marks a SnapTrade user as unlinked locally. With `--delete-provider-user`, the command also requests provider-side user deletion.

## Disable Connection

```
broker snaptrade disable-connection <user-key> <connection-id>
```

Force-disables a SnapTrade connection for reconnect testing, then marks the local connection disabled.

## Sync Broker Data

```
broker snaptrade sync <user-key> [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
```

Fetches and stores read-only broker data:

- connections
- accounts
- position snapshots
- account activities/transactions
- sync run status

Account activities are fetched page by page so large accounts are not limited to the first provider response.

This does not import anything into local portfolios.

## Sync Due Broker Users

```
broker snaptrade sync-due [--max-users n] [--min-age-hours hours] [--force]
```

Syncs active SnapTrade users whose latest successful sync is older than the configured freshness window.

- Default freshness window is 24 hours.
- `--force` syncs active users even if they are not stale.
- `--max-users` caps the number of due users synced in one run.
- This stores provider-side data only; it does not import transactions into local portfolios.

## List Broker Accounts

```
broker snaptrade accounts
```

Lists locally stored broker accounts and their current portfolio mapping.

## Map Account To Portfolio

```
broker snaptrade map-account <account-id> <portfolio-id>
```

Maps a synced broker account to an existing local portfolio.

## Import Mapped Transactions

```
broker snaptrade import-transactions [--portfolio-id id]
```

Imports transactions from mapped broker accounts into local portfolios.

- Unmapped accounts are ignored.
- Re-running the command is idempotent.
- Imported rows are linked through `broker_portfolio_txn_map`.
- Imported broker batches use `broker-sync` as their batch type.
