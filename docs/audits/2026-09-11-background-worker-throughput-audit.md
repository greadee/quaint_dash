# Background worker and queue-throughput audit

Date: 2026-09-11

Scope: the desktop launch path, routine ingestion worker, holding-price worker, portfolio-data worker, queue claiming, retry behavior, cadence, throughput, and Operations observability. Financial calculations and persistence contracts were out of scope and were not changed.

## Outcome

The overnight queue did not drain because the workers started from Operations were never given an active background task. The `start` endpoints called `enable()`, which changed the displayed flag, but did not call `start()`. That made the controls report success while automatic work remained idle.

The remediation makes all three Start actions create their real background task. It also changes routine ingestion from a fixed idle cadence to a productive-backlog cadence: after a cycle completes work and pending jobs remain, the worker follows up after one second instead of sleeping for the normal 60-second source default or five-minute example configuration. Once progress stops or the queue clears, it returns to the conservative idle cadence.

The target is 500 queued jobs in under one hour when providers are available and average job time stays below seven seconds. External rate limits, unavailable credentials, or provider failures can still prevent that SLA; the application now surfaces those as blockers rather than pretending the worker is running.

## Pass 1: shared desktop entry point

The requested launch was attempted only through Windows desktop-app control. Native application control was unavailable in this session, so no terminal substitute was launched.

The installed shortcut is also stale:

- Shortcut: `C:\Users\prool\Desktop\Quaint Dash.lnk`
- Current target: `C:\Users\CodexSandboxOffline\quaint_dash\scripts\qd.cmd desktop`
- Expected repository target: `C:\Users\prool\quaint_dash\scripts\qd.cmd desktop`

The service already listening on port 8000 is a global Python 3.14 process, not the repository `.venv` process used by `scripts\qd.cmd desktop`. It started at 2026-09-11 14:19 local time. Its data was useful for read-only diagnosis, but it is not accepted as post-fix desktop-entry validation.

Required local follow-up: reinstall the shortcut from this checkout with `scripts\qd.cmd install-desktop`, then start Quaint Dash from the repaired desktop shortcut. This rewrites the shortcut target; it was not done during this audit because the desktop file is outside the repository and the user requested one shared launch path.

## Pass 2: live queue evidence

Read-only API observations from the running service:

- Pending: 507
- Running: 0
- Failed: 0
- Dead letter: 7
- Oldest pending job: 2026-09-04 15:04:43
- All 507 pending jobs have never been claimed; all sampled and domain-complete results have `attempt_count = 0`.
- The newest completed job is dated 2026-07-30. There is no evidence of an overnight queue completion.

Exact pending composition:

| Domain | Dataset | Jobs |
| --- | --- | ---: |
| market | dividends | 84 |
| market | splits | 84 |
| market | price_daily | 57 |
| corporate | earnings_calendar | 57 |
| corporate | financial_statements | 11 |
| corporate | earnings_actuals | 9 |
| sentiment | factor_snapshot | 75 |
| sentiment | quant_rating | 75 |
| sentiment | sentiment_daily | 55 |
| **Total** | | **507** |

The seven dead-letter jobs are FMP financial-statement jobs that reached the configured retry limit after provider-rate-limit failures. They are separate from the 507 never-attempted pending jobs.

## Pass 3: worker responsibilities

### Routine ingestion worker

This is the primary queue consumer. It schedules bounded due work and claims pending market, corporate, and sentiment jobs.

Before this fix, a UI start changed `enabled` to true without starting `_run_loop`. Even if started through environment configuration, the source default could process at most five jobs per 60-second idle interval, or 300 jobs/hour before provider time. The example configuration was more restrictive: one job every 300 seconds, or 12 jobs/hour. Neither meets the requested SLA.

### Holding-price worker

This worker refreshes current held-asset prices directly through Yahoo and writes current/daily price observations. It does not claim ingestion-queue rows. Its visible API traffic therefore looked like worker activity without reducing the 507-job queue.

### Portfolio-data worker

This worker identifies missing valuation inputs, schedules new ingestion jobs, processes bounded batches, and recalculates existing portfolio views. It can add and complete work in the same cycle, so the gross queue count can remain flat. Routine ingestion remains the primary backlog drainer.

All three workers share the API process write lock. That deliberately serializes DuckDB writes and prevents unsafe concurrent writers. Provider calls also occur inside those bounded worker operations. The lock limits parallelism but does not prevent the one-hour target at the configured provider policies when providers are healthy.

## Pass 4: throughput budget

The remediated routine worker retains bounded batches and provider rate limiting, but removes idle sleeps while work is succeeding:

- Source default batch: 5 jobs
- Productive-backlog follow-up: 1 second
- 500 jobs require 100 batches
- Configured inter-batch wait: 99 seconds total
- Remaining one-hour budget for job execution: 3,501 seconds
- Maximum average execution time while meeting the target: approximately 7.0 seconds/job

The current provider policies are 30 Yahoo calls/minute with a 1.5-second minimum interval and 45 FMP calls/minute with a 1.25-second minimum interval. The current queue has 225 market jobs, 77 corporate jobs, and 205 local sentiment-derived jobs. Healthy-provider rate limiting therefore leaves substantial margin under one hour. Provider timeouts, entitlement failures, and exhausted external quotas remain legitimate blockers rather than performance bugs.

## Pass 5: remediation

- All Operations Start commands now call both `enable()` and `start()`.
- Routine ingestion uses the one-second productive-backlog cadence only while a cycle completes jobs and more pending work remains.
- A zero-progress or empty cycle returns to the normal idle cadence, avoiding a busy loop against a blocked provider.
- Operations health now treats `enabled = true` plus `running = false` as a critical incident.
- Routine-worker status records start time, last queue progress, and completed jobs since start.
- Operations explains that holding-price refreshes do not consume the queue and that portfolio-data work may enqueue missing inputs.
- `.env.example` documents `INGESTION_BACKGROUND_BACKLOG_INTERVAL_SECONDS=1`.

## Verification

- Full Python suite: 683 passed in 283.18 seconds.
- Worker/API/health Python selection: 82 passed after the final status-counter addition.
- Full frontend unit suite: 23 files and 116 tests passed.
- Full Playwright suite: 76 passed across desktop, tablet, and mobile; two platform-specific cases were intentionally skipped.
- ESLint, TypeScript, production build, Ruff, and architecture boundaries: passed.
- A regression budget proves 500 jobs incur only 99 seconds of configured inter-batch waiting at the source-default batch size.
- Rendered post-restart verification remains pending because the stale desktop shortcut could not be launched through the unavailable native-app control surface. No substitute service was launched.

## Remaining operational blockers

1. Repair the stale desktop shortcut and restart through it so the service uses this checkout and its `.venv`.
2. Review the seven FMP dead letters after confirming provider quota/entitlement. They should not be blindly retried while access remains blocked.
3. Observe `Completed since start`, `Last queue progress`, pending count, and worker state for at least two refresh intervals. A healthy drain must show `running`, a rising completed count, and a falling pending count.
4. If average job time exceeds seven seconds, profile the specific provider/dataset before increasing concurrency. DuckDB remains single-writer by design.
