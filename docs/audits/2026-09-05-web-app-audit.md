# Web application audit — 2026-09-05

## Scope, method, and guardrails

This was a live, read-only audit of the locally running application at `http://127.0.0.1:8000`. It used repeated desktop and 390 px-wide mobile passes through the user interface plus read-only API, browser-console, and local server-log checks.

The audit intentionally did **not** trigger any action that could mutate local records, start ingestion, contact a provider, refresh prices, import transactions, reconnect a broker, schedule/run/retry jobs, create an alert/watchlist item, or delete history. Therefore, this report validates the visible pathways and operational state, but not the successful execution of those write or external-provider actions.

Pages and pathways reviewed:

- Overview, Portfolios (aggregate and individual), News, Retail sentiment, Signals and signal detail
- Compare (empty state, adding one symbol, then a second symbol), Benchmarks
- Brokers (accounts and Import & Reconciliation), Operations, Settings
- Asset chart, news, fundamentals, and business-strength views
- Desktop and mobile responsive behavior; browser console; representative API response timings; operational API responses; server logs

No financial calculation, persistence contract, source data, or application code was changed during this audit.

### Severity definitions

| Severity | Meaning |
| --- | --- |
| P0 | Can materially mislead an investment or operational decision, exposes inappropriate raw data, or prevents a core user workflow from being understood. |
| P1 | High-impact reliability, data-quality, or usability problem that should be prioritized after P0 containment. |
| P2 | Meaningful clarity, accessibility, layout, or efficiency issue; fix as part of the next UX/reliability cycle. |

## Executive summary

The application is fast locally and has a generally coherent dark-shell visual system, but it is currently **not safe to present as a reliably current decision-support surface**. The most serious pattern is that authoritative-looking metrics, rankings, and recommendations remain visible while the underlying source health is stale, disabled, synthetic, failed, or incomplete. The Overview’s "0 attention / data healthy" message directly conflicts with the Operations, Signals, News, Retail, and Benchmarks pages.

The most urgent containment work is to make source provenance, freshness, and operational failure states unavoidable wherever they affect a number or recommendation. The second urgent issue is broker reconciliation: ticker cells render full raw provider objects rather than a usable instrument identifier.

### Pressing issues, in priority order

