# Audit reconciliation and bugfixing sprint plan

## Purpose

This plan turns every finding in the [2026-09-05 web application audit](../audits/2026-09-05-web-app-audit.md) into an executable remediation slice. It is deliberately broader than a P0-only incident response: all audit findings are covered, including UX, accessibility, mobile, performance-risk, data-governance, and verification items.

The work is ordered to restore truthful product behavior first, repair underlying operating failures second, then improve workflows and presentation. A green-looking interface must never outrun the state of its evidence.

## Non-negotiable guardrails

- Do **not** alter financial formula definitions, calculation behavior, or investment decision thresholds as part of this sprint.
- Do **not** change persistence contracts, storage schema semantics, transaction-import idempotency, or raw-payload retention behavior without a separately approved migration/design decision.
- It is permitted to add read models, response fields, display-only guards, health aggregation, diagnostics, tests, and UI states when these leave the existing persistence and calculation contracts unchanged.
- Avoid provider traffic in automated tests. Use fixtures, stubbed clocks, and test databases.
- Keep raw broker/provider payloads out of response models consumed by ordinary UI routes.
- Every slice must add regression coverage before it can be marked complete.

## Operating model

### Execution status — 2026-09-08

- S0 baseline is committed as `5ad9210`.
- S1's bounded implementation and isolated verification are complete: database ownership/lifecycle safeguards, phase-specific safe worker diagnostics, full queue counts/age/failure groups, and Operations presentation. See the [S1 verification record](../audits/2026-09-08-s1-runtime-verification.md) and [recovery runbook](../operations/runtime-recovery.md).
- S1 acceptance exception: the historical `s.snapshot_date` error (INF-01) does not reproduce against the current production schema and DuckDB 1.5.5. No SQL change was justified. Regression coverage and persistent-within-session phase diagnostics are delivered, but the historical root cause and live operational closure remain unverified. Do not mark that incident fixed merely because these tests pass.
- S6 still owns cross-page health reconciliation and the broader Operations experience; S9 retains the release/live-recovery gate. No production jobs were drained or workers enabled during S1 verification.
- S2's shared `evidence-display.v1` policy is implemented locally as of 2026-09-08. It initially defined five type-specific freshness windows, source/coverage precedence, confidence-independent eligibility, safe compatibility adapters, and matching Python/TypeScript response shapes. S3 extends the same versioned vocabulary with a 36/96-hour retail-sentiment policy and applies it additively to decision surfaces. See the [S2 verification record](../audits/2026-09-08-s2-evidence-policy-verification.md).
- S3's decision-surface containment is implemented and verified locally as of 2026-09-08. Retail, news, signals, asset price/analytics, portfolio fundamentals, Business Strength, Compare, and Benchmarks now preserve evidence at the point of interpretation and block stale, fixture, proxy, or incomplete output from default decision paths. See the [S3 verification record](../audits/2026-09-08-s3-decision-surface-verification.md).
- S4's broker presentation boundary is implemented and verified locally as of 2026-09-08. Import preview and reconciliation now expose a strict scalar instrument identity, omit raw provider objects and identifiers, and render bounded desktop/narrow layouts without changing broker retention, mapping, reconciliation, or import persistence behavior. See the [S4 verification record](../audits/2026-09-08-s4-broker-presentation-boundary-verification.md).

### Recommended models

| Model | Best use in this sprint |
| --- | --- |
| `gpt-6-astra` | Cross-cutting design, DuckDB/concurrency diagnosis, API contract boundaries, migration-risk review, and final integration. Use `xhigh`/`max` when the slice spans backend, frontend, and state semantics. |
| `gpt-5.6-sol` | Focused implementation in established patterns: typed APIs, React routes, component states, test additions, and broker workflow integration. Use `high` for multi-file slices. |
| `gpt-5.6-terra` | Self-contained visual/layout/accessibility fixes and bounded performance profiling. Use `high` where visual regression and responsive behavior matter. |
| `gpt-5.6-luna` | Mechanical test expansion, fixture creation, copy cleanup, and verification-only tasks after an owner has established the implementation pattern. Use `medium`/`high`; do not assign it the cross-cutting architectural slices. |

### Delivery conventions

