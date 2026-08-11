# Deterministic Candidate Contracts

The candidate domain represents research-oriented outside-holding reviews. It does not assign recommendation actions, determine suitability, size trades, or call providers.

## Package Boundary

The provider-neutral contract lives in `dashboard.rules_and_data.candidates`:

- `CandidateRun` records one point-in-time candidate evaluation and its reproducibility metadata.
- `CandidateReview` records one canonical asset's candidate state in a run.
- `CandidateSourceMatch` records why a source nominated an asset.
- `CandidateEvidenceRef` identifies one stored material source fact.
- `CandidateScore` and `CandidateScoreComponent` represent fit, diversification, and redundancy states without defining scoring policy.
- `CandidateHighlight`, `CandidateWarning`, and `CandidateMissingMetric` preserve structured supporting and limiting context.
- `CandidateSourceWatermark` records source coverage at the run boundary.
- `CandidateRunService` composes the frozen invocation, adapters, scoring, guardrails, and immutable run repository without exposing a transport boundary.

The domain models, identity functions, and canonical serializer import no database, API, provider, ranking, analytics, or UI module. `CandidateRunRepository` is the candidate-owned DuckDB infrastructure boundary. Source, scoring, and guardrail services query stored repository tables through narrow read-only connection boundaries.

## Versions

Current contract versions are:

| Contract | Version |
| --- | --- |
| Candidate run schema | `candidate-run.v1` |
| Candidate review schema | `candidate-review.v1` |
| Candidate evidence schema | `candidate-evidence.v1` |
| Candidate methodology | `candidate-engine.deterministic.v3` |
| Candidate orchestration policy | `candidate-orchestration.v1` |
| Candidate screen policy | `candidate-screens.v1` |
| Candidate scoring policy | `candidate-scoring.v1` |
| Candidate guardrail policy | `candidate-guardrails.v1` |
| Candidate score inputs | `candidate-score-inputs.v1` |
| Economic-overlap source | `candidate-economic-overlap.v1` |
| Candidate identity evidence | `candidate-identity.v1` |
| Candidate price evidence | `candidate-price-snapshot.v1` |
| Candidate liquidity evidence | `candidate-liquidity-snapshot.v1` |
| Candidate reason definitions | `candidate-reason-codes.v2` |
| Candidate source adapters | `candidate-source-adapters.v1` |
| Economic-exposure identity | `candidate-economic-exposure.v1` |
| Portfolio gap policy | `candidate-portfolio-gap.v1` |
| Portfolio analytics source | `portfolio-analytics-snapshot.v1` |
| Benchmark exposure source | `benchmark-exposure-snapshot.v1` |
| Business peer source | `business-strength-peer-group.v1` |
| Business classification source | `asset-business-classification.v1` |
| Profile theme source | `profile-theme-benchmark.v1` |

Contract-shape changes require a schema-version change. Material identity, normalization, score, ordering, or guardrail semantic changes require a methodology-version change. Adding or changing the meaning of a reason code requires a reason-code version change.

## Identity

IDs use a lowercase type prefix and lowercase SHA-256 digest:

- `candidate-run:<digest>` derives from candidate methodology version and input snapshot hash.
- `candidate:<digest>` derives from canonical repository asset identity.
- `candidate-review:<digest>` derives from candidate run ID and candidate ID.
- `candidate-evidence:<digest>` derives from source domain, source schema version, stable source record identity, effective `as_of`, and material payload hash.

Tickers are uppercase point-in-time labels and do not determine identity. Model validation rejects malformed or materially inconsistent IDs.

For outside-holding exclusion, direct repository assets and documented CDR wrappers resolve to one economic-exposure identity. The resolver uses repository asset metadata and the shared CDR alias policy; it does not infer arbitrary ticker relationships. ETF overlap remains a later weighted redundancy relationship and is not identity equivalence. Missing or ambiguous identities and missing CDR underlyings fail closed as blocked nominations with evidence-backed warnings.

## Source Adapters And Outside-Holding Pool

Deterministic read-only adapters cover:

- the latest persisted stock-ranking snapshot at or before `as_of`;
- active watchlist rows updated at or before `as_of`;
- bounded asset and stock-catalog search results updated at or before `as_of`;
- the latest stored benchmark composition and its constituents at or before `as_of`.

Each nomination has one versioned source reason and at least one stable evidence reference. The pool merges duplicate economic exposures, retains all distinct source reasons and evidence, and excludes direct or resolvable equivalent held exposures before scoring. The adapters do not hydrate data, call providers, mutate source tables, score candidates, or assign recommendation actions.

