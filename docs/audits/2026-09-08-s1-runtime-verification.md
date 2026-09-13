# S1 runtime implementation and verification

The bounded S1 implementation is delivered. Database imports no longer open the live file,
shutdown waits for owned background work, and Operations exposes safe phase failures and the
whole queue rather than a capped 500-row count. Financial calculations, database schemas,
job identities, retries, import idempotency and stored raw payloads are unchanged.

This is not a claim that the audited live backlog has recovered. The historical scheduler
incident remains unproven on the current revision; no live worker, provider, or retry action
was executed as part of verification.

## Implemented boundaries

| Area | Change | Evidence |
| --- | --- | --- |
| DuckDB ownership | Default ASGI initialization occurs at startup, not module import. Separate-process contention produces actionable instructions. Partial initialization releases acquired connections. | `tests/api/test_database_lifecycle.py`: subprocess import/lock tests, isolated-file reopen, startup/stop failure cleanup. |
| Worker lifecycle | Ingestion, market freshness, data readiness and broker background work join their owned threads before shutdown releases resources. Overlapping phase work is skipped; cancellation cannot detach an active DB operation. | Lifecycle and worker tests cover gated threads, repeated cancellation, manual schedule/stop races, and broker restart. |
| Worker status | Fixed safe categories/messages/guidance, UTC occurrence time, phase counts, current failures and most recent history. A successful run cannot clear a scheduling failure. Sync status reads are locked against phase transitions. | `tests/api/test_worker_diagnostics.py`: classification/redaction, phase recovery, concurrent status snapshots, and provider failure retained across no-op polls. |
| Queue status | Read-only aggregate endpoint counts all pending/running/dead-letter/legacy-failed jobs, oldest active job age, safe cause groups and inferred affected products. A failed read returns 503, never invented zero counts. | `tests/api/test_operations_queue_status.py`: 701 pending rows, unchanged stored rows, unknown attribution, redaction, empty/error/future timestamps, UTC normalization. |
| Error presentation | Job-list responses suppress raw error/terminal text using fixed catalog messages. Stored payloads remain intact. | API tests prove secret-like strings stay out of responses and original stored text is unchanged. |
| Operations UI | Always-visible read-only diagnostics, current-versus-history distinction, exact full counts, unavailable-state handling, bounded-retry guidance and scoped responsive spacing. | Component tests and mocked desktop/mobile browser checks; screenshots inspected for the new panel and horizontal overflow. |

## Historical scheduler reconciliation (INF-01)

The current `_due_sentiment_snapshot_assets` SQL already declares alias `s`. Eight new
regressions execute the actual scheduler against initialized database tables, covering all
three snapshot families, exact date/asset scope, pending/running deduplication, completed and
failed jobs, unrelated job scope, per-family limits and repeated scheduling.

The historical binder error did not reproduce with installed DuckDB 1.5.5. There is no
evidence-backed SQL repair in this slice. If it recurs, capture the runtime revision, DuckDB
version, schema and local traceback. The phase-specific status now preserves that failure
even when the runner subsequently succeeds. INF-01's historical root cause remains open;
the plan's original failing-before/passing-after SQL acceptance criterion is not claimed met.

## Verification results

Commands run from the repository root unless marked `web/`:

| Command | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest -q` | 634 passed in 284.89 seconds. This full run preceded the final status-snapshot lock regression. |
| `.\.venv\Scripts\python.exe -m pytest tests/api/test_worker_diagnostics.py -q` | 20 passed after the status-snapshot lock and concurrent-read regression were added. |
| `npm.cmd test` (`web/`) | 100 passed across 22 files. |
| `npm.cmd test -- operationsRoute operationsViewModels` (`web/`) | 15 passed after the final panel spacing/copy edits. |
| `npm.cmd run test:e2e -- operations-diagnostics.spec.ts` (`web/`) | 4 passed: desktop 1440×1000 and mobile 390×900, each testing display and read-only error/recovery refresh. |
| `npm.cmd run build` / `npm.cmd run lint` (`web/`) | Production build and ESLint passed. |
| Python Ruff on changed runtime and regression files | Passed. |
| `.\.venv\Scripts\python.exe -m tools.check_architecture_boundaries` | Passed. |
| `git diff --check` | Passed. |

Browser tests intercept every `/api/v1/` request and reject unexpected mutations. Backend
regressions use synthetic rows, temporary/in-memory databases, subprocesses and stubbed
providers. No production queue recovery is implied by the test counts.

The sandboxed browser run completed its assertions but could not finish server teardown.
The final run with process-management permission completed normally with all four passing.
Screenshots are generated under ignored `web/test-results/`; rerun the committed spec to
recreate them.

## Remaining scope and operational cautions

- Worker history is process-local and resets on restart; queue history stays persisted.
- Queue provider attribution is inferred from allowlisted error signatures, not a provider ledger.
- A worker's idle state is not proof of fresh data or successful provider access. Lower-level
  persisted job failures remain visible in the queue even when a worker loop completes.
- Broker-facing status, other routes' raw-payload presentation, freshness/eligibility policy,
  global health messaging and broad visual redesign remain in their planned later slices.
- Graceful shutdown can wait for an in-flight provider timeout. Forced termination remains
  outside this guarantee.
- The user's running backend was not restarted and live ingestion was not exercised. A server
  restart is required to load backend changes; use the [recovery runbook](../operations/runtime-recovery.md)
  before any explicitly authorized bounded live recovery.

Next: S2's shared evidence/freshness presentation contract, then its dependent route work.
