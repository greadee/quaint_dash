# ADR PH10: Modular Boundary Blueprint For Phase 1.5

## Status

Accepted.

## Context

Phase 1 produced a detailed inventory of pages, features, widgets, workflows,
data inputs, outputs, coupling problems, and platform suitability. The next
refactor needs stable module boundaries before any broad feature movement.

The current project is a local-first Python/FastAPI/DuckDB backend with a
React/Vite web app. Existing ADRs already support backend-owned analytics,
provider abstraction, deterministic signal querying, safe local operations, and
current architecture documentation. The primary architectural gap is not the
absence of code structure, but the lack of enforceable ownership between UI,
API orchestration, domain logic, provider adapters, workers, and future AI or
platform consumers.

## Decision

Use a modular monolith target architecture with explicit contracts,
application-use-case boundaries, pure domain modules, infrastructure adapters,
and platform-specific presentation modules.

The target dependency direction is:

```text
platform presentation -> API/application contracts -> application use cases
application use cases -> domain modules
infrastructure -> implements application/domain interfaces
API/workers/AI -> adapters around application use cases
```

The refactor will use a strangler migration. Current web/API behavior remains
compatible while one capability at a time moves behind a documented facade,
contract, or adapter. Temporary adapters require deletion criteria.

## Evidence

- Phase 1 feature inventory shows many reusable capabilities across portfolio,
  asset research, analytics, news, operations, broker, and comparison surfaces.
- Existing backend analytics and scorecard logic already demonstrates that
  investment calculations should stay server/domain-owned.
- Existing API routes and web routes are route-centric and convenient, but mix
  orchestration, presentation transformations, and transport contracts.
- Provider integrations and ingestion workers require stable anti-corruption
  layers before mobile, desktop, or AI consumers can safely reuse outputs.
- Data provenance and freshness exist in multiple places but need a shared
  contract for investment decisions and future platform clients.

## Alternatives Considered

- Separate services now: rejected because current scaling needs are not service
  deployment boundaries, and service extraction would increase migration risk.
- Frontend-first shared packages: rejected because financial truth, provider
  fallback, and freshness semantics must remain backend-owned.
- Documentation-only architecture: rejected because boundary drift should be
  caught by lightweight automated checks.
- Full folder migration in Phase 1.5: rejected because the phase explicitly
  requires no broad refactor or behavior change.

## Consequences

- Feature migration can happen incrementally and remain rollback-friendly.
- Future desktop/mobile/AI consumers get stable contracts rather than page
  payloads or database rows.
- Some current routes will remain transitional until application use cases are
  introduced.
- Developers must maintain the module catalog and ownership matrix when new
  features are added.

## Risks

- Architecture docs can drift if not linked to CI and review checklists.
- Too many modules could slow implementation, so modules are tied to existing
  feature evidence rather than nouns alone.
- Contract generation between Python and TypeScript remains deferred and must be
  solved before large cross-platform work.

## Migration Impact

Phase 1.5 adds documentation, diagrams, an ADR, a lightweight boundary checker,
and one small Operations view-model pilot. It does not change database schema,
provider behavior, API semantics, or web layout.

## Validation Method

- Run Python lint and tests.
- Run web lint, tests, and build.
- Run architecture boundary checks.
- Verify API health and the Vite app launch.
- Confirm pilot formatting is covered by unit tests.

## Related Features

Portfolio overview, holdings exposure, asset research, market prices,
fundamentals, valuation, performance/risk analytics, benchmarking, comparisons,
news, sentiment, business strength, Operations/Data Quality, simulations,
widget configuration, and AI insights.

## Related ADRs

ADR PH6, ADR PH7, ADR PH8, ADR PH9, ADR-061, ADR-065, ADR-076, ADR-077,
ADR-078, ADR-079, and ADR-080 remain valid and are refined by this blueprint.