- One branch/PR per slice; do not mix the runtime repair, evidence policy, and visual polish in one review.
- Every PR must link the audit IDs it closes and state the unchanged financial/persistence contracts.
- Use fixtures representing: fresh, warning-age, stale, blocked provider, proxy, synthetic/fixture, incomplete model, no efficacy sample, dead-letter backlog, and raw broker payload.
- Add an implementation decision record when a slice needs a product-policy choice, rather than silently choosing a financial or retention policy.
- Run the full relevant backend and frontend test suites for each slice; run the end-to-end reconciliation suite before merging a release wave.

## Sequencing overview

```text
S0 Baseline and safety rails
 ├─ S1 Runtime repair and operational telemetry
 └─ S2 Evidence/freshness contract
     ├─ S3 Decision-surface containment (signals, retail, news, assets, benchmarks, compare)
     ├─ S4 Broker presentation boundary
     │   └─ S5 Broker review workflow
     └─ S6 Overview and Operations health experience
         └─ S7 Benchmark request-shaping

S8 Visual, responsive, and accessibility polish
S9 End-to-end reconciliation, performance, and release sign-off
```

S1 and the design portion of S2 may start after S0. S3–S7 should not merge before S2’s API/display semantics are agreed. S8 can begin after S0, but its affected routes should be rebased after S3/S6 to avoid unnecessary merge conflict. S9 is the release gate.

## Slice backlog

### S0 — baseline, policy decisions, and regression harness

**Objective:** establish unambiguous definitions and a protected baseline before modifying product behavior.

**Audit coverage:** enables every finding; explicitly protects UX-07 (the existing direct New Portfolio route).

**Implementation work:**

1. Capture deterministic fixtures for the observed states listed in the delivery conventions.
2. Document the product definitions of `current`, `warning`, `stale`, `blocked`, `proxy`, `fixture`, `incomplete`, and `eligible for action`.
3. Identify response models/routes consumed by Overview, Operations, Signals, Retail, News, Compare, asset pages, Benchmarks, and Brokers.
4. Add baseline tests proving that current financial output values and persistence-side effects are unchanged for representative portfolio, signal, and import fixtures.
5. Add a route-level regression for the direct `New Portfolio` entry point; it remains present and visible but need not submit a portfolio in this sprint.

**Acceptance criteria:**

- The state definitions are approved in-repo and reused by later slices.
- A test fixture can render each data-quality state without provider traffic.
- Baseline contract tests pass before and after every dependent slice.
- The financial calculations/persistence contract boundary is explicit in each follow-on PR.

**Recommended model:** `gpt-6-astra` at `xhigh`. This is a short but architecture-setting slice; ambiguity here would make every later fix inconsistent.

**Estimated size:** S.

---

### S1 — ingestion scheduler, DuckDB ownership, and operational error capture

**Objective:** repair the verified backend failures and expose safe diagnostic state without changing job or persistence semantics.

**Audit coverage:** INF-01, INF-02, INF-04; supports DQ-01.

**Implementation work:**

1. Reproduce the scheduler query failure with a deterministic test and correct the invalid SQL alias/reference (`s.snapshot_date`) in the scheduling path.
2. Map the current DuckDB connection lifecycle and identify concurrent writers/processes. Implement the smallest compatible coordination fix: single application writer ownership, scoped connection lifecycle, retry/backoff only where safe, and an explicit failure state rather than an unbounded retry loop.
3. Capture worker execution outcomes in a structured operational read model: latest error category, safe message, timestamp, count, worker name, backlog count/oldest age, dead-letter count by provider/error, and affected data products.
4. Preserve raw stack traces in server logs/support diagnostics only; do not send them to normal UI response models.
5. Mark whether a worker is intentionally disabled, misconfigured, blocked, failing, or idle. `Disabled` alone is not a sufficient operating state.
6. Add provider-rate-limit guidance as state/copy, not as an automatic aggressive retry mechanism.

**Do not do in this slice:** start workers by default, drain the existing 355 jobs automatically, change retry/deduplication semantics, or alter job persistence schemas. Any recovery execution needs a separate, explicit operational runbook and approval.

**Acceptance criteria:**

- The scheduler test reproduces the old failure and passes with the corrected query.
- Parallel/process contention is covered by an integration test or a documented testable coordinator boundary.
- A deliberately failed worker produces an Operations-safe error state within the expected read interval.
- A rate-limited provider produces actionable guidance and does not invite blind repeated retries.
- Job queue and import idempotency baseline tests remain unchanged.

