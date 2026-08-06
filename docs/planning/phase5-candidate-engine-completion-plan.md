# Phase 5 Deterministic Candidate Engine Completion Plan

**Objective:** finish Phase 5 as a deterministic, evidence-backed outside-holding candidate engine without starting Phase 6 recommendation logic.

This plan deliberately divides the remaining work into stopped slices. Implement one slice, run its verification, produce its stop report, and stop. Do not begin the next slice in the same implementation task, pull request, or commit series unless the user explicitly authorizes it after reviewing the completed gate.

## Current State

The repository already provides useful inputs:

- deterministic stock rankings in `PortfolioApiService.stock_rankings()`;
- tracked, held, watchlisted, and all-stock universe flags;
- portfolio sector and country exposure analytics;
- benchmark metadata and constituents;
- valuation, risk, momentum, earnings, institutional-flow, and sentiment calculations;
- signal evidence models and persisted evidence rows;
- stock-ranking snapshots and missing-input reporting.

Those inputs do not yet form the Phase 5 candidate engine. The current ranking response includes held assets, has no candidate reason taxonomy, does not calculate portfolio fit or diversification effects, does not expose stable evidence references, and does not enforce candidate-specific freshness guardrails.

Phase 4 is also a hard prerequisite. Phase 5 may consume a deterministic investor profile, but it must not recreate profile inference inside candidate scoring. If the required profile contract and fixture coverage are unavailable when Slice 5.0 runs, stop and complete Phase 4 first.

## Scope Boundaries

Phase 5 includes:

- generating outside-holding candidate sets from deterministic local data;
- explaining why each asset entered the candidate set;
- scoring fit, diversification effect, and redundancy;
- exposing valuation, risk, sentiment, and missing-data context;
- attaching stable evidence references and guardrail warnings;
- deterministic ranking and tie-breaking;
- persistence required to reproduce and audit candidate runs;
- tests for evidence, freshness, missing metrics, exclusion rules, and determinism.

Phase 5 does not include:

- `hold`, `watch`, `research_more`, `rebalance_preview`, `trim_candidate`, or `add_candidate` decisions;
- personalized investment recommendations or suitability claims;
- trade sizing, order construction, or execution;
- LLM or frontier-provider calls;
- public UI work or a recommendation endpoint;
- changes to existing ranking semantics unless an adapter cannot safely isolate candidate behavior.

Use research-oriented language such as `candidate`, `screen result`, `fit`, and `requires review`. Do not label a Phase 5 output as advice, a recommendation, or a buy decision.

## Global Implementation Rules

- Inspect the real schema, services, and fixtures before each slice. Record verified dependencies and unresolved assumptions.
- Keep candidate logic in a dedicated backend module instead of adding more candidate behavior to `src/dashboard/api/services.py`.
- Use stored backend data. Candidate generation must not call external providers or trigger ingestion.
- Accept point-in-time snapshots or explicit `as_of` inputs. Do not silently combine data from incompatible dates.
- Reuse existing analytics through narrow adapters. Do not duplicate ranking, valuation, exposure, or benchmark calculations.
- Keep models provider-neutral and LLM-neutral.
- Preserve missing and unsupported values. Never convert missing evidence into a neutral score.
- Version candidate methodology, reason-code definitions, evidence schema, and snapshot hashing inputs.
- Keep all ordering deterministic, including database reads, source merging, deduplication, evidence lists, warning lists, and final ties.
- Do not continue past a failed gate. Document the failure and stop.

## Initial Model Baseline

Use this as the starting allocation, not an automatic escalation schedule. The stop report for each slice must recommend the model and reasoning effort for the next slice based on the complexity, uncertainty, and failure modes actually discovered.

| Slice | Initial model | Reasoning effort | Why |
| --- | --- | --- | --- |
| 5.0 Prerequisite audit and contract freeze | GPT-5.6 Sol | high | Broad repository tracing and contract judgment need strong reasoning, but no production code is allowed. |
| 5.1 Domain models and evidence protocol | GPT-5.6 Sol | high | Canonical identities, serialization, and invariants have a high downstream cost if defined incorrectly. |
| 5.2 Persistence and reproducibility | GPT-5.6 Sol | high | Migration safety, idempotency, and historical reproducibility require careful code and schema review. |
| 5.3 Outside-holding universe and adapters | GPT-5.6 Sol | xhigh | Economic-exposure identity, deduplication, and exclusion failures can invalidate every later candidate result. |
| 5.4 Portfolio gaps and associations | GPT-5.6 Sol | xhigh | Taxonomy, profile alignment, benchmark coverage, and false diversification signals require deeper cross-domain reasoning. |
| 5.5 Screens and candidate scoring | GPT-5.6 Sol | max | This is the hardest quality-first slice: scoring interactions, deterministic ordering, fixtures, and anti-bypass behavior all meet here. |
| 5.6 Freshness, missing data, and guardrails | GPT-5.6 Sol | max | Safety and failure-mode reasoning matter more than latency; stale or incomplete evidence must fail predictably. |
| 5.7 Orchestration and internal service | GPT-5.6 Sol | xhigh | Integration crosses snapshots, profiles, adapters, persistence, and deterministic replay. |
| 5.8 Verification and closure | GPT-5.6 Sol | high | The work is broad and evidence-heavy, but the expected behavior should already be frozen and implemented. |

