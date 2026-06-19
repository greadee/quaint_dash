# Phase 5 Web Application

Phase 5 adds a local-first FastAPI backend and React browser interface while preserving the
existing CLI.

## Development

The common local workflows are available through the repo command wrapper:

```cmd
scripts\qd.cmd setup
scripts\qd.cmd api
scripts\qd.cmd web
```

The `.cmd` wrapper is the preferred Windows entry point because it handles local PowerShell
execution policy restrictions. If your shell allows repo scripts directly, the PowerShell form is:

```powershell
.\scripts\qd.ps1 setup
.\scripts\qd.ps1 api
.\scripts\qd.ps1 web
```

For a two-terminal local launch, run:

```cmd
scripts\qd.cmd launch
```

Routine checks are grouped under the same wrapper:

```cmd
scripts\qd.cmd verify-py
scripts\qd.cmd verify-web
scripts\qd.cmd verify
scripts\qd.cmd smoke
```

Install the Python environment and start the API:

```powershell
python -m pip install -e ".[dev]"
dashboard-web
```

The API binds to `http://127.0.0.1:8000`. Interactive API documentation is available at
`http://127.0.0.1:8000/api/docs`.

`dashboard-web` imports `dashboard.api.app:app` and keeps the FastAPI server running until the
process is stopped. The equivalent module command is:

```powershell
python -m dashboard.api.app
```

In a second terminal, install and start the React application:

```powershell
cd web
npm install
npm run dev
```

The Vite development server binds to `http://127.0.0.1:5173` and proxies `/api` requests to
FastAPI.

## Production-style Local Run

Build the frontend, then start FastAPI:

```powershell
cd web
npm install
npm run build
cd ..
dashboard-web
```

FastAPI serves the compiled application from `web/dist`. Build output and installed Node
packages are intentionally excluded from Git.

## Portfolio Management Routes

The committed React app serves these portfolio routes:

- `/portfolios?tab=aggregate`
- `/portfolios?tab=portfolios`
- `/portfolios?tab=fundamentals`
- `/portfolios/{portfolio_id}?tab=overview`
- `/portfolios/{portfolio_id}?tab=holdings`
- `/portfolios/{portfolio_id}?tab=performance`
- `/portfolios/{portfolio_id}?tab=risk`
- `/portfolios/{portfolio_id}?tab=optimization`
- `/portfolios/{portfolio_id}?tab=fundamentals`
- `/portfolios/{portfolio_id}?tab=activity`
- `/assets/{asset_id}?tab=chart`
- `/assets/{asset_id}?tab=news`
- `/assets/{asset_id}?tab=fundamentals`
- `/signals`
- `/signals/{signal_id}`

The portfolio UI uses backend DTOs for performance, risk, fundamentals, and optimization. The
browser may format values and draw charts, but the Python/DuckDB backend is the source of truth
for portfolio weights, CAGR, Sharpe, Sortino, beta, volatility, drawdown, concentration, and
optimization weights.

The signals UI uses backend DTOs for signal definitions, evaluations, evidence, portfolio impact,
lifecycle, and user state. The browser may sort/filter through URL-backed controls and draw
presentation charts, but Python/DuckDB remains the source of truth for strength, confidence,
portfolio priority, evidence grouping, freshness, and alert/review state.

## Metric Semantics

- Actual historical performance is a transaction-aware daily time-weighted return series. External
  cash flows break return subperiods.
- Hypothetical current-weight backtests are separate from actual performance and must not be shown
  as the default portfolio history.
- Money-weighted return remains a ledger metric for investor experience.
- Current-weight forward expected CAGR comes from the existing weighted valuation rollup.
- Optimized expected CAGR is returned only by the optimization preview endpoint and is not
  persisted as a trade or stored position.

Unavailable values are rendered as unavailable/null with missing-input context. They should not be
displayed as zero unless the backend returns a real zero.

## Portfolio API Surface

The portfolio UI currently uses:

- `GET /api/v1/portfolios`
- `GET /api/v1/portfolios/aggregate/overview`
- `GET /api/v1/portfolios/aggregate/positions`
- `GET /api/v1/portfolios/{portfolio_id}`
- `GET /api/v1/portfolios/{portfolio_id}/positions`
- `GET /api/v1/portfolios/{portfolio_id}/performance`
- `GET /api/v1/portfolios/{portfolio_id}/risk`
- `GET /api/v1/portfolios/{portfolio_id}/fundamentals`
- `POST /api/v1/portfolios/{portfolio_id}/optimization/preview`
- `GET /api/v1/assets/{asset_id}`
- `GET /api/v1/assets/{asset_id}/prices`
- `GET /api/v1/assets/{asset_id}/analytics`
- `GET /api/v1/assets/{asset_id}/activity`
- `GET /api/v1/signals`
- `GET /api/v1/signals/{signal_id}`
- `PUT /api/v1/signals/{signal_id}/user-state`
- `POST /api/v1/signals/{signal_id}/alerts`

Optimization is preview-only. Applying target allocations should be a separate confirmed workflow
only if the application later persists target weights.

## Signal Semantics

- Factor: a persistent characteristic such as momentum, sentiment, earnings, quality, value, or
  growth.
- Condition: the current stored level or state of an input, such as a ranking component score,
  trigger value, freshness state, or missing-data state.
- Signal: a meaningful threshold crossing or evidence combination derived from stored inputs.
- Alert: a user-configured notification rule based on a signal or condition.

Signal strength, confidence, and portfolio priority are intentionally separate. Strength is the
normalized magnitude of the current signal. Confidence is the available input coverage. Portfolio
priority combines strength, confidence, current position weight, and affected portfolio count.
Historical efficacy is shown only when enough prior point-in-time evaluations exist; otherwise the
response reports sample size zero and withholds performance claims.

## Startup Sync

Set `BROKER_SYNC_ON_SERVER_STARTUP=true` to run the same stale-user broker sync used by
`broker snaptrade sync-due` when the backend starts. `BROKER_SYNC_MAX_USERS` and
`BROKER_SYNC_MIN_AGE_HOURS` control the launch-time sync window.

## Routine Ingestion Worker

The Operations page can start or stop the routine ingestion worker for the current API process.
When enabled, the worker periodically schedules due routine ingestion work and runs bounded
batches. It can also run one immediate cycle from the browser. The startup default remains off
unless `INGESTION_BACKGROUND_ENABLED=true` is set.

The worker is intentionally conservative: `INGESTION_BACKGROUND_MAX_JOBS_PER_TICK`,
`INGESTION_BACKGROUND_MAX_ASSETS_PER_SCHEDULE`, `INGESTION_BACKGROUND_SCHEDULE_INTERVAL_SECONDS`,
`INGESTION_BACKGROUND_RUN_INTERVAL_SECONDS`, `INGESTION_BACKGROUND_YEARS`, and
`INGESTION_BACKGROUND_PRICES_ONLY` bound its work.

For always-on local use, keep `dashboard-web` running in a terminal, Windows Terminal profile,
Task Scheduler task, or service wrapper. The React dev server can be started later; it will proxy
to the backend when it comes online.

## Current Boundaries

- The application is single-user and binds to localhost by default.
- DuckDB remains the application database.
- Broker connections remain read-only.
- Ingestion actions are bounded synchronous requests.
- Authentication, hosted deployment, hosted workers, AI features, native clients, and trading are
  deferred.
- Cross-currency support now has a committed `fx_rate` schema foundation, but provider ingestion
  for dated FX rates is not yet implemented.
