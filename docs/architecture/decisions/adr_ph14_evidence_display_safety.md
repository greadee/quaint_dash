# ADR PH14: Evidence display safety vocabulary

## Status

Accepted

## Date

2026-09-07

## Context

The 2026-09-05 web application audit found inconsistent presentation of freshness, provider
health, proxy/fixture provenance, coverage, and actionability. Different pages could present the
same kind of imperfect evidence as healthy, active, current, or high confidence. The issue is a
display/read-model concern; the audit did not identify authority to change financial calculations,
provider ingestion, persistence semantics, or investment thresholds.

The codebase already has several local freshness and provenance conventions. Candidate reviews,
benchmark ingestion, comparison data, broker status, and news all have useful signals, but they
are not one UI-safe vocabulary. A later implementation must be able to migrate surfaces without
breaking existing persisted records or numerical output.

## Decision

Create the internal, read-only `dashboard.api.evidence_contract` vocabulary as the baseline for
future API/read-model work. It is not yet an API response field and does not evaluate live data.

The versioned vocabulary is:

| Dimension | States | Meaning |
| --- | --- | --- |
| Source kind | `real`, `proxy`, `fixture`, `inferred`, `unknown` | What kind of evidence produced the existing value. |
| Freshness | `current`, `warning`, `stale`, `blocked`, `unknown` | Age/availability state, evaluated later with evidence-type-specific policies. |
| Coverage | `complete`, `partial`, `missing`, `unsupported`, `unknown` | Whether the required source/input set exists. |
| Action eligibility | `eligible`, `caution`, `blocked` | Whether the resulting display may be used in ranking, recommendation, alert, or other action-like UI. |

All non-normal states require one or more stable, lowercase dotted reason codes. Human text is
deliberately outside this type, so routes can give context-specific copy without changing the
machine-readable state.

The future evaluator must be clock-injectable and type-aware. It must not use one freshness
threshold for prices, news, financial statements, signals, or benchmark observations. Policy
precedence is conservative: a blocked source, fixture/synthetic source, or essential missing
input cannot be visually overridden by a numerical confidence value.

## Consequences

- S2 of the audit reconciliation sprint has a stable, tested vocabulary before it adds route/API
  adapters or UI display logic.
- Existing calculation functions and persisted entities remain unchanged.
- Existing public response models remain unchanged in this slice; future additive response fields
  must be versioned/compatible and covered by contract tests.
- A display state alone never triggers provider work, job execution, imports, retries, writes, or
  alert/watchlist persistence.
- New analytical UI must show provenance/freshness/coverage/action eligibility together rather
  than presenting confidence alone as a quality guarantee.

## Verification

`tests/api/test_evidence_contract_baseline.py` freezes the state vocabulary, validates reason-code
requirements, and proves that constructing display state does not alter a representative financial
calculation result. Existing calculation, broker-redaction, import-idempotency, and direct
portfolio-creation tests remain the broader S0 regression baseline.
