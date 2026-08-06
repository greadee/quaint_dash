# Module Ownership Matrix

Every Phase 1 feature group has a target owner. Feature IDs are defined in
[feature_widget_segmentation_plan.md](../planning/feature_widget_segmentation_plan.md).

| Feature IDs | Current Location | Owning Module | Supporting Modules | Presentation Owner | Data/API Owner | Classification | Adapter Needed | Migration |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `NAV-*`, `LAYOUT-*` | `web/src/routes`, `web/src/pageFeatureStore.ts` | Widget Configuration | User Preferences | Web Platform | Preferences contracts | Web now, shared config later | Yes, storage adapter | A |
| `PF-001` to `PF-006` | portfolio routes, analytics, API | Portfolio | Holdings, Performance, Benchmarking | Web Portfolio feature | Portfolio API/use cases | Shared core with web/mobile views | Yes, portfolio facade | B |
| `HL-*` | portfolio route, analytics/API | Holdings | Portfolio, Business Strength, Market Prices | Web Portfolio feature | Holdings API/use cases | Shared core | Yes | B |
| Allocation charts/tables | portfolio route/API | Holdings | Portfolio, Benchmarking | Web Portfolio feature | Holdings/Portfolio API | Shared core with platform-specific charting | Yes | B |
| `ASSET-001`, identity header | asset route/API | Asset Research | Market Prices, Fundamentals | Web Asset feature | Asset API/use cases | Shared core | Yes | B |
| `ASSET-002`, price summary/chart/timeframe | asset route/API | Market Prices | Asset Research | Web Asset feature | Market Data API | Shared core | Yes | B |
| Fundamentals panels | asset route/API | Fundamentals | Valuation, Business Strength | Web Asset feature | Fundamentals API | Shared core | Yes | B |
| Valuation/profitability/risk panels | asset route/API | Valuation | Fundamentals, Risk Analytics | Web Asset feature | Valuation API | Shared core | Yes | C |
| Earnings/calendar blurb | asset route/API | Fundamentals | Corporate Calendar future | Web Asset feature | Fundamentals/Calendar API | Shared core | Yes | B |
| Related news feed | asset/news routes/API | News | Sentiment, AI Insights | Web News/Asset features | News API | Shared core with mobile compact view | Yes | B |
| AI-generated summary placeholder | asset/news future | AI Insights | News, Asset Research | Platform-specific rendering | AI contract | AI service only, platform display | Yes | F |
| `CMP-*` | compare route/API | Comparisons | Asset Research, Portfolio, Benchmarking, Business Strength | Web Compare workspace | Compare API | Shared core; desktop preferred for large workspaces | Yes | C |
| Benchmark picker/association | compare/assets/API | Benchmarking | Asset Research | Web Compare/Asset | Benchmarking API | Shared core | Yes | B |
| `NEWS-*` | news route, `src/dashboard/news` | News | Sentiment, Asset Research | Web News Terminal | News API/use cases | Shared core, mobile compact | Yes | B |
| Sentiment tags/signals | news/signals/operations | Sentiment | News, Signals | Web News/Signals | Sentiment API | Shared core | Yes | C |
| `SIG-*` | signals route/API | Performance Analytics | Risk, Sentiment, Market Prices | Web Signals | Analytics API | Shared core, desktop advanced | Yes | C |
| Business-strength scorecards | services/business_strength/API/routes | Business Strength | Fundamentals, Holdings | Web Asset/Portfolio/Compare | Scorecard API | Shared core | Yes | C |
| `BRK-*` | brokers route, brokers module/API | Transactions | Portfolio, Holdings | Web Broker workspace | Broker/Transactions API | Web/desktop; mobile read-only later | Yes | D |
| Import transactions | broker route/API | Transactions | Broker Provider Adapters | Web Broker workspace | Transaction command API | Server-only write path | Yes | D |
| Watchlist controls | asset/watch support | Watchlists | Market Prices, User Preferences | Web Asset/Watchlist | Watchlist API | Shared core, mobile preferred | Yes | D |
| `OPS-001` ingestion jobs table | operations route/API | Operations/Data Quality | Background Jobs, Database | Web Operations | Operations API | Web/admin, server-only commands | Yes | A |
| `OPS-002` routine worker status card | operations route/API/application facade | Operations/Data Quality | Background Jobs | Web Operations | Operations API/application query | Web/admin, status shared | View-model pilot and status query facade created | A started |
| Market freshness card | operations route/API | Operations/Data Quality | Market Prices, Background Jobs | Web Operations | Operations API | Shared status, web/admin controls | Yes | A |
| Projection/data readiness tables | operations route/API | Operations/Data Quality | Fundamentals, Portfolio, Valuation | Web Operations | Readiness API | Web/admin, shared status | Yes | A |
| Manual refresh/retry controls | operations route/API/application command facade | Operations/Data Quality | Background Jobs, Provider Adapters | Web Operations | Operations command API/application command | Web/admin only | Worker command facade created for start/stop/tick; broader manual refresh still pending | A started |
| Monte Carlo/forecasting | analytics/API/future | Simulations | Portfolio, Market Prices, Risk | Desktop future/web preview | Simulation API | Desktop preferred, server/shared core | Yes | E |
| AI ticker insight/news synthesis | experimental/future | AI Insights | News, Market Prices, Asset Research | Platform display | AI API/worker | AI service, desktop/server preferred | Yes | F |
| Deterministic investor profile | `src/dashboard/ai_brain` | Investor Intelligence | Portfolio, Holdings, Risk, Valuation, Sentiment, Watchlists | No presentation owner in Phase 4 | Pure profile contract/engine | Shared backend core | Source adapter still required | E started |

## Unclear Or Deferred Ownership

- Corporate calendar deserves its own module only when earnings/dividend/event
  workflows expand beyond fundamentals support. Until then, Fundamentals owns
  earnings-date blurbs and exposes calendar-like fields through contracts.
- Alerts are currently future-facing. They should not become a module until a
  durable alert rule, notification, and persistence workflow exists.
- File exports belong to platform adapters unless they require deterministic
  analytics, in which case the analytics module owns the data and the platform
  owns the file format.