Do not increase reasoning effort merely because a slice follows a difficult slice. Recommend `high`, `xhigh`, or `max` only when the next slice's measured ambiguity and risk justify it.

## Stop Report Required After Every Slice

Each slice ends with a short report containing:

1. changed files and migrations;
2. implemented behavior and explicit exclusions;
3. exact verification commands and results;
4. schema or contract decisions made;
5. remaining risks, deferred work, and data limitations;
6. the next slice, identified but not started;
7. the recommended model and reasoning effort for that next slice, with a one-sentence complexity rationale.

## Slice 5.0 - Prerequisite Audit And Contract Freeze

### Work

1. Trace the existing investor-profile output, evidence snapshots, ranking snapshots, portfolio exposure analytics, watchlist source, benchmark constituents, peer metadata, and valuation/risk/sentiment inputs.
2. Produce a dependency matrix that distinguishes available, partial, missing, stale-capable, and unsupported inputs.
3. Confirm Phase 4 provides a versioned deterministic investor profile with evidence references, confidence, missing inputs, and fixture coverage.
4. Freeze the Phase 5 vocabulary:
   - candidate run;
   - candidate review;
   - candidate source;
   - reason code;
   - evidence reference;
   - blocked versus downgraded candidate;
   - fit, diversification effect, and redundancy.
5. Decide canonical timestamp, decimal precision, stable identifier, and hashing rules before creating persisted candidate data.
6. Write an ADR for the candidate engine boundary and point-in-time policy.

### Gate

- The dependency matrix is backed by file, table, and test references.
- The Phase 4 profile contract is available and tested. If it is not, stop Phase 5.
- Every required Phase 5 output has a written type and semantic definition.
- No production schema or scoring implementation is added in this slice.

### Mandatory Stop

Stop for contract review. Do not create candidate tables or scoring code.

## Slice 5.1 - Domain Models And Evidence Protocol

### Work

Create a dedicated candidate-engine package following the repository's approved module boundaries. Define provider-neutral models for at least:

- `CandidateRun`;
- `CandidateReview`;
- `CandidateSourceMatch`;
- `CandidateEvidenceRef`;
- `CandidateHighlight`;
- `CandidateWarning`;
- `CandidateMissingMetric`;
- score components for fit, diversification, and redundancy.

The candidate review contract must include:

- stable candidate ID, asset ID, and ticker;
- one or more versioned reason codes;
- fit score;
- diversification effect;
- overlap or redundancy score;
- valuation, risk, and sentiment highlights;
- missing metrics;
- guardrail warnings;
- stable evidence references;
- data and methodology timestamps;
- final eligibility state: `eligible`, `downgraded`, or `blocked`.

Define canonical serialization and hashing. Include schema version, methodology version, normalized timestamps, source identifiers, numeric precision, deterministic ordering, and an explicit list of volatile fields excluded from hashes.

### Tests

- Model validation rejects malformed IDs, unknown states, duplicate reason codes, and every evidence-free candidate review.
- Canonically equivalent inputs produce the same serialized value and hash.
- Materially different evidence produces a different hash.
- Permuted source and evidence order produces identical output.

### Gate

Pure contract tests pass. No database, API, ranking adapter, or scoring behavior is introduced.

### Mandatory Stop

Stop for domain and evidence-contract review.

## Slice 5.2 - Candidate Run Persistence And Reproducibility

### Work

Add the minimum persistence needed to audit and reproduce candidate runs. Prefer narrowly scoped tables equivalent to:

- candidate run metadata and input snapshot hash;
- candidate review results;
- source matches and reason codes;
- evidence references;
- missing metrics and warnings.

Persist structured columns where they are queried and versioned JSON only where the shape is intentionally extensible. Do not add Phase 6 recommendation, decision, prompt, provider, or model-call tables.

Make writes idempotent for the same run identity and input snapshot. Preserve historical runs. Never mutate an old run to represent new evidence.

### Tests

- Schema initialization and migration are repeatable.
- A candidate run round-trips without losing ordering or precision.
- Repeating the same run does not duplicate results.
- A changed snapshot creates a distinct run.
- Historical runs remain readable after a newer run is stored.

### Gate

Persistence tests pass against a temporary database, architecture-boundary checks pass, and no existing table semantics change.

### Mandatory Stop

