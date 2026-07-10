# Phase 1.5 Architecture Blueprint

This folder is the entry point for the modular boundary plan that sits between
the Phase 1 feature inventory and any later refactor. It defines the target
module structure, ownership rules, public contracts, migration sequence, and
checks needed before moving features.

Phase 1.5 does not move broad features. The current web app, API routes,
workers, database schema, and provider integrations remain the source of truth
until a feature is migrated through the documented strangler sequence.

## Required Inputs Reviewed

- Phase 1 inventory: [feature_widget_segmentation_plan.md](../planning/feature_widget_segmentation_plan.md)
- Phase 1 hierarchy diagram: [feature_hierarchy.mmd](../planning/feature_hierarchy.mmd)
- Phase 1 data map: [data_dependency_map.mmd](../planning/data_dependency_map.mmd)
- Existing overview: [architecture.md](../architecture.md)
- Data safety: [data_safety.md](../data_safety.md)
- ADR index: [../adr/index.md](../adr/index.md)
- CI: [../../.github/workflows/ci.yaml](../../.github/workflows/ci.yaml)
- Web scripts: [../../web/package.json](../../web/package.json)
- Python config: [../../pyproject.toml](../../pyproject.toml)
- Environment template: [../../.env.example](../../.env.example)

## Blueprint Index

- [Current State](current-state.md)
- [Target State](target-state.md)
- [Module Catalog](module-catalog.md)
- [Module Ownership](module-ownership.md)
- [Dependency Rules](dependency-rules.md)
- [Public Interfaces](public-interfaces.md)
- [Domain Models](domain-models.md)
- [Data Provenance](data-provenance.md)
- [Platform Capabilities](platform-capabilities.md)
- [API Boundaries](api-boundaries.md)
- [Transitional Architecture](transitional-architecture.md)
- [Security Boundaries](security-boundaries.md)
- [Testing Strategy](testing-strategy.md)
- [Naming Conventions](naming-conventions.md)
- [Migration Roadmap](migration-roadmap.md)
- [Phase 2 Migration Log](phase-2-migration-log.md)
- [Pilot Report](pilot-report.md)
- [Where Should This Code Go?](where-should-this-code-go.md)
- [Phase 1.5 Completion Report](phase-1.5-completion-report.md)

## Diagram Index

- [Current-state architecture](diagrams/current_state_architecture.mmd)
- [Target-state architecture](diagrams/target_state_architecture.mmd)
- [Module dependency](diagrams/module_dependency.mmd)
- [Platform interaction](diagrams/platform_interaction.mmd)
- [API boundary](diagrams/api_boundary.mmd)
- [Data flow](diagrams/data_flow.mmd)
- [Ingestion pipeline](diagrams/ingestion_pipeline.mmd)
- [AI insight pipeline](diagrams/ai_insight_pipeline.mmd)
- [Transitional migration](diagrams/transitional_migration.mmd)
- [Repository/package map](diagrams/repository_package_map.mmd)
- [Domain ownership map](diagrams/domain_ownership_map.mmd)
- [Security trust boundary](diagrams/security_trust_boundary.mmd)

## Status

Accepted for Phase 1.5 planning. Implementation migrations remain future work
unless a migration milestone explicitly starts Phase 2.
