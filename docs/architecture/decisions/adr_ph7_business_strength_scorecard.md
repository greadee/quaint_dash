# ADR PH7: Deterministic Business Strength Scorecard and Sector-Aware Templates

## Status

Accepted

## Context

Business quality, valuation, expected return, and market risk answer different questions. Combining
them into one opaque score would make the dashboard harder to audit and easier to misuse.

Different sectors also require different metrics. Banks, insurers, REITs, semiconductor companies,
software businesses, utilities, and marketplaces cannot be scored fairly with one universal formula.

## Decision

Numerical Business Strength scoring is owned by deterministic backend code. The implementation uses
versioned methodologies, sector-aware templates, normalized metric scores, confidence scoring, and
persisted metric-level audit trails.

Valuation attractiveness, expected CAGR, risk-adjusted return, price momentum, and technical
indicators remain separate systems. They may be linked from the UI but do not feed the Business
Strength score.

AI and agent research are deferred. The data model includes future qualitative input and research
interfaces, but those inputs are disabled and unpopulated in this phase.

## Consequences

The same inputs and methodology version produce the same score. Users can trace a score to raw
metrics, normalization rules, category weights, template version, peer context, source timestamps,
missing data, and confidence penalties.

Templates make cross-sector comparison safer: normalized category scores are comparable, while
template-specific raw metrics are shown with warnings when selected assets use different templates.

Future qualitative research can be added as reviewed evidence or override proposals without
rewriting the deterministic scoring engine.
