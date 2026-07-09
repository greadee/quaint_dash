# Codebase Map

This map is grounded in the current repository layout, `pyproject.toml`, `web/package.json`,
`src/dashboard/db/db_conn.py`, `src/dashboard/api/app.py`, `src/dashboard/api/routes.py`, and the
test folders under `tests/` and `web/src/`.

## Top-level folders

- `src/dashboard/`: Python package for the CLI, FastAPI backend, storage layer, ingestion,
  analytics, broker sync, news, and domain models.
- `web/`: React, TypeScript, Vite, React Query, route components, API client, tests, and Playwright
  config for the local browser dashboard.
- `tests/`: Python pytest coverage for CLI commands, schema contracts, API endpoints, ingestion,
  broker sync, news, analytics, streaming, and business-strength behavior.
- `tools/`: Operational scripts for full data-health scans, benchmark repairs/audits, signal
  profiling, news operations, and portfolio metric hydration audits.
- `scripts/`: Windows-friendly workflow wrapper. Prefer `scripts\qd.cmd` for setup, launch,
  verification, health, and smoke checks.
- `docs/`: ADRs, architecture docs, usage guides, ER diagrams, class/component diagrams, process
  notes, and evidence notes.
- `data/`, `tmp/`, local logs, `.env`, `.venv`, and generated build outputs: local-only runtime
  artifacts; they are intentionally ignored by Git.

## Python package ownership

- `dashboard.cli`: interactive CLI entrypoint. It initializes DuckDB, runs bounded startup
  maintenance, and enters the view loop.
- `dashboard.api`: FastAPI app factory, request dependencies, route handlers, response models,
  API service layer, and API-owned background workers.
- `dashboard.db`: DuckDB connection helper, base schema, migrations, and query constants.
- `dashboard.models`: domain dataclasses, CLI views, storage facade, and command mixins. The active
  command mixins live under `dashboard.models.commands`.
- `dashboard.analytics`: calculation-first analytics engine, repository, persistence helpers, and
  shared analytics models.
- `dashboard.ingestion`: price history, trading calendar, corporate calendar, fundamentals,
  benchmark indices, stock catalog, ticker universe, rate limits, and live-price streaming.
- `dashboard.ingestion_sentiment`: provider-neutral retail/news sentiment ingestion, scoring,
  aggregation, ticker matching, job scheduling, and provider adapters.
- `dashboard.brokers`: read-only SnapTrade integration, secret encryption abstraction, repository,
  sync scheduler, portfolio projection, and CLI parser.
- `dashboard.news`: provider-neutral news normalization, entity resolution, classification,
  clustering, ranking, repository, and API service.
- `dashboard.services`: transaction import, table formatting, asset metadata import, and business
  strength scoring services.

## Browser ownership

- `web/src/App.tsx` and `web/src/appRoutes.tsx`: route shell and navigation.
- `web/src/api.ts`: typed browser client for `/api/v1`.
- `web/src/routes/`: route-level UI for overview, portfolios, assets, compare, benchmarks,
  brokers, operations, signals, settings, news, and retail sentiment.
- `web/src/pageFeatures.ts` and `web/src/pageFeatureStore.tsx`: feature visibility and layout
  metadata.
- `web/src/*Utils.ts` and `web/src/routes/route*.tsx`: shared formatting, pickers, analytics, and
  display helpers.

## Low-risk consolidation completed

`src/dashboard/models/storage.py` had stale module-level benchmark and live-price helpers that had
already moved into `dashboard.models.commands.ingestion.IngestionCommands` and
`dashboard.models.commands.streaming.StreamingCommands`. Repo search showed the stale helpers were
definitions only, while tests and CLI code call the command mixins through `DashboardManager`. The
stale block and now-unused imports were removed without changing the public `DashboardManager`
surface.

## Current cleanup candidates

- ADR numbering has historical duplicates (`ADR-064`, `ADR-068`, `ADR-069`, `ADR-079`, `ADR-080`,
  and `ADR-032`). Do not renumber old ADRs; use `docs/adr/index.md` as the normalized index.
- Generated SVG diagrams under `docs/classes/to-display/` and `docs/erd/to-display/` are older
  than some current schema and route surfaces. Prefer the Mermaid docs added in this pass for
  current architecture, and regenerate display SVGs only when a render tool is available.
- `src/dashboard/models/storage.py` remains a legacy facade with CLI-era methods plus command
  mixins. Larger decomposition would be risky and should be done as a separate behavior-preserving
  refactor with focused tests.
