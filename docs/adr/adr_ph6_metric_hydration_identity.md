# ADR PH6: Metric Hydration Identity

## Status

Accepted

## Context

Portfolio holdings can be tradable wrappers, CDRs, ADRs, ETFs, indexes, or ordinary operating
companies. A held wrapper needs its own price history for valuation, return, and transaction
reporting, but company-level fundamentals may only be available on the underlying operating
company. Compare and Ticker View must not silently read wrapper fundamentals when the wrapper lacks
independent statements.

## Decision

The application separates these identities:

- `asset_id`: the tradable security held by the user and used for pricing, returns, positions, and
  transactions.
- `fundamental_asset_id`: the company-level asset used for financial statements, estimates,
  dividends, beta, shares, market capitalization, margins, free cash flow, and ROIC.
- Provider identity: kept at the ingestion/provider boundary and mapped into local asset rows or
  statement source metadata.

Comparison profiles now expose the resolved `fundamental_asset_id`, a `fundamental_status`, and
`missing_fundamental_metrics`. The price series remains tied to the tradable `asset_id`. CDR-style
asset enrichment prefers underlying company metadata for company-level fields, while wrapper price
history remains unchanged.

## Consequences

The same operating-company metric set can be checked consistently in Compare and in audit tooling.
Missing values remain explicit as partial hydration, not zeros or hidden cards. A held CDR can show
underlying company fundamentals while preserving wrapper-specific valuation and return history.

`tools/audit_portfolio_metric_hydration.py` is the repeatable audit/backfill preflight. It reports
held tickers, resolved underlying assets, expected/present/missing metrics, stale statement periods,
provider/source evidence, and affected UI surfaces, and it exits nonzero until held operating
company tickers are fully hydrated.
