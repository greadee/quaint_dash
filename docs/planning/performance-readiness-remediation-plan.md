# Performance, Ingestion, and Readiness Remediation Plan

**Source audit:** `docs/evidence/2026-07-23-full-web-performance-audit.md`
**Goal:** restore a completely accountable ingestion queue and readiness state, remove the system-wide API bottleneck, eliminate the measured N+1 paths, and prevent polling or background ingestion from degrading interactive traffic.

This plan intentionally separates queue correctness from performance work. The database and job state must be made trustworthy before pending or failed rows are cleared. “Clear” means every job is moved to a truthful terminal state or completed; it does not mean deleting evidence of failures.

## Target end state

The work is complete only when:

- `pending = 0`, `running = 0`, and legacy `failed = 0`.
- Every previously failed job is classified as succeeded, superseded, cancelled, unsupported, or dead-lettered with an explicit reason.
- Every required, provider-supported readiness input for every tracked target is present and current.
- Unsupported data is represented as `unsupported`, not retried forever or falsely reported as ready.
- No worker can remain `running` indefinitely after a crash.
- No duplicate active job can exist for the same work key.
- Provider calls never occur while the interactive database writer lock is held.
- Ordinary reads do not acquire the application writer lock.
- Interactive endpoints meet the query-count, latency, payload, and request-count budgets from the audit.
- Hidden routes do not poll, abandoned requests are cancelled, and polling cannot create a persistent backend queue.
- The full data-health workflow, 53-route browser scan, backend tests, frontend tests, and live browser review all pass.

## Architectural decisions

### Queue and readiness

Use one durable state machine for all market, corporate, sentiment, ranking, and readiness work. The current implementations have incompatible claim rules and retry behavior. In particular, the market worker only claims jobs with `attempt_count = 0`, while retrying a failed job changes only its status; that can create permanently pending work.

Adopt these terminal and active states:

- `pending`: eligible when `next_attempt_at <= now()`.
- `leased`: atomically owned by one worker until `lease_expires_at`.
- `succeeded`: data was persisted and sync state advanced.
- `superseded`: newer successful work covers this job.
- `unsupported`: provider or subscription cannot supply the dataset.
- `cancelled`: intentionally removed from scope.
- `dead_letter`: retry budget exhausted or integrity intervention required.

Keep legacy status mapping during migration, but stop creating new `running`, `done`, and `failed` rows once all callers use the state machine.

### DuckDB concurrency

Do not simply delete the application lock.

The preferred design is:

1. Open one application-owned DuckDB base connection during FastAPI lifespan.
2. Give each synchronous request a short-lived cursor derived from that persistent base connection.
3. Let read-only handlers use independent cursors without the writer lock.
4. Retain one narrow writer lock for short claim/persist/commit transactions.
5. Perform external provider calls and CPU-heavy transformations outside the writer lock.
6. Close cursors after requests and close the base connection during lifespan shutdown.

DuckDB cursors from a shared connection must pass concurrent read and read/write stress tests before this replaces the existing dependency. If it does not remain correct under the project’s threadpool and ingestion load, use a dedicated single-writer command queue plus read cursors. A periodically refreshed read replica is the fallback, not the first choice.

### N+1 and progressive loading

Pagination must be applied before expensive work. Calculating the full universe and slicing the response afterward is not an optimization.

Use three patterns:

- **Small summaries:** one set-based query or a versioned snapshot, with no per-row analytics.
- **Collections:** cursor pagination, usually 20–25 items, with stable sort and `next_cursor`.
- **Heavy detail:** load only after the user opens the tab, expands the row, or asks for more history.

Expensive deterministic analytics should follow:

`source change → derived-data job → versioned snapshot → interactive read`

## Phase 0 — Safety, baselines, and recovery tooling

