# Current State

## Repository Shape

The app is currently a Python backend plus a Vite/React web frontend:

- `src/dashboard/api`: FastAPI routes, API models, and route-level orchestration.
- `src/dashboard/db.py`: database connection helpers and persistence entry points.
- `src/dashboard/models.py`: legacy CLI-facing repository facade.
- `src/dashboard/analytics`: portfolio and asset analytics calculations.
- `src/dashboard/services/business_strength`: business-strength scoring logic.
- `src/dashboard/ingestion` and `src/dashboard/ingestion_sentiment`: background
  ingestion pipelines and provider-sensitive refresh logic.
- `src/dashboard/news`: news ingestion, sentiment, API service logic, and news
  terminal support.
- `src/dashboard/brokers`: broker import, sync, and portfolio mapping logic.
- `web/src/routes`: page components, route view models, feature menus, and chart
  composition.
- `web/src/api.ts`: browser-side API client and DTO types.
- `web/src/pageFeatureStore.ts`: widget visibility and per-page feature
  customization.

## Important Coupling Findings

The Phase 1 inventory shows strong user-facing capability coverage, but the
implementation boundaries are mixed.

- API routes often orchestrate persistence, analytics, provider refresh, and
  response shaping in one layer.
- Web route files own both presentation and some view-model logic.
- API response DTOs are used as convenient frontend contracts but are not
  stable shared domain contracts.
- Ingestion workers and Operations UI expose provider and scheduler details
  directly enough that future mobile/desktop consumers would need adapters.
- AI and deterministic analytics are not yet separated by an explicit contract.
- Data freshness and provenance exist in several payloads and status routes, but
  there is no single cross-platform model.
- Naming differs by context: asset, ticker, security, holding, position, quote,
  price, metric, and ratio are used with overlapping meanings.

## Existing Strengths To Preserve

- Financial calculations are backend-owned and should stay that way.
- Provider fallbacks and readiness states are explicit enough to document.
- CI already runs Python lint and tests.
- The web app has route-level tests and a strong API client boundary.
- ADRs preserve historical reasoning and should remain append-only.
- The Phase 1 planning docs assign stable feature IDs across pages, widgets, and
  supporting capabilities.

## Documentation Gaps

- Some current APIs are documented by implementation and tests rather than by
  contract docs.
- Existing diagrams do not show multi-platform or AI boundaries.
- Temporary compatibility rules were not previously documented with deletion
  criteria.
- Feature-to-module ownership did not previously exist in a central matrix.

