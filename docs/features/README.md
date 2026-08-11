# Feature Index

Feature guides describe domain behavior after the product tour. They distinguish capabilities
available in the browser from deterministic backend foundations that are not yet public product
surfaces.

## User-Facing Features

| Feature | Where it appears | Guide |
| --- | --- | --- |
| Business Strength | Asset detail and holding grades | [Business Strength](business-strength.md) |
| Financial news | News terminal, portfolio news, asset news | [Financial news](news.md) |
| Retail sentiment | Retail sentiment, optional signal input, Operations | [Retail sentiment](retail-sentiment.md) |

Portfolio analytics, signals, comparisons, benchmarks, brokers, and Operations are introduced in
the [product flow](../product/README.md) and specified further by the
[web application guide](../product/web-app.md).

## Deterministic Backend Foundations

| Feature | Current boundary | Guide |
| --- | --- | --- |
| Investor profile | Pure, versioned observation of stored portfolio evidence; no suitability decision | [Investor profile](investor-profile.md) |
| Candidate engine | Internal, persisted outside-holding research runs; no public API, UI, recommendation, or trade action | [Candidate engine](candidate-engine.md) |

These foundations live in `src/dashboard/rules_and_data`. They make no LLM calls. Any future model
integration remains a separate optional explanation layer and cannot own calculations,
eligibility, guardrails, or persistence.