1. Stop ingestion, readiness, freshness, and broker workers through their normal stop commands.
2. Stop the API cleanly so DuckDB releases the database file.
3. Copy the database and verify the backup can be opened read-only.
4. Export a queue ledger containing counts and IDs by status, domain, dataset, attempt count, age, and normalized error class.
5. Export readiness coverage by target and required input.
6. Record the current endpoint/query/payload baselines using the two audit profilers.
7. Add a recovery command with `--dry-run`, `--apply`, and JSON output. It must never delete `asset_sync_state`.
8. Add a migration rollback or backup-restore procedure before changing job schema or indexes.

**Gate:** no mutation proceeds until the backup opens successfully and dry-run reconciliation accounts for every queue row.

## Phase 1 — Make the ingestion state machine crash-safe and idempotent

### Schema

Add:

- `work_key`: deterministic hash/key of domain, dataset, asset, job type, and requested range.
- `lease_owner`, `leased_at`, and `lease_expires_at`.
- `next_attempt_at`, `max_attempts`, and retained `attempt_count`.
- `error_code`, `error_class`, and bounded/sanitized `error_message`.
- `completed_at` and optional `superseded_by_job_id`.
- a current-work table keyed by `work_key`, or an equivalent uniqueness mechanism that guarantees one active job per key.

Do not depend on a partial unique index unless the pinned DuckDB version proves it supports the required predicate correctly. A separate current-work table with a primary key is safer.

### Claim and completion

1. Replace `SELECT pending` followed by `UPDATE running` with one atomic claim transaction using a conditional `UPDATE … RETURNING`.
2. A claim succeeds only if the row is still pending and eligible.
3. Release the transaction and writer lock immediately after leasing.
4. Fetch provider data outside the lock with explicit connect/read timeouts.
5. Reacquire the writer lock for an idempotent upsert plus job/sync-state completion in one transaction.
6. On startup and each scheduler tick, reclaim expired leases:
   - retry if attempts remain and the error is retryable;
   - otherwise move to `dead_letter`.
7. Use exponential backoff with jitter for retryable network, timeout, 429, and provider 5xx failures.
8. Classify subscription/plan failures such as HTTP 402 as `unsupported`, not failed.
9. Bound retry count and error size. Never requeue a permanent failure.
10. Remove the market-only `attempt_count = 0` claim rule. Eligibility becomes `attempt_count < max_attempts`.

### Scheduler correctness

1. Make enqueue idempotent by `work_key`.
2. Prevent the readiness worker and routine scheduler from enqueuing the same work.
3. Do not warm stock rankings synchronously inside the routine scheduling lock; schedule a snapshot job instead.
4. Ensure only one scheduler instance is active for a database.
5. Add a heartbeat and worker ID to status output.

### Tests

- Two workers racing to claim one job: exactly one lease.
- Crash after claim: lease expires and work is recovered.
- Crash after provider fetch but before persist: idempotent retry produces one data result.
- Retried market job is claimable.
- Permanent 402/unsupported work is never requeued.
- Retryable errors use bounded attempts/backoff.
- Duplicate schedule requests create one active work item.
- Job success and `asset_sync_state` success commit together.
- Job failure cannot erase a newer success.
- Error and status transitions satisfy a transition table/property test.

**Gate:** state-machine tests pass for market, corporate, and sentiment domains before current jobs are touched.

## Phase 2 — Reconcile and completely clear the existing queue

Run this only after Phase 1 is deployed.

1. Reclassify stale `running` rows as expired leases.
2. Group active rows by work key:
   - keep the newest/highest-priority valid row;
   - mark redundant rows `superseded`;
   - do not delete the history.
3. For each failed row:
   - mark covered by a newer success as `superseded`;
   - mark plan/subscription/provider-unavailable errors `unsupported`;
   - requeue transient failures with a valid retry budget;
   - move integrity/data-contract failures to `dead_letter` for explicit repair.
4. Repair the DuckDB ingestion-job index mutation problem while the API is stopped:
   - verify table integrity and duplicate primary/work keys;
   - recreate only the affected queue index after backup;
   - reopen read-only and validate all row counts;
   - run a small claim/complete transaction before full recovery.
