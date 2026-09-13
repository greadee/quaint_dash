# Contributing

## Architecture First For Feature Movement

Before moving or adding feature code, check the Phase 1.5 architecture blueprint:

- [Architecture entry point](docs/architecture/README.md)
- [Module ownership](docs/architecture/module-ownership.md)
- [Dependency rules](docs/architecture/dependency-rules.md)
- [Where Should This Code Go?](docs/architecture/where-should-this-code-go.md)

Do not move broad features without a migration milestone, a compatibility plan,
and tests that preserve current behavior.

## Boundary Rules

- Keep deterministic investment calculations in backend/domain/application code.
- Keep provider clients and secrets out of UI code.
- Keep UI formatting and layout out of domain code.
- Treat API DTOs, persistence rows, and React props as separate models unless an
  ADR or contract says otherwise.
- Include structured freshness/provenance for investment data that can become
  stale or provider-dependent.
- AI output may explain deterministic results but may not replace them.

## Verification

Use the narrowest checks for the change, then broaden when touching shared
behavior:

```cmd
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m tools.check_architecture_boundaries
cd web
npm.cmd run lint
npm.cmd test
npm.cmd run build
```

For web-facing changes, also refresh the running app and verify the API health
endpoint and affected route.

## Commit Messages

Prefer lowercase verb-led subjects such as `add architecture boundary checks`,
`fix portfolio metric hydration`, or `upd broker sync docs`.
