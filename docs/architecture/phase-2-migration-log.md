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