Ranking and benchmark composition records are dated snapshots. Watchlist, asset catalog, stock catalog, and broker position-map rows are mutable current-state tables; their watermarks and limitations explicitly report that historical reconstruction is partial. Empty requested snapshots report missing coverage. Omitted search terms or benchmark IDs report unsupported coverage rather than fabricating candidates.

## Portfolio Gap And Association Policy

Five deterministic source families cover:

- sector gaps compare the latest frozen portfolio analytics exposure snapshot with one explicit benchmark exposure snapshot;
- geography gaps use the same policy for country exposure;
- peer associations require common effective-dated `business_strength_peer_member` membership;
- industry associations require common effective-dated `asset_business_classification.industry` values;
- themes require an observed investor-profile theme tilt, an explicit versioned theme-to-index alias, and a stored theme benchmark composition.

Gap nomination is deliberately narrow. Portfolio and benchmark exposure totals must each be between 95% and 105%. At least 75% must have known classifications. `Unknown`, `Unclassified`, `Other`, and `Broad Market` never become positive gap dimensions. The portfolio must have at least 40% in one known sector or 60% in one known country. A benchmark dimension must carry at least 5%, and its gap versus the portfolio must be at least 10 percentage points.

Profile use is descriptive, not a suitability assessment. The profile must match the portfolio and supported schema/methodology, cannot be from the future, and cannot carry insufficient-data or dimension-classification conflicts. A conflict produces an evidence-backed blocked source nomination; it does not become a score penalty. Theme nominations additionally require an observed theme weight above zero and below 30%. This threshold identifies a bounded, profile-consistent research association; it does not assert that the investor should increase that theme.

Current asset labels and peer-group definitions remain mutable even where membership is effective-dated. Their source results therefore report partial historical coverage. Incomplete portfolio or benchmark exposure, missing mappings, missing compositions, and absent profile support return explicit missing or unsupported metadata and no fabricated candidates.

## Deterministic Screens

Three read-only screen sources cover:

- quality requires a latest stored business-strength score of at least 70 with confidence and completeness each at least 60;
- value averages available DCF and dividend-discount margins of safety, maps -25% to 0 and +50% to 100, and requires a normalized score of at least 65;
- momentum requires a latest stored ticker-factor momentum score of at least 70.

Scores must come from snapshots at or before `as_of`. The adapters do not calculate or hydrate missing source rows. A source with snapshots but no qualifying asset reports `available` coverage and `no_qualifying_assets`; a source without a snapshot reports `missing` coverage.

## Candidate Scoring Policy

The versioned `candidate-scoring.v1` policy constructs three independent score states.

Profile fit uses five observed investor-profile dimensions plus bounded source support:

| Component | Weight |
| --- | ---: |
| Growth alignment | 16% |
| Value alignment | 20% |
| Quality alignment | 20% |
| Income alignment | 12% |
| Speculative-risk alignment | 12% |
| Source support | 20% |

Each alignment is `100 - absolute(candidate score - observed profile score)`, bounded to 0-100. Candidate factors prefer the stored ticker-factor snapshot. Stored asset analytics may supply growth, valuation, and risk where the factor snapshot does not; the latest business-strength score is the quality authority. Income uses the stored dividend factor. A numeric fit requires all five alignment dimensions. Source support starts at 35 for one evidenced source family, adds 15 per additional family and 5 per additional evidence domain, and is capped at 100. It cannot make an incomplete alignment numeric.

Diversification models a fixed 5% hypothetical allocation for comparison only. It scales the existing sector or country exposure to 95%, adds 5% to the candidate classification, and measures the HHI reduction against the maximum possible reduction at that allocation size. Both sector and geography require 95%-105% total exposure, at least 75% known classification, and a known candidate classification. The final diversification score weights sector and geography equally. It does not size a trade or claim that the hypothetical allocation should occur.

Redundancy builds economic-exposure maps from the frozen portfolio positions and stored ETF look-through rows where applicable. It is the sum of the minimum candidate and portfolio weights for shared economic exposures, bounded to 0-100. Direct and equivalent holdings remain exclusions before scoring. An ETF without look-through holdings has an unavailable redundancy score instead of zero. ETF holdings are a mutable current-state source, so the policy leaves overlap evidence `unknown` when an undated ETF look-through row participates and downgrades the review. A score of 50 or more also moves an otherwise complete review to `downgraded`; it is not silently subtracted from another score.

Valuation, quality, momentum, risk, and sentiment highlights preserve their own bounded 0-100 source metric and evidence. An absent highlight produces a noncritical missing metric and no synthetic zero-valued highlight.

Final ordering is:

1. eligibility: `eligible`, `downgraded`, then `blocked`;
2. fit descending, with null last;
3. diversification descending, with null last;
4. redundancy ascending, with null last;
5. distinct evidence-domain coverage descending;
6. canonical asset ID ascending.