**Recommended model:** `gpt-6-astra` at `max`. DuckDB locking and scheduler ownership are the highest-risk technical issues and require careful repository-wide reasoning.

**Estimated size:** M.

---

### S2 — shared evidence, freshness, and eligibility contract

**Objective:** define one display-safe, read-only evidence contract so every analytical surface describes source provenance, freshness, completeness, and whether it may be used for action-like UI.

**Audit coverage:** DQ-01, DQ-03, DQ-04, DQ-05, DQ-06, DQ-07, DQ-08, DQ-09, UX-02, UX-03, UX-11.

**Implementation work:**

1. Introduce a versioned presentation/read-model type, separate from persistence entities and calculation outputs. Suggested fields:
   - `source_kind`: real, proxy, fixture, inferred;
   - `source_name` and source health;
   - `observed_at`, `retrieved_at`, and `freshness_state`;
   - `coverage_state`, missing inputs, and confidence/effectiveness evidence;
   - `action_eligibility`: eligible, warning, blocked;
   - user-facing limitation/reason code.
2. Implement a single policy evaluator with a clock injected for tests. It must be type-aware: a price, news item, financial statement, benchmark metric, and monthly signal do not necessarily share the same freshness threshold.
3. Derive display-state fields from existing source metadata; do not recalculate financial metrics or alter their stored values.
4. Define precedence. A blocked provider, fixture/synthetic source, or essential missing model input must not be visually overridden by a high numeric confidence value.
5. Add compatibility adapters so existing consumers can migrate incrementally, with no silent contract break to unrelated clients.

**Acceptance criteria:**

- Tests cover all fixture states and precedence rules.
- State calculations are deterministic with a frozen clock.
- Existing calculation results are unchanged; only their display eligibility/provenance changes.
- No UI-facing read model contains raw provider payloads by default.
- Later route slices can consume the same state without implementing bespoke stale logic.

**Recommended model:** `gpt-6-astra` at `max`. This is the central reconciliation architecture; a weaker, page-by-page solution would recreate the audit’s inconsistent messaging problem.

**Estimated size:** M.

---

### S3 — decision-surface containment and truthful analytical UI

**Objective:** apply S2 consistently to every surface that currently presents stale, synthetic, proxy-only, or incomplete output as authoritative.

**Audit coverage:** DQ-02 through DQ-09, UX-02, UX-05, UX-11.

**Implementation work by area:**

| Area | Required change |
| --- | --- |
| Retail sentiment | If providers have no credentials/posts, render a clear unavailable/setup state. Do not show source-attributed post counts, confidence, held-stock coverage, or a 10% add-on as actual data. Fixture/demo content must be unmistakably labelled and non-decisioning. |
| News and asset news | Remove `example.test` from normal production cards or mark it as sample data. Carry degraded provider state and article age into both News and asset-level News; improve empty/degraded layout and title/date spacing. |
| Signals and signal detail | Give stale/blocked signals a primary state, de-emphasize numerical confidence, show data age and no-efficacy evidence, and prevent stale signals from looking “Active”/actionable. Alert/watchlist/review controls should make ineligibility clear before invoking a write path. |
| Fundamentals and Business Strength | When essential inputs are absent, lead with `not eligible`/conditional state and missing-input list. Reconcile aggregate and component confidence/completeness values; keep existing financial calculations intact. |
| Compare | Make one-asset mode explicit, explain/confirm the default benchmark, attach freshness to every series/row/chart, and prevent stale results from winning default comparisons. |
| Benchmarks | When data is proxy-only or all stale, lead with that status and prevent strong returns from presenting as current live facts. |

**Do not do in this slice:** change score algorithms, valuation models, expected-return calculations, source ingestion, or alert persistence logic. Those are outside the approved scope.

**Acceptance criteria:**

- Each listed route has screenshot/component tests for fresh, warning, stale, blocked, proxy, fixture, incomplete-input, and no-efficacy cases as applicable.
- No fixture/mock retail/news item can resemble real current data without an unmistakable label.
- A stale/proxy/incomplete result cannot appear as the default winner, active recommendation, or action-eligible outcome.
- Asset and compare downstream components preserve per-series freshness, not merely a page-level banner.
- Business Strength messaging and numeric confidence/completeness agree in all fixtures.

