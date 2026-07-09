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

## Startup And Background Sync

Set `BROKER_SYNC_ON_SERVER_STARTUP=true` to run the same stale-user broker sync used by
`broker snaptrade sync-due` when the backend starts. `BROKER_SYNC_MAX_USERS` and
`BROKER_SYNC_MIN_AGE_HOURS` control the launch-time sync window.

Set `BROKER_SYNC_BACKGROUND_ENABLED=true` only when the running API process should periodically
run broker `sync-due`. The committed default is safe-off so provider calls do not start just
because credentials are configured.

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

## Full Data Health Workflow

Use the full data health workflow after web-facing ingestion, valuation, projection, signal,
or portfolio changes, and whenever the Operations page reports failed jobs or missing data.
It coordinates the live API workers, drains runnable jobs, checks portfolio readiness, and scans
the rendered app for unresolved missing-data text.

With the API on `http://127.0.0.1:8000` and Vite on `http://localhost:5173`, run:

```cmd
.\.venv\Scripts\python.exe tools\run_full_data_health_workflow.py --cycles 4 --run-batches 10 --external-audit --json
cd web
npm.cmd exec -- node ..\tools\scan_web_app_data_health.mjs
```

The Python workflow starts and ticks the ingestion background worker, data-readiness worker, and
market-freshness worker. It retries failed jobs, schedules due full ingestion work, runs bounded
job batches, checks readiness endpoints, runs optimization previews, and optionally compares a
bounded price sample against Yahoo Finance chart responses. It does not delete ingestion history
or sync-state evidence unless `--clear-history` is passed explicitly.

The browser scanner walks Overview, Operations, Signals, Brokers, Settings, aggregate portfolio
tabs, and every portfolio detail tab. It fails if routes return errors, API requests fail, console
errors appear, or visible missing-data markers such as `Unavailable` or `Loading dashboard data`
remain after refresh.

Passing the workflow means:

- `GET /api/v1/health` reports database connected.
- `/api/v1/ingestion/readiness` and ranking readiness are fully ready.
- No pending, running, or failed ingestion jobs remain in the scanned job window.
- Portfolio overview, positions, performance, risk, fundamentals, and optimization preview
  payloads avoid nulls for critical valuation, projection, risk, and simulation metrics.
- The refreshed web app renders without missing-data markers, stuck loading states, console
  errors, or failed API requests.

External price checks are proof samples, not a guarantee that every historical data point is
globally authoritative. They are used to catch obvious drift or provider mistakes and should name
the source and tolerance in the workflow output.

## Portfolio Metric Hydration Audit

Use the portfolio metric hydration audit when a ticker shows missing fundamentals in Compare,
Ticker View, portfolio fundamentals, or ranking/holding factor surfaces:

```cmd
.\.venv\Scripts\python.exe tools\audit_portfolio_metric_hydration.py --json
```

The audit enumerates every held portfolio ticker through the same API service layer used by the
web app. It preserves the held tradable security for price history, returns, transaction history,
and valuation, then resolves a separate `fundamental_asset_id` for company-level metrics. For CDRs
and similar wrappers, the wrapper keeps its own market price series while fundamentals, beta,
shares, market capitalization, margins, free cash flow, and ROIC come from the underlying company
when the local resolver identifies one.

To enqueue the existing ingestion pipelines for incomplete company-level assets, run:

```cmd
.\.venv\Scripts\python.exe tools\audit_portfolio_metric_hydration.py --schedule-missing --run-batches 10 --json
```

The command exits nonzero while any held operating-company ticker remains `partial`, `stale`, or
`failed`. It reports input ticker, canonical ticker, underlying-security ticker, exchange, currency,
security type, provider/source, latest successful ingestion time, expected metrics, present
metrics, missing metrics, invalid metrics, stale metrics, affected UI surfaces, and final status.
This is the fast preflight for the broader full data health workflow above.

## Current Boundaries

- The application is single-user and binds to localhost by default.
- DuckDB remains the application database.
- Broker connections remain read-only.
- Ingestion actions are bounded synchronous requests.
- Authentication, hosted deployment, hosted workers, AI features, native clients, and trading are
  deferred.
- Cross-currency support now has a committed `fx_rate` schema foundation, but provider ingestion
  for dated FX rates is not yet implemented.
