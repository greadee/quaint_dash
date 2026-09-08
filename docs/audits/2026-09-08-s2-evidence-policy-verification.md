# S2 evidence policy implementation and verification

S2 is implemented as a shared, display-only contract. It does not attach the contract to existing
routes yet; route and component adoption belongs to S3–S7. No financial calculation, stored
record, schema, ingestion rule, provider selection, retry behavior, or persistence contract was
changed.

## Delivered

- `evidence-display.v1` now carries evidence type, source kind/name/health, observation and
  retrieval timestamps, freshness, coverage, missing inputs, confidence, efficacy sample size,
  action eligibility, and stable reason codes.
- A clock-injected evaluator applies explicit elapsed-time policies for prices, news, financial
  statements, benchmarks, and monthly signals. There is no generic fallback.
- Precedence prevents confidence from overriding blocked providers, fixture/proxy/unknown
  provenance, stale or unknown observations, unsupported evidence, or essential missing inputs.
- Degraded, inferred, warning-age, partial, and explicit no-efficacy-sample states are cautionary.
- Python and TypeScript define matching response shapes for incremental consumers.
- Compatibility helpers either validate an already-public payload or select an explicit field
  allowlist. Known secret and raw-provider keys are rejected recursively.
- ADR PH15 records the thresholds, semantics, and change boundary.

## Acceptance evidence

| S2 criterion | Evidence |
| --- | --- |
| All policy states and precedence are covered | Parameterized tests execute exact current/warning/stale boundaries for five evidence types, blocked health, fixture, proxy, unknown source, essential missing inputs, unsupported coverage, degraded/inferred/partial evidence, and no efficacy sample. |
| Deterministic with a frozen clock | Repeated evaluation with the same immutable input and injected clock produces equal states. Naive database timestamps, offset timestamps, dates, missing timestamps, and future timestamps have explicit behavior. |
| Calculations unchanged | The S0 financial-output baseline remains green. S2 reads metadata and never imports or invokes a calculation function in its evaluator. |
| Persistence unchanged | The diff contains no database schema, repository, command, migration, or write-route changes. The full backend suite, including import/idempotency coverage, passes. |
| No raw provider payload in the display model | The typed model has no raw object field. Adversarial adapter tests omit raw/debug objects through allowlisting and reject nested credential/token/raw-payload structures. |
| Later routes can share one state | `evaluate_evidence`, `EvidenceDisplayResponse`, and the `EvidenceDisplay` TypeScript type provide one contract; route adoption does not require page-local freshness logic. |

## Verification results

| Command | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest -q` | 661 passed in 284.22 seconds. |
| Focused evidence, Operations API, and import regression suite | 82 passed in 33.36 seconds before the final policy-hardening tests. |
| Focused S0/S2 evidence suite after final hardening | 35 passed in 0.22 seconds. |
| `npm.cmd test` in `web/` | 100 passed across 22 files. |
| `npm.cmd run build` and `npm.cmd run lint` in `web/` | Passed. |
| Ruff on the changed Python contract/model/tests | Passed. |
| Architecture boundary check | Passed. |
| `git diff --check` | Passed. |

All tests used in-memory facts, frozen clocks, existing fixtures, or temporary databases. No live
provider was contacted and no live ingestion job was scheduled or run.

## Deferred by design

- S3 applies the contract to Retail, News, Signals, Fundamentals, Compare, and Benchmarks.
- S4 applies the public-field boundary to broker reconciliation responses.
- S6 uses the contract for Overview and broader Operations health aggregation.
- Product copy and visual treatment for each limitation remain with those surface slices.
- Any revision to PH15's initial display thresholds requires explicit policy review and updated
  boundary tests; these values are not ingestion schedules or financial-model inputs.
