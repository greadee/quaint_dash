# Dependency Rules

## Layer Rules

| Consumer | Contracts | Domain | Application | Infrastructure | API | Workers | Web UI | Desktop UI | Mobile UI | AI |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Contracts | Limited | Forbidden | Forbidden | Forbidden | Forbidden | Forbidden | Forbidden | Forbidden | Forbidden | Forbidden |
| Domain | Allowed for identifiers only | Limited | Forbidden | Forbidden | Forbidden | Forbidden | Forbidden | Forbidden | Forbidden | Forbidden |
| Application | Allowed | Allowed | Limited | Interfaces only | Forbidden | Forbidden | Forbidden | Forbidden | Forbidden | Interfaces only |
| Infrastructure | Allowed | Allowed | Allowed | Limited | Forbidden | Transitional only | Forbidden | Forbidden | Forbidden | Provider interfaces only |
| API | Allowed | Transitional only | Allowed | Transitional only | Limited | Transitional only | Forbidden | Forbidden | Forbidden | Application interface only |
| Workers | Allowed | Transitional only | Allowed | Allowed | Forbidden | Limited | Forbidden | Forbidden | Forbidden | Application interface only |
| Web UI | Allowed | Forbidden | API client only | Forbidden | HTTP only | Forbidden | Limited | Forbidden | Forbidden | Display contracts only |
| Desktop UI | Allowed | Forbidden | API/local service only | Forbidden | HTTP/local adapter | Forbidden | Forbidden | Limited | Forbidden | Local/service adapter only |
| Mobile UI | Allowed | Forbidden | HTTP/cache only | Forbidden | HTTP only | Forbidden | Forbidden | Forbidden | Limited | Display contracts only |
| AI | Allowed | Forbidden direct mutation | Application queries only | Provider adapter only | Forbidden | Worker adapter only | Forbidden | Forbidden | Forbidden | Limited |

Legend: `Allowed` is normal use; `Limited` means same-layer submodules only;
`Interfaces only` means no implementation imports; `Transitional only` requires
a removal milestone; `Forbidden` must fail review and, where possible, checks.

## Non-Negotiable Rules

- Domain code must not import FastAPI, React, database drivers, provider SDKs,
  environment readers, or platform UI modules.
- UI code must not query the database, import provider adapters, or own
  investment calculations.
- API response models are transport contracts, not automatically domain models.
- Persistence models are not public contracts.
- Provider payloads are normalized behind infrastructure adapters.
- Schedulers and workers may orchestrate jobs but may not own business formulas.
- AI modules may explain deterministic outputs but may not replace or invent
  deterministic metrics.
- Shared contracts may contain structured freshness/provenance metadata; clients
  must not infer freshness only from display text.

## Transitional Exceptions

| Exception | Reason | Current Reference | Replacement Path | Remove By |
| --- | --- | --- | --- | --- |
| API routes call analytics/service functions directly. | Current FastAPI layer predates application use cases. | `src/dashboard/api` to `src/dashboard/analytics` and services. | Introduce application query/command facades. | Milestones B-C. |
| Web routes compose many widgets directly. | Existing Vite app is route-centric. | `web/src/routes/*.tsx`. | Move route-local view models first, then feature adapters. | Milestones A-D. |
| Operations route shows scheduler implementation details. | Admin surface exposes current worker settings. | `web/src/routes/operationsRoute.tsx`, operations APIs. | Operations/Data Quality contracts with typed status models. | Milestone A. |
| API DTOs are reused as frontend TypeScript types. | Existing client is generated/hand-maintained in `web/src/api.ts`. | `web/src/api.ts`. | Versioned backend contracts and generated or mirrored TS types. | Milestone B. |

## Automated Check Scope

`python -m tools.check_architecture_boundaries` enforces the first practical guardrails:

- Python domain/service/ingestion modules do not import web frameworks.
- Python application modules do not import web frameworks, web UI modules, or
  database drivers.
- API code does not import web UI code.
- Web code does not import Python backend implementation packages directly.

The check is intentionally small. It should grow only when a rule is stable
enough to enforce without blocking legitimate migration work.
