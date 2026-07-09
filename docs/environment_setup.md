# Environment Setup

Use `.env.example` as the only committed template. Real credentials belong in `.env`, which is
ignored by Git, or in a secret manager outside the repository.

## Core local runtime

- `DASHBOARD_DB_PATH`: DuckDB file path. Default code path is `data/persistent_db.db`.
- `DASHBOARD_API_HOST`: API host. Keep `127.0.0.1` for local-first use.
- `DASHBOARD_API_PORT`: API port. Default is `8000`.
- `DASHBOARD_WEB_DEV_ORIGIN`: Vite origin allowed by API CORS. Default is
  `http://127.0.0.1:5173`.

## Market, fundamentals, news, and sentiment credentials

- `FMP_API_KEY`: FMP metadata, fundamentals, benchmark, and extended-hours access.
- `FINNHUB_API_KEY`: Finnhub live streaming and optional news/sentiment credential.
- `NEWS_API_KEY`: optional news provider credential used by the generic news sentiment provider.
- `ALPHA_VANTAGE_API_KEY`: optional news provider credential.
- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`: Reddit OAuth credentials.
- `X_BEARER_TOKEN`: X recent-search bearer token.

Leave these blank unless you are intentionally running provider-backed ingestion.

## Provider bounds

- `FMP_RATE_LIMIT_PER_MINUTE`, `FMP_MIN_SECONDS_BETWEEN_CALLS`,
  `FMP_MAX_CALLS_PER_RUN`: shared FMP call budget controls.
- `FMP_STABLE_BASE_URL`: FMP stable API base URL.
- `FMP_EXTENDED_HOURS_MAX_SYMBOLS`: extended-hours batch symbol cap.
- `FINNHUB_WEBSOCKET_URL`: optional override for the Finnhub websocket URL. Leave blank to let the
  client build the URL from `FINNHUB_API_KEY`.
- `FINNHUB_WEBSOCKET_MAX_SYMBOLS`: live-stream subscription cap.
- `LIVE_STREAM_FMP_EXTENDED_POLL_SECONDS`: extended-hours polling interval.

## API background workers

All provider-heavy workers should be safe-off unless intentionally enabled.

- `INGESTION_BACKGROUND_ENABLED`: routine ingestion scheduler/runner. Default template: `false`.
- `MARKET_FRESHNESS_ENABLED`: current price freshness poller. Default template: `false`.
- `DATA_READINESS_WORKER_ENABLED`: valuation/readiness worker. Default template: `false`.
- `BROKER_SYNC_BACKGROUND_ENABLED`: periodic broker sync. Default template: `false`.

The corresponding interval, batch, asset, job, and lookback variables in `.env.example` bound how
much work each enabled worker can do per tick.

## Broker sync

- `SNAPTRADE_CLIENT_ID`
- `SNAPTRADE_CONSUMER_KEY`
- `QUAINT_BROKER_SECRET_KEY`
- `SNAPTRADE_BASE_URL`
- `SNAPTRADE_TIMEOUT_SECONDS`
- `SNAPTRADE_ACTIVITY_PAGE_LIMIT`
- `BROKER_SYNC_ON_STARTUP`: optional CLI startup sync.
- `BROKER_SYNC_ON_SERVER_STARTUP`: optional API startup sync.
- `BROKER_SYNC_BACKGROUND_ENABLED`: optional periodic API background sync.
- `BROKER_SYNC_MAX_USERS`
- `BROKER_SYNC_MIN_AGE_HOURS`

Broker sync is read-only. It stores provider-side account and transaction data locally, then imports
mapped transactions into the local ledger only when explicitly requested.

## Safety rules

- Do not commit `.env`.
- Do not commit local DuckDB, SQLite, log, coverage, Vite, node, or virtualenv artifacts.
- Do not paste real account numbers, provider secrets, bearer tokens, exported broker payloads, or
raw portfolio exports into docs or tests.
- Test fixtures should use fake keys such as `fake-key`, `test-key`, or `secret` only when the test
asserts redaction behavior.
