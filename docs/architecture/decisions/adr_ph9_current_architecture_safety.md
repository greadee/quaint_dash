# ADR PH9: Current Architecture Documentation And Safe Local Operations

## Status

Accepted

## Date

2026-07-09

## Context

The implementation has grown beyond the original CLI and Phase 2 ingestion diagrams. The current
repo includes a FastAPI backend, React/Vite client, broker sync, benchmark ingestion, live prices,
financial news, retail sentiment, business-strength scoring, background workers, and full
data-health tooling.

Earlier ADRs remain useful history, but several decisions are now distributed across implementation
and tests rather than one current index. Onboarding was also missing a complete safe `.env`
reference, current schema overview, and explicit worker safety posture.

## Decision

Keep the app local-first and DuckDB-backed. Treat Python services and DuckDB as the source of truth
for financial calculations, ingestion state, provider facts, broker data, readiness, and valuation
metrics. The browser consumes typed API payloads and formats/visualizes them.

Document the current architecture through:

- `docs/development/onboarding.md`
- `docs/architecture/codebase-map.md`
- `docs/architecture/overview.md`
- `docs/architecture/database/current_schema.md`
- `docs/development/environment.md`
- `docs/development/testing.md`
- `docs/operations/data-safety.md`
- `docs/architecture/decisions/index.md`

Default provider-heavy API workers to safe-off unless explicitly enabled by environment variables.
Keep `.env.example` as the committed placeholder-only template and keep real credentials in ignored
local `.env` files or external secret stores.

Preserve older ADR files as history. Use `docs/architecture/decisions/index.md` as the normalized status and
supersession index rather than renumbering historical duplicate ADR IDs.

## Consequences

- New contributors have one path for setup, architecture, schema, tests, safety, and ADR status.
- Documentation claims are tied to files, tests, schemas, and commands.
- Provider-backed jobs are less likely to run by surprise during API startup.
- Historical ADR numbering quirks remain visible, but the current index explains them.
- Generated display diagrams should be regenerated in a later graphics-focused pass when Mermaid or
  PlantUML render tooling is available.
