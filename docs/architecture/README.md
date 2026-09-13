# Architecture

Start with the current implementation. The boundary and migration documents that follow describe
how the code should evolve without implying that every target module already exists.

## Current System

- [Architecture overview](overview.md): runtime, persistence, ingestion, broker, analytics, and
  background-worker flows.
- [Current-state assessment](current-state.md): implemented package boundaries, strengths, and
  remaining coupling.
- [Codebase map](codebase-map.md): repository and package ownership.
- [Current database schema](database/current_schema.md): live DuckDB domains and source-of-truth
  rules.
- [Data provenance](data-provenance.md) and [security boundaries](security-boundaries.md).
- [Current and target diagrams](diagrams/README.md).

## Contracts And Ownership

- [Module catalog](module-catalog.md)
- [Module ownership](module-ownership.md)
- [Dependency rules](dependency-rules.md)
- [API boundaries](api-boundaries.md)
- [Public interfaces](public-interfaces.md)
- [Domain models](domain-models.md)
- [Platform capabilities](platform-capabilities.md)
- [Testing strategy](testing-strategy.md)
- [Naming conventions](naming-conventions.md)
- [Where should this code go?](where-should-this-code-go.md)

## Evolution Roadmap

These documents are directional. They describe the intended modular architecture and migration
sequence; they are not a claim that the target structure is complete.

- [Target state](target-state.md)
- [Transitional architecture](transitional-architecture.md)
- [Migration roadmap](migration-roadmap.md)

## Decisions And History

- [Architecture decision record index](decisions/index.md)
- [Historical reports and generated phase diagrams](../archive/README.md)

The architecture contracts were initially drafted during Phase 1.5. Current behavior is governed
by the implementation, tests, and current-system documents above. Historical reports are retained
for context but are not onboarding instructions.
