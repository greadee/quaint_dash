# Phase 4 - Broker Sync

## ADR-068: Read-Only Broker Sync Through SnapTrade

**Decision:** Phase 4 broker connectivity will use SnapTrade first, with read-only account linking only.

**Context:**
The application needs broker data from Wealthsimple and TD Direct Investing without becoming a trading surface. The user should link accounts through a hosted provider portal instead of entering broker credentials into this application.

SnapTrade's connection portal endpoint accepts a `connectionType` request body field. The SnapTrade documentation defines `read` as data access only and separates that from trading access options: https://docs.snaptrade.com/reference/Authentication/Authentication_loginSnapTradeUser

SnapTrade also documents the hosted connection portal flow as the way for an application to send a user to SnapTrade to connect a brokerage account: https://docs.snaptrade.com/docs/implement-connection-portal

**Rationale:**
- Keeps brokerage credential handling out of this application.
- Supports Wealthsimple through SnapTrade's brokerage integration surface: https://snaptrade.com/brokerage-integrations/wealthsimple-api
- Gives a provider-neutral path for TD Direct Investing and other brokers when available through SnapTrade's supported brokerage catalog.
- Keeps Phase 4 aligned with the product requirement that no trading functionality be implemented.
- Avoids Plaid-first assumptions because Canadian self-directed investing coverage is the primary need.

**Implementation Notes:**
- `dashboard.brokers.snaptrade.SnapTradeProvider` sends `connectionType: "read"` when creating a portal URL.
- The CLI command is:
  - `broker snaptrade portal <user-key> [--broker slug] [--register-if-missing]`
- The broker slug is optional so SnapTrade's portal can show the provider selection UI when no slug is passed.
- No order preview, order placement, cancellation, replacement, or trading endpoint is implemented.

## ADR-069: Immutable Broker Users and Secret Storage

**Decision:** Broker sync uses a local immutable user key mapped to SnapTrade's `userId` and encrypted SnapTrade `userSecret`.

**Context:**
SnapTrade's register-user endpoint creates a user under the partner client ID and returns a `userSecret`. SnapTrade states that the partner chooses the user ID, recommends it be unique and immutable, and says the generated user secret must be stored securely: https://docs.snaptrade.com/reference/Authentication/Authentication_registerSnapTradeUser

Most SnapTrade user-level account operations require both `userId` and `userSecret`, including connection listing and account data access. SnapTrade's docs repeat that the user secret should be stored securely and rotated if compromised: https://docs.snaptrade.com/reference/Connections/Connections_listBrokerageAuthorizations

**Rationale:**
- Immutable local keys avoid coupling users to mutable fields such as email addresses.
- Encrypted storage lets the CLI reuse SnapTrade user credentials without prompting the user again.
- The secret abstraction keeps local development encryption replaceable by OS keyring or KMS later.
- Explicit environment configuration prevents silently encrypting broker secrets with a hardcoded default.

**Implementation Notes:**
- Broker users are stored in `broker_user`.
- SnapTrade user secrets are encrypted through `SecretCipher`.
- Real CLI use requires `QUAINT_BROKER_SECRET_KEY`.
- SnapTrade API credentials are read from:
  - `SNAPTRADE_CLIENT_ID`
  - `SNAPTRADE_CONSUMER_KEY`
  - optional `SNAPTRADE_BASE_URL`
  - optional `SNAPTRADE_TIMEOUT_SECONDS`
- The local cipher is intentionally scoped behind `SecretCipher` so it can be replaced later.

## ADR-069A: Broker Lifecycle Commands

**Decision:** Phase 4 supports lifecycle management for reconnecting disabled connections, rotating SnapTrade user secrets, locally unlinking broker users, optionally deleting provider users, and force-disabling test connections.

**Context:**
SnapTrade's connection portal accepts a `reconnect` parameter for repairing disabled connections: https://docs.snaptrade.com/reference/Authentication/Authentication_loginSnapTradeUser

SnapTrade documents user-secret rotation and warns that a newly returned secret must be saved because the old one will stop working: https://docs.snaptrade.com/reference/Authentication/Authentication_resetSnapTradeUserSecret

SnapTrade also documents provider-side user deletion as an irreversible asynchronous operation that deletes the registered user and associated data: https://docs.snaptrade.com/reference/Authentication/Authentication_deleteSnapTradeUser

SnapTrade's force-disable connection endpoint is documented for reconnect-flow testing and is not intended for normal production use: https://docs.snaptrade.com/reference/Connections/Connections_disableBrokerageAuthorization

**Rationale:**
- Users need a repair path when a broker authorization becomes disabled.
- Secret rotation is necessary if a generated SnapTrade user secret is compromised.
- Local unlinking lets the application stop using a broker user without erasing local audit history.
- Provider deletion is explicit because it is irreversible.
- Force-disable is exposed as an explicit command for testing reconnect behavior.

