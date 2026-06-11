# Phase 5 Web Application

Phase 5 adds a local-first FastAPI backend and React browser interface while preserving the
existing CLI.

## Development

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

## Startup Sync

Set `BROKER_SYNC_ON_SERVER_STARTUP=true` to run the same stale-user broker sync used by
`broker snaptrade sync-due` when the backend starts. `BROKER_SYNC_MAX_USERS` and
`BROKER_SYNC_MIN_AGE_HOURS` control the launch-time sync window.

For always-on local use, keep `dashboard-web` running in a terminal, Windows Terminal profile,
Task Scheduler task, or service wrapper. The React dev server can be started later; it will proxy
to the backend when it comes online.

## Current Boundaries

- The application is single-user and binds to localhost by default.
- DuckDB remains the application database.
- Broker connections remain read-only.
- Ingestion actions are bounded synchronous requests.
- Authentication, hosted deployment, background workers, AI features, native clients, and
  trading are deferred.