**Recommended model:** `gpt-5.6-sol` at `high`, after S2 has supplied the shared semantics. It is a broad but pattern-driven frontend/API integration slice; use `gpt-6-astra` for design review of any exceptional decision gating.

**Estimated size:** L; split implementation into route-focused PRs if review size becomes excessive, while keeping one shared acceptance suite.

---

### S4 — broker response normalization and raw-payload boundary

**Objective:** make broker reconciliation readable and ensure ordinary presentation routes cannot leak raw provider payloads.

**Audit coverage:** BR-01, INF-05; supports BR-02 and UX-06.

**Implementation work:**

1. Identify where the provider instrument object enters the reconciliation response and replace it with a typed display object: symbol, description/name, exchange, currency, stable local resolution identifier, and resolution status.
2. Validate serialisation at the API boundary so unknown/raw nested payload objects cannot reach table cells.
3. Move support-only raw data behind an explicit privileged diagnostic route/view, or omit it entirely from UI-facing APIs according to the existing retention policy.
4. Add handling for unresolvable/unsupported instruments that gives a concise human message rather than a raw object.
5. Add a UI table renderer that is resilient to missing display fields, without stringifying arbitrary objects.

**Acceptance criteria:**

- Reconciliation API contract snapshots contain no raw provider IDs/objects, logo URLs, or FIGI unless the route is expressly designated diagnostics-only.
- Every reconciliation row has a readable primary label and deterministic fallback label.
- Existing mapping/import persistence contract tests pass unchanged.
- Desktop and mobile table snapshots remain bounded/readable with long names and absent symbols.

**Recommended model:** `gpt-5.6-sol` at `high`. The work is strongly bounded by typed response/view-model patterns, with `gpt-6-astra` review required if it exposes a previously implicit API contract used outside the web app.

**Estimated size:** M.

---

### S5 — broker review queue and account/asset resolution pathway

**Objective:** give users a safe, scoped route from “needs review” to the correct account or asset resolution task.

**Audit coverage:** BR-02, UX-06; also resolves ambiguity around disabled account-assignment controls.

**Implementation work:**

1. Create a read-only review-queue view grouped by blocker type: unassigned account, unresolved asset, unsupported transaction, and ready-to-import.
2. Link each summary and row to the appropriate mapping/resolution UI with broker, account, transaction, and asset context retained in URL/state.
3. Explain disabled controls in place: what condition blocks the action and which route fixes it.
4. Make import scope explicit per account; default detail panels closed and paginate/virtualize transaction lists.
5. Keep state-changing import/mapping actions governed by existing authorization/confirmation behavior; the new queue itself should be safe to browse.

**Acceptance criteria:**

- From a review summary, a user reaches the correct scoped resolver in one visible action.
- No route loses broker/account context while navigating between reconciliation and mapping.
- 2,806-review-style fixtures stay performant and do not render all records by default on mobile.
- Disabled controls expose their prerequisite in text accessible to keyboard/screen-reader users.
- Existing import idempotency and persistence behavior are unchanged.

**Recommended model:** `gpt-6-astra` at `xhigh`. This spans navigation, broker identity/context, data contracts, and user-safety boundaries; it should not be attempted as a purely cosmetic UI task.

**Estimated size:** L.

---

### S6 — unified Overview and Operations health experience

**Objective:** replace contradictory status with one understandable health narrative and a controlled route to remediation.

**Audit coverage:** DQ-01, INF-02, INF-04, UX-03, UX-11.

**Implementation work:**

1. Consume S1 telemetry and S2 evidence states to calculate an aggregate health summary with explicit severity rules.
2. Replace the unconditional/overly optimistic Overview message with a concise status that identifies affected domains and links to a filtered Operations view.
3. Add an Operations incident header: backlog/age, workers, critical provider failures, dead letters, data products affected, and recommended next step.
4. Clearly distinguish read-only status from actions that cause job/provider traffic. Provide specific help for FMP rate-limit, missing social credentials, and intentionally disabled workers.
5. Add a compact, persistent data-status affordance to the shell without overwhelming normal portfolio navigation.

**Acceptance criteria:**

