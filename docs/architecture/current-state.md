# Current State

## Repository Shape

Quaint Dash is a Python backend and CLI with a Vite/React browser client:

- `src/dashboard/api`: FastAPI routes, DTOs, application services, and API-owned workers.
- `src/dashboard/db`: DuckDB connections, schema, migrations, and query constants.
- `src/dashboard/models`: domain dataclasses, the legacy storage facade, CLI views, and commands.
- `src/dashboard/analytics`: portfolio and asset analytics, repositories, and snapshots.
- `src/dashboard/rules_and_data`: deterministic investor-profile and outside-holding candidate
  evaluation. It has no LLM integration or public recommendation surface.
- `src/dashboard/services/business_strength`: deterministic business-strength scoring.
- `src/dashboard/ingestion` and `src/dashboard/ingestion_sentiment`: bounded market, fundamental,
  benchmark, live-price, news, and social-sentiment ingestion.
- `src/dashboard/news`: normalized news ingestion, ranking, storage, and API services.
- `src/dashboard/brokers`: read-only broker linking, synchronization, mapping, and import.
- `web/src/routes`: route components and route-specific view-model composition.
- `web/src/api.ts`: typed browser API client and DTO contracts.
- `web/src/pageFeatureStore.tsx`: persisted page visibility, ordering, and layout settings.

## Implemented Boundaries

- Python and DuckDB own calculations, persistence, provenance, and readiness state.
- React owns navigation, interaction, formatting, and visualization of API payloads.
- Request-scoped DuckDB connections and an API process lock serialize browser writes.
- Provider work is bounded by explicit jobs, rate limits, call budgets, and safe-off workers.
- Broker integrations are read-only; imports require an explicit account-to-portfolio mapping.
- The deterministic rules layer is separate from any future LLM explanation layer. No LLM can
  currently calculate metrics, choose candidates, make suitability decisions, or initiate trades.

## Remaining Coupling

- The main API route module remains broad and combines many product surfaces.
- Some route handlers still coordinate persistence, analytics, refresh, and response shaping.
- `DashboardManager` remains a compatibility facade across CLI-era storage and command mixins.
- Web route files combine component composition with some page-specific transformation logic.
- API DTOs are stable for the browser but are not yet shared multi-client domain contracts.
- Freshness and provenance are explicit in many payloads but do not use one universal model.
- Asset, ticker, security, holding, position, quote, and metric naming still overlaps by context.

## Strengths To Preserve

- Financial calculations are backend-owned and tested independently of the UI.
- Transactions remain the durable portfolio ledger; positions are projections.
- Missing and stale data remain explicit instead of being silently converted to zero.
- Provider failures and entitlement limits are persisted with redacted errors.
- Python and web verification run in CI, with focused route and API coverage.
- Architecture decisions preserve reasoning and remain append-only.

## Next Architectural Work

- Continue extracting application services from broad route and compatibility facades.
- Formalize reusable provenance and freshness contracts for future clients.
- Migrate only through tested compatibility boundaries described in the
  [transitional architecture](transitional-architecture.md).
- Keep future AI work optional and downstream of deterministic facts, rules, and guardrails.
