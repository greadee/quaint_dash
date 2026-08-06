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

The domain models, identity functions, and canonical serializer import no database, API, provider, ranking, analytics, or UI module. `CandidateRunRepository` is the candidate-owned DuckDB infrastructure boundary added in Slice 5.2. Source adapters and scoring begin in later slices.

## Versions

Current contract versions are:

| Contract | Version |
| --- | --- |
| Candidate run schema | `candidate-run.v1` |
| Candidate review schema | `candidate-review.v1` |
| Candidate evidence schema | `candidate-evidence.v1` |
| Candidate methodology | `candidate-engine.deterministic.v1` |
| Candidate reason definitions | `candidate-reason-codes.v1` |

Contract-shape changes require a schema-version change. Material identity, normalization, score, ordering, or guardrail semantic changes require a methodology-version change. Adding or changing the meaning of a reason code requires a reason-code version change.

## Identity

IDs use a lowercase type prefix and lowercase SHA-256 digest:

- `candidate-run:<digest>` derives from candidate methodology version and input snapshot hash.
- `candidate:<digest>` derives from canonical repository asset identity.
- `candidate-review:<digest>` derives from candidate run ID and candidate ID.
- `candidate-evidence:<digest>` derives from source domain, source schema version, stable source record identity, effective `as_of`, and material payload hash.

Tickers are uppercase point-in-time labels and do not determine identity. Model validation rejects malformed or materially inconsistent IDs.

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

Slice 5.2 adds no:

- API or transport model;
- source query or adapter;
- candidate nomination or held-asset exclusion;
- score weight, threshold, ranking, or tie-break policy;
- freshness or guardrail adjudication;
- recommendation action, LLM call, provider call, or UI.

## Verification

```powershell
.\.venv\Scripts\python.exe -m ruff check src\dashboard\ai_brain\candidates tests\ai_brain\candidates
.\.venv\Scripts\python.exe -m pytest tests\ai_brain\candidates -q
.\.venv\Scripts\python.exe -m tools.check_architecture_boundaries
```
