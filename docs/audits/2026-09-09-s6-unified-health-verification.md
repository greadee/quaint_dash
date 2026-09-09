# S6 unified health verification

Date: 2026-09-09

Branch: `phase5-prediff`

Audit coverage: DQ-01, INF-02, INF-04, UX-03, UX-11

## Outcome

S6 is implemented and verified locally. Overview, Operations, and the persistent application shell now consume one read-only health summary. Overview no longer treats an empty legacy failed-job query as proof that data is healthy.

The live local database correctly produced a `critical` summary rather than a green state. At verification time it reported 375 queued jobs, a five-day oldest backlog, zero of three automatic workers enabled, seven dead letters, an FMP provider-rate-limit group, a failed FMP news source, stale benchmark evidence, stale cached signals, and missing Reddit/X credentials. The response identified eight affected products and linked directly to the focused pending-job view.

## Severity policy

The policy in `dashboard.application.operations.build_operations_health_summary` is explicit and independently testable:

- one or more dead letters is critical;
- an enabled provider failure is critical;
- a worker in failed, blocked, or misconfigured state, or with a current phase failure, is critical;
- pending work older than one hour while routine ingestion is disabled is critical;
- active backlog, stale essential benchmark evidence, stale providers, stale cached signals, and missing optional social credentials are warnings;
- intentionally disabled workers with no old blocked backlog are informational and do not make the system unhealthy by themselves;
- a failed unified health read is unavailable, never a zero/healthy fallback.

The response is additive and read-only. It combines S1 queue/worker diagnostics and S2 benchmark evidence states. It does not schedule, claim, retry, clear, or run work.

## User-path verification

The browser check used the production-like local state at `http://127.0.0.1:5173`.

1. Overview showed “Data health needs immediate attention,” the primary reason, all affected product domains, nine active incidents, and a “Review data status” link.
2. Following that link opened `/operations?incident=blocked-backlog&status=pending#operations-health`.
3. Operations highlighted the selected incident, showed backlog count/age, dead letters, enabled-worker coverage, affected-product count, and a safe next step.
4. The job table was filtered to `Pending`; no recovery action ran during navigation.
5. Read-only status and mutation/provider-traffic controls were visually and verbally separated. The page header now exposes only “Refresh status”; scheduling, running, retrying, clearing, and worker actions remain in the lower operational sections with provider-traffic guidance.
6. At the narrow in-app browser width, Overview and Operations remained bounded. The persistent health affordance was present in the mobile navigation drawer and linked to the same focused incident.

No browser action contacted a provider or changed application data.

## Automated verification

- `python -m pytest -q` — 679 passed in 285.12 seconds.
- `npm test -- --run` — 114 passed across 23 files.
- `npm run build` — passed. Vite retained the pre-existing advisory that the main bundle exceeds 500 kB; request shaping and bundle/performance work remain owned by S7/S9.
- `python -m tools.check_architecture_boundaries` — passed.
- Targeted health/queue policy tests and Overview/Operations/App component tests passed before the full suites.

Regression coverage proves that critical source failure, stale essential evidence, a blocked worker, and the dead-letter threshold cannot report healthy. It also proves that a deliberately disabled idle worker is informational and that the primary link preserves incident and job-filter context.

## Contract statement

No financial calculation, valuation rule, signal score, expected return, portfolio total, broker reconciliation rule, ingestion mutation, or persistence contract changed. S6 adds a read-only aggregate response and presentation behavior only.

## Remaining gates

- The controlled failure/recovery drill remains S9 work and was intentionally not run against the user’s live local data.
- The health endpoint is conservative and may report multiple related incidents (for example, dead letters plus their provider category); this is deliberate so cause and queue consequence remain separately visible.
- The health snapshot currently includes active benchmark evidence through the existing benchmark summary query. S7 owns benchmark request-shaping and latency budgets.