| ID | Severity | Finding | Evidence observed | Recommended first action |
| --- | --- | --- | --- | --- |
| DQ-01 | P0 | The global health message says data is healthy while major feeds and jobs are stale, failed, disabled, or backlogged. | Overview reported `0` attention / `data healthy`; Operations showed 355 pending jobs and disabled workers; News, Signals, and Benchmarks showed stale or degraded inputs. | Build one shared data-health model and show a persistent warning on every affected analytical page. Do not call the system healthy until blocking sources are current. |
| DQ-02 | P0 | Retail sentiment is displayed as if it is sourced from Reddit/X even though both providers have missing credentials and zero stored posts. | Operations/API: Reddit and X `configured: false`, `post_count: 0`; Retail presented 29 held stocks, 150 posts, repeated Reddit/X post counts, confidence, and a 10% add-on. | Hide/disable retail-derived recommendations until real source content is present, or visibly label the content as fixture/synthetic data and remove decision-weight language. |
| BR-01 | P0 | Broker reconciliation renders raw provider objects in the ticker column. | Every affected row displayed a large object including IDs, descriptions, currency/exchange objects, logo URL, and FIGI rather than a symbol/name. | Normalize the API/view model to a display symbol and name; keep raw payload strictly out of the customer-facing table. |
| DQ-03 | P0 | Stale signals continue to look active and high confidence. | Signals were computed/data-as-of 2026-08-10; signal detail showed an active 93% confidence signal with data as of 2026-08-05; current audit date is 2026-09-05. | Apply a staleness gate that suppresses action language, ranking, and confidence presentation past the configured freshness threshold. |
| INF-01 | P0 | Scheduler/DB failures exist in server logs but are not surfaced in Operations. | Logs contained repeated DuckDB file-lock errors and the ingestion scheduling SQL binder error `Referenced table "s" not found`; Operations did not present a corresponding actionable last error. | Fix the SQL alias failure and single-writer/concurrency design, then send the last error, error count, and remediation state to Operations. |
| DQ-04 | P1 | Benchmarks present strong performance figures even though fresh data is 0/34 and latest metric is from 2026-06-18. | Benchmarks page: `Fresh data 0/34`, `Proxy coverage 34`; high-return metrics remained central. | Show a blocking stale-data state; distinguish proxy observations from fresh benchmark data in every metric/card/chart. |
| DQ-05 | P1 | News is degraded and uses mock sources/`example.test`, yet Overview continues to show it as ordinary news. | News health: corporate calendar stale, FMP 402, mock news stale; visible items used `mock_news` and external links to `example.test`. | Exclude placeholder links from production feed cards or place them behind an explicit demo indicator; promote degraded status to Overview. |
| BR-02 | P1 | 2,806 transactions need review without a clear in-context route to resolve account/asset mapping. | Import screen showed 2,806 needs review, unresolved assets, and rows asking for account assignment/asset resolution; no direct resolver path was apparent in that workflow. | Add direct “resolve account” and “resolve asset” actions/links with filtered context, plus a safe review queue. |
| UX-01 | P1 | The broker desktop hero uses a narrow text column and leaves a large empty area, creating awkward line wrapping. | Broker profile content wrapped nearly word-by-word in a tall desktop card. | Correct the layout grid/max-width and test at common desktop widths. |
| UX-02 | P1 | Comparison, asset, and benchmark numbers do not consistently carry their freshness state into downstream charts/tables. | NVDA.TO was explicitly >10 days stale in Compare but still appeared alongside fresh AMD.TO in normal-looking tables/charts; asset chart/fundamentals lacked a prominent freshness state. | Carry an asset-level freshness badge into every dependent metric, row, chart, export, and decision card. |
| INF-02 | P1 | A disabled worker with 355 pending jobs is not represented as an urgent system condition. | Operations showed background/price/portfolio workers disabled and never run, while pending jobs remained 355 and dead-lettered FMP tasks were visible. | Add an operations incident banner with severity, backlog age, affected data products, and controlled recovery guidance. |
| DQ-06 | P1 | Asset fundamentals/business strength show confident-looking outputs while readiness is incomplete or internally contradictory. | Fundamentals: 1/3 model inputs ready, DCF missing, yet fair values/CAGRs shown. Business Strength: components say insufficient/low-confidence data while confidence and completeness display 100%. | Gate or de-emphasize outputs that have missing inputs; repair confidence/completeness semantics and expose calculation eligibility. |

## Pass 1 — navigation, discoverability, and first-screen truthfulness

### Goal

Assess whether the main navigation makes core jobs discoverable, whether first views make their current state understandable, and whether summary language agrees with underlying data health.

### What was reviewed

Overview, Portfolios, News, Retail sentiment, Signals, Compare, Benchmarks, Brokers, Operations, and Settings were opened through the normal navigation shell.

### Findings

#### DQ-01 — conflicting system-health story (P0)

The Overview is reassuring: it showed portfolio totals, 54 holdings, 7 portfolios, broker mapping progress, and `0` attention with the label `data healthy`. That message is not supportable based on the rest of the application:

- News was visibly degraded (stale corporate calendar, FMP HTTP 402, stale mock news).
- Signals were approximately four weeks old, while still counted as active/high confidence.
- Benchmarks reported fresh data for 0 of 34 benchmarks.
- Operations reported 355 pending jobs and multiple disabled workers.
- Retail source providers had no credentials or posts.

This is more than a copy mismatch: a global green/healthy status acts as a trust signal that can override page-level caveats. A user who only visits Overview receives the opposite of the operational truth.

