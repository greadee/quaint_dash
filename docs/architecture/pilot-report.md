# Pilot Report: Operations Status Detail View Model

## Feature Selected

`OPS-002` routine worker/market freshness/data readiness status detail text on
the Operations page.

## Reason

The feature is small, connected to backend status APIs, visible in the web UI,
and currently has display transformation logic embedded in a large route file.
It is representative of the future pattern where route components consume
contracts and delegate presentation shaping to a feature-local boundary.

## Current Flow

1. `OperationsPage` polls status endpoints through `web/src/api.ts`.
2. Route-local helper functions format background, market freshness, and data
   readiness status details.
3. Cards render the returned text in the Operations page.

## Target Ownership

- Domain/data owner: Operations/Data Quality.
- API contract owner: Operations API.
- Presentation owner: Web Operations feature.
- Supporting modules: Background Jobs, Market Prices, Data Readiness.

## Public Contract

The pilot does not alter backend contracts. The view-model functions accept the
existing API client status types and return deterministic display strings.

## Phase 1.5 Change

The helpers are extracted from the route component into
`web/src/routes/operationsViewModels.ts`. `OperationsPage` imports the same
functions. This validates a low-risk presentation boundary without changing
layout, data, route behavior, or API meaning.

## Tests

`web/src/routes/operationsViewModels.test.ts` verifies the formatted outputs for
representative status payloads. Existing Operations route tests remain in place.

## Lessons

- View-model extraction is a safe first step for route-heavy pages.
- The API status types are useful but still frontend-local; later milestones
  should promote stable Operations status contracts.
- Structured freshness should eventually accompany status details so mobile and
  desktop clients do not parse display text.