**Implementation Notes:**
- `broker snaptrade portal <user-key> --reconnect <connection-id>` opens a read-only repair portal.
- `broker snaptrade rotate-secret <user-key>` rotates and stores the generated user secret.
- `broker snaptrade unlink-user <user-key> [--delete-provider-user]` marks the local broker user unlinked and can request provider deletion.
- `broker snaptrade disable-connection <user-key> <connection-id>` force-disables a connection for test/reconnect flows.
- Local user and connection rows are status-updated rather than deleted.

## ADR-070: Direct SnapTrade REST Client With Request Signatures

**Decision:** Phase 4 uses a small direct REST client instead of adding the SnapTrade SDK.

**Context:**
The project already depends on `requests`, and the needed Phase 4 surface is narrow:
- register user
- create read-only connection portal URL
- list connections
- list accounts
- list positions
- list account activities

SnapTrade documents direct API request signing with `clientId`, Unix `timestamp`, and a `Signature` header. The signature payload contains `content`, `path`, and `query`, then uses canonical JSON, HMAC-SHA256 with `consumerKey`, and base64 encoding: https://docs.snaptrade.com/docs/request-signatures

**Rationale:**
- Avoids adding an SDK dependency for a small read-only subset.
- Keeps tests deterministic with fake sessions and known signed payload fixtures.
- Makes request signing explicit and reviewable.
- Keeps the provider implementation isolated from the rest of the app.

**Implementation Notes:**
- `compute_snaptrade_signature()` implements the documented signature payload.
- `SnapTradeProvider._request()` signs every request.
- Tests verify the canonical payload signature and the read-only portal request body.
- The direct client only exposes read/account-data behavior.

## ADR-071: Broker Sync Storage Before Portfolio Import

**Decision:** Broker data is first persisted in broker-specific tables, then optionally imported into local portfolios.

**Context:**
The existing application treats `txn` as the local source of truth and derives `position` from it. Broker data can change, be incomplete, arrive cached, or contain provider-specific raw payloads. SnapTrade documents that connections can contain multiple accounts: https://docs.snaptrade.com/reference/Connections/Connections_listBrokerageAuthorizations

SnapTrade's account activity endpoint returns historical transactions for an account, is paginated, and documents that data is cached and refreshed once a day: https://docs.snaptrade.com/reference/Account%20Information/AccountInformation_getAccountActivities

SnapTrade's account positions endpoint returns stock/ETF/crypto/mutual fund positions, with data freshness depending on plan/brokerage and cached daily data when real-time access is unavailable: https://docs.snaptrade.com/reference/Account%20Information/AccountInformation_getUserAccountPositions

**Rationale:**
- Separates provider state from local portfolio truth.
- Allows account-to-portfolio mapping before importing transactions.
- Preserves raw provider payloads for debugging and future AI context.
- Allows sync to be retried without duplicating local transactions.
- Keeps eventual Wealthica/Plaid/future provider support behind the same domain model.

**Implementation Notes:**
- Provider-side data is stored in:
  - `broker_connection`
  - `broker_account`
  - `broker_position_snapshot`
  - `broker_transaction`
  - `broker_sync_run`
- Local portfolio import is opt-in through:
  - `broker snaptrade import-transactions [--portfolio-id id]`
- The idempotency table is:
  - `broker_portfolio_txn_map`
- A broker account must have `portfolio_id` before its transactions can be imported.
- Imported transactions use `import_batch.batch_type = 'broker-sync'`.

## ADR-072: Explicit Account Mapping and Idempotent Portfolio Projection

**Decision:** Broker accounts are mapped to portfolios manually, and mapped transactions are imported idempotently.

**Context:**
A single brokerage login can expose multiple accounts. Those accounts may correspond to different local portfolios, or the user may want some accounts synced but not projected into local portfolio ledgers.

Local portfolio analytics depend on `txn` and `position`. Automatically importing every broker account into a single portfolio would be unsafe and likely incorrect.

**Rationale:**
- Prevents accidental mixing of TFSA, RRSP, margin, or other account types.
- Lets users decide which broker accounts should affect portfolio analytics.
- Enables sync-only usage where broker data is stored but not imported.
- Prevents duplicate transactions when broker sync is rerun.

**Implementation Notes:**
- `broker snaptrade accounts` lists locally stored broker accounts and mapping status.
- `broker snaptrade map-account <account-id> <portfolio-id>` maps an account.
- `broker snaptrade import-transactions` only imports mapped accounts.
- `broker_portfolio_txn_map` prevents duplicate local `txn` rows for the same provider transaction.
- Broker asset transactions preserve existing local ledger conventions:
  - buys and sells store quantity and price
  - sells are normalized to negative quantity
  - cash amount is reserved for cash-like events and dividend income