#### DQ-05 — mock/degraded news is indistinguishable from usable market news at the summary level (P1)

Overview presented three conventional news cards. Each was sourced from `mock_news` and linked to `example.test`. News itself did show a degraded banner, but the page still displayed dated June 30 stories under a synchronised timestamp and permitted the mock cards to look like usable current research.

The production behavior should be one of the following, chosen explicitly:

1. Do not render fixture/mock content outside an explicitly labelled demo mode.
2. Render it with a strong “sample data” treatment and suppress decision-oriented prominence.
3. Render only real, successfully fetched sources, with a meaningful empty/degraded state when none is available.

#### DQ-02 — retail page gives synthetic/unsupported social signals decision weight (P0)

Retail sentiment appeared polished and persuasive: 29 held stocks with social data, 30 popular names, 150 recent posts, post-source counts, confidence values, and a stated 10% add-on when enabled. The repeated structure is itself suspicious (for example, the same source split/confidence/shift pattern appears across entries), but Operations and the retail API establish the issue decisively: Reddit and X were not configured, zero stored posts existed, and there were no recent posts.

This must not be framed as actual social ingestion. In particular, the 10% add-on label can appear to influence an investor’s expected outcome. Disable that influence until source provenance, fetch time, and actual content are available.

#### DQ-03 — signal discovery continues to advertise stale recommendations (P0)

Signals displayed 34 active signals and many high-confidence opportunities, but the page itself identified a 2026-08-10 computation/data date. At the time of audit (2026-09-05), that is stale for a ranking/recommendation interface. It also reported 515 stale/incomplete items while rendering action-like “Active” status nearby.

The UI needs a policy such as: current, warning, stale, blocked. A stale policy must alter both visual priority and allowed language; simply placing a date in metadata is inadequate.

#### UX-03 — navigation is broad but the shell communicates status poorly (P2)

The left navigation exposes the main domains and is generally easy to scan on desktop. However, there is no persistent cross-page health indicator, no data recency summary, and no quick route from a stale/degraded outcome to the responsible operation. Users must independently discover Operations, then interpret a dense set of controls and status panels.

Add a compact app-wide data-status affordance that links to a filtered Operations/health view. It should summarize: degraded sources, oldest critical data, active backlog/dead letters, and whether background processing is operating.

#### UX-04 — card density is high and visual hierarchy sometimes competes with content (P2)

The visual system is attractive in isolation: dark background, high-contrast cards, restrained accent colors, and clear panel boundaries. Across entire pages, though, it leans heavily on large rounded cards, status chips, and filter strips. On Signals, Benchmarks, and Brokers, the cumulative effect is a dashboard-like wall of UI where the actual next action is less prominent than the framing around it.

This makes the product read as an “AI dashboard” rather than a deliberate portfolio workspace: many summary metrics and confidence badges are presented before their evidence, eligibility, or freshness. Consider reducing card framing for secondary metadata, reserving accent color/chips for genuinely actionable exceptions, and grouping related controls behind progressive disclosure.

## Pass 2 — end-to-end user pathways and missing routes

### Goal

Follow concrete, non-mutating workflows from entry page through visible next steps, looking for missing actions, traps, unclear handoffs, and unsafe interpretation.

### What was reviewed

Comparison setup, an individual asset, asset tabs, a signal-detail view, an individual portfolio and its news, broker account/import/reconciliation views, and the portfolio creation entry point.

### Findings

#### UX-05 — comparison’s one-asset state is conceptually inconsistent (P2)

The empty comparison state correctly asks the user to add at least two assets. After adding NVDA.TO, however, the interface immediately rendered a substantial one-asset analysis and silently added TSXCOMP as the benchmark. This is potentially useful, but the behavior is not explained and conflicts with the stated “two assets” requirement.

Make the transition explicit: either maintain a clearly labelled single-asset preview until a second asset is added, or change the empty-state wording and explain the automatic benchmark selection. The user should be able to choose/confirm the benchmark before it affects results.

