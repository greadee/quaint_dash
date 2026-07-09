# Phase 5 - API-First Web Application

> 2026-07-09 audit note: The local-first API and backend-owned analytics decisions remain current.
> Current onboarding, diagrams, schema scope, worker defaults, and safety posture are consolidated
> in [ADR PH9](adr_ph9_current_architecture_safety.md), [the ADR index](index.md), and
> `docs/architecture.md`.

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

## ADR-079: Signals Are Versioned Evaluations, Not Alerts or Factor Scores

**Decision:** The `/signals` workspace separates persistent factors, current conditions,
point-in-time signal evaluations, and user alert rules. Signal definitions live separately
from evaluations, and each rendered signal exposes strength, confidence, and portfolio
priority as distinct values.

**Rationale:**
- Keeps stable methodology metadata separate from time-specific observations.
- Prevents a generic buy/sell score from hiding contradictory evidence.
- Allows user review, mute, notes, and alert rules to persist without mutating the
  point-in-time evaluation.

## ADR-080: Deterministic Server-Side Signal Querying

**Decision:** Signal summary and detail endpoints adapt existing stored ranking inputs
into deterministic `signals.rankings.v1` evaluations. The browser never calculates
authoritative signal scores, and provider calls are not made during page rendering.

**Rationale:**
- Reuses existing ticker, portfolio, watchlist, sentiment, earnings, and ranking data.
- Avoids duplicated frontend calculation logic and N+1 provider requests.
- Gives `/signals` one API response containing all collapsed-row fields, with detail
  evidence and history loaded only for the selected signal.

## ADR-081: Portfolio Priority and Freshness Lifecycle

**Decision:** Portfolio priority combines normalized strength, input confidence, current
portfolio weight, and number of affected portfolios. Signal lifecycle is derived from
input completeness, confidence, strength, and source-specific freshness windows.

**Rationale:**
- Makes portfolio relevance visible without treating exposure as signal confidence.
- Keeps stale or incomplete signals visible with explicit status instead of replacing
  cached results with blank loading states.
- Provides a documented path to add source-specific staleness rules and historical
  efficacy once enough point-in-time evaluations exist.

## ADR-079: Backend-Owned Portfolio Management Analytics

**Decision:** The `/portfolios` browser surface uses typed backend DTOs for actual performance,
risk, fundamentals, and optimization preview. React is responsible for navigation, controls,
formatting, and charts, but not for authoritative portfolio calculations.

**Rationale:**
- Keeps financial calculations in the Python/DuckDB layer where transactions, prices,
  fundamentals, benchmark data, and broker snapshots already live.
- Separates actual historical performance from hypothetical current-weight backtests, investor
  money-weighted return, current-weight forward expected CAGR, and optimized expected CAGR.
- Prevents frontend-only random or mock weights from influencing production portfolio decisions.

## ADR-080: Optimization Is Preview-Only

**Decision:** Portfolio optimization supports `max_expected_cagr` and
`max_risk_adjusted_return` through `POST /api/v1/portfolios/{portfolio_id}/optimization/preview`.
The endpoint returns current weights, optimized weights, deltas, before/after metrics, constraints,
coverage, warnings, assumptions, and a calculation timestamp. It does not update stored positions.

**Rationale:**
- Users can inspect target allocations without accidentally mutating broker-linked or ledger-backed
  holdings.
- A future apply-target-allocation workflow can add explicit confirmation and persistence if target
  weights become a first-class domain concept.