- A critical source failure, stale essential dataset, blocked worker, or dead-letter threshold changes Overview out of `healthy`.
- The health message identifies why and gives a direct non-mutating path to details.
- Operations shows safe, actionable state without exposing stack traces.
- UI tests prove no contradictory combination of green health with the listed critical fixtures.

**Recommended model:** `gpt-5.6-sol` at `high`. The visual/API integration is tractable after S1/S2; ask `gpt-6-astra` to review severity rules because they are product-safety policy.

**Estimated size:** M.

---

### S7 — benchmark request-shaping and performance proof

**Objective:** remove the observed benchmark-page request fan-out risk and establish a measurable performance budget.

**Audit coverage:** INF-03, DQ-04, UX-04.

**Implementation work:**

1. Instrument the Benchmarks route to enumerate client requests and measure route-ready time under an injected-latency test server.
2. Replace per-benchmark eager detail/price/metric/exposure/constituent requests with a summary/batch response or bounded aggregate query.
3. Load detail-heavy data only after selecting/opening a benchmark; cache keyed read-only responses appropriately.
4. Ensure the summary payload carries the S2 freshness/proxy fields so performance improvements do not hide evidence status.
5. Define budgets for initial request count, initial payload size, and route-ready time at a representative number of benchmarks.

**Acceptance criteria:**

- Automated test records a bounded initial request count independent of the number of unselected benchmark details.
- Selected benchmark details load on demand and retain correct stale/proxy labels.
- A latency-injected test meets the agreed route-ready budget.
- No performance optimization changes benchmark calculation values or persistence behavior.

**Recommended model:** `gpt-5.6-terra` at `high`. This is a focused profiling/refactor task once the evidence contract exists; escalate to `gpt-6-astra` only if batch-query design risks the storage boundary.

**Estimated size:** M.

---

### S8 — visual hierarchy, responsive behavior, and accessibility polish

**Objective:** eliminate audited layout defects and make normal versus exceptional data visually clear without re-opening data-contract decisions.

**Audit coverage:** UX-01, UX-04, UX-06, UX-08, UX-09, UX-10, UX-11; regression protection for UX-07.

**Implementation work:**

1. Correct the desktop Broker profile grid so copy uses appropriate width and intentional empty space becomes useful status content or disappears.
2. Reduce unnecessary card elevation/status chips on Signals, Benchmarks, and Operations; normalize portfolio card treatment with the dark shell.
3. Repair narrow metadata layouts, displaced asset labels, and asset-news title/date spacing/empty-state geometry.
4. Add accessible names, labels, focus treatment, and tooltips to every icon-only control, particularly mobile navigation.
5. At mobile widths, use compact metric grouping where it improves comparison, retain readable tap targets, and default large broker sections to collapsed.
6. Add visual regression snapshots at desktop, tablet, and 390 px mobile widths for Overview, Signals, Asset, Benchmarks, Brokers, Import, and Operations.

**Acceptance criteria:**

- No desktop Broker hero text wraps one word per line at target desktop widths.
- No audited page has overflow, overlap, unexplained empty space, or inaccessible image-only action at the test breakpoints.
- Primary data-quality state is more visually prominent than secondary confidence/count cards.
- The direct portfolio creation action remains visible on the aggregate Portfolio page.
- Accessibility checks pass for labelled controls and keyboard reachability on the touched routes.

**Recommended model:** `gpt-5.6-terra` at `high`. This is visual and interaction-focused work where disciplined screenshot/AX verification is more valuable than maximal backend reasoning.

**Estimated size:** M.

---

### S9 — end-to-end reconciliation, operations drill, and release gate

**Objective:** prove that the system now tells one truthful story from source state through operational recovery and user-facing decisions.

**Audit coverage:** all IDs: DQ-01–DQ-09, BR-01–BR-02, INF-01–INF-05, UX-01–UX-11.

**Implementation work:**

1. Build seeded end-to-end scenarios for:
   - all healthy/current real sources;
   - FMP rate limit and stale/degraded news;
   - missing Reddit/X credentials with zero posts;
   - stale monthly signal with no efficacy sample;
   - proxy-only/stale benchmarks;
   - incomplete model inputs and conflicting component evidence;
   - pending/dead-letter jobs with worker disabled/failed;
   - reconciliations needing account and asset resolution;
   - raw-provider-object adversarial fixture.
