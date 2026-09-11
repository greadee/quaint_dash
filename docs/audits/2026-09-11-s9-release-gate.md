# S9 end-to-end reconciliation and release gate

Date: 2026-09-11

Slice: S9 — end-to-end reconciliation, operations drill, and release gate

Audit coverage: DQ-01–DQ-09, BR-01–BR-02, INF-01–INF-05, UX-01–UX-11

## Outcome

The audited remediation wave passes its code release gate. Seeded browser scenarios now prove one consistent story from shell and Overview health through Operations, affected decision surfaces, and broker resolver links. A controlled recovery drill against a temporary DuckDB database proves a stored failure is presented through a redacted safe category, retried through the existing bounded recovery endpoint, and returned to pending state without provider traffic.

The live local dataset is **not healthy**, and the application does not claim that it is. The final rendered walkthrough showed nine active incidents, 507 queued jobs, a six-day oldest backlog, seven dead-letter jobs, stale benchmark evidence, unavailable social sources, and broker-review work. These are operational/data follow-ups rather than hidden release defects; the UI leads with them and keeps affected outputs non-decisioning.

No financial formula, investment threshold, metric value, database schema, persistence contract, import-idempotency rule, or raw-payload retention behavior changed. The only production code changes in S9 are an injectable CLI database path for test isolation and frontend route-level lazy loading.

## Pass 1 — seeded end-to-end scenario matrix

`web/e2e/release-gate.spec.ts` intercepts every `/api/v1/**` request, aborts unexpected or non-GET requests, and supplies deterministic fixtures. The same matrix runs at 1440 × 1000 desktop, 768 × 1024 tablet, and 390 × 900 mobile.

| Scenario | Cross-surface proof |
| --- | --- |
| Current real sources | Overview and Operations report `Data health is clear`, zero queue work, and no false incident. |
| FMP rate limit and degraded/stale news | Shell remains critical; News leads with the rate-limit state, labels fixture content, and omits the placeholder external link. Operations names provider impact and bounded guidance. |
| Missing Reddit/X credentials and zero posts | Retail states that no usable configured evidence exists, suppresses the supplied unsupported count, disables retail inclusion, and Operations names the configuration gap. |
| Stale monthly signal and no efficacy sample | Signal detail retains the record for audit, explicitly states the zero-size efficacy sample, and disables alert/review decision actions. |
| Proxy-only/stale benchmarks | Benchmarks leads with `Benchmark evidence blocked`, removes ranked winners, retains values only for audit, and disables comparison selection. |
| Incomplete model inputs and contradictory confidence | Asset Fundamentals leads with the missing-input gate and marks otherwise-confident numeric results as calculation audit only. Business Strength independently demotes a high stored aggregate to secondary confidence and names its missing critical input. |
| Pending/dead-letter work and a disabled worker | Overview links into the exact Operations incident; Operations reports 355 queued jobs, rate-limit groups, affected products, and worker state without running work. |
| Account and asset reconciliation blockers | Broker review exposes account assignment and asset resolver paths with preserved queue context and pagination. |
| Adversarial provider object | Broker UI renders only the normalized instrument label and rejects `FIGI`, logo URL, provider-object, and secret-shaped content. Backend allowlist/model tests independently enforce the same boundary. |

All nine seeded routes also pass a document-level overflow assertion at every viewport. The existing S8 suite independently retains 21 pixel baselines, accessible icon-action checks, keyboard navigation, collapsed broker-import disclosures, and the direct `New portfolio` regression.

## Pass 2 — controlled DuckDB operations drill

`tests/api/test_s9_release_gate.py` creates a new database under Pytest's temporary directory and inserts one synthetic failed market job. It then performs the full allowed sequence:

1. Read queue status and observe one safely categorized failure.
2. Prove the stored token-shaped diagnostic is absent from the response.
3. Call the existing `/api/v1/ingestion/retry-failed` action with `domain=market` and `max_jobs=1`.
4. Read the post-recovery status and observe zero failed plus one pending job.
5. Inspect persistence and confirm the existing retry contract: status `pending`, attempt count unchanged at `1`, error cleared.

