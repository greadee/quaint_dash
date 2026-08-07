# Deterministic Candidate Contracts

The Phase 5 candidate domain represents research-oriented outside-holding reviews. It does not assign recommendation actions, determine suitability, size trades, or call providers.

## Package Boundary

The provider-neutral contract lives in `dashboard.ai_brain.candidates`:

- `CandidateRun` records one point-in-time candidate evaluation and its reproducibility metadata.
- `CandidateReview` records one canonical asset's candidate state in a run.
- `CandidateSourceMatch` records why a source nominated an asset.
- `CandidateEvidenceRef` identifies one stored material source fact.
- `CandidateScore` and `CandidateScoreComponent` represent fit, diversification, and redundancy states without defining scoring policy.
- `CandidateHighlight`, `CandidateWarning`, and `CandidateMissingMetric` preserve structured supporting and limiting context.
- `CandidateSourceWatermark` records source coverage at the run boundary.

The domain models, identity functions, and canonical serializer import no database, API, provider, ranking, analytics, or UI module. `CandidateRunRepository` is the candidate-owned DuckDB infrastructure boundary added in Slice 5.2. Slice 5.3 source adapters query stored repository tables through a narrow read-only connection boundary. Scoring begins in later slices.

## Versions

Current contract versions are:

| Contract | Version |
| --- | --- |
| Candidate run schema | `candidate-run.v1` |
| Candidate review schema | `candidate-review.v1` |
| Candidate evidence schema | `candidate-evidence.v1` |
| Candidate methodology | `candidate-engine.deterministic.v1` |
| Candidate reason definitions | `candidate-reason-codes.v1` |
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

Slice 5.3 adds deterministic read-only adapters for:

- the latest persisted stock-ranking snapshot at or before `as_of`;
- active watchlist rows updated at or before `as_of`;
- bounded asset and stock-catalog search results updated at or before `as_of`;
- the latest stored benchmark composition and its constituents at or before `as_of`.

Each nomination has one versioned source reason and at least one stable evidence reference. The pool merges duplicate economic exposures, retains all distinct source reasons and evidence, and excludes direct or resolvable equivalent held exposures before scoring. The adapters do not hydrate data, call providers, mutate source tables, score candidates, or assign recommendation actions.

Ranking and benchmark composition records are dated snapshots. Watchlist, asset catalog, stock catalog, and broker position-map rows are mutable current-state tables; their watermarks and limitations explicitly report that historical reconstruction is partial. Empty requested snapshots report missing coverage. Omitted search terms or benchmark IDs report unsupported coverage rather than fabricating candidates.

## Portfolio Gap And Association Policy

Slice 5.4 adds five deterministic source families:

- sector gaps compare the latest frozen portfolio analytics exposure snapshot with one explicit benchmark exposure snapshot;
- geography gaps use the same policy for country exposure;
- peer associations require common effective-dated `business_strength_peer_member` membership;
- industry associations require common effective-dated `asset_business_classification.industry` values;
- themes require an observed Phase 4 theme tilt, an explicit versioned theme-to-index alias, and a stored theme benchmark composition.

Gap nomination is deliberately narrow. Portfolio and benchmark exposure totals must each be between 95% and 105%. At least 75% must have known classifications. `Unknown`, `Unclassified`, `Other`, and `Broad Market` never become positive gap dimensions. The portfolio must have at least 40% in one known sector or 60% in one known country. A benchmark dimension must carry at least 5%, and its gap versus the portfolio must be at least 10 percentage points.

Profile use is descriptive, not a suitability assessment. The profile must match the portfolio and supported schema/methodology, cannot be from the future, and cannot carry insufficient-data or dimension-classification conflicts. A conflict produces an evidence-backed blocked source nomination; it does not become a score penalty. Theme nominations additionally require an observed theme weight above zero and below 30%. This threshold identifies a bounded, profile-consistent research association; it does not assert that the investor should increase that theme.

Current asset labels and peer-group definitions remain mutable even where membership is effective-dated. Their source results therefore report partial historical coverage. Incomplete portfolio or benchmark exposure, missing mappings, missing compositions, and absent profile support return explicit missing or unsupported metadata and no fabricated candidates.

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

The contract supports valuation, risk, and sentiment highlights, but does not require all three when source data is unavailable. Missing values belong in `CandidateMissingMetric`, not fabricated highlights.

## Evidence Protocol

Evidence includes:

- evidence schema version;
- source domain and source schema version;
- stable source record identity;
- effective UTC `as_of`;
- material payload hash;
- freshness state: `current`, `stale`, or `unknown`.

Evidence newer than a review's `data_as_of` is invalid. Source matches, numeric score components, highlights, and warnings require evidence. A review with no evidence is invalid, including blocked reviews.

Freshness is represented but not adjudicated in Slice 5.1. Candidate-specific stale downgrade and block thresholds belong to Slice 5.6.

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

Through Slice 5.4, the candidate engine adds no:

- API or transport model;
- score weight, threshold, ranking, or tie-break policy;
- quality, value, or momentum screen;
- freshness or guardrail adjudication;
- recommendation action, LLM call, provider call, or UI.

## Verification

```powershell
.\.venv\Scripts\python.exe -m ruff check src\dashboard\ai_brain\candidates tests\ai_brain\candidates
.\.venv\Scripts\python.exe -m pytest tests\ai_brain\candidates -q
.\.venv\Scripts\python.exe -m pytest tests\test_ticker_universe.py -q
.\.venv\Scripts\python.exe -m tools.check_architecture_boundaries
```
