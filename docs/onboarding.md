# Contributor Onboarding

Use this guide with the repository root as the working directory.

## Project overview

Quaint Dash is a local-first investment dashboard. It started as a Python CLI for portfolios,
transactions, positions, and DuckDB-backed storage. It now also includes a FastAPI backend, a React
browser app, ingestion workers, analytics, broker sync, benchmark ingestion, news, sentiment, and
operations/data-health tooling.

Authoritative financial calculations and provider-derived data live in Python and DuckDB. The
browser formats and visualizes API payloads; it should not fabricate returns, risk, valuation,
readiness, broker, benchmark, or holdings metrics.

## Local setup

```cmd
scripts\qd.cmd setup
```

This installs Python dev dependencies from `pyproject.toml` and Node dependencies from
`web/package.json`. If you need to do it manually:

```cmd
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
cd web
npm.cmd install
```

## Environment setup

Copy `.env.example` to `.env` and fill in only the credentials you need. Leave optional providers
blank for normal local development. See `docs/environment_setup.md` for every currently documented
setting and its source.

## Run the app

CLI:

```cmd
dashboard
```

API:

```cmd
scripts\qd.cmd api
```

Web:

```cmd
scripts\qd.cmd web
```

Two-terminal launch helper:

```cmd
scripts\qd.cmd launch
```

The API binds to `http://127.0.0.1:8000`; API docs are at
`http://127.0.0.1:8000/api/docs`. Vite binds to `http://127.0.0.1:5173`.

## Database initialization

`dashboard.db.db_conn.init_db()` runs `src/dashboard/db/schema.sql`, then applies these migration
files:

- `src/dashboard/db/migrations/live_price_streaming.sql`
- `src/dashboard/db/migrations/benchmark_indices.sql`
- `src/dashboard/db/migrations/business_strength.sql`
- `src/dashboard/db/migrations/financial_news.sql`

It also seeds the static stock catalog with `dashboard.ingestion.stock_catalog.seed_stock_catalog`.
The default DB path is `data/persistent_db.db`, controlled by `DASHBOARD_DB_PATH`.

## How ingestion works

The shared ingestion spine is the `ingestion_job` table plus domain-specific services:

- Market price history: `dashboard.ingestion.price_history.*`
- Trading calendars: `dashboard.ingestion.trading_calendar.*`
- Corporate calendar and fundamentals: `dashboard.ingestion.corporate_calendar.*` and
  `dashboard.ingestion.fundamentals.*`
- Benchmark indices: `dashboard.ingestion.indices.*`
- Live prices: `dashboard.ingestion.websocket.*`
- News and retail sentiment: `dashboard.news.*` and `dashboard.ingestion_sentiment.*`

Routine background work is intentionally bounded. API workers are configured in
`dashboard.api.ingestion_background`, `dashboard.api.market_freshness_background`,
`dashboard.api.data_readiness_background`, and `dashboard.api.broker_background`. Provider-heavy
work should remain explicit unless a worker config clearly bounds it.

## Adding a provider

1. Find the relevant provider protocol or adapter family.
2. Add a provider implementation with explicit credentials, timeouts, rate limits, and redaction.
3. Register it through the existing service factory or provider registry.
4. Add synthetic tests that do not call the real provider.
5. Document env vars in `.env.example` and `docs/environment_setup.md`.
6. Add an ADR or update `docs/adr/index.md` if the provider changes architecture or data ownership.

## Adding an ingestion job

1. Add or reuse a domain service that can schedule and process the work.
2. Store work in `ingestion_job` unless the domain has a documented separate queue.
3. Use statuses already expected by the APIs: `pending`, `running`, `done`, and `failed`.
4. Record provider errors after redacting keys/tokens.
5. Add API/CLI tests for scheduling, running, retry behavior, and permanent failures.

## Adding a CLI command

1. Add behavior to the relevant mixin under `src/dashboard/models/commands/`.
2. Wire parser/view handling in `src/dashboard/models/cli_view.py` or provider-specific CLI modules.
3. Test through `tests/cli/` or the relevant service-level tests.
4. Update `docs/usage/cmds/`.

## Adding a test

Use pytest for Python and Vitest for React. Prefer synthetic fixtures and `tmp_path` databases.
Provider tests should monkeypatch HTTP clients or use fake providers rather than making network
calls.

## Troubleshooting

- `python` is not on PATH: use `.\.venv\Scripts\python.exe` or `scripts\qd.cmd`.
- PowerShell blocks scripts: use `scripts\qd.cmd`, which runs the repo PowerShell wrapper with
  execution policy bypass.
- API health fails: check `DASHBOARD_DB_PATH`, then run `scripts\qd.cmd health`.
- Vite route loads but data is missing: verify `GET /api/v1/health`, then inspect the exact API
  payload before changing React.
- Broker commands fail with missing secrets: set `SNAPTRADE_CLIENT_ID`,
  `SNAPTRADE_CONSUMER_KEY`, and `QUAINT_BROKER_SECRET_KEY` in `.env`.
- FMP returns HTTP 402: the configured plan cannot access that endpoint; the scheduler records this
  as a provider limitation and should not crash the process.
- Full data-health reports `Unavailable` or stuck loading: treat it as a blocker unless the
  corresponding API payload proves the provider cannot supply the data.
