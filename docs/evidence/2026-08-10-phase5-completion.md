# Phase 5 Deterministic Candidate Engine Completion

**Date:** 2026-08-10

**Branch:** `phase5-prediff`

**Scope:** closure of the deterministic outside-holding candidate engine through Slice 5.8

## Result

Phase 5 is complete. The implementation produces persisted, point-in-time,
evidence-backed research candidates from stored local data. It does not make
investment recommendations, assess suitability, size or execute trades, call a
provider, expose an HTTP endpoint, render a candidate UI, or invoke an LLM.

The primary contract is `dashboard.ai_brain.candidates.CandidateRunService`.
It composes the frozen Phase 4 investor profile, the resolved outside-holding
pool, deterministic scoring, freshness guardrails, immutable persistence, and
replay identity under `candidate-engine.deterministic.v3`.

## Requirement Traceability

| Requirement | Implementation and evidence |
| --- | --- |
| Top-ranked, watchlist, all-universe, and benchmark sources | `source_adapters.py`, `universe.py`, and `test_candidate_universe.py` |
| Sector/geography gaps; peer, industry, and theme associations | `portfolio_sources.py` and `test_candidate_portfolio_sources.py` |
| Quality, value, and momentum screens | `screen_adapters.py` and `test_candidate_screens.py` |
| Held economic-exposure exclusion and source deduplication | `universe.py`, shared CDR policy, and `test_candidate_universe.py` |
| Candidate identity, reason codes, evidence, missing metrics, warnings | `models.py`, `canonical.py`, `serialization.py`, and `test_candidate_contracts.py` |
| Fit, diversification, redundancy, highlights, stable ordering | `scoring.py` and `test_candidate_scoring.py` |
| Freshness and insufficient-evidence policy | `guardrails.py` and `test_candidate_guardrails.py` |
| Immutable, reproducible runs | `persistence.py` and `test_candidate_persistence.py` |
| Frozen-input orchestration and idempotent replay | `orchestration.py` and `test_candidate_orchestration.py` |
| Phase 4 prerequisite | `investor_profile.py` and `tests/ai_brain/test_investor_profile.py` |

## Final Verification

```text
ruff check src tests: passed
architecture boundary check: passed
repository pytest: 574 passed; 1 existing Starlette/httpx deprecation warning
web lint: passed with 0 errors; 4 existing Fast Refresh warnings
web tests: 88 passed across 22 files
web production build: passed
full data-health workflow: ok=true; findings=[]
  four cycles; 66/66 readiness targets; zero actionable jobs after cycle one;
  healthy yfinance provider; 12/12 external price checks matched exactly
web data-health scan: ok=true; 53/53 routes returned 200; no console errors;
  no failed requests
live review: overview, signals, portfolio analytics, benchmarks, and operations
  rendered through the Vite app without console errors
API health: 200; status=ok; database=connected
Vite app: 200
```

## Data Limitations And Deferred Work

- Mutable sources retain their recorded watermark and partial-history semantics.
  The candidate engine reports missing or unsupported evidence rather than
  hydrating it.
- Historical dead-letter ingestion records remain for unsupported/rate-limited
  corporate provider requests. They were not actionable in the final workflow;
  its queue drained and its provider health was healthy.
- Operations displayed stale worker-status counts from an earlier background
  tick during live review, while the authoritative ingestion API reported no
  pending, running, or failed jobs and the full health workflow passed. This is
  an Operations status-refresh issue, outside the deterministic candidate
  contract; it should be addressed before treating that panel as a live queue
  authority.
- Recommendation decisions, suitability, trade behavior, APIs, dashboard UI,
  prompts, LLM providers, embeddings, and model output evaluation remain
  deferred to their separately authorized phases.

## Boundary Confirmation

Search and architecture verification confirm there is no Phase 5 LLM or
provider runtime path. Candidate generation and scoring read stored snapshots
only. A future LLM may explain already-persisted evidence, but it must not own
candidate selection, score calculation, guardrails, eligibility, or run
persistence.

## Stop

Stop at Phase 5 closure. Phase 6 requires separate authorization and a fresh
plan for deterministic recommendation and decision behavior.

## Next Model Recommendation

Use **GPT-5.6 SOL Extra High** for the first Phase 6 planning and contract
slice. Recommendation actions introduce a new safety boundary, action taxonomy,
and guardrail interaction that require deeper design review than Phase 5
closure.
