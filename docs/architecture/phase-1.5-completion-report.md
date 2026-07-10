# Phase 1.5 Completion Report

## Executive Summary

The selected architecture is a modular monolith with explicit contracts,
application use cases, pure domain modules, infrastructure adapters, and
platform-specific presentation layers. This matches the current single-repo
Python API plus React web app while creating a path for desktop, mobile, workers,
and AI consumers.

Unchanged: user-facing behavior, database schema, provider integrations, API
response meaning, web navigation/layout, and background job behavior.

Established in code: lightweight architecture boundary check and the Operations
status view-model pilot. Established in documentation: target repository
structure, module catalog, ownership matrix, dependency rules, public interface
catalog, shared domain model strategy, provenance model, platform matrix, API
boundary strategy, transitional adapters, security rules, testing strategy,
naming conventions, migration sequence, ADR, and Mermaid diagrams.

## Current-State Findings

- API routes currently mix orchestration, response shaping, and business/data
  access.
- Web route files often combine page composition, widget display, and
  presentation transformations.
- API DTOs, UI props, and persistence shapes are not consistently separated.
- Data freshness/provenance is present but not standardized.
- AI boundaries are future-facing and need strict evidence/freshness contracts.
- Tests exist, but architecture-boundary tests were missing before this phase.

## Target Architecture

- Modules: Portfolio, Holdings, Transactions, Asset Research, Market Prices,
  Fundamentals, Valuation, Performance Analytics, Risk Analytics, Benchmarking,
  Comparisons, News, Sentiment, Business Strength, Simulations, Watchlists,
  Widget Configuration, Operations/Data Quality, AI Insights, User Preferences,
  plus infrastructure modules.
- Layers: presentation -> API/application -> domain; infrastructure implements
  interfaces; workers and API are adapters.
- Platforms: web remains full dashboard; desktop is preferred for heavy
  analytics and AI; mobile focuses on compact summary, alerts, watchlists, and
  quick checks.
- Data boundary: structured provenance/freshness is required for market,
  fundamentals, analytics, news, simulations, and AI outputs.
- AI boundary: AI explains deterministic results and references evidence; it
  does not own or replace deterministic calculations.

## Repository Changes

| File or Directory | Reason | Behavior Impact | Risk | Verification |
| --- | --- | --- | --- | --- |
| `docs/architecture/*` | Central Phase 1.5 blueprint. | None. | Documentation drift if not maintained. | Link and content review. |
| `docs/architecture/diagrams/*` | Required Mermaid architecture diagrams. | None. | Diagram drift. | Diagram files reviewed. |
| `docs/adr/adr_ph10_modular_boundary_blueprint.md` | Record consequential architecture decision. | None. | ADR overlap mitigated by index links. | ADR index updated. |
| `tools/check_architecture_boundaries.py` | Lightweight import-boundary enforcement. | None at runtime. | Rule false positives if expanded carelessly. | Architecture check and pytest. |
| `tests/test_architecture_boundaries.py` | CI coverage for boundary checker. | None. | Test maintenance with boundary changes. | Pytest. |
| `web/src/routes/operationsViewModels.ts` | Pilot view-model boundary. | Intended none. | Formatting drift if duplicated. | Unit test and web tests/build. |
| `web/src/routes/operationsViewModels.test.ts` | Pilot behavior guard. | None. | None material. | Vitest. |
| `README.md`, `CONTRIBUTING.md` | Link architecture entry point and developer rules. | None. | None material. | Link review. |

## Pilot Results

- Feature: Operations status detail formatting.
- Before: helper functions lived inside `operationsRoute.tsx`.
- After: helper functions live in a route-local view-model module and are
  imported by the route.
- Behavior: intended identical; backend/API contracts unchanged.
- Tests: status detail unit tests added.
- Lesson: route-local view-model extraction is a safe early migration pattern
  for web-heavy surfaces.

## Migration Roadmap

- A Foundations: Small.
- B Read-only shared capabilities: Large.
- C Deterministic analytics: Large.
- D Stateful workflows: Large.
- E Heavy analytics: Very large.
- F AI orchestration: Large.
- G Additional platforms: Very large.

## Exceptions And Open Questions

- Corporate calendar is owned by Fundamentals until it becomes a broader event
  workflow.
- Alerts remain future-facing until alert rules, notifications, and persistence
  exist.
- Contract generation between Python and TypeScript is deferred.
- AI provider/model selection is deferred and requires privacy/consent design.
- Existing APIs remain compatibility routes until consumers migrate.

## Verification Evidence

Commands run:

| Command | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m ruff check .` | Passed. |
| `.\.venv\Scripts\python.exe -m pytest` | Passed: 412 tests, 1 existing FastAPI/Starlette deprecation warning, 4:16. |
| `.\.venv\Scripts\python.exe -m tools.check_architecture_boundaries` | Passed. |
| `cd web && npm.cmd run lint` | Passed with 4 existing `react-refresh/only-export-components` warnings. |
| `cd web && npm.cmd test` | Passed: 21 files, 83 tests. |
| `cd web && npm.cmd run build` | Passed. |
| `Invoke-WebRequest http://127.0.0.1:8000/api/v1/health` | Passed: HTTP 200 after elevated background API launch. |
| `Invoke-WebRequest http://127.0.0.1:5173` | Passed: HTTP 200 after elevated Vite launch. |
| HTTP checks for `/operations`, `/portfolio`, `/assets` | Passed: HTTP 200. |
| Playwright route smoke for `/`, `/operations`, `/portfolio`, `/assets` | Passed: HTTP 200 page loads, no browser console errors captured. |

Known verification notes:

- Direct sandboxed execution of `.\.venv\Scripts\python.exe -m tools.check_architecture_boundaries`
  returned `Access is denied`; rerunning with approved elevated execution passed.
- Initial API background launch failed while another Python process held
  `data/persistent_db.db`; after the lock holder exited, the approved elevated
  launch returned API health 200.
- No secrets or provider keys were moved.
- No database schema, API response meaning, provider behavior, or user-facing
  layout was intentionally changed.

