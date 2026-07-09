# Evidence: 2026-07-09 Documentation, Architecture, Safety Pass

## Changed

- Updated `.env.example` with safe placeholders for provider credentials, rate limits, streaming,
  data readiness, broker sync, and background-worker settings.
- Changed broker background sync defaults to safe-off in `src/dashboard/api/broker_background.py`
  and the broker status service default in `src/dashboard/api/services.py`.
- Removed stale benchmark/live-price helper definitions from `src/dashboard/models/storage.py`;
  active implementations live in command mixins.
- Added onboarding, environment, testing, codebase map, architecture, current ER schema,
  data-safety, ADR index, and ADR PH9 docs.
- Updated `README.md` to point contributors at current docs and workflows.

## Evidence inspected

- Repo structure: `rg --files`, `Get-ChildItem -Force`, `git status --short --branch`.
- Existing docs: `README.md`, `docs/usage/web_app.md`, `docs/usage/cmds/*.md`,
  `docs/news_terminal.md`, `docs/retail_sentiment_ingestion.md`, and all files under `docs/adr/`.
- Schema sources: `src/dashboard/db/schema.sql`,
  `src/dashboard/db/migrations/live_price_streaming.sql`,
  `src/dashboard/db/migrations/benchmark_indices.sql`,
  `src/dashboard/db/migrations/business_strength.sql`,
  `src/dashboard/db/migrations/financial_news.sql`, and `src/dashboard/db/db_conn.py`.
- API sources: `src/dashboard/api/app.py`, `src/dashboard/api/dependencies.py`,
  `src/dashboard/api/routes.py`, `src/dashboard/api/services.py`, and API background worker files.
- CLI sources: `src/dashboard/cli.py`, `src/dashboard/models/cli_view.py`,
  `src/dashboard/models/storage.py`, and `src/dashboard/models/commands/*`.
- Provider and safety sources: broker secret handling, benchmark error redaction, rate-limit tests,
  API broker redaction tests, provider env reads, and `.gitignore`.
- Web sources: `web/package.json`, `web/src/api.ts`, route tests, and route files listed by
  `rg --files`.

## Safety scan evidence

Commands:

```cmd
git ls-files data tmp '*.db' '*.sqlite' '*.duckdb' '*.log' '.env' '.env.example'
git ls-files | rg "(^data/|^tmp/|\.db$|\.sqlite$|\.duckdb$|\.log$|\.env$)"
rg "(api[_-]?key|secret|token|password|bearer|\.duckdb|\.sqlite|account number|routing number|private key)" -i --glob "!web/node_modules/**" --glob "!web/dist/**" --glob "!docs/classes/to-display/**" --glob "!docs/erd/to-display/**" --glob "!*.svg" --glob "!*.png" --glob "!*.lock" .
```

Findings:

- No tracked local database, log, or real `.env` files were found.
- Pattern matches were env-var names, placeholders, docs, tests with synthetic secrets, redaction
  logic, and account masking tests.
- Git history was not scanned.

## Verification performed

- `.\.venv\Scripts\python.exe -m ruff check`: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\test_production_schema_contracts.py tests\api\test_operations_api.py tests\test_broker_sync.py -q`: 75 passed, 1 existing FastAPI/TestClient deprecation warning.
- `.\.venv\Scripts\python.exe -m pytest -q`: 408 passed, 1 existing FastAPI/TestClient deprecation warning.
- `cd web && npm.cmd run lint`: passed with 4 existing `react-refresh/only-export-components` warnings.
- `cd web && npm.cmd exec -- tsc -b`: passed.
- `cd web && npm.cmd run build`: passed.
- `cd web && npm.cmd test`: 20 test files passed, 80 tests passed.
- Local Markdown link check with PowerShell `Test-Path`: all local Markdown links resolved.
- Mermaid blocks were identified by `rg` and checked by inspection; no Mermaid renderer was available in this pass.
- `scripts\qd.cmd verify`: attempted, but the wrapper hit a Windows launcher error calling
  `.venv\Scripts\python.exe -m ruff check` with `Access is denied`. The underlying Ruff, pytest,
  web lint, TypeScript, build, and Vitest commands were run directly and passed as listed above.

## Remaining uncertainty

- Mermaid diagrams were checked by inspection unless a renderer is available during final
  verification.
- Generated SVG diagram files were not regenerated in this pass.
- ADR status was audited from current code and tests, but old ADR IDs were intentionally preserved
  even where numbering duplicates exist.
