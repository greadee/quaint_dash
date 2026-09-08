# S3 decision-surface containment verification

## Outcome

S3 is implemented and verified on 2026-09-08. Retail sentiment, news, signals,
asset price/analytics, portfolio fundamentals, Business Strength, Compare, and
Benchmarks now consume the shared `evidence-display.v1` presentation policy.
Blocked, stale, proxy, fixture, inferred, incomplete, and no-efficacy evidence
remains available for audit without being presented as ordinarily action-eligible.

This slice is additive and display-only. It does not change financial formulas,
valuation assumptions, ranking algorithms, persistence schemas, write payloads,
ingestion schedules, provider selection, or alert/import persistence behavior.

## Audit coverage

| Audit ID | S3 result |
| --- | --- |
| DQ-02 | Retail output is blocked when neither Reddit nor X has configured, ingested posts. Unsupported counts, confidence, coverage, and the retail signal add-on are hidden or disabled. |
| DQ-03, DQ-09 | Signals carry monthly-signal evidence. Blocked rows sort after usable rows, disappear from actionable summary panels, de-emphasize confidence, and disable alert/review writes in detail. Zero historical samples are explicit. |
| DQ-04 | Benchmark summaries, detail, prices, and daily metrics carry proxy/freshness evidence. An all-blocked collection leads with a blocking notice and cannot choose a stale row as a leader, winner, or default baseline. |
| DQ-05, DQ-08 | Feed and asset-news articles carry provider health and age. Fixture sources are labelled, and `example.test` URLs are removed from the API presentation response and hidden defensively in the UI. |
| DQ-06, DQ-07 | Asset analytics, portfolio fundamentals, and Business Strength carry financial-statement evidence. Missing essential inputs block decision use while numeric results remain available only as calculation audit. Confidence is secondary to eligibility. |
| DQ-08 | Asset news preserves per-article evidence instead of relying only on a page-level feed state. |
| UX-02 | Asset chart, asset analytics, Compare assets/series, and benchmark rows carry evidence at the downstream surface where the number is interpreted. |
| UX-05 | Compare explicitly identifies single-asset context mode, suppresses winners/ranks/differences and forward comparison scenarios, and explains the automatically associated benchmark. |
| UX-11 | The canonical badge vocabulary and blocking banners prevent authoritative visual treatment from outrunning evidence quality. |

## Implementation boundary

### Shared presentation adapters

`dashboard.api.evidence_adapters` copies existing public response values and adds
evidence metadata. It does not call providers, write records, or recompute a
financial value. Route changes make read-only metadata queries for existing source
dates, source names, retrieval timestamps, and provider status.

The S2 policy was extended within the same versioned vocabulary with a retail
sentiment cadence: current through 36 hours, warning through 96 hours, stale after
96 hours. Fixture precedence includes explicit test/demo/mock/sample sources.

### Surface behavior

| Surface | Containment behavior |
| --- | --- |
| Retail sentiment | A leading unavailable/setup state replaces unsupported decision cards. Retail-derived signal controls are disabled and reset before another query can include them. |
| News | Feed and article evidence is visible; degraded provider state is retained; placeholder links do not render as production sources. |
| Signals | Eligibility is the primary row/detail state. The pre-existing 31-day service filter is accurately labelled `Legacy age filter` rather than being conflated with the shared 45/75-day evidence policy. |
| Asset chart | The asset header and chart carry price-source evidence derived from the newest stored live/daily observation. |
| Asset analytics | Price evidence governs historical risk/return context. Separate financial-statement evidence governs valuation and forecast outputs; blocked outputs are labelled `Audit only`. |
| Portfolio fundamentals | Overall and holding-level evidence use stored statement dates and missing-input facts. Blocked holding results display `Not eligible`. |
| Business Strength | Overall/category/metric evidence is attached. Missing critical inputs or stale statements lead with `not decision eligible`; numeric confidence cannot override the block. |
| Compare | Assets, history series, price facts, fundamental facts, and benchmark context preserve evidence. The reference falls back only to a decision-eligible asset. |
| Benchmarks | Index summaries, detail, prices, and metrics preserve proxy/stale evidence. Eligible-only leadership and risk summaries replace raw best/worst promotion when evidence is blocked. |

## Live application passes

The API and Vite application were launched locally and inspected through the
rendered browser at `http://127.0.0.1:5173`.

1. **Retail and responsive containment:** verified the leading blocked provider
   state, absent unsupported metrics, disabled retail add-on, and no horizontal
   overflow at the available narrow viewport. A responsive page-title/status-banner
   stacking defect found during this pass was corrected.
2. **News provenance:** verified degraded provider messaging, visible sample-only
   labels, per-story state, and absent `example.test` source links.
3. **Signals and efficacy:** verified evidence-first rows, blocked stale rows after
   usable rows, explicit no-sample copy, and the corrected 31-day legacy filter
   wording. Restarting the API confirmed the final adapter label in the rendered UI.
4. **Compare:** verified explicit single-asset context, disabled comparison-mode
   selection, no winners/differences/forward scenario section, no false reference
   change warning, and benchmark association explanation.
5. **Benchmarks:** verified the all-blocked banner, stale/proxy badges, disabled row
   actions, eligible-only leadership/risk behavior, and no horizontal overflow.
6. **Asset and portfolio analytics:** verified Business Strength and portfolio
   holding evidence. A final coverage review found that the asset price/fundamentals
   route itself still lacked evidence; S3 was expanded before sign-off to add
   separate price and financial evidence and audit-only valuation treatment.

## Automated verification

Final clean regression results after the asset-surface closure:

- Backend: `665 passed` with the local API stopped so DuckDB was not held by a
  separate process.
- Frontend: `23` test files, `111 passed`.
- Python lint: Ruff passed.
- Architecture boundary check: passed.
- Frontend lint: ESLint passed.
- Production frontend build: TypeScript and Vite passed.
- Diff hygiene: `git diff --check` passed before staging.

An earlier full backend run produced `664 passed, 1 failed` only because the live
API intentionally held `data/persistent_db.db` while the legacy CLI smoke test tried
to open that same DuckDB file. Stopping the API made the complete suite green. This
is expected evidence of the S1 single-owner production-risk safeguard, not an S3
calculation or persistence failure.

## Acceptance conclusion

The listed S3 decision surfaces now fail visibly and conservatively: unsupported
evidence can be inspected, but cannot silently become a current winner,
recommendation, comparison reference, or action-enabled result. Existing calculated
values and persistence contracts remain unchanged.
