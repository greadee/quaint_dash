# Migration Roadmap

## Milestone A: Foundations

- Included: shared identifiers, freshness/provenance contracts, dependency rules,
  architecture checks, Operations view-model pilot, widget id ownership.
- Prerequisites: Phase 1 inventory and Phase 1.5 blueprint.
- Movement: minimal; adapters and contracts only.
- Tests: architecture boundary test, pilot unit test, existing lint/test/build.
- Rollback: remove pilot adapter/import and boundary check.
- Completion: rules documented, checks passing, web still functional.
- Complexity: Small.

## Milestone B: Read-Only Shared Capabilities

- Included: asset identity, prices, fundamentals, news, portfolio summaries,
  benchmark identity.
- Prerequisites: contract model decisions from A.
- Movement: introduce application queries behind existing API routes.
- Adapters: API facade and contract mirror.
- Tests: API contract tests, provider normalization tests, UI route tests.
- Rollback: route facade returns to existing service calls.
- Complexity: Large.

## Milestone C: Deterministic Analytics

- Included: performance, risk, benchmarking analytics, attribution, business
  strength scoring, compare metrics.
- Prerequisites: read-only models and provenance.
- Movement: pure formulas into domain analytics modules; API calls application
  services.
- Tests: deterministic fixture tests and existing compare/portfolio route tests.
- Rollback: feature-level facade points to legacy analytics.
- Complexity: Large.

## Milestone D: Stateful Workflows

- Included: transactions, portfolio editing, watchlists, user preferences, widget
  configuration persistence.
- Prerequisites: repository interfaces and authorization rules.
- Movement: commands and repository adapters.
- Tests: command tests, repository contract tests, E2E for write workflows.
- Rollback: command adapter delegates to legacy implementation.
- Complexity: Large.

## Milestone E: Heavy Analytics

- Included: Monte Carlo, scenario analysis, backtesting, optimization.
- Prerequisites: deterministic analytics and job/result contracts.
- Movement: simulation engines behind application jobs.
- Tests: seeded simulations, long-running job tests, desktop payload tests.
- Rollback: keep preview routes on legacy analytics.
- Complexity: Very large.

## Milestone F: AI Orchestration

- Included: daily ticker insights, news synthesis, portfolio explanations,
  research assistance.
- Prerequisites: evidence/freshness contracts and privacy/consent strategy.
- Movement: AI contracts and model/provider adapters.
- Tests: fake-model contract tests, redaction tests, evidence reference tests.
- Rollback: disable AI feature flags without affecting deterministic analytics.
- Complexity: Large.

## Milestone G: Additional Platforms

- Included: desktop shell, mobile companion, notifications, offline/cache
  behavior.
- Prerequisites: stable contracts and platform capability matrix.
- Movement: platform apps consume shared APIs/local adapters.
- Tests: platform integration, mobile payload, desktop bulk-analysis tests.
- Rollback: platform-specific release gating.
- Complexity: Very large.

