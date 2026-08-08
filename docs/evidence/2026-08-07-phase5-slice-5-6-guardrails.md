# Phase 5 Slice 5.6 Freshness And Guardrails

**Date:** 2026-08-07

**Branch:** `phase5-prediff`

**Purpose:** add deterministic evidence-type freshness, missing-data sufficiency, and structured candidate guardrails without starting Slice 5.7 orchestration

## Result

Slice 5.6 adds `candidate-guardrails.v1` as a monotonic post-scoring policy. It evaluates evidence against the frozen review boundary, adds stored identity/price/liquidity evidence, rewrites every nested reference to one canonical freshness state, preserves missing metrics, and applies explicit warning and eligibility effects before the existing stable ordering rule.

The candidate methodology advances to `candidate-engine.deterministic.v2` and reason definitions advance to `candidate-reason-codes.v2`. Review and evidence shapes remain compatible at `v1`; no migration is required.

## Changed Files

- `src/dashboard/ai_brain/candidates/guardrails.py`
- `src/dashboard/ai_brain/candidates/models.py`
- `src/dashboard/ai_brain/candidates/scoring.py`
- `src/dashboard/ai_brain/candidates/__init__.py`
- `tests/ai_brain/candidates/test_candidate_guardrails.py`
- `tests/ai_brain/candidates/test_candidate_scoring.py`
- `docs/candidate_contracts.md`
- `docs/adr/adr_ph13_candidate_engine_boundary.md`
- `docs/evidence/2026-08-07-phase5-slice-5-6-guardrails.md`

## Contract Decisions

- Freshness uses evidence-type thresholds and `data_as_of`; wall-clock time is excluded.
- Unknown source domains remain `unknown` and cannot satisfy a critical freshness requirement.
- Identity, price, and risk are critical. Missing, unknown, or expired evidence blocks.
- Material support is restricted to ranking, screen, benchmark, gap, peer, industry, and theme evidence.
- Catalog, watchlist, profile, portfolio, overlap, and sentiment evidence cannot independently establish material support.
- Sentiment-only support receives a dedicated blocking code.
- Missing liquidity is noncritical and remains explicit; it is never converted to zero.
- Low and extremely low observed liquidity downgrade research standing. They do not make a trade or suitability decision.
- High speculative risk is visible without overriding profile fit. Extreme speculative risk downgrades.
- Concentration is informational. Material redundancy keeps the Slice 5.5 downgrade and gains a structured warning.
- Undated ETF look-through leaves overlap freshness unknown and downgrades.
- Stale positive evidence plus current negative evidence downgrades before ordering.
- Warnings do not change numeric scores.

## Test Coverage

Focused fixtures cover:

- distinct policy thresholds by evidence type;
- exact current, stale, and expired boundaries for material, price, identity, and critical-risk evidence;
- unknown critical-risk freshness failing closed;
- critical identity, price, and risk missing states;
- noncritical liquidity coverage without zero substitution;
- exact liquidity and speculative-risk boundaries;
- sentiment-only support blocking;
- unsupported classification blocking;
- undated ETF look-through freshness;
- stale positive evidence unable to outrank current contradictory evidence;
- stable warning-code ordering, evidence closure, and byte-equivalent replay;
- the model-level rejection of evidence-free reviews.

Focused guardrail plus scoring tests pass: `58 passed`.

All candidate contract, persistence, source, scoring, and guardrail tests pass: `106 passed`.

## Data Limitations

- Liquidity uses the median of up to 20 positive-volume daily rows and requires 10 observations.
- Daily notional remains in the asset's local currency because no point-in-time FX conversion is part of the candidate contract.
- Catalog and watchlist tables remain mutable current-state sources and are not material analytical support.
- ETF look-through has no effective date. Any participating look-through keeps overlap freshness unknown.
- Unknown noncritical evidence remains visible but does not automatically block; unknown critical evidence does.

## Explicit Exclusions

This slice does not orchestrate or persist a complete candidate run, expose an internal/public API, render UI, assign recommendation actions, infer suitability, size a trade, call a provider, or call an LLM.

## Verification

```text
focused guardrail + scoring tests: 58 passed
candidate package tests: 106 passed
candidate Ruff: passed
architecture boundary command: passed
full Ruff: passed
repository tests: 569 passed, 1 existing Starlette/httpx deprecation warning
web lint: passed with 0 errors and 4 existing Fast Refresh warnings
web tests: 88 passed across 22 files
web production build: passed
full data-health workflow: ok=true; findings=[]; 66/66 readiness targets;
  zero pending jobs in all four cycles; 92 subscriptions; healthy provider;
  12/12 external price checks matched exactly
web data-health scan: ok=true; 53/53 routes returned 200; no console errors;
  no failed requests; 44 warning markers reflect explicit unavailable, missing,
  or provider-state text rather than a failed request or unresolved readiness job
API health: 200; status=ok; database=connected
Vite app: 200
GitHub Actions: recorded after push
```

## Gate Result

The three mandatory Phase 5 invariants are proven in focused fixtures: no evidence-free candidate, deterministic stale downgrade/block behavior, and explicit missing metrics. Stop after full verification and remote CI; do not begin Slice 5.7 in this task.

## Next Model Recommendation

Use **GPT-5.6 SOL Extra High** for Slice 5.7. Orchestration crosses frozen source watermarks, Phase 4 profiles, scoring, guardrails, canonical run identity, persistence, replay, and partial-run failure handling. The individual policies are now explicit, so extra-high reasoning is justified without maximum effort.
