# ADR PH13: Deterministic Candidate Engine Boundary

## Status

Accepted.

## Context

Quaint Dash has deterministic portfolio analytics, stock rankings, watchlists, benchmark constituents and proxies, asset classifications, valuation, risk, and sentiment data. These capabilities can nominate and describe assets outside the current portfolio, but they do not yet form an auditable candidate engine.

The candidate engine will feed a later recommendation layer. If Phase 5 mixes profile inference, candidate discovery, recommendation actions, provider calls, or transport models, later decisions will be difficult to reproduce and unsafe to explain. The boundary and point-in-time contract therefore need to be fixed before domain models, persistence, or scoring are added.

## Decision

Create a dedicated deterministic candidate-engine domain and application boundary. It consumes frozen portfolio evidence and a completed Phase 4 investor profile, produces research candidates, and persists reproducible candidate runs. It does not make recommendation decisions.

The dependency direction is:

```text
stored source snapshots -> narrow source adapters -> candidate domain
Phase 4 profile --------^                         |
                                                   v
                                      candidate run persistence
```

API routes, UI components, LLM providers, and recommendation services may consume the candidate application contract later. They do not own candidate generation or scoring.

## Frozen Vocabulary

### Candidate run

A complete deterministic evaluation of one portfolio scope, one investor-profile version, one methodology version, and one compatible set of point-in-time source snapshots.

The same semantic inputs must produce the same input snapshot hash, run identity, and ordered candidate reviews.

### Candidate review

The research record for one canonical outside-holding asset in one candidate run. It records why the asset entered the pool, its component scores, evidence, missing metrics, warnings, and eligibility state. It is not a recommendation or authorization to trade.

### Candidate source

A versioned deterministic nomination mechanism. Required source families are ranking, watchlist, all-universe screen, sector gap, geography gap, quality/value/momentum screen, peer/industry association, benchmark constituent or proxy, and profile-consistent underrepresented theme.

A source can nominate an asset. It cannot bypass evidence, identity, freshness, profile, or guardrail checks.

### Reason code

A stable, versioned machine code explaining a source match or material scoring condition. Display labels are presentation fields and may change without changing reason identity.

Reason codes use lowercase dotted namespaces, for example:

- `source.ranking.aggregate`;
- `source.watchlist.active`;
- `gap.sector.underrepresented`;
- `association.industry.member`;
- `screen.value.qualifies`;
- `guardrail.evidence.stale`;
- `guardrail.exposure.already_held`.

### Evidence reference

A stable reference to a stored source fact or snapshot record. It identifies the source domain, source record or natural key, source schema version, effective `as_of`, and material payload hash. A display label or list position is not an evidence identity.

### Eligibility state

- `eligible`: all critical evidence and identity requirements pass.
- `downgraded`: the asset remains researchable, but a noncritical freshness, coverage, or warning policy lowers its standing.
- `blocked`: the asset may be retained in an audit result but cannot appear in an eligible candidate list. The blocking reason and evidence must be explicit.

Every candidate review, including a blocked review, must contain at least one stable evidence reference. An asset with no source evidence is not a candidate review.

### Fit score

A bounded deterministic measure of consistency with the completed Phase 4 profile. It does not measure suitability, expected return, or recommendation strength.

### Diversification effect

A deterministic before/after estimate of how a standardized hypothetical exposure changes approved portfolio dimensions. It is not a rebalance amount. The hypothetical weight and comparison policy must be versioned and visible.

### Redundancy score

A bounded estimate of overlap with existing economic exposure, including direct holdings and resolvable underlying exposure. Unknown exposure is missing evidence, not zero redundancy.

## Point-In-Time Policy

1. Every candidate run has one UTC `as_of` timestamp and a source watermark for each input domain.
2. No source record effective after the run's `as_of` may affect the run.
3. Freshness is measured relative to the run's `as_of`, not the wall-clock time of replay.
4. Source adapters read stored snapshots or bounded point-in-time queries. They do not call providers, schedule ingestion, or hydrate missing data.
5. Profile, portfolio evidence, ranking, benchmark, classification, valuation, risk, and sentiment inputs must declare compatible schema and methodology versions.
6. An incompatible or missing critical watermark fails the run closed with a structured blocking condition.
7. Historical candidate runs are immutable. New evidence creates a new run instead of updating an old run.

Use RFC 3339 UTC timestamps at whole-second precision with a `Z` suffix. Use ISO 8601 dates in `YYYY-MM-DD` form. Naive local timestamps are invalid at the candidate boundary.

