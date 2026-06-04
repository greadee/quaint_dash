# Phase 5 - API-First Web Application

## ADR-076: Local-First API and Web Client

**Decision:** Phase 5 introduces a versioned FastAPI backend and standalone React/TypeScript
client. The API binds to localhost by default and preserves the CLI as a supported interface.

**Rationale:**
- Gives browser, future mobile, desktop, and AI clients one application boundary.
- Keeps calculations and provider workflows in Python services.
- Allows each interface to evolve without duplicating investment logic.

## ADR-077: Request-Scoped DuckDB Access

**Decision:** API requests open and close their own DuckDB connection. Mutating HTTP actions
are serialized with an application-level lock.

**Rationale:**
- Avoids sharing one connection across concurrent requests.
- Keeps the Phase 5 database unchanged while making write behavior explicit.
- Leaves a clear migration path to a server database for hosted deployment.

## ADR-078: Stable Analytics and Redacted Broker Responses

**Decision:** HTTP analytics endpoints preserve the existing `phase3.analytics.v1` payload.
Broker HTTP responses use explicit response models that exclude secrets and raw provider data.

**Rationale:**
- Avoids introducing a second analytics contract.
- Prevents accidental disclosure through generic dataclass serialization.
- Keeps provider credentials and debugging payloads outside browser clients.