#### UX-02 — stale comparison data lacks downstream safeguards (P1)

Compare did display a small warning that NVDA.TO’s stored price was more than 10 calendar days old. The warning did not travel with the associated performance tables, valuation panels, or charts. When AMD.TO was added, stale NVDA.TO values looked materially equivalent to fresh AMD.TO values.

Freshness needs to be attached at the individual metric/series level, not only stated once in a surrounding card. A stale series should be visually distinct and excluded from rank/winner treatments by default.

#### DQ-06 — incomplete fundamental inputs still produce authoritative-looking outputs (P1)

The NVDA.TO Fundamentals view is candid in one place: model input readiness was `1 / 3 ready`, DCF was missing cash flow/share, and valuation models lacked inputs such as balance sheet, cash flow, shares, or free cash flow. Yet nearby cards showed a blended CAGR, a forecast expected value, a DDM fair value, implied growth, and an extreme dividend growth figure.

This audit does **not** assess whether those calculations are mathematically correct. The issue is display safety: figures with material missing inputs should not have the same visual treatment as eligible, validated models. Show “not eligible” as the primary state, name the missing source fields, and only surface estimates in an explicitly conditional/low-confidence panel.

#### DQ-07 — business-strength confidence and completeness are contradictory (P1)

The NVDA.TO Business Strength panel reported high overall confidence/completeness and “no missing critical metrics.” Individual components simultaneously described insufficient data and low confidence while each displayed 100% confidence and 100% completeness. The panel also cited data as of late June without a prominent stale warning.

This makes it impossible to tell whether a score is ready for use. Define confidence and completeness once, compute/display them consistently at component and aggregate levels, and put date/source coverage near the score itself.

#### DQ-08 — asset news conceals degraded/stale feed condition (P1)

The NVDA.TO News tab contained a single old mock article, with no equivalent of the News page’s degradation banner. The UI also ran the headline and date together (for example, the title visually met `6/30/2026` without clear spacing), and left a large empty content area beneath the small result.

Asset-level news must inherit global source health and distinguish “no current verified articles” from a normal populated feed. Treat the empty/degraded state as first-class UI rather than a short, ordinary-looking card.

#### DQ-09 — stale signal detail retains strong action authority (P1)

The NVDA.TO signal-detail page showed an active 93% input-confidence signal even though its data was as of 2026-08-05 and historical efficacy had no sample size. The page offered actions such as alerts, watchlist, and review without an intervening freshness/validation gate.

Add an explicit “not current” state to the primary signal header and require a user acknowledgement or a fresher recomputation before alert/watchlist actions can be framed as timely. Make lack of historical efficacy more prominent than the confidence percentage.

#### BR-01 — raw provider objects make reconciliation unusable (P0)

The Import & Reconciliation table’s ticker column contained full provider-shaped data objects. Aside from making each row unreadable, it exposed fields such as internal IDs, currencies, exchange objects, logo URLs, and FIGI values. Users cannot efficiently scan, filter, or decide how to resolve rows in this state.

Return a stable presentation object (for example, `symbol`, `name`, `exchange`, `currency`, `resolution status`) and keep any raw provider payload accessible only through a deliberate developer/support diagnostic pathway with appropriate privacy controls.

#### BR-02 — high review backlog has no visible, guided resolution pathway (P1)

The Import view reported 59 ready transactions, 4,656 already imported, 49 unsupported, and 2,806 needing review. Rows visibly need account assignment or asset resolution, yet the workflow does not offer an in-context, scoped next action to complete those steps. Some account-assignment controls elsewhere appeared disabled without a reason.

Users need a review queue that answers “what should I do next?” by grouping blockers and linking directly to the correct mapping/resolution screen with transaction and broker context preserved. Also explain disabled assignment controls and what prerequisite would enable them.

#### UX-06 — import workflow is overloaded on mobile (P1)

