# Testing Strategy

## Test Categories

| Category | Purpose | Owners |
| --- | --- | --- |
| Domain unit tests | Validate pure formulas, invariants, score rules. | Domain modules. |
| Application use-case tests | Validate orchestration, auth, error handling, and interfaces. | Application modules. |
| Repository contract tests | Ensure persistence adapters satisfy repository protocols. | Infrastructure. |
| Provider adapter tests | Normalize raw provider payloads and fallback behavior. | Infrastructure/providers. |
| API contract tests | Validate request/response schemas and compatibility routes. | API. |
| UI component tests | Validate route rendering, states, controls, and view models. | Web/features/shared UI. |
| Platform integration tests | Validate web/desktop/mobile adapters. | Platform apps. |
| End-to-end tests | Validate critical routes and workflows. | Cross-platform. |
| Data-quality tests | Validate readiness, freshness, null handling, provider coverage. | Operations/Data Quality. |
| Architecture-boundary tests | Validate forbidden imports and direction rules. | Repository-wide. |
| AI contract tests | Validate evidence references, freshness, prompt version, and no metric mutation. | AI Insights. |

## Module Requirements

| Module | Required Tests Before Migration Completion |
| --- | --- |
| Portfolio/Holdings | Unit tests for valuation/allocation, API contract tests, web route tests. |
| Market Prices | Repository/provider adapter tests, freshness tests, chart payload tests. |
| Fundamentals/Valuation | Missing/null handling tests, provider fallback tests, contract tests. |
| Performance/Risk | Formula unit tests with deterministic fixtures, benchmark alignment tests. |
| Business Strength | Score rule tests, evidence/missing input tests, API contract tests. |
| News/Sentiment | Pagination/filter tests, source metadata tests, provider normalization tests. |
| Operations/Data Quality | Worker command tests, status contract tests, architecture boundary tests. |
| Transactions/Brokers | Import fixture tests, reconciliation tests, sensitive logging tests. |
| Simulations | Seeded deterministic tests, assumption/audit tests, long-running job tests. |
| AI Insights | Contract tests for evidence refs, redaction tests, prompt version tests. |

## Fixtures And Mocks

- Domain tests own small deterministic fixtures.
- Provider adapters own provider payload fixtures.
- API tests mock application interfaces, not database rows, after migration.
- UI tests mock API client responses, not backend internals.
- AI tests use deterministic fake model providers and never call real providers
  in CI.

