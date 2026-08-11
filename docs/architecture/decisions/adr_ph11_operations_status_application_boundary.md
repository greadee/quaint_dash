# ADR PH11: Operations Status Application Boundary

## Status

Accepted.

## Context

Phase 2 starts with small, rollback-friendly feature migrations. The Operations
page exposes ingestion background, market freshness, and data-readiness worker
status. Before this slice, the HTTP routes read worker status directly from
`request.app.state`, which kept the API adapter coupled to process-local worker
implementations.

## Decision

Introduce `dashboard.application.operations.OperationsStatusQueries` as a
read-only application-layer facade for Operations/Data Quality status.

The current FastAPI routes continue to expose the same `/api/v1` response
models and response shapes, but route status reads now go through the
application facade. Worker command endpoints remain unchanged until a later
command-specific migration.

## Evidence

- Phase 1.5 identifies Operations/Data Quality as a Milestone A module.
- The status endpoints are low risk and already covered by API tests.
- The worker status methods return structured dictionaries that match existing
  Pydantic response models, so the facade can preserve behavior without
  duplicating business logic.

## Alternatives Considered

- Move worker classes into application: rejected because workers still own
  process scheduling and infrastructure concerns.
- Introduce new API response models now: rejected because this slice must avoid
  API behavior changes.
- Leave routes coupled to workers: rejected because it blocks the documented
  application-layer migration path.

## Consequences

- API routes no longer read status directly from worker implementations.
- The new application package is now part of the enforceable boundary set.
- Command endpoints still need a future Operations command facade.

## Risks

- The facade is intentionally thin; expanding it without contracts could create
  another pass-through layer. Future slices should add contracts only when a
  status model or command behavior is migrated.

## Migration Impact

No user-facing behavior, database schema, worker behavior, or API response
meaning changes. The slice adds application tests and expands the boundary
checker to forbid application imports of FastAPI, UI modules, and DuckDB.

## Validation Method

- Operations application unit tests.
- Existing Operations API tests.
- Architecture boundary check.
- Full lint/test/build pass before handoff.

## Related ADRs

ADR PH10 defines the modular boundary blueprint. ADR PH11 is the first Phase 2
implementation slice under that blueprint.