At 390 px wide, import cards stack acceptably, but account/transaction content expands into a very long vertical surface. Multiple account panels were expanded with dense transaction rows, while the global import action sits near the top. This risks rendering and scrolling cost on lower-end devices and makes it hard to understand what will be imported.

Default account detail to collapsed, paginate/virtualize long tables, expose a per-account readiness summary, and make the import scope explicit before the user reaches a destructive/external action.

#### UX-07 — the portfolio creation entry point is present (verified)

The aggregate Portfolios page includes a direct New Portfolio action. This is the correct discoverable location and avoids the earlier broker-only path. No issue was found with the entry point during this read-only review; submission was not performed.

## Pass 3 — ingestion, job traffic, APIs, and infrastructure

### Goal

Reconcile user-facing operational claims with read-only health endpoints, job/provider state, local response behavior, browser errors, and service logs.

### What was reviewed

Representative GET endpoints for health, overview, portfolio, signals, benchmarks, news, brokers, reconciliation, workers/jobs, and retail sentiment were sampled. Browser console state and local API server logs were also inspected.

### Observed local responsiveness

The sampled endpoints were responsive locally: roughly 1–91 ms per request in this environment. Examples included Overview (20–50 ms), Signals (59 ms for a 25-item response), Retail (21 ms), Reconciliation (12 ms), and broker/worker status endpoints (about 1–4 ms). The browser console showed no errors or warnings during the audit.

This is encouraging, but it is not a load test or evidence of production-scale performance.

### Findings

#### INF-01 — critical scheduler and database errors are hidden from the operations surface (P0)

Local server logs contained two material classes of operational failures:

- DuckDB could not open `data/persistent_db.db` because another process was using it.
- Background ingestion scheduling repeatedly failed with a SQL binder error: `Referenced table "s" not found`, associated with a predicate using `s.snapshot_date`.

Operations showed workers as disabled/never run but did not present these failures as active or historic error conditions with enough detail to act. A user could mistake “disabled” for a clean idle system rather than a failed or blocked one.

Correct the SQL alias/query, define the intended DuckDB writer/concurrency model, and report the latest error, error count, timestamp, affected worker, and safe remediation to Operations. Avoid exposing raw stack traces to ordinary users, but do not hide the failure category.

#### INF-02 — backlog and disabled workers require incident-level clarity (P1)

Operations reported 355 pending jobs. Background worker, holding-price worker, and portfolio-data worker were disabled and had never scheduled/run. The page also contained dead-letter financial-statement tasks due to an FMP rate-limit error. Some readiness panels separately reported `76/80 READY` and `25/25 COMPLETE`, which makes the current state difficult to reconcile.

Add an incident summary at the top of Operations:

- backlog count and oldest job age;
- worker status and why it is disabled;
- dead-letter count by provider/error class;
- data products currently affected;
- a safe, role-appropriate recovery path; and
- a distinction between historical readiness and live refresh readiness.

#### INF-03 — benchmark page appears to create a large request fan-out (P2, performance risk)

Single endpoint latency was low, but server logs showed the Benchmarks view requesting multiple resources for many benchmark symbols: details, prices, metrics, exposures, and constituents. With 34 benchmarks this is a sizeable page-load fan-out. It is a risk rather than a confirmed local latency bug; the local machine completed it quickly.

Profile this view under realistic latency and data volume. Prefer a summary/batch endpoint, lazy-load only selected benchmark details, cache immutable responses, and avoid requesting constituent/exposure data until users open it.

#### INF-04 — source failure states need ownership, not only controls (P1)

Operations exposes many powerful controls—start worker, run cycle, refresh prices, force readiness, schedule/run retail, retry failed jobs—without a concise explanation of the current desired recovery sequence or which controls contact external services. This is risky for a non-operator and can encourage repeated manual attempts when a provider is rate limited.

