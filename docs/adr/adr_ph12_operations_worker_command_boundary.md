# ADR PH12: Operations Worker Command Boundary

## Status

Accepted.

## Context

ADR PH11 moved Operations/Data Quality status reads behind an application-layer
facade. The matching command endpoints still called process-local worker
implementations directly from FastAPI routes for `start`, `stop`, and `tick`.

The command behavior is already tested through existing Operations API tests and
worker tests. This slice needs to preserve the existing `/api/v1` response
shape while moving command orchestration out of the route adapter.

## Decision

Add `OperationsWorkerCommands` to `dashboard.application.operations` and route
the Operations worker command endpoints through it.

The facade covers:

- ingestion background `start`, `stop`, and `tick`
- market freshness `start`, `stop`, and `tick`
- data readiness `start`, `stop`, and `tick`

Worker classes still own process-local scheduling, bounded job execution, and
status mutation. The application facade owns route-independent command intent
and returns the same dictionaries the existing API response model already wraps.

## Evidence

- The three worker types expose a common command shape: `enable()`, async
  `disable()`, async `tick()`, and `status()`.
- Existing API tests assert command response payloads and status side effects.
- Phase 1.5 identified Operations/Data Quality as the first Milestone A module.

## Alternatives Considered

- Move worker implementations into application: rejected because workers are
  process-local infrastructure/scheduler components.
- Create new command DTOs in this slice: rejected to avoid API behavior changes.
- Keep commands in routes until all Operations work moves: rejected because the
  read facade already proved the boundary and commands are the next direct
  coupling.

## Consequences

- FastAPI routes no longer directly call worker command methods.
- The Operations application module now owns read and command use-case entry
  points for worker status/control.
- Future work can add idempotency, authorization policy, and structured command
  contracts behind the facade without changing the route surface first.

## Risks

- The command facade is still process-local. It is not yet a durable job command
  API for mobile/desktop/automation.
- Authorization semantics are unchanged and remain route/API responsibility
  until a later security boundary slice.

## Migration Impact

No database schema, worker behavior, route path, response model, provider call,
or UI behavior changes. The slice is rollback-friendly by restoring route calls
to direct worker methods.

## Validation Method

- Operations application unit tests.
- Existing Operations API tests.
- Architecture boundary check.
- Full backend and web verification before commit.
- Operations live route/API smoke.

## Related ADRs

ADR PH10 defines the target module boundary. ADR PH11 introduced the Operations
status read facade. ADR PH12 completes the matching worker command facade.