Profile identity/version/coverage conflicts and missing critical score evidence block ordering. Raw ranking magnitude is source evidence only and is not a fit component, so it cannot bypass profile conflict, unavailable critical scores, or a material redundancy downgrade. These definitions are versioned and are not tuned from production outcomes.

## Freshness And Guardrail Policy

`candidate-guardrails.v1` applies after scoring and before final ordering. Freshness is evaluated against the review's frozen `data_as_of`, never the wall clock. Calendar age is defined by evidence type:

| Evidence type | Current through | Block after |
| --- | ---: | ---: |
| Daily market price | 7 days | 14 days |
| Daily liquidity sample | 14 days | 30 days |
| Factor or ranking snapshot | 45 days | 120 days |
| Valuation or risk analytics | 120 days | 365 days |
| Business quality | 180 days | 540 days |
| Portfolio state or gap | 30 days | 90 days |
| Benchmark composition | 90 days | 365 days |
| Classification | 365 days | 1,095 days |
| Peer or industry association | 365 days | 730 days |
| Canonical identity metadata | 365 days | 730 days |
| Investor profile | 30 days | 90 days |
| Sentiment | 3 days | 14 days |
| Catalog or watchlist state | 180 days | 365 days |
| Dated derived overlap | 30 days | 90 days |

Evidence at the current boundary is `current`. Evidence one day beyond that boundary is `stale`. Critical identity, price, or risk evidence within its stale window downgrades; evidence beyond its block boundary blocks. Unknown critical freshness also blocks. If every material source reference is stale, the review downgrades; if every material source reference is beyond its block boundary, the review blocks. Stale material evidence alongside current material support remains visible as an informational warning. Unknown domains retain `unknown` freshness rather than inheriting a global default.

Material candidate support is limited to versioned ranking, screen, benchmark, gap, peer, industry, and theme evidence. Catalog presence, watchlist membership, investor-profile facts, portfolio state, overlap calculations, and sentiment do not independently establish material support. A review with no material support blocks. A sentiment-only review receives the specific `guardrail.support.sentiment_only` block.

Stored `asset_quote_daily` rows provide critical price evidence and a 20-row liquidity sample. Liquidity requires at least 10 positive-volume observations. Missing coverage remains an explicit noncritical metric and downgrades. Median daily local-currency notional below 1,000,000 downgrades as low liquidity; below 100,000 receives the stronger `extremely_low` warning but remains a research downgrade, not a trade or suitability decision.

Risk highlights at or above 70 receive a structured speculative-risk warning without changing eligibility. A score at or above 90 downgrades. Diversification at or below 20 produces an informational concentration warning. Redundancy at or above 50 produces a structured downgrade warning. Missing supported sector or geography classification blocks when the corresponding diversification input is unavailable.

A stale positive highlight combined with current negative evidence produces `guardrail.evidence.current_contradiction` and downgrades the review, so it cannot outrank a current eligible review. Mixed current positive and negative evidence remains visible as informational context. Warnings never alter numeric fit, diversification, or redundancy values; eligibility effects are explicit in the versioned policy.

## Orchestration And Run State

The internal `CandidateRunService` accepts a frozen `CandidateRunRequest` containing one positive portfolio ID, one UTC whole-second `as_of`, one completed investor profile, and normalized source parameters. Search terms and benchmark IDs are deduplicated and sorted. Request IDs, clocks, and runtime measurements are not material inputs.

The service executes all twelve stored-source families through `OutsideHoldingUniverseBuilder`, applies `CandidateScoringEngine` and `CandidateGuardrailPolicy`, derives the final run identity, persists through `CandidateRunRepository`, reads the immutable row back, and returns `CandidateRun`. Source reads and persistence share one DuckDB transaction so a run cannot combine before-and-after views of concurrent source writes. It has no provider, network, recommendation, trade, API, or UI dependency.

The `candidate-engine.deterministic.v3` input snapshot hash includes:

- run, review, evidence, adapter, screen, scoring, guardrail, identity, and orchestration versions;
- normalized portfolio scope, `as_of`, source parameters, and the complete material investor profile;
- all source watermarks, pool candidates, held-exposure exclusions, blocked identities, and source limitations;
- the evidence, score-input states, missing metrics, freshness states, and guardrail states resolved before final run IDs are rebound.

Creation time, request ID, runtime, output hash, and temporary pre-hash run IDs remain excluded. Repeating the same versioned invocation returns the originally persisted run, including its volatile audit fields. Changed source evidence changes the input hash and creates a new immutable run.

