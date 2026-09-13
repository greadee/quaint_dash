# Transitional Architecture

Migration uses a strangler pattern. Current code remains usable while new module
interfaces are introduced behind adapters.

## Compatibility Components

| Component | Old Consumer | Old Interface | New Target | Responsibility | Create | Remove When | Risk If Retained |
| --- | --- | --- | --- | --- | --- | --- | --- |
| API facade | Web routes | Existing REST endpoints | Application queries/commands | Preserve route shape while delegating to use cases. | A-B | All consumers use v2/contracts. | Route layer keeps business logic. |
| View-model adapter | Web route components | Route-local formatting/functions | Feature presentation module | Move display-only transformations without changing UI. | A | Feature has platform-specific presenter. | Duplicate display logic. |
| Repository adapter | Analytics/services | Direct DB helpers | Repository protocols | Hide DuckDB and persistence row shape. | B-C | Domain/app code no longer imports DB helpers. | Persistence leaks into domain. |
| Provider anti-corruption adapter | Ingestion/news/broker code | Provider raw payloads | Normalized provider result contracts | Keep provider-specific semantics out of domain/API. | B-D | Provider payload no longer leaves infrastructure. | Provider quirks become public API. |
| Contract mirror | `web/src/api.ts` | Hand-maintained TS types | Versioned contracts/generated types | Keep current client working while contracts stabilize. | B | Contract generation or explicit sync exists. | TS and Python contracts drift. |
| Worker command adapter | Current background jobs/tools | Script/function entry points | Application commands | Let workers call stable use cases. | A-E | Jobs run through command interfaces. | Scheduler keeps business rules. |
| AI evidence adapter | Future AI prompts | Ad hoc prompt inputs | Evidence reference contract | Prevent AI from inventing deterministic data. | F | AI module consumes stable evidence refs. | Sensitive or stale data leaks into prompts. |

## Rollback Rule

Each migrated feature keeps the old route/API path until the new facade has:

1. Contract tests.
2. Existing UI route still passing.
3. Data provenance/freshness documented where applicable.
4. Manual or automated route verification.
5. A deletion issue or milestone for the adapter.

