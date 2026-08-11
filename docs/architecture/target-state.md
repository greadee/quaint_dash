# Target State

## Architecture Choice

The selected target is a modular monolith with explicit adapters, not a split
microservice architecture. The current repository already runs as one web/API
system, and the main risk is unclear ownership rather than independent deploy
scaling. A modular monolith supports incremental migration, shared backend-owned
finance logic, and future web/mobile/desktop reuse without forcing a service
split before contracts are stable.

## Proposed Repository Structure

The structure below is the target boundary. Some application and deterministic-rules boundaries
now exist, but the broader target package layout remains directional unless marked implemented.

| Path | Purpose | Allowed Contents | Forbidden Contents | Status |
| --- | --- | --- | --- | --- |
| `src/dashboard/contracts` | Shared DTO/schema contracts for API, workers, desktop, mobile, and AI consumers. | Versioned request/response schemas, shared identifiers, provenance/freshness models. | Database rows, provider raw payloads, React props. | Future boundary; not created as an empty package. |
| `src/dashboard/domain` | Pure investment domain models and deterministic business rules. | Entities, value objects, metric formulas, scoring rules, invariants. | FastAPI, DuckDB connections, React, provider SDKs, environment reads. | Future boundary. |
| `src/dashboard/application` | Use cases that orchestrate domain logic through interfaces. | Queries, commands, repository protocols, service interfaces, authorization checks. | UI rendering, provider-specific parsing, direct SQL details. | Future boundary. |
| `src/dashboard/infrastructure` | Implementations of persistence, provider, cache, scheduler, and file adapters. | DuckDB repositories, provider clients, cache adapters, importer implementations. | Business meaning that belongs in domain, API response models. | Future boundary. |
| `src/dashboard/api` | HTTP adapter for the modular backend. | FastAPI routers, request parsing, auth, API DTO translation, compatibility routes. | Core calculations, provider fallback policy, UI-specific formatting. | Exists now; remains transitional. |
| `src/dashboard/workers` | Background worker entry points and scheduler adapters. | Job runners, worker composition, scheduling adapters. | Metric formulas, provider payload contracts as public models. | Future extraction from current ingestion/background code. |
| `src/dashboard/ai` | AI orchestration for summaries and explanations. | Prompt templates, insight contracts, model adapters, evidence references. | Deterministic calculations, direct portfolio writes, UI components. | Future boundary; current AI-like surfaces are placeholders/experimental. |
| `web/src/features` | Web feature adapters and page-level presentation modules. | React feature components, route view models, feature-local UI state. | Investment calculations, provider clients, database imports. | Future boundary; current routes remain in place. |
| `web/src/shared_ui` | Platform-agnostic web UI primitives. | Reusable charts, cards, badges, table controls, empty/loading states. | Page-specific business rules, API calls with hidden behavior. | Future boundary. |
| `web/src/platform/web` | Browser-specific services. | localStorage, routing, responsive behavior, browser-only adapters. | Shared domain logic, backend secrets. | Future boundary. |
| `apps/desktop` | Future desktop shell. | Desktop-specific UI, local compute adapters, export flows. | Shared finance formulas duplicated from backend domain. | Future only. |
| `apps/mobile` | Future mobile shell. | Mobile screens, notification handling, compact charts. | Provider keys, heavy analytics, full admin workflows. | Future only. |

## Layer Direction

Presentation depends on application contracts. Application depends on domain and
interfaces. Infrastructure implements interfaces. API and workers are adapters.
AI consumes deterministic results through contracts and may not replace them.

## Compatibility Requirements During Migration

- Runtime API routes and response meanings.
- Database schema and migrations.
- Provider integrations.
- Web layout, styling, navigation, and calculations.
- Background job behavior.
- Authentication and environment variable names.