No live database, provider, calculation function, or new recovery behavior is involved.

The full backend run initially exposed a separate test-harness DuckDB risk: `test_cli_isAlive` opened `data/persistent_db.db` while the running API owned it. `cli_loop` now accepts an optional database path, defaulting to the exact existing production path, and the smoke test injects a temporary path. The complete suite subsequently passed while the live API continued to hold the production database lock. This is stronger evidence than passing only after stopping the app.

INF-01's historical `s.snapshot_date` log failure still cannot be reproduced against the current schema/query implementation. S9 closes the release risk on the evidence available: the current scheduler regressions pass, no invalid alias exists in the current scheduling source, lock ownership produces an explicit safe error, worker failure history remains visible, and the complete suite passes under a real external production-DB lock. This is not a claim about the unknowable historical root cause.

## Pass 3 — live rendered reconciliation

Computer-assisted read-only inspection used the running API and web service. No manual worker, retry, refresh, broker import, mapping, seed, or harden control was invoked.

- Operations: `critical`, nine incidents, 507 queued, six-day oldest backlog, seven dead letters, workers enabled 3/3 and currently idle. Safe provider/error guidance and affected products were visible before manual controls.
- Benchmarks: all 34 visible rows were stale or blocked; `Fresh data 0/34` and `Proxy coverage 34` led the page. High returns remained visible only behind `Benchmark Evidence Blocked`, no leader/risk ranking was chosen, and every comparison action was disabled.
- Brokers: import scope started collapsed; the page reported 2,806 needing review and rendered separate queue counts for 629 account assignments, 350 asset resolutions, 1,876 unsupported/invalid items, and 59 ready items. Resolver links retained account and transaction context. Reconciliation displayed concise symbol/name/exchange/currency labels rather than provider objects.
- Portfolios: the aggregate page still exposes the direct `New portfolio` action in the page title area.

The live page remains open on `/portfolios?tab=portfolios` for user review.

## Pass 4 — performance and production packaging

The live benchmark profile was rerun with the S7 budgets and 250 ms injected API latency.

| Measure | S7 observation | S9 observation | Budget | Result |
| --- | ---: | ---: | ---: | --- |
| Route ready | 551.49 ms | 546.4 ms | < 1,000 ms | Pass |
| Initial benchmark requests | 1 | 1 | ≤ 1 | Pass |
| Initial total page requests | 2 | 2 | ≤ 2 | Pass |
| Summary payload | 42,331 bytes | 42,331 bytes | < 300,000 bytes | Pass |
| Eager detail requests | 0 | 0 | 0 | Pass |

The remaining S7/S8 build advisory was also closed. Route components now load through React `lazy`/`Suspense`; the initial application chunk fell from 512.77 kB to 233.53 kB minified. The largest chunk is the existing chart vendor at 433.04 kB, below the 500 kB advisory threshold. All route, visual, accessibility, and browser tests pass after the packaging change.

## Pass 5 — audit closure matrix