5. Process retryable work in bounded batches. Respect provider rate limits and persist progress after every job.
6. Resolve dead letters one error class at a time. Do not globally retry them.
7. Archive terminal history older than the retention period into an audit table/file. Purge only after row-count reconciliation and only if database size/maintenance requires it.
8. Never call the current `clear_ingestion_history()` as the recovery mechanism because it deletes both job history and `asset_sync_state`.

**Queue-clear gate:**

- active pending: 0;
- active leased/running: 0;
- legacy failed: 0;
- expired leases: 0;
- duplicate active work keys: 0;
- every original job ID appears in the reconciliation ledger;
- terminal unsupported/dead-letter work has a reason and is not counted as silently ready.

## Phase 3 — Rebuild readiness as a complete, fair pipeline

### Define the readiness contract

Create a manifest that defines, by asset type and feature, which inputs are:

- required;
- optional;
- unsupported by design;
- subject to freshness windows;
- sufficient when the provider returned an authoritative empty result.

Readiness states should be `ready`, `pending`, `stale`, `unsupported`, `error`, or `not_applicable`. A global “ready” result means all required, supported inputs are ready—not that missing data was hidden.

### Remove readiness N+1 queries

Replace per-asset checks with set-based snapshots:

1. Load target assets once.
2. Aggregate price coverage by asset in one query.
3. Aggregate statement coverage and latest dates by asset/type in one query.
4. Load asset metadata/shares in one query.
5. Load sync state in one query.
6. Load active/latest jobs in one query.
7. Join these results in SQL or one bounded in-memory merge.
8. Persist a `readiness_snapshot` keyed by target, requirement, and source version.

Target: no more than 20 queries for a full readiness refresh and no more than 5 for a paged interactive read.

### Guarantee fair coverage

The current worker always slices `_valuation_targets(... )[:max_assets_per_tick]`, which can starve targets after the first 50. Replace this with:

- a persisted cursor or `last_checked_at`;
- missing/stale targets first;
- oldest checked next;
- deterministic tie-breaking;
- progress fields `total`, `examined`, `ready`, `pending`, `unsupported`, `error`, and `next_cursor`.

Every target must be examined within a bounded number of ticks.

### Separate scheduling, ingestion, and calculation

1. Readiness inspection detects gaps and creates idempotent work items only.
2. Provider workers ingest gaps independently.
3. Derived analytics jobs run after source versions advance.
4. Readiness snapshots update after successful commits.
5. The worker never calls `yfinance` or another provider directly while holding a database lock.
6. Portfolio valuations run only for assets whose required inputs are ready.
7. A failed valuation creates a derived-data job error; it does not corrupt source readiness.

### Complete the backfill

After the new pipeline is deployed:

1. Generate the complete target/requirement matrix.
2. Schedule only genuinely missing or stale supported inputs.
3. Run bounded ingestion until no supported gaps remain.
4. Run derived portfolio, risk, fundamentals, ranking, and signal snapshot jobs.
5. Recompute readiness.
6. Repeat until the matrix converges with zero pending/error states.
7. Produce a final exception list for unsupported/not-applicable requirements.

**Readiness gate:** 100% of required supported inputs are ready; pending/error is zero; unsupported/not-applicable rows are explicit; a second no-change run schedules zero jobs.

## Phase 4 — Remove interactive read contention safely

1. Add separate `get_read_cursor` and `get_write_cursor` dependencies.
2. Move health to a persistent read cursor or an in-memory process/database health snapshot.
3. Migrate GET handlers to read cursors.
4. Mark mutation routes explicitly and keep their transactions short.
5. Refactor workers into:
   - short atomic claim;
   - unlocked provider/CPU phase;
   - short atomic persist.
6. Record `writer_lock_wait_ms`, `connection/cursor_acquire_ms`, and transaction duration.
7. Add cancellation checks before expensive post-query transformations.
8. Run:
   - 8/20/50 concurrent health/read calls;
   - reads during ingestion claims and commits;
   - worker crash/restart;
   - long analytical reads during short writes;
   - database integrity checks afterward.