Stop for schema and reproducibility review.

## Slice 5.3 - Outside-Holding Universe And Source Adapters

### Work

Build deterministic source adapters for:

- top-ranked stocks;
- active watchlist assets;
- all-universe search results;
- benchmark constituents or documented benchmark proxies.

Use one canonical asset identity and deduplicate across sources. Exclude every currently held economic exposure before scoring, including direct holdings and equivalent underlying exposure where the repository can resolve it. Record unresolved identity or underlying mappings as warnings or blocks; do not silently treat them as outside holdings.

Each emitted source match must include a reason code and at least one evidence reference. Source adapters may nominate assets but may not assign recommendation actions.

### Tests

- Direct holdings are excluded.
- Resolved equivalent or underlying holdings are excluded according to the frozen policy.
- The same asset from multiple sources appears once with all source reasons retained.
- A source match without evidence is rejected.
- Watchlist and benchmark source ordering is deterministic.
- Empty and unsupported source sets return truthful run metadata rather than fabricated candidates.

### Gate

The engine can produce a deduplicated, evidence-backed outside-holding pool without calculating final fit scores.

### Mandatory Stop

Stop for universe and identity-resolution review.

## Slice 5.4 - Portfolio Gap And Association Sources

### Work

Add deterministic source adapters for:

- sector diversification gaps;
- geography diversification gaps;
- peer and industry associations;
- underrepresented themes consistent with the Phase 4 profile.

Calculate gaps from point-in-time portfolio exposure and an explicit comparison policy. Do not infer that every underweight dimension should be filled. A gap may nominate a candidate only when the profile permits it and the source data supports the association.

Version sector, geography, peer, industry, benchmark, and theme mappings. Surface unknown classifications and incomplete benchmark coverage.

### Tests

- Concentrated portfolios produce relevant sector or geography source matches.
- Balanced portfolios do not receive artificial gap candidates.
- Unknown classifications do not become an `Other` gap that receives a positive score.
- Peer and theme associations require stored, versioned evidence.
- Profile conflicts block the corresponding source reason.

### Gate

Every source family required by Phase 5 has an implemented adapter and tests. A run may report a source as unavailable or unsupported only when its point-in-time local data proves that state; the implementation itself may not waive a required source family.

### Mandatory Stop

Stop for source-coverage and taxonomy review.

## Slice 5.5 - Deterministic Screens And Candidate Scoring

### Work

Implement quality, value, and momentum screens by adapting existing stored metrics. Then calculate:

- profile fit;
- expected sector and geography diversification effect;
- overlap or redundancy with current economic exposures;
- source support strength;
- bounded valuation, risk, momentum, quality, and sentiment highlights.

Freeze scoring bands, weights, caps, normalization, and tie-break rules in versioned definitions. Keep reason qualification separate from score magnitude. Multiple weak reasons must not overwhelm a blocking guardrail or one material missing input.

The final tie-break must be stable and explicit, for example:

1. eligibility state;
2. fit score descending;
3. diversification benefit descending;
4. redundancy ascending;
5. evidence coverage descending;
6. canonical asset ID ascending.

### Tests

- Golden fixtures cover concentrated growth, dividend/income, broad ETF-heavy, speculative small-cap, balanced, and insufficient-data portfolios.
- Repeated runs and permuted inputs return byte-equivalent ordered results.
- Exact score ties resolve by the documented tie-break.
- A high raw ranking cannot bypass profile conflict, redundancy, or missing critical evidence.
- Highlights report source metrics without converting absent metrics to zero.

### Gate

Candidate scores are deterministic, explainable from components, and reproducible from the recorded snapshot.

### Mandatory Stop

Stop for scoring-policy review. Do not tune weights from production outcomes in this slice.

## Slice 5.6 - Freshness, Missing Data, And Guardrails

### Work

Add candidate-specific policies for freshness and data sufficiency. Define thresholds by evidence type rather than using one global age threshold.

At minimum:

- block candidates with no material supporting evidence;
- block or downgrade stale candidates according to the frozen policy;
- block candidates when identity, price, or critical risk evidence is insufficient;
- preserve and display noncritical missing metrics;
- flag concentration, redundancy, liquidity, speculative-risk, unsupported-classification, and conflicting-evidence conditions when supported by local data;
- prevent sentiment from acting as sole material support;
- prevent stale positive evidence from outranking current contradictory evidence.

Keep guardrails structured and versioned. A warning is not a score penalty unless the methodology explicitly defines it as one.

### Tests

- No candidate is emitted as eligible or downgraded without evidence.
- Stale candidates are downgraded or blocked at each policy boundary.
- Missing metrics are surfaced exactly and do not become neutral values.
- Critical missing evidence blocks while noncritical missing evidence remains visible.
- Sentiment-only candidates are blocked.
- Guardrails produce stable codes, ordering, and evidence references.

