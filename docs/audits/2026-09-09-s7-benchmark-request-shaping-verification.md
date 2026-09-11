# S7 benchmark request-shaping verification

Date: 2026-09-09
Slice: S7 — benchmark request-shaping and performance proof
Audit coverage: INF-03, DQ-04, UX-04

## Outcome

The Benchmarks workspace now becomes useful from one bounded, cached benchmark-summary request. It does not fetch price, metric, exposure, constituent, or detail resources until a user explicitly selects a comparison or opens a benchmark. The summary route also stopped expanding each list row through `get_benchmark`; provider, symbol, proxy, freshness, and action-eligibility metadata now arrive in the aggregate query.

No benchmark return, volatility, normalization, or other financial calculation changed. No table, write path, ingestion behavior, or persistence contract changed.

## Pass 1 — request-path profile

The pre-S7 code had two overlapping catalog queries and automatically selected a baseline plus two rows. A cold route therefore initiated two summary requests and three price-history requests, in addition to the shell health request. Behind each summary request, the API called `get_benchmark` once per returned row, creating an additional N+1 server-side query path.

The post-S7 route has these bounded phases:

1. Initial route: shell health plus one `/api/v1/benchmarks?is_active=true&limit=500` request.
2. Filter and sort: local work against the cached summary; no network request.
3. Compare: price history for the explicit selection and its baseline, keyed by benchmark, period, and start date.
4. Open: detail, prices, and enabled detail panels load only on the benchmark detail route.

## Pass 2 — aggregate query and evidence contract

`BenchmarkApiService.list_benchmarks` now joins one deterministic primary symbol per benchmark in its existing aggregate SELECT. The additive summary fields are:

- `primary_provider`
- `primary_symbol`
- `primary_is_proxy`

The evidence adapter derives `source_name` and `source_kind` directly from those fields, so the list route no longer needs per-row detail objects. Existing metric values and evidence policy evaluation remain unchanged. A route regression replaces `get_benchmark` with a function that raises and proves the summary endpoint does not invoke it. API assertions also prove direct and proxy source identity survives the refactor.

## Pass 3 — client request shaping and cache behavior

The workspace uses a single stable React Query key with a 60-second stale window and five-minute cache retention. Search, category, currency, proxy, freshness, and sort controls operate against the cached 500-row summary. Provider and ticker search remain available through the additive primary-source fields.

The former automatic three-series comparison was removed. The comparison chart now explains that the catalog loads without price history and that selecting a row fetches only the requested series and baseline. Price history remains keyed by benchmark and period, so adding another benchmark reuses already-cached selected series.

## Pass 4 — measurable performance budget

The canonical UI budget is defined in `web/src/benchmarkPerformance.ts` and enforced by unit and browser profiling.

| Measure | Budget |
| --- | ---: |
| Representative catalog | 100 benchmarks |
| Initial benchmark API requests | 1 |
| Initial total page API requests | 2, including shell health |
| Summary payload | 300,000 bytes |
| Injected benchmark API latency | 250 ms |
| Route-ready time | 1,000 ms |

The browser profiler can be rerun with `cd web` followed by `npm run perf:benchmarks`. It records every initial API response, rejects non-2xx responses, identifies eager detail requests, measures the summary body, injects latency, and writes the ignored diagnostic artifact to `tmp/benchmarks-browser-profile.json`.

Live local measurement with 34 stored benchmarks:

| Measure | Observed |
| --- | ---: |
| Route-ready time with 250 ms injected latency | 551.49 ms |
| Initial benchmark API requests | 1 |
| Initial total page API requests | 2 |
| Summary payload | 42,331 bytes |
| Eager detail requests | 0 |
| Direct summary endpoint time | 92.22 ms |

All measured values were within budget. A 100-summary latency-injected component test independently enforces bounded request count, payload size, route readiness, and zero eager price requests.

## Pass 5 — rendered behavior

Computer-assisted inspection covered the live catalog and an opened benchmark at the app's narrow viewport. The catalog rendered 34 rows from the summary response, led with the existing blocked-evidence warning, showed `0/34` fresh coverage, and displayed the new empty comparison instruction without a loading waterfall. Opening `IND_SEMICONDUCTORS` then loaded its price, metric, exposure, and constituent panels and retained `Not Decision Eligible · Stale` plus `ETF proxy` disclosures.

The narrow catalog remains usable as stacked benchmark cards. Broader cross-route responsive and visual hierarchy work remains intentionally owned by S8.

## Verification

- `python -m pytest tests/api/test_benchmark_api.py -q` — 16 passed.
- `python -m pytest -q` — 680 passed.
- `npm test -- --run src/benchmarks.test.tsx src/benchmarkUtils.test.ts` — 13 passed.
- `npm test -- --run` — 115 passed.
- `npm run lint` — passed.
- `npm run build` — passed; the pre-existing main-chunk advisory above 500 kB remains for S9.
- `python -m ruff check ...` for touched Python files — passed.
- `python -m tools.check_architecture_boundaries` — passed.
- `npm run perf:benchmarks` against the running API — passed all request, status, payload, eager-detail, and latency checks.

## Boundaries retained

- Financial outputs are read and displayed exactly as before; no formula or stored result was changed.
- The database schema and persistence behavior are unchanged.
- Existing benchmark detail routes and response fields remain; the summary response only gained source metadata.
- Seed, harden, refresh, and ingestion mutations are unchanged.
- No production job or provider request was initiated during verification.