- After import, derived positions and portfolio tickers are refreshed.

## ADR-072A: Paginated Activity Sync and Broker Transaction Normalization

**Decision:** Broker transaction sync must retrieve all SnapTrade activity pages and normalize common provider activity types into the local transaction vocabulary.

**Context:**
SnapTrade documents that account activities are paginated, default to 1000 rows, return a maximum of 1000 transactions per request, and support `offset` and `limit` query parameters: https://docs.snaptrade.com/reference/Account%20Information/AccountInformation_getAccountActivities

The same endpoint documents common activity types such as `BUY`, `SELL`, `DIVIDEND`, `CONTRIBUTION`, `WITHDRAWAL`, `REI`, `STOCK_DIVIDEND`, `INTEREST`, `FEE`, `TAX`, `TRANSFER`, and split/option events: https://docs.snaptrade.com/reference/Account%20Information/AccountInformation_getAccountActivities

**Rationale:**
- Large accounts can exceed a single response page.
- Broker activity categories are broader than the local transaction vocabulary.
- Skipping or misclassifying common cash events would distort analytics.
- Keeping unknown activity conservative is better than inventing unsupported local semantics.

**Implementation Notes:**
- `SnapTradeProvider.list_transactions()` loops with `offset` and `limit` until the final partial page.
- `SNAPTRADE_ACTIVITY_PAGE_LIMIT` can override the default page limit for testing or tuning.
- `REI` and stock-dividend-like activity becomes a local buy when symbol, quantity, and price are available.
- `FEE` and `TAX` become withdrawals.
- `INTEREST` becomes interest.
- Unsupported asset transactions without a symbol are skipped during portfolio import.

## ADR-073: Daily Due Sync Scheduler

**Decision:** Broker sync can be run through a due-user scheduler that refreshes active users whose latest successful sync is older than the configured freshness window. The dashboard can also run that due sync automatically on startup when explicitly enabled by environment configuration.

**Context:**
SnapTrade documents that account activity data is daily cached and refreshed once per day, with exact timing varying by brokerage: https://docs.snaptrade.com/reference/Account%20Information/AccountInformation_getAccountActivities

The application already records broker sync runs. A daily scheduler can use those run records to avoid repeatedly refreshing the same user inside the same freshness window.

**Rationale:**
- Matches SnapTrade's documented daily account-activity freshness.
- Avoids unnecessary provider calls.
- Keeps automatic sync separate from local portfolio import.
- Allows users to force a refresh when they know a connection changed.
- Preserves the existing rule that local portfolio ledger writes are explicit.

**Implementation Notes:**
- `broker_sync_run.user_key` records which local broker user was synced.
- `BrokerSyncRepository.due_broker_users()` selects users with no successful sync or a stale successful sync.
- `BrokerSyncScheduler.sync_due_users()` runs the existing read-only sync service for due users.
- CLI command:
  - `broker snaptrade sync-due [--max-users n] [--min-age-hours hours] [--force]`
- Startup automation:
  - `BROKER_SYNC_ON_STARTUP=true`
  - `BROKER_SYNC_MAX_USERS=<optional cap>`
  - `BROKER_SYNC_MIN_AGE_HOURS=24`
- Due sync stores provider-side data only. Users must still run `broker snaptrade import-transactions` to write mapped transactions into local portfolios.

## ADR-074: Current Limits and Next Phase Hooks

**Decision:** Phase 4 stops at read-only sync, account mapping, portfolio import, CLI-triggered due sync, and opt-in dashboard-startup due sync. It does not implement a long-running scheduler process, webhooks, or a graphical account-linking portal.

**Context:**
SnapTrade documents account data freshness and notes that account activity data is cached and refreshed daily: https://docs.snaptrade.com/reference/Account%20Information/AccountInformation_getAccountActivities

SnapTrade also exposes connection refresh, disabled connection repair, secret rotation, and broader account data endpoints, but Phase 4 is intentionally scoped to the smallest useful read-only sync path.

**Rationale:**
- Keeps Phase 4 shippable and testable.
- Avoids background scheduling before the CLI flow is proven.
- Keeps provider connection lifecycle concerns out of the first implementation.
- Leaves a clean surface for a later AI and UI layer to present account-linking status.

**Implementation Notes:**
- Future work should add:
  - long-running broker sync scheduler process
  - connection disabled/reconnect handling
  - secret rotation workflow
  - paginated account activity retrieval
  - optional broker sync storage toggle if users want account linking without persisted provider payloads
  - a web UI portal launcher once the application has a browser-facing layer
