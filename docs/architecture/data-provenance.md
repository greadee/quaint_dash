# Data Provenance And Freshness

Investment outputs need structured source and freshness metadata. Display text
may summarize this metadata, but platforms must not infer freshness from text.

## Standard Contract

```text
DataProvenance
  provider: string
  dataset: string
  source_endpoint: string optional
  retrieved_at: timestamp optional
  market_timestamp: timestamp/date optional
  calculated_at: timestamp optional
  currency: string optional
  adjustment_status: raw | adjusted | split_adjusted | total_return_adjusted | unknown
  quality_state: ok | partial | stale | missing | estimated | provider_failed
  missing_fields: string[]
  estimated_fields: string[]
  fallback_provider: string optional
  calculation_version: string optional
```

## Outputs Requiring Provenance

| Output | Required Metadata | Owner |
| --- | --- | --- |
| Prices and quotes | provider, market timestamp, retrieved time, currency, adjustment status, stale state | Market Prices |
| Price history | provider, date range, adjustment status, missing dates, calculation version for derived returns | Market Prices |
| Fundamentals and ratios | provider, fiscal period, retrieved time, missing fields, estimated fields | Fundamentals/Valuation |
| News | source/provider, published time, retrieval time, URL/id, sentiment source | News/Sentiment |
| Earnings/events | provider, event date, retrieval time, estimate/confirmed flag | Fundamentals/Corporate Calendar |
| Portfolio valuation | price inputs, calculated_at, currency, missing/stale holding list | Portfolio/Holdings |
| Benchmarks | benchmark source, proxy holdings/prices if used, calculated_at | Benchmarking |
| Risk/performance metrics | input series references, calculation version, calculated_at | Analytics |
| Simulations | input assumptions, seed if used, calculation version, generated_at | Simulations |
| AI insights | deterministic input refs, news refs, prompt version, model id, generated_at | AI Insights |

## Missing And Stale Data Rules

- Missing critical metrics must remain missing or unavailable; they must not be
  silently rendered as zero.
- Estimated values must be flagged with `quality_state=estimated`.
- Provider fallback must identify both failed and fallback sources when known.
- API responses should expose timestamps for data and calculation separately.
- Mobile and desktop clients should receive compact structured freshness, not
  only long Operations text.

