# Phase 2 Migration Log

This log records completed Phase 2 slices. Each entry must identify the feature,
boundary moved, behavior impact, tests, documentation, and rollback path.

## Slice 1: Operations Status Application Boundary

- Date: 2026-07-10.
- Feature IDs: `OPS-002` routine worker status, market freshness status, data
  readiness status.
- Module owner: Operations/Data Quality.
- Current consumers: existing `/api/v1/ingestion/background/status`,
  `/api/v1/market/freshness/status`, and `/api/v1/data/readiness/status`.
- Change: added `dashboard.application.operations.OperationsStatusQueries` and
  routed read-status endpoints through it.
- Behavior impact: intended none. Existing response models and worker state are
  unchanged.
- Boundary established: API adapter now calls an application query facade for
  status reads.
- Boundary enforcement: `tools/check_architecture_boundaries.py` now checks that
  `src/dashboard/application` does not import FastAPI, web UI modules, or
  DuckDB.
- Tests added: `tests/application/test_operations_status_queries.py`.
- Targeted verification: `pytest tests\application\test_operations_status_queries.py tests\api\test_operations_api.py -q`
  passed with 39 tests and 1 existing FastAPI/Starlette warning.
- Full verification:
  - `.\.venv\Scripts\python.exe -m ruff check .` passed.
  - `.\.venv\Scripts\python.exe -m pytest` passed with 414 tests and 1
    existing FastAPI/Starlette warning.
  - `.\.venv\Scripts\python.exe -m tools.check_architecture_boundaries` passed.
  - `cd web && npm.cmd run lint` passed with 4 existing Fast Refresh warnings.
  - `cd web && npm.cmd test` passed with 83 tests.
  - `cd web && npm.cmd run build` passed.
  - `GET /api/v1/health`, `GET /api/v1/ingestion/background/status`, and
    `GET /operations` returned HTTP 200 locally.
  - Playwright smoke loaded `/operations` with no browser console errors.
- Rollback: restore the three status routes to direct worker `.status()` calls
  and remove the application facade/test.
- Follow-up: migrate Operations worker commands (`start`, `stop`, `tick`) behind
  an application command facade with idempotency and authorization semantics.

## Slice 2: Operations Worker Command Boundary

- Date: 2026-07-10.
- Feature IDs: `OPS-002` routine worker status/control, market freshness
  status/control, data readiness status/control.
- Module owner: Operations/Data Quality.
- Current consumers: existing `/api/v1/ingestion/background/start|stop|tick`,
  `/api/v1/market/freshness/start|stop|tick`, and
  `/api/v1/data/readiness/start|stop|tick`.
- Change: added `OperationsWorkerCommands` and routed worker command endpoints
  through it.
- Behavior impact: intended none. Existing response models, worker methods,
  bounded job behavior, and API paths are unchanged.
- Boundary established: FastAPI routes now call an application command facade
  instead of direct process-local worker methods.
- Tests added: command tests in
  `tests/application/test_operations_status_queries.py`.
- Targeted verification: `pytest tests\application\test_operations_status_queries.py tests\api\test_operations_api.py -q`
  passed with 41 tests and 1 existing FastAPI/Starlette warning.
- Full verification:
  - `.\.venv\Scripts\python.exe -m ruff check .` passed.
  - `.\.venv\Scripts\python.exe -m pytest` passed with 416 tests and 1
    existing FastAPI/Starlette warning.
  - `.\.venv\Scripts\python.exe -m tools.check_architecture_boundaries` passed.
  - `cd web && npm.cmd run lint` passed with 4 existing Fast Refresh warnings.
  - `cd web && npm.cmd test` passed with 83 tests after the test script was
    pinned to tracked `vite.config.ts`; the ignored generated `vite.config.js`
    otherwise resolves the setup file as `/src/test/setup.ts`.
  - `cd web && npm.cmd run build` passed.
  - `GET /api/v1/health`, `GET /api/v1/ingestion/background/status`,
    `GET /api/v1/market/freshness/status`, `GET /api/v1/data/readiness/status`,
    and `GET /operations` returned HTTP 200 locally.
  - Playwright smoke loaded `/operations` with no browser console errors.
- Data-health verification:
  - `tools\run_full_data_health_workflow.py --cycles 4 --run-batches 10 --external-audit --json`
    exercised the worker command endpoints successfully, but returned `ok:
    false` because of existing portfolio data issues: null fundamentals,
    missing price-history inputs, infeasible optimization previews, and external
    price mismatches for `AMD.TO` and `META.TO`.
  - `tools\scan_web_app_data_health.mjs` returned `ok: false` with portfolio
    route loading markers/timeouts and unavailable data markers. Direct
    `/operations` and the three affected status APIs returned HTTP 200 after the
    scan.
- Rollback: restore command routes to direct worker method calls and remove the
  command facade tests.
- Follow-up: define durable Operations command contracts with idempotency,
  authorization, and audit metadata before exposing these commands to desktop,
  mobile, or automation consumers.