## Canonical Identity

- Canonical asset identity is the repository `asset_id` after documented alias and underlying resolution.
- Candidate review ID is derived from the candidate run ID and canonical asset ID.
- Candidate run ID is derived from the candidate methodology version and canonical input snapshot hash.
- Evidence reference ID is derived from source domain, source schema version, stable source record identity, effective `as_of`, and material payload hash.
- Direct holdings, CDRs, aliases, and resolvable underlying exposures share an economic-exposure identity for exclusion and redundancy checks.
- ETF overlap remains a weighted exposure relationship, not automatic identity equivalence.
- Unresolved aliases or underlyings cannot be assumed distinct. Candidate eligibility fails closed according to the versioned guardrail policy.

IDs use lowercase type prefixes followed by lowercase hexadecimal SHA-256 values. Human-readable tickers and labels are not part of identity.

## Canonical Serialization And Hashing

Candidate canonical JSON uses:

- UTF-8 encoding;
- lexicographically sorted object keys;
- arrays sorted by their stable identity or documented semantic order;
- no insignificant whitespace;
- booleans and nulls as JSON primitives;
- timestamps and dates in the formats fixed above;
- decimal values represented as normalized decimal strings, not binary floating-point renderings.

Calculations may keep greater internal precision, but canonical score and weight values are quantized to eight decimal places using round-half-even before hashing or persistence. API display rounding is presentation behavior and does not affect hashes.

The input snapshot hash includes:

- candidate schema and methodology versions;
- portfolio scope and economic-exposure identities;
- investor-profile identity, version, and material dimensions;
- source watermarks;
- every material source evidence ID and normalized value;
- missing, unsupported, stale, and blocking states that can change output.

The input snapshot hash excludes:

- run creation and update timestamps;
- database surrogate row IDs that do not represent source identity;
- presentation labels, summaries, and ordering metadata;
- request IDs, logging fields, and runtime duration;
- cached values that are not consumed by the methodology.

The output hash additionally includes ordered candidate review identities, reason codes, score components, eligibility states, missing metrics, warnings, and evidence references.

## Contract Semantics

Phase 5 domain models must eventually represent these semantic fields without importing FastAPI response models:

| Contract | Required semantics |
| --- | --- |
| Candidate run | run ID, portfolio scope, `as_of`, schema version, methodology version, profile ID/version, input snapshot hash, output hash, source watermarks, source coverage, run status, candidate counts, blocking conditions |
| Candidate review | review ID, run ID, canonical asset ID, ticker snapshot, reason codes, source matches, fit, diversification effect, redundancy, highlights, missing metrics, warnings, eligibility state, evidence references |
| Source match | source family, source methodology version, reason code, nomination strength if applicable, evidence references |
| Evidence reference | evidence ID, source domain, source schema version, stable record identity, `as_of`, freshness state, material payload hash |
| Highlight | category, normalized value, unit, direction where meaningful, source date, evidence references |
| Missing metric | stable metric code, criticality, expected source, reason, guardrail effect |
| Warning | stable warning code, severity, blocking flag, evidence references |
| Score component | stable component code, normalized decimal value, weight, contribution, reason codes, evidence references |

No candidate review may omit fit, diversification, or redundancy state. When a numeric result cannot be computed, the value remains null and a structured missing metric explains why.

## Module Ownership

The candidate engine belongs in a dedicated backend package aligned with the modular-monolith dependency rules from ADR PH10. The package owns domain contracts, canonical serialization, source-adapter interfaces, scoring policy, guardrails, and orchestration.

Infrastructure code owns DuckDB persistence and source queries. Existing analytics, rankings, benchmarks, watchlists, and signals remain separate capabilities accessed through narrow adapters.

`PortfolioApiService` is not the candidate domain owner. Temporary adapters around its current ranking and factor methods require explicit deletion criteria.

## Alternatives Considered

### Extend stock-ranking responses into candidates

Rejected. Rankings are one nomination source and include held assets. They do not represent profile fit, diversification effect, economic-exposure redundancy, candidate evidence, or guardrails.

### Reuse signal evaluations as candidate reviews

Rejected. Signals describe factor conditions and portfolio impacts. Their evidence IDs are currently positional, and their lifecycle does not establish outside-holding eligibility.

### Infer the investor profile inside candidate scoring