Required profile schema, profile methodology, profile identity, portfolio scope, profile time, candidate identity methodology, source watermark domains, and source schema versions are checked before persistence. Incompatibility raises `CandidateInputCompatibilityError` with a structured reason, dependency, expected value, and actual value. Scoring does not execute when pool versions are incompatible.

Run state is deterministic:

- `blocked` when no review exists or every review is blocked;
- `partial` when at least one review can proceed but any source watermark is partial, missing, or unsupported;
- `completed` when at least one review can proceed and every source watermark is available.

Candidate eligibility remains independent of run state. `CandidateRun` exposes eligible, downgraded, and blocked counts. `missing_dependencies` deterministically combines missing or unsupported source domains with every review's structured missing-metric source. Source coverage remains available in the persisted watermarks.

## Review Invariants

Every candidate review must contain:

- one canonical asset and one candidate/run identity;
- at least one unique, versioned, lowercase dotted reason code;
- at least one evidence-backed source match;
- explicit fit, diversification, and redundancy score states;
- top-level evidence containing every nested source, score, highlight, and warning reference;
- UTC whole-second data and methodology timestamps;
- exactly one eligibility state: `eligible`, `downgraded`, or `blocked`.

A numeric score requires components and evidence. An unavailable score remains null and names a `CandidateMissingMetric` included by the review. Missing values are not converted to neutral scores. A blocking warning requires blocked eligibility.

The contract supports valuation, quality, momentum, risk, and sentiment highlights, but does not require all five when source data is unavailable. Missing values belong in `CandidateMissingMetric`, not fabricated highlights.

## Evidence Protocol

Evidence includes:

- evidence schema version;
- source domain and source schema version;
- stable source record identity;
- effective UTC `as_of`;
- material payload hash;
- freshness state: `current`, `stale`, or `unknown`.

Evidence newer than a review's `data_as_of` is invalid. Source matches, numeric score components, highlights, and warnings require evidence. A review with no evidence is invalid, including blocked reviews.

Freshness states are material run output derived from evidence-type thresholds and the frozen review boundary. Replaying the same evidence at the same `data_as_of` yields the same freshness and guardrail output.

## Canonical Serialization

Canonical JSON uses:

- UTF-8-compatible JSON with ASCII escaping;
- lexicographically sorted object keys;
- no insignificant whitespace;
- UTC RFC 3339 timestamps at whole-second precision with `Z`;
- ISO 8601 dates;
- decimal strings quantized to eight places with round-half-even;
- stable identity ordering for reviews, components, evidence, source matches, highlights, missing metrics, warnings, watermarks, and reason codes.

Equivalent source, evidence, and reason-code permutations serialize and hash identically. A material evidence change changes the review and run output hash.

## Hash Material

Candidate hashes include every material contract field. `VOLATILE_HASH_FIELDS` explicitly excludes:

- `created_at`;
- `output_hash`;
- `request_id`;
- `runtime_ms`.

The run's `input_snapshot_hash` is material. `CandidateRun.expected_output_hash` recomputes the material output hash, and `output_hash_is_valid` reports integrity. Candidate persistence rejects writes and reads whose output hash does not match.

## Persistence

`src/dashboard/db/migrations/candidate_runs.sql` creates eight narrowly scoped tables:

- candidate run metadata;
- source watermarks;
- candidate reviews;
- review reason codes;
- source matches;
- run-scoped evidence;
- missing metrics;
- warnings.

Run-scoped evidence preserves freshness as evaluated at that run's point in time. Query-critical review fields, including eligibility and the three top-level scores, use typed columns. The complete versioned review graph is also stored as canonical JSON so score components, highlights, and nested evidence associations round-trip without prematurely freezing later scoring-query tables.

Writes are transactional and immutable. Repeating the same run identity and material output is idempotent and leaves the original `created_at`, request ID, and runtime unchanged. Reusing a run identity with different material output fails with `CandidatePersistenceConflict`. New input snapshot hashes create distinct historical runs.

Reads rebuild domain models, verify canonical review payload hashes, compare typed and normalized child rows with the payload, validate run-scoped evidence, and recompute the run output hash. Any mismatch fails with `CandidatePersistenceIntegrityError`.

## Current Explicit Exclusions

The current candidate engine adds no:

- API or transport model;
- recommendation action, LLM call, provider call, or UI.

## Verification

```powershell
.\.venv\Scripts\python.exe -m ruff check src\dashboard\rules_and_data\candidates tests\rules_and_data\candidates
.\.venv\Scripts\python.exe -m pytest tests\rules_and_data\candidates -q
.\.venv\Scripts\python.exe -m pytest tests\test_ticker_universe.py -q
.\.venv\Scripts\python.exe -m tools.check_architecture_boundaries
```