Add role-sensitive guidance and a recommended next step based on the error class. For example, FMP rate limit: delay/retry window and quota status, not a generic retry prompt. Clearly mark actions that initiate provider traffic.

#### INF-05 — raw broker payload storage needs visible governance (P2)

Broker status reports raw payload storage enabled. Raw data already appeared accidentally in reconciliation, demonstrating why this feature requires a boundary. The normal UI should disclose the retention/privacy consequence, allow controlled opt-out where appropriate, and ensure raw payload cannot leak into presentation models.

## Pass 4 — visual design, layout, density, and responsive behavior

### Goal

Evaluate visual hierarchy, spacing, margins, clarity, mobile behavior, and whether the design communicates warranted confidence.

### Findings

#### UX-01 — broker desktop layout has a visible column-sizing defect (P1)

The desktop Broker profile hero constrained descriptive content to a very narrow left column while the rest of the card remained largely empty. Text wraps line-by-line and creates an unusually tall card. This is conspicuous at normal desktop width and makes a core operational screen feel unfinished.

Fix the grid/template columns, allow the primary copy block an appropriate maximum width, and use the right side for concise account/connection status if that space is intentionally reserved.

#### UX-08 — several pages overuse elevated cards and status pills (P2)

Portfolio summaries and selected pages are readable, but Signals, Benchmarks, and Operations contain many adjacent outlined/elevated containers. This increases visual clutter and makes exception states look similar to normal explanatory metadata. Bright white portfolio cards against the dark shell also create a different visual language from surrounding dark panels.

Adopt a smaller number of visual elevation levels. Use plain grouped sections for reference data, reserve elevation and accent colors for actions/exceptions, and normalize portfolio-card treatment with the rest of the shell.

#### UX-09 — narrow metadata columns create wasted space and awkward wrapping (P2)

Signals uses a narrow metadata area with many stacked pills next to broad whitespace, while some asset/fundamental header labels appear visually displaced at the far right. These layouts consume vertical space without improving scanability. The asset-news card also has an oversized empty remainder after one short item.

At desktop widths, use content-aware max widths and a responsive grid that collapses secondary metadata into a single concise line/expandable disclosure rather than a tall stack.

#### UX-10 — mobile is readable but inefficient and partially inaccessible (P1)

At 390 × 844:

- Overview cards and major actions did not overlap and were readable.
- The mobile menu control appeared in the accessibility tree as an unlabeled button containing only an image. At least one additional image-only control was similarly unlabeled.
- Card stacking creates a long scroll before a user can compare related metrics.
- Broker Import becomes especially tall due to default-expanded detail content.

Provide accessible names/tooltips for every icon-only control, consider a compact two-column metric layout where appropriate, and use progressive disclosure for large operational content.

#### UX-11 — authoritative styling amplifies low-quality data (P1)

The product looks professional enough that its numbers, score bars, confidence percentages, and recommendation-like labels read as authoritative. The same visual treatment is applied to mock news, stale signals, proxy-only benchmarks, and incomplete valuation models. This is the main way the product currently “looks AI”: it presents a high density of synthesized outputs with confidence framing while provenance and uncertainty are visually secondary.

The design solution is not decorative. Make evidence, source state, age, coverage, and eligibility part of the primary visual hierarchy. A less populated card that clearly says “blocked: source unavailable” is more trustworthy than a confident-but-unverified estimate.

## Pass 5 — data freshness, evidence, and decision-safety cross-check

### Goal

Trace whether freshness, completeness, and source provenance remain visible from the system summary down to decision-facing details.

### Cross-page evidence