2. Verify each scenario across Overview, the affected product page, Operations, and the relevant workflow link.
3. Run a controlled operational drill in a non-production/test database: one failure, its safe status presentation, a permitted recovery action, and post-recovery status. Do not run this against the user’s live data without explicit approval.
4. Run UI accessibility and visual checks at the agreed responsive breakpoints.
5. Run the benchmark request-count/latency check, then compare against the baseline captured in S0.
6. Produce a short release evidence document listing passes, remaining known limitations, and the exact test commands/results.

**Release gate:**

- No P0 audit finding remains open.
- No route can label the system healthy when its supplied fixture has a critical failed/stale/blocked source.
- No normal reconciliation response/UI contains raw provider objects.
- Financial-output and persistence baseline tests are unchanged.
- All slice acceptance suites and the end-to-end scenario matrix pass.
- Any deferred P1/P2 item has an owner, issue link, rationale, and a product-safe interim state.

**Recommended model:** `gpt-6-astra` at `xhigh`, with `gpt-5.6-luna` at `high` for mechanical fixture/test expansion after Astra establishes the scenario matrix. The final gate benefits from strong cross-cutting reasoning and independent verification.

**Estimated size:** M.

## Audit coverage matrix

Every issue from the audit maps to a delivery slice and a release test.

| Audit ID | Primary slice | Secondary slice / regression |
| --- | --- | --- |
| DQ-01 | S2, S6 | S9 |
| DQ-02 | S2, S3 | S6, S9 |
| DQ-03 | S2, S3 | S9 |
| DQ-04 | S2, S3 | S7, S9 |
| DQ-05 | S2, S3 | S6, S9 |
| DQ-06 | S2, S3 | S9 |
| DQ-07 | S2, S3 | S9 |
| DQ-08 | S2, S3 | S9 |
| DQ-09 | S2, S3 | S9 |
| BR-01 | S4 | S5, S9 |
| BR-02 | S5 | S9 |
| INF-01 | S1 | S6, S9 |
| INF-02 | S1, S6 | S9 |
| INF-03 | S7 | S9 |
| INF-04 | S1, S6 | S9 |
| INF-05 | S4 | S9 |
| UX-01 | S8 | S9 |
| UX-02 | S2, S3 | S9 |
| UX-03 | S6 | S8, S9 |
| UX-04 | S8 | S7, S9 |
| UX-05 | S3 | S9 |
| UX-06 | S5, S8 | S9 |
| UX-07 | S0 | S8, S9 (regression only; no defect to change) |
| UX-08 | S8 | S9 |
| UX-09 | S8 | S9 |
| UX-10 | S5, S8 | S9 |
| UX-11 | S2, S3, S6 | S8, S9 |

## Efficient execution schedule

### Wave A — establish truth and repair operational blockers

Run S0 first. Then run S1 and the design/contract portion of S2 in parallel only if they work in isolated files. Merge S1 before implementing Operations health presentation in S6.

**Expected output:** reliable error telemetry, a written/display-state policy, protected contract baselines.

### Wave B — contain misleading user-facing output

Run S3 and S4 in parallel after S2. Start S6 once S1 and S2 are merged. S3 should be subdivided by route if it would otherwise create a very large PR, but all sub-PRs must use the same S2 contract.

**Expected output:** no stale/synthetic/proxy/incomplete output appears as ordinary current advice; reconciliation rows are human-readable; Overview is no longer falsely green.

### Wave C — restore complete, performant workflows

Run S5, S7, and S8 in parallel after their dependencies are stable. Keep S5’s navigation/state changes separate from S8’s visual refinements to preserve reviewability.

**Expected output:** guided reconciliation workflow, bounded benchmark loading, responsive/accessible surfaces.

### Wave D — release verification

Run S9 only after all prior slice acceptance criteria pass. Treat it as a gate, not a paper exercise. Any scenario that contradicts the product’s displayed health state reopens the responsible slice.

## Definition of done

This sprint is done only when the application can make the following truthful promise:

> Every decision-facing value clearly communicates the quality and recency of its evidence; when that evidence is absent, stale, synthetic, proxy-only, or operationally blocked, the product says so prominently and does not present the result as normal actionable intelligence.

It is not done merely because the widgets are visually polished, the worker controls exist, or the unit suite is green. The end-to-end state must be internally consistent across Overview, Operations, every affected analytical page, and the broker reconciliation path.
