# ADR PH15: Shared evidence freshness and eligibility policy

## Status

Implemented

## Date

2026-09-08

## Context

ADR PH14 established the display vocabulary but intentionally did not evaluate source facts.
The audit reconciliation plan requires later routes to use one clock-injectable, type-aware
policy instead of inventing stale logic page by page. This decision affects presentation only;
it does not authorize changes to financial calculations, persisted values, ingestion cadence,
retry behavior, or provider selection.

## Decision

`dashboard.api.evidence_contract.evaluate_evidence` is the single shared evaluator for the first
six decision-facing evidence types. It normalizes naive database timestamps as UTC and applies
these elapsed-time display windows:

| Evidence type | Current through | Warning through | Stale after |
| --- | ---: | ---: | ---: |
| Price | 36 hours | 96 hours | 96 hours |
| News | 24 hours | 72 hours | 72 hours |
| Financial statement | 150 days | 240 days | 240 days |
| Benchmark | 36 hours | 96 hours | 96 hours |
| Monthly signal | 45 days | 75 days | 75 days |
| Retail sentiment | 36 hours | 96 hours | 96 hours |

These are initial display thresholds, not ingestion schedules or model inputs. Price and
benchmark warning windows deliberately tolerate ordinary closed-market weekends without calling
old observations current indefinitely. Financial statements use a materially longer window than
market observations because their natural reporting cadence differs.

The evaluator carries source name, source health, observation/retrieval timestamps, missing
inputs, confidence and effectiveness sample size into a versioned `evidence-display.v1` read
model. Confidence is descriptive and never participates in the eligibility decision.

Precedence is conservative:

- a blocked source, fixture, proxy, unknown source kind/name, stale or unknown observation,
  unsupported coverage, or essential missing input yields `action_eligibility=blocked`;
- degraded or unknown source health, inferred evidence, warning-age evidence, partial optional
  coverage, or an explicit zero-size efficacy sample yields `action_eligibility=caution`;
- only real, named, healthy, current, complete evidence without those limitations is `eligible`.

A future observation or retrieval timestamp is invalid for display and blocks eligibility. A
missing observation is `freshness_state=unknown`; retrieval time alone cannot prove that the
underlying evidence is current.

Compatibility is additive. Existing response values can be copied unchanged and receive a new
`evidence` field. The default compatibility helper rejects known secret/raw-provider keys, while
the stronger allowlisted helper selects explicit public fields before attaching evidence. Route
migration remains in later slices so this policy does not silently alter existing API contracts.

## Consequences

- S3–S7 can consume one Python policy and one matching TypeScript shape.
- Existing calculation functions, database schemas, stored records, provider traffic, and
  action persistence are unaffected.
- Proxy and fixture data remain available for explanation but cannot be presented as ordinarily
  action-eligible.
- The thresholds are reviewable product policy. Changing them requires updating this ADR and
  boundary tests rather than editing scattered components.
- The contract contains display-safe metadata only; raw provider objects are not part of it.

## Verification

`tests/api/test_evidence_policy.py` executes exact boundary behavior for all six types, identical
ages under different policies, UTC normalization, precedence against confidence, missing/future
timestamps, no-efficacy state, response validation, additive compatibility, and adversarial raw
payload rejection. The S0 calculation baseline continues to prove that evidence construction does
not change a representative financial output.