| Surface | Data-quality state observed | User-facing risk |
| --- | --- | --- |
| Overview | Calls data healthy; shows mock news as normal cards. | Users may assume all downstream insights are current. |
| News | FMP 402; corporate calendar/mock feed stale; external `example.test` links. | Old/sample content can be mistaken for real research. |
| Retail | Provider credentials absent; zero posts; rich sentiment cards shown. | Synthetic content can influence allocation/expected-return impressions. |
| Signals | Data/computation about four weeks old; signals remain active/high confidence. | Timing-sensitive ideas can be treated as actionable. |
| Signal detail | Older data and no efficacy sample; 93% confidence/active treatment persists. | Confidence can be misread as demonstrated predictive value. |
| Asset fundamentals | Inputs incomplete; estimates/fair values still highly visible. | Conditional model output can be mistaken for validated valuation. |
| Business Strength | Insufficient data text conflicts with 100% confidence/completeness. | Users cannot judge score validity. |
| Compare | One stale asset warned once, then rendered normally in downstream comparison. | Fresh and stale series appear equally comparable. |
| Benchmarks | Fresh 0/34, proxy coverage 34; strong return metrics highlighted. | Proxy/stale figures can be treated as live benchmark facts. |
| Operations | Backlog, disabled workers, dead letters, and hidden log failures. | Users cannot connect stale outputs to their operating cause. |

### Required product behavior

Implement a shared evidence contract for every analytical output. At a minimum it should carry:

- source/provider and whether it is real, proxy, fixture, or inferred;
- observation/as-of time and retrieval time;
- freshness state based on the type of data;
- source health/error state;
- completeness/eligibility state;
- a user-facing limitation message; and
- whether the result can participate in ranking, recommendation, alerting, or expected-return displays.

The interface should use that contract consistently rather than allowing each page to decide how much caveat to reveal.

## Recommended remediation sequence

### Wave 1 — prevent misleading decisions

1. Replace the global healthy status with a conservative aggregate health model.
2. Gate/hide mock, synthetic, stale, proxy-only, and incomplete-data outputs from recommendation-like presentation.
3. Fix raw provider-object rendering in broker reconciliation immediately.
4. Correct the scheduler SQL alias and resolve/contain DuckDB writer-lock behavior.
5. Surface live worker failures, backlog severity, and dead-letter status in Operations.

### Wave 2 — complete blocked workflows

1. Add an in-context broker review queue for account and asset resolution.
2. Explain disabled controls and preserve context when routing to mapping/reconciliation.
3. Add per-account import scope, review counts, and controlled, clearly labelled action paths.
4. Clarify Compare’s automatic benchmark behavior and one-asset mode.

### Wave 3 — improve clarity and resilience

1. Batch/lazy-load benchmark resources and profile the fan-out under realistic latency.
2. Correct confidence/completeness semantics in Business Strength and model-readiness presentation.
3. Repair desktop grid/margin defects and reduce card/chip density.
4. Add accessible names for icon-only controls and optimize default mobile expansion behavior.
5. Add a source-health/setup location or a clear link from Settings/Overview to Operations.

## Validation checklist after fixes

- Overview cannot report healthy while a critical provider is failed, essential data is stale, or a required job backlog is blocked.
- Retail cannot render provider-attributed post counts, confidence, or allocation influence without stored source content and an as-of timestamp.
- Every broker reconciliation row renders a concise symbol/name and never raw provider data.
- A stale/proxy/incomplete value is visibly marked wherever it appears and cannot silently win a ranking or drive an alert.
- Business Strength confidence/completeness values agree with component-level evidence.
- Operations shows the current/most recent failure, backlog age, worker status, and a safe next action.
- A user can move from a transaction needing review directly into a scoped account/asset resolution workflow.
- Benchmark page-load request volume is bounded and selected details are loaded on demand.
- Desktop broker hero, asset metadata, and mobile import layout are verified at common viewport widths.
- Icon-only mobile controls have accessible names and keyboard/screen-reader behavior is verified.

## Audit limits

This report does not claim that the financial formulas themselves are correct or incorrect. It evaluates whether the application conveys enough freshness, eligibility, provenance, and uncertainty for users to interpret the outputs safely. It also does not validate external provider authentication, refreshes, imports, background execution, retries, or persistence because those actions were intentionally not run in a read-only audit.
