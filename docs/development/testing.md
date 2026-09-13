# Testing And Verification

## Standard checks

Python:

```cmd
scripts\qd.cmd verify-py
```

Web:

```cmd
scripts\qd.cmd verify-web
```

Everything:

```cmd
scripts\qd.cmd verify
```

The wrapper runs the same commands defined in `scripts/qd.ps1`: Ruff, pytest, ESLint, TypeScript,
and Vite build.

## Focused Python tests

```cmd
.\.venv\Scripts\python.exe -m pytest tests\api
.\.venv\Scripts\python.exe -m pytest tests\ingestion_benchmarks tests\ingestion_sentiment
.\.venv\Scripts\python.exe -m pytest tests\test_production_schema_contracts.py
```

Use `tmp_path` databases and fake providers for new tests. Provider-backed tests must not require
real credentials or network access.

## Focused web tests

```cmd
cd web
npm.cmd test -- --run src/routes/operationsRoute.test.tsx
npm.cmd run lint
npm.cmd exec -- tsc -b
npm.cmd run build
```

## Live app review

For web-facing changes, start the API and Vite app and verify:

```cmd
scripts\qd.cmd smoke
```

The required surfaces are:

- `http://127.0.0.1:8000/api/v1/health`
- `http://127.0.0.1:5173` or `http://localhost:5173`

Inspect the affected page and nearby navigation for failed requests, console errors, stuck loading
states, zeroed metrics, and missing data. If the browser shows missing data, inspect the matching
API payload before deciding whether the bug is frontend rendering, service behavior, or provider
data.

## Full data-health workflow

For ingestion, valuation, projection, portfolio metric, signal, websocket, or Operations work:

```cmd
.\.venv\Scripts\python.exe tools\run_full_data_health_workflow.py --cycles 4 --run-batches 10 --external-audit --json
cd web
npm.cmd exec -- node ..\tools\scan_web_app_data_health.mjs
```

Treat failed/running/pending jobs, missing readiness, null critical metrics, failed optimization
previews, websocket gaps, console errors, visible `Unavailable`, and stuck loading states as
blockers unless the handoff documents a provider limitation.

## Markdown and diagram checks

No Markdown linter is currently configured. For docs-only work, use these checks:

```cmd
rg "\]\([^)#]+\.md\)" docs README.md
rg "```mermaid" docs
```

If a Mermaid CLI or Markdown renderer is available, render the changed files. Otherwise, verify
diagrams by inspection and keep Mermaid syntax simple.