Rejected. It would duplicate Phase 4, hide profile assumptions, and make candidate scores impossible to compare independently from profile changes.

### Use current wall-clock freshness during replay

Rejected. A historical run would change without input changes and could not be reproduced.

### Add the public API and UI during Phase 5

Rejected. Phase 5 completes the deterministic backend candidate contract. Read-only product surfaces belong to the later API/UI phase.

## Consequences

- Phase 5 cannot proceed beyond Slice 5.0 until the Phase 4 profile contract exists.
- Existing analytics and ranking code remain reusable but require adapters and stronger evidence identity.
- Candidate results become reproducible, point-in-time, and auditable before recommendation logic exists.
- Canonical serialization and precision add implementation work in Slice 5.1 but prevent unstable IDs and snapshot drift later.
- Economic-exposure ambiguity fails closed instead of silently producing duplicate or already-held candidates.

## Implementation Status

Slice 5.1 implements the provider-neutral contracts and canonical evidence protocol under `src/dashboard/rules_and_data/candidates`. The frozen schema, methodology, reason-code, identity, timestamp, decimal, ordering, and volatile-field rules are documented in `docs/features/candidate-engine.md` and covered by pure contract tests.

Slice 5.2 implements repeatable DuckDB schema initialization and immutable candidate-run persistence. Query-critical run and review fields are structured; canonical versioned review payloads preserve score components, highlights, and nested evidence associations. Reads verify normalized rows and canonical hashes before returning domain models.

Slice 5.3 implements read-only persisted-source adapters for rankings, watchlists, asset/catalog search, and benchmark constituents or proxies. It also implements shared CDR-underlying resolution and a deterministic outside-holding pool that merges source evidence, excludes direct and resolvable equivalent holdings, and blocks unresolved nominations.

Slice 5.4 implements sector and geography gap adapters over frozen portfolio and benchmark exposure snapshots, effective-dated peer and industry associations, and profile-consistent theme associations over stored benchmark compositions. Gap thresholds, unknown-classification exclusions, profile conflicts, and theme aliases are versioned. Incomplete exposure fails closed.

Slice 5.5 implements quality, value, and momentum screen adapters plus deterministic profile-fit, diversification, economic-overlap redundancy, source-support, highlight, and ordering policies. Numeric scores require their documented contributors; missing critical score evidence blocks ordering, material redundancy downgrades eligibility, and raw ranking magnitude cannot override either state. Screen and score policies are versioned separately from source schemas.

Slice 5.6 implements evidence-type freshness thresholds and a monotonic post-scoring guardrail policy. Critical identity, price, and risk evidence fails closed; material support excludes sentiment, catalog, watchlist, profile, portfolio, and overlap-only evidence. Liquidity, speculative risk, concentration, redundancy, unsupported classification, undated ETF look-through, and stale/current conflicts produce stable warnings with explicit eligibility effects. Numeric scores are never silently penalized.

Slice 5.7 implements `candidate-orchestration.v1` behind one internal `CandidateRunService`. A normalized request, complete Phase 4 profile, resolved source pool, and pre-identity evidence/missing-state graph determine `candidate-engine.deterministic.v3` run identity. The service applies existing scoring and guardrails, persists once through the immutable repository, and returns the persisted `CandidateRun`. Unsupported or incomplete source coverage produces deterministic partial or blocked run states. Required profile, identity, watermark, and source-version conflicts raise a structured compatibility error before scoring or persistence.

Mutable current-state sources disclose partial historical coverage. Phase 4 profile observations constrain source eligibility but are not treated as suitability permission. No candidate source, guardrail, or orchestration path hydrates missing data or calls a provider. No public API, recommendation, or UI behavior is implemented through Slice 5.7.

## Deferred

- Phase 5 closure evidence and full requirement traceability to Slice 5.8.
- Public API, UI, recommendation decisions, LLM providers, and trade behavior to later phases.

## Validation Method

- Verify every prerequisite claim against current code, schema, and tests.
- Run candidate contract, persistence, source, scoring, freshness, and guardrail tests.
- Run repository lint, architecture, test, data-health, and live-web regression checks.
- Confirm no provider, recommendation, trade, API, or UI path was added.

## Related ADRs

ADR-061, ADR-063, ADR-065, ADR-079, ADR-080, ADR-081, ADR PH6, ADR PH10, ADR PH11, and ADR PH12 remain valid. ADR PH13 narrows how their analytics, ranking, evidence, and module boundaries may be consumed by the candidate engine.
