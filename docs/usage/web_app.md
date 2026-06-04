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

## Current Boundaries

- The application is single-user and binds to localhost by default.
- DuckDB remains the application database.
- Broker connections remain read-only.
- Ingestion actions are bounded synchronous requests.
- Authentication, hosted deployment, background workers, AI features, native clients, and
  trading are deferred.
