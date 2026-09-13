# Data Safety And Sensitive Information Checklist

This project handles financial, broker, provider, and local portfolio data. Treat local runtime
data as sensitive even when the app is bound to localhost.

## Current safeguards

- `.gitignore` ignores `.env`, `.venv`, `data/`, `tmp/`, database files, logs, coverage, build
  outputs, `web/node_modules/`, and generated Vite artifacts.
- `git ls-files` currently shows `.env.example` as the only tracked env/data-style file from the
  safety scan.
- `.env.example` uses blank placeholders for credentials and safe-off worker defaults.
- Broker provider user secrets are encrypted through `dashboard.brokers.secrets.LocalSecretCipher`
  before persistence.
- Broker API responses are tested to omit raw payloads, provider user IDs, user secrets, account
  numbers, and sensitive sync errors.
- Benchmark provider errors redact `apikey` and `api_key` query values before persistence.
- Tests use synthetic keys, fake providers, monkeypatching, and `tmp_path` databases.

## What not to commit

- Real `.env` files.
- Provider keys or bearer tokens.
- SnapTrade user secrets, broker account numbers, raw broker exports, or provider payload dumps.
- Local DuckDB, SQLite, or database backup files.
- Logs that include provider URLs or raw account payloads.
- Raw portfolio exports from a personal broker.
- Generated reports containing personal account identifiers.

## Secret and sensitive-data scan performed

Commands used during this pass:

```cmd
git ls-files data tmp '*.db' '*.sqlite' '*.duckdb' '*.log' '.env' '.env.example'
git ls-files | rg "(^data/|^tmp/|\.db$|\.sqlite$|\.duckdb$|\.log$|\.env$)"
rg "(api[_-]?key|secret|token|password|bearer|\.duckdb|\.sqlite|account number|routing number|private key)" -i --glob "!web/node_modules/**" --glob "!web/dist/**" --glob "!docs/archive/diagrams/**" --glob "!*.svg" --glob "!*.png" --glob "!*.lock" .
```

Findings:

- No tracked database, SQLite, DuckDB, log, or real `.env` files were found.
- Matches were placeholders, env-var names, redaction logic, tests with synthetic secrets, and
  documentation about secret handling.
- The scan is pattern-based; it does not inspect Git history. If a real secret was ever committed,
  rotate it and use history-cleaning procedures outside this docs pass.

## Redaction expectations

- Persisted provider errors should remove API keys and bearer tokens before writing to sync state
  or job error columns.
- API responses should not include raw provider payloads by default.
- Browser UI should mask account numbers. Keep helpers such as `web/src/brokerUtils.ts` covered by
  tests.
- Docs must use placeholders like `<client id>` or blank assignments, never real values.

## Open safety follow-ups

- `LocalSecretCipher` is appropriate for local development but should be replaced by OS keyring or
  managed KMS if the app becomes hosted or multi-user.
- Historical Git secret scanning was not run in this pass. Run a dedicated tool such as gitleaks
  before sharing the repo broadly.
- Raw provider payload retention is configurable for broker sync, but old raw payloads are not
  automatically deleted when storage is disabled.