| Audit IDs | Release evidence | Status |
| --- | --- | --- |
| DQ-01, INF-02, INF-04, UX-03 | Healthy and combined-critical browser fixtures; shared Overview/Operations path; live critical incident readout | Closed |
| DQ-02 | Missing Reddit/X fixture suppresses counts and decision inclusion; provider state visible in Operations | Closed |
| DQ-03, DQ-09 | Stale zero-efficacy signal fixture disables writes and leads with audit-only state | Closed |
| DQ-04, INF-03 | Proxy/stale benchmark fixture, live blocked catalog, request/payload/latency profiler | Closed |
| DQ-05, DQ-08 | Rate-limited news fixture, fixture label, placeholder-link suppression, affected-source health | Closed |
| DQ-06, DQ-07 | Incomplete financial-statement fixture gates asset analytics while preserving calculation output | Closed |
| BR-01, INF-05 | Adversarial API/model and browser assertions; live normalized reconciliation | Closed |
| BR-02 | Account and asset queues, paginated fixture, scoped resolver links, live queue walkthrough | Closed |
| INF-01 | Current scheduler regression, safe failure history, isolated recovery drill, full suite under live DB lock | Closed with historical-cause caveat documented above |
| UX-01, UX-04, UX-06, UX-08, UX-09, UX-10, UX-11 | S8 pixel/accessibility suite plus S9 route overflow matrix at all three breakpoints | Closed |
| UX-02, UX-05 | Existing asset/compare evidence tests plus S9 incomplete/stale downstream fixture | Closed |
| UX-07 | Direct `New portfolio` browser regression and live rendered confirmation | Verified; no defect |

No P0 audit finding remains open. No supplied critical fixture can report healthy. No normal broker response or rendered reconciliation contains raw provider objects. There are no deferred P1/P2 code items from the audit.

## Operational follow-ups

These do not block the code release because the product exposes them truthfully and prevents unsafe decision presentation. They do block describing the current local data as healthy.

Tracking links: [OPS-01](#ops-01-queue-and-dead-letter-recovery), [OPS-02](#ops-02-provider-access), [OPS-03](#ops-03-stale-analytical-evidence), and [OPS-04](#ops-04-broker-review-backlog).

### OPS-01: queue and dead-letter recovery

- Owner: local application operator.
- Issue: seven dead-letter jobs and 507 queued jobs, oldest six days.
- Rationale: recovery can contact providers and mutate local job state, so S9 did not execute it without explicit approval.
- Product-safe interim state: global critical status, read-only cause groups, affected products, and bounded recovery guidance.

### OPS-02: provider access

- Owner: local application operator / provider-account owner.
- Issue: FMP news failure/rate limit and missing Reddit/X configuration.
- Rationale: credentials, plan access, and quota decisions are external to this code slice.
- Product-safe interim state: provider incidents are promoted globally; fixture/social outputs are non-decisioning.

### OPS-03: stale analytical evidence

- Owner: ingestion operator.
- Issue: benchmark and signal evidence needs a successful current-source refresh.
- Rationale: live refresh would use provider traffic and write new observations.
- Product-safe interim state: benchmark leadership is suppressed, comparison buttons are blocked, and stale signal actions are disabled.

### OPS-04: broker review backlog

- Owner: portfolio/account owner.
- Issue: live review queues contain account, asset, and unsupported-activity blockers.
- Rationale: mapping and importing require user decisions and can change financial records.
- Product-safe interim state: the queue is read-only, paginated, context-preserving, and separate from the confirmed import action.

## Exact verification results

- `python -m pytest -q` — 681 passed in 291.35 s while the running API held `data/persistent_db.db`.
- S9/baseline backend selection — 49 passed.
- CLI isolation plus S9 drill — 4 passed.
- `python -m ruff check ...` — passed for every S9 Python file.
- `npm test` — 23 files, 116 tests passed.
- `npm run lint` — passed.
- `npm run build` — passed with no chunk-size advisory.
- `npm run test:e2e` — 76 passed, 2 intentional non-mobile skips.
- S9 Chromium-only development run — 6 passed before the full three-project run.
- `npm run perf:benchmarks` — all route-ready, request-count, response-status, payload, and no-eager-detail checks passed.
- `git diff --check` — passed before documentation; rerun in final gate.

## Boundaries retained

- Financial output values and functions are unchanged; `tests/api/test_evidence_contract_baseline.py` passes inside the full suite.
- No database schema or persistence semantics changed.
- Broker mapping/import mutations and raw-payload retention remain unchanged.
- Route splitting changes JavaScript delivery boundaries only.
- CLI's default database remains `data/persistent_db.db`; only tests inject an isolated path.
- Seeded browser fixtures are read-only and cannot contact providers or mutate local state.
