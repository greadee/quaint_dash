# Runtime diagnostics and recovery

S1 adds process-local worker diagnostics and a read-only queue summary. The financial calculations,
database schemas, job identities, retry rules, import mappings, and stored payloads retain their
existing contracts.

## Database ownership

Run one API process against the local database file. API requests use independent pooled
connections, and mutation routes/background workers share the existing in-process writer lock.
The configured native DuckDB connection supports read/write concurrency within one process;
an unrelated writer process cannot open the same file concurrently. See the
[DuckDB concurrency documentation](https://duckdb.org/docs/current/connect/concurrency).

API module imports now construct the default ASGI app without opening or migrating the default
database. Its database opens during server startup. Explicit `create_app(path)` callers retain
eager initialization for existing test seeders; `initialize_on_startup=True` opts into deferral.
Tests can import the API while the desktop app is running and use their own `tmp_path` databases.

When a separate command encounters an owned database, it fails promptly with instructions to use
the running app or stop the owner before executing the command. It does not retry writes or
terminate another process. The original driver exception remains in the server/terminal exception
chain for diagnosis. Ordinary worker status exposes only safe, fixed messages.

Partial connection-pool startup and schema initialization release acquired handles on failure.
Shutdown joins in-flight background database work before releasing the API pool, including when
a waiter is cancelled. It can therefore wait for a provider call's configured timeout. This is a
graceful shutdown guarantee, not a forced-termination guarantee.

## Read the status before acting

The Operations page reads `/api/v1/ingestion/queue/status` every 30 seconds. It counts the full
queue rather than counting a limited list response. Counts and oldest backlog timestamps come
from one read snapshot; status lookup failure is shown as unavailable, not an empty queue.

The ingestion, market-price, and data-readiness status endpoints add:

- worker name and state (`disabled`, `idle`, `running`, `failed`, `blocked`, `misconfigured`);
- current failures by phase, such as scheduling versus running;
- the last failure, its UTC timestamp, category, per-phase count, and suggested next step;
- a lifetime failure count for the current worker instance.

A successful run no longer clears a scheduling failure. Each phase clears only its own current
failure after success, while the most recent historical failure remains available. Disabling a
worker also does not erase its failure. `enabled` describes configuration and the legacy `running`
field describes the background loop; the new `state` identifies active work or an unresolved
failure. An enabled but idle worker is not proof of a completed cycle.

The diagnostics are process-local and reset when the server restarts. The queue and its historical
failed/dead-letter jobs remain persisted. This slice does not migrate old logs into worker history.
Broker background work uses the same safe lifecycle helper; broker-facing status integration
remains under the existing broker workflow.

## Recovery by failure category

| Condition | Next step |
| --- | --- |
| Database owned elsewhere | Use the existing app for data operations. For an offline command, gracefully stop the database owner first; do not delete the database or WAL. |
| Scheduler query failure | Read local logs for the matching worker/phase/timestamp and reproduce against an isolated database before applying a query/schema repair. |
| Provider rate limit | Check the provider's quota/reset window and configured call budget; allow the window to reset before explicitly requesting a bounded retry. |
| Missing credentials or subscription access | Correct configuration/access, then explicitly test one bounded operation. A 402 access failure is not repaired by repeated retries. |
| Pending work with disabled workers | Review the affected data products and oldest job age, then decide whether to enable periodic work or request one bounded cycle. |
| Failed/dead-letter jobs | Review the safe category summary and local diagnostic details. Existing retry/idempotency rules apply; no automatic drain or replacement jobs occur when opening status. |

Provider attribution in queue summaries is inferred from known names in stored diagnostic text,
because the queue has no provider column. Unknown or mixed attribution stays explicit. It is not
an authoritative provider ledger.

## Historical scheduler error reconciliation

The audit recorded a DuckDB binder error at `s.snapshot_date`. The current
`_due_sentiment_snapshot_assets` query already declares `s`, and the error does not reproduce with
DuckDB 1.5.5 on an initialized test database. S1 does not claim a SQL correction or invent a cause
for the historical log. New production-schema regressions execute all three real snapshot queries
and cover date scope, pending/running deduplication, completed jobs, and bounded selection.

If the error returns, capture the runtime revision, DuckDB version, schema and full local traceback
before deciding on a repair. The new phase-specific status prevents a subsequent successful
runner step from hiding it.

## Focused verification

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\api\test_database_lifecycle.py tests\api\test_worker_diagnostics.py tests\api\test_broker_worker_lifecycle.py tests\test_sentiment_scheduler_regression.py
.\.venv\Scripts\python.exe -m tools.check_architecture_boundaries
```

These checks use temporary databases, fake providers, gated background threads, and subprocesses.
They do not access the user's production data or execute queued provider jobs. Operations API and
web regression suites separately verify the queue summary, safe messages, and rendered failure
states. Live provider recovery remains an explicit operational action after code validation.