**Decision gate:** retire the whole-request lock only if concurrent tests show correct results, zero write conflicts/corruption, and interactive p95 remains within budget. Otherwise use the dedicated writer queue fallback.

**Target:** health p95 below 50 ms locally and 8-way health tail below 250 ms.

## Phase 5 — Eliminate N+1 work and add progressive loading

| Endpoint family | Current issue | Backend change | UI/loading boundary | Query target |
| --- | --- | --- | --- | ---: |
| `/overview/updates` | 916 queries | One set-based overview read from portfolio/data-version summaries | Render headline cards first; defer news/readiness details | ≤20 |
| `/portfolios` and aggregate overview | 914 queries; projection calculated per portfolio | Read one portfolio summary table/query; remove live `portfolio_report()` | Six summaries load immediately; projections on expand or from snapshot | ≤20 |
| Portfolio detail/positions/transactions | 135–137 queries | Batch prices, metadata, broker mappings, gains; cursor-page transactions | Default 20–25 rows; “Load more” appends | ≤20 |
| Portfolio performance/risk/fundamentals | 270–405 queries | Read versioned analytics snapshots; calculate after source changes | Fetch only active tab; default period first; longer history on request | ≤20 |
| Holding signals | 711 queries | Join stored signal evaluations to holdings | First 20 holdings; grades/evidence on expand | ≤20 |
| `/signals` | 4,718 queries before slicing | Query stored `signal_evaluation` with SQL filters/sort/cursor | First 25; “Load more”; summary counts from snapshot | ≤10 |
| `/signals/:id` and signal mutations | 5,247 queries for one signal | Direct indexed lookup plus small evidence/history queries | Detail only when opened | ≤10 |
| Stock rankings | Full-universe calculation on request | Read `stock_ranking_snapshot`; refresh asynchronously | First 25; load more; explicit refresh action | ≤10 |
| `/ingestion/readiness` | 1,781 queries and 101 KB | Read readiness summary plus paged details | Summary counts first; default 25 missing/stale items | ≤5 read |
| Ranking readiness | Per-asset checks | Set-based snapshot | First 25 gaps; load more | ≤5 read |
| Asset analytics | 36 queries/live compute | Read asset analytics snapshot by version | Summary first; calculation details on expand | ≤10 |
| Comparison | 63 queries and 57 KB | Batch all selected symbols; section projection | Visible comparison metrics first; fundamentals/history on tab | ≤20 |
| Benchmark prices/metrics | 315 KB + 197 KB | Default date window and server downsampling | Default chart window; “Load full history” action | ≤5 |
| Streaming status | 17 DB queries | Keep live worker/socket counters in memory; fetch subscription details separately | Status immediately; details on expand | ≤5 |
| Broker import/reconciliation | 168 KB, 6,289 DOM nodes | Cursor-page account/group details; summary counts | Collapsed groups, 25 rows, load more; virtualize | ≤10 |
| Ingestion jobs | First-page details polled repeatedly | Set-based totals endpoint plus cursor detail page | Counts first; detail only on Operations tab/filter | ≤5 |

API collection envelope:

```text
items
next_cursor
has_more
total
summary
data_version
generated_at
```

Use keyset cursors rather than large offsets on growing tables. Enforce server-side maximum limits. Apply filters and limits in SQL before constructing models or analytics objects.

### Snapshot lifecycle

Enable and complete the existing analytics snapshot infrastructure rather than adding a second ad hoc cache:

- Extend source signatures to include positions/transactions, latest price dates, benchmark version, fundamentals version, and model version.
- Refresh portfolio/asset snapshots after relevant source commits.
- Make signal and stock-ranking snapshot refreshes explicit derived jobs.
- Expose snapshot freshness and source version in API responses.
- Fall back to the last complete snapshot with a visible stale marker; do not block the page on recomputation.

## Phase 6 — Replace polling storms with version-aware refresh

### Request cancellation