### Gate

The three mandatory Phase 5 invariants are proven: no evidence-free candidate, stale-data downgrade or block, and explicit missing metrics.

### Mandatory Stop

Stop for guardrail and failure-mode review.

## Slice 5.7 - Orchestration And Read-Only Internal Service

### Work

Add one orchestration service that accepts a frozen portfolio evidence snapshot and Phase 4 investor profile, executes source adapters, applies guards and scores, persists the run, and returns the candidate-review contract.

The service must:

- perform no provider calls;
- perform no trade or recommendation action;
- avoid hidden writes except the explicit candidate-run persistence boundary;
- return the same result for the same versioned inputs;
- expose run status, source coverage, blocked counts, missing dependencies, and methodology version;
- fail closed when required snapshot versions are incompatible.

Do not add a public recommendation endpoint or UI. A narrow internal invocation or test harness is sufficient for Phase 5 unless the architecture contract explicitly requires a read-only candidate endpoint before Phase 8.

### Tests

- End-to-end fixtures exercise every source family and eligibility state.
- Identical snapshot and profile inputs return the same run identity and results.
- Changed evidence creates a new run.
- Provider clients are not invoked.
- Incompatible snapshot versions fail closed with a structured reason.
- Query and runtime budgets are measured for representative all-universe fixtures.

### Gate

One deterministic service can reproduce a complete candidate run from stored point-in-time inputs.

### Mandatory Stop

Stop for end-to-end service review. Do not begin recommendation logic.

## Slice 5.8 - Phase 5 Verification And Closure

### Work

1. Run all candidate unit, persistence, integration, architecture, and golden-fixture tests.
2. Run the existing ranking, signal, analytics, benchmark, watchlist, schema, and API tests affected by adapters.
3. Run the repository's full data-health workflow because Phase 5 consumes ranking, valuation, projection, portfolio, signal, and ingestion-readiness data.
4. Run the web data-health scan to prove backend changes did not break existing consumer surfaces.
5. Refresh the running application and inspect API health, rankings, signals, portfolio analytics, watchlists, and nearby navigation for regressions.
6. Produce a Phase 5 completion report mapping every master-prompt requirement to code, tests, and evidence.
7. Record unsupported source families, data limitations, methodology versions, and known biases without declaring them complete.

### Required Commands

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m tools.check_architecture_boundaries
.\.venv\Scripts\python.exe tools\run_full_data_health_workflow.py --cycles 4 --run-batches 10 --external-audit --json
Set-Location web
npm.cmd exec -- node ..\tools\scan_web_app_data_health.mjs
```

Also verify:

- `http://127.0.0.1:8000/api/v1/health`;
- `http://127.0.0.1:5173` or `http://localhost:5173`.

### Final Gate

Phase 5 is complete only when:

- every required candidate source family is implemented and tested;
- held economic exposures are excluded;
- every candidate has a reason code and stable evidence reference;
- fit, diversification, redundancy, highlights, missing data, and warnings are present;
- scoring and tie-breaking are deterministic;
- stale and insufficient evidence are downgraded or blocked by tested policy;
- all required fixture classes pass;
- candidate runs are point-in-time, versioned, persisted, and reproducible;
- no LLM, provider call, recommendation action, or trade path is involved;
- the full verification suite and live regression review pass;
- the completion report identifies no unresolved Phase 5 blocker.

### Mandatory Stop

Stop after publishing the Phase 5 completion report. Phase 6 requires separate authorization and a fresh implementation plan.

## Requirement Traceability

| Phase 5 requirement | Completion slice |
| --- | --- |
| Top-ranked stocks | 5.3 |
| Sector diversification gaps | 5.4 |
| Geography diversification gaps | 5.4 |
| Quality, value, and momentum screens | 5.5 |
| Peer and industry associations | 5.4 |
| Benchmark constituents or proxies | 5.3 |
| Watchlist assets | 5.3 |
| Profile-consistent underrepresented themes | 5.4 |
| Candidate ID and ticker | 5.1 |
| Reason code | 5.1, 5.3, 5.4 |
| Fit score | 5.5 |
| Diversification effect | 5.5 |
| Overlap or redundancy score | 5.5 |
| Valuation, risk, and sentiment highlights | 5.5 |
| Missing data | 5.1, 5.6 |
| Guardrail warnings | 5.1, 5.6 |
| Evidence references | 5.1, 5.3, 5.4 |
| Deterministic ranking and tie-breaks | 5.5 |
| No candidate without evidence | 5.6 |
| Stale candidate downgrade or block | 5.6 |
| Missing metrics surfaced | 5.6 |

Do not treat code changes alone as completion. Finish Phase 5 only after the candidate engine is reproducible from stored evidence, every required invariant is proven by tests, existing data and web surfaces have passed regression checks, and the completion report states any remaining limitations with evidence.
