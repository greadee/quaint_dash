# S8 visual, responsive, and accessibility verification

Date: 2026-09-11
Slice: S8 — visual hierarchy, responsive behavior, and accessibility polish
Audit coverage: UX-01, UX-04, UX-06, UX-08, UX-09, UX-10, UX-11; UX-07 regression protection

## Outcome

The audited application routes now use a clearer responsive hierarchy at desktop, tablet, and 390 px mobile widths. The Broker hero no longer compresses its explanation into a narrow column; asset identity, price, news timestamp, and evidence labels stay grouped; secondary Signals, Benchmarks, and Operations surfaces use less elevation and fewer decorative pills; and direct portfolio cards follow the active shell surface tokens.

Mobile navigation controls now have accessible names, tooltips, expanded state, and a shared visible focus treatment. Compact two-column metric groups remain readable at 390 px, large broker import disclosures remain closed by default, and the direct `New portfolio` action remains visible.

No financial calculation, API response model, database schema, persistence path, provider call, ingestion action, or broker mutation changed in this slice.

## Pass 1 — desktop hierarchy and shell consistency

- Replaced the Broker hero's competing flexible columns with an explicit two-column desktop grid. The explanatory copy receives the larger track and the action group receives a bounded track; below 980 px both become one intentional column.
- Removed shadow/elevation from secondary status, ranking, summary, and control panels while retaining prominent incident and evidence surfaces.
- Removed decorative inset rings from signal count tiles and reduced their height and typography.
- Replaced the bright standalone portfolio-card styling with the shared dark/light shell surface, border, and text tokens.
- Converted low-level Signals and Benchmarks metadata from individual white pills into compact inline metadata with separators.
- Moved the Signals degraded-provider notice before the count tiles so source state leads numerical summary cards.

## Pass 2 — asset identity and news geometry

- Added an asset-page layout boundary so long company names render beneath the ticker instead of becoming a displaced trailing fragment.
- Kept the displayed asset price on one line while allowing the action group to wrap without horizontal overflow.
- Added semantic `<time>` markup and an `asset-news-copy` group so headline and publication date stay together.
- Bound asset-news columns at desktop, collapse them at narrow widths, and removed excess empty-state height.
- Verified a deliberately long company name and news headline at all three breakpoint projects.

## Pass 3 — mobile and tablet behavior

- Extended title/action stacking through the 900 px shell breakpoint. This fixed a real 768 px Signals overflow discovered during the first visual-baseline run.
- Restored two-column compact metric groups at 390 px and three-column benchmark comparison facts where side-by-side reading is useful.
- Enforced 44 px minimum tap targets for mobile navigation and page/card actions.
- Made narrow data-health banners place their action on a separate row instead of squeezing the incident headline.
- Kept broker import scope, account preview groups, and technical details collapsed by default. Browser tests assert the disclosure state.

## Pass 4 — accessibility semantics

- Added `Primary navigation` semantics and a stable `primary-navigation` relationship.
- Added `Open navigation` and `Close navigation` accessible names and matching tooltips; the open control exposes `aria-expanded` and `aria-controls`.
- Added a shared high-contrast `:focus-visible` outline for links, buttons, inputs, selects, summaries, and keyboard-focusable elements.
- The route-level browser audit rejects any visible icon-only button or link that lacks an accessible name or tooltip.
- The mobile navigation flow is exercised from keyboard focus through menu opening, and its computed focus outline is asserted.

## Pass 5 — visual regression matrix

Deterministic read-only fixtures cover the observed degraded and normal UI states without using the live database or invoking mutations. Playwright now has explicit projects for:

- desktop: 1440 × 1000;
- tablet: 768 × 1024;
- mobile: 390 × 900.

Twenty-one committed viewport baselines cover Overview, Signals, Asset News, Benchmarks, Brokers, Broker Import, and Operations. Every route assertion checks its primary heading, loaded fonts, document-level horizontal overflow, visible unnamed icon actions, unexpected API calls, and pixel baseline.

Rendered inspection of all 21 images caused three additional repairs before approval: the 768 px Signals action overflow, the desktop asset-name/price split, and the squeezed mobile Overview health action. Computer-assisted live inspection also confirmed that `New portfolio` is visible, primary navigation controls have accessible names, and the portfolio card view uses the active theme consistently.

## Verification

- `npm test -- --run` — 23 files, 116 tests passed.
- `npm run build` — passed; the pre-existing main-chunk advisory above 500 kB remains for S9.
- `npm run lint` — passed.
- `npm run test:e2e` — 58 passed, 2 intentionally skipped non-mobile navigation cases.
- `npm run test:e2e -- e2e/visual-regression.spec.ts` — 28 passed, 2 intentionally skipped non-mobile navigation cases; all 21 pixel baselines matched.
- `git diff --check` — passed.
- Live API and web health checks returned HTTP 200 before computer-assisted inspection.

## Boundaries retained

- All monetary values, returns, risk values, signal values, and benchmark values are read and formatted through their existing calculation paths.
- No Python, SQL, migration, storage, API contract, or persistence code changed.
- Visual fixtures intercept every `/api/v1/**` request and abort unexpected or non-GET requests, so screenshot generation cannot run jobs or change local data.
- The broker import action and existing authorization/confirmation behavior are unchanged.