1. Change every query function to accept TanStack Query context.
2. Pass `context.signal` through `request()` to `fetch`.
3. Treat `AbortError` as cancellation, not a user-facing failure.
4. Add tests proving route changes abort requests and free backend work.

### Polling policy

Replace the current seven 10-second Operations queries and multiple 60-second route queries.

| Data | New schedule |
| --- | --- |
| In-memory worker summary | One combined `/operations/status-summary`; 15 s while a worker is active, 60 s while idle, visible tab only |
| Job/readiness detail | Fetch on Operations entry, filter/page change, mutation success, or summary `data_version` change; no fixed 10 s polling |
| Overview/portfolio market data | One lightweight data-version check every 60 s while visible and every 5 min when idle; invalidate only affected queries |
| News | 5 min while the News route is visible, plus explicit refresh/mutation invalidation |
| Heavy analytics, signals, rankings | No timer polling; source-version invalidation or explicit refresh |
| Hidden/background tabs | No polling (`refetchIntervalInBackground: false`) |

Add jitter so multiple timers do not fire together. Back off to 2–5 minutes after errors. Pause polling when the document is hidden or offline. Mutations invalidate only exact affected keys.

### Cache policy

- Keep stable query keys.
- Use longer stale times for versioned snapshots.
- Add private ETags/conditional GETs based on `data_version`.
- Keep previous pages while cursor pagination loads more.
- Bound retained pages and garbage-collect inactive detail queries.

**Gate:** a five-minute idle Operations session produces only lightweight summary calls; no heavy readiness/job query repeats without a version change.

## Phase 7 — Verification and release

### Correctness

1. Run all queue/state-machine/readiness unit and integration tests.
2. Verify queue counts and reconciliation ledger.
3. Verify readiness matrix and derived snapshot freshness.
4. Run the full mandated workflow:

```text
.\.venv\Scripts\python.exe tools\run_full_data_health_workflow.py --cycles 4 --run-batches 10 --external-audit --json
```

5. Run the web data-health scan:

```text
cd web
npm.cmd exec -- node ..\tools\scan_web_app_data_health.mjs
```

No pending/running/legacy-failed jobs, missing supported readiness, null critical metrics, failed optimization previews, missing subscribed prices, console errors, `Unavailable`, or stuck loaders may remain.

### Performance

1. Run endpoint latency and query profilers.
2. Compare every changed endpoint to the audit baseline.
3. Run production build and local production-mode browser audit.
4. Test 10 repeated tab switches and at least 50 route changes.
5. Test active ingestion while browsing every major route.
6. Confirm:
   - cached repeat navigation ≤300 ms;
   - core GET p95 ≤500 ms;
   - heavy analytical GET p95 ≤1.5 s;
   - visible page complete ≤2.5 s;
   - no ordinary GET calls a provider;
   - no endpoint exceeds its query/payload budget;
   - memory, threads, handles, cursors, leases, and request counts stabilize.

### Live UI review

Refresh `http://127.0.0.1:5173` and inspect all affected pages plus nearby navigation. Check the API health endpoint, browser console, loading/error/empty states, pagination/load-more behavior, stale indicators, Operations job totals, and readiness explanations.

## Delivery sequence

Implement as small reviewable changes in this order:

1. Add state-machine tests and recovery dry-run.
2. Add schema/state migration and atomic lease behavior.
3. Reconcile the queue and repair the affected index.
4. Drain/reclassify all current jobs.
5. Replace readiness N+1/fairness logic and complete the backfill.
6. Add persistent read cursors and narrow writer transactions.
7. Wire request cancellation and replace polling.
8. Convert portfolio/overview endpoints to set-based summaries/snapshots.
9. Convert signals/rankings and readiness endpoints to snapshot-backed cursor pagination.
10. Convert remaining heavy endpoint families and broker/benchmark rendering.
11. Run the complete correctness, data-health, performance, and browser gates.

Do not combine queue recovery with broad endpoint changes in one commit. Each stage needs its own before/after evidence and a rollback point.
