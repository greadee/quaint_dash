# Where Should This Code Go?

Use these questions before adding new code:

1. Is this a business rule or display concern?
2. Is it shared across web, desktop, mobile, workers, API, or AI?
3. Does it depend on a provider or database?
4. Does it write data?
5. Does it orchestrate a workflow?
6. Is it deterministic or AI-generated?
7. Does it belong to an existing business capability?
8. Would this create a circular dependency?
9. Is the interface stable enough to expose?
10. Is the code reusable, or only coincidentally similar?

## Examples

### A New Valuation Ratio

Put the formula in Valuation domain when it is deterministic. Put provider field
mapping in infrastructure. Put request/response shape in contracts/API. Put the
card label, formatting, and chart placement in web presentation.

### A New Chart

The chart component belongs in web shared UI or a page feature. The calculation
and data series belong in the relevant analytics/domain module. The API returns
structured data and provenance, not chart-specific styling.

### A New Market-Data Provider

Add a provider adapter in infrastructure. Normalize its payload into Market
Prices/Fundamentals contracts. Do not import the provider client from UI, API
routes, domain formulas, or AI prompts directly.

### A New AI Summary

AI Insights owns prompt/template versioning, evidence references, model id, and
generation timestamp. The deterministic metrics remain owned by analytics or
business modules. Web/mobile/desktop only render the insight contract.

### A New Mobile Card

Mobile owns layout, compact wording, and offline/cache behavior. The metric data
comes from shared contracts or mobile-safe API payloads. Do not duplicate backend
formulas in the card.

### A New Background Refresh Job

Workers own scheduling and execution. Application commands own workflow intent.
Provider adapters own external calls. Domain modules own business meaning and
formulas. Operations owns status and readiness reporting.

### A New Portfolio Calculation

If deterministic, it belongs in Portfolio, Holdings, Performance, or Risk
domain depending on the business question. API routes and UI components may
format or request it but may not own the calculation.

### A New API Response Field

First identify the owning module and model. Add provenance/freshness if the
field represents market, fundamentals, valuation, analytics, news, simulation,
or AI data. Avoid leaking database columns or provider-specific raw names.

