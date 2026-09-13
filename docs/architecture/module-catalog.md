# Module Catalog

This catalog defines target ownership. Current locations may remain legacy until
the migration roadmap moves them.

## Business Modules

| Module | Type | Purpose | Owned Features | Current Code | Future Location | Priority | Difficulty |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Portfolio | Business | Own portfolios, selected portfolio context, valuation summaries, account-level views, and user portfolio decisions. | `PF-*`, `BRK-*` portfolio mapping, portfolio overview widgets. | `src/dashboard/analytics`, `src/dashboard/models.py`, `src/dashboard/api`, `web/src/routes/portfolio*`. | `domain/portfolio`, `application/portfolio`, `contracts/portfolio`. | High | Large |
| Holdings | Business | Own positions/holdings, exposure, holding grades, and portfolio contribution semantics. | `HL-*`, holding cards, allocation drilldowns. | `src/dashboard/analytics`, `src/dashboard/api`, `web/src/routes/portfolioRoute.tsx`. | `domain/holdings`, `application/holdings`. | High | Medium |
| Transactions | Business | Own imported transactions, cash flow meaning, realized/unrealized gain inputs, and broker reconciliation. | Transaction import/list/edit workflow, broker sync writes. | `src/dashboard/brokers`, `src/dashboard/api`, `web/src/routes/brokersRoute.tsx`. | `domain/transactions`, `application/transactions`. | Medium | Large |
| Asset Research | Business | Own asset overview, identity, business profile, related analytics, and asset page composition. | `ASSET-*`, asset header, metric panels, earnings/date blurbs, related news. | `src/dashboard/api`, `src/dashboard/analytics`, `web/src/routes/assetsRoute.tsx`. | `domain/assets`, `application/assets`. | High | Large |
| Market Prices | Business | Own quotes, price history, return series inputs, and market freshness semantics. | Price charts, current price cards, quote/freshness badges. | `src/dashboard/ingestion`, `src/dashboard/api`, `web/src/api.ts`. | `domain/market_data`, `application/market_data`. | High | Medium |
| Fundamentals | Business | Own financial statement metrics and provider-derived company fundamentals. | Fundamental summaries, readiness metrics, valuation inputs. | `src/dashboard/ingestion`, `src/dashboard/analytics`, `src/dashboard/api`. | `domain/fundamentals`, `application/fundamentals`. | High | Large |
| Valuation | Analytical | Own valuation ratios, relative valuation, and valuation-specific quality states. | Valuation panels, benchmark financial metric hydration. | `src/dashboard/analytics`, `src/dashboard/api`. | `domain/valuation`, `application/valuation`. | High | Medium |
| Performance Analytics | Analytical | Own CAGR, total return, drawdown, volatility-ready return series, and benchmark-relative performance. | Performance cards, comparison returns, portfolio return charts. | `src/dashboard/analytics`, `web/src/routes/*`. | `domain/analytics/performance`. | High | Large |
| Risk Analytics | Analytical | Own volatility, beta, correlation, Sharpe-style metrics, risk cards, and risk dashboards. | Risk metric panels, signal/risk surfaces. | `src/dashboard/analytics`, `web/src/routes/signalsRoute.tsx`. | `domain/analytics/risk`. | Medium | Medium |
| Benchmarking | Business/Analytical | Own benchmark identity, associations, financial metric snapshots, and comparison baselines. | Benchmark pickers, benchmark associations, compare baselines. | `src/dashboard/api`, `src/dashboard/ingestion`, `web/src/routes/compareRoute.tsx`. | `domain/benchmarking`, `application/benchmarking`. | High | Medium |
| Comparisons | Workflow | Own compare workspace orchestration and cross-asset/portfolio comparison use cases. | `CMP-*`, compare tables, Kiviat/radar, diff panels. | `src/dashboard/api`, `web/src/routes/compareRoute.tsx`. | `application/comparisons`, `contracts/comparisons`. | High | Large |
| News | Business | Own ticker/market news, source metadata, sentiment tags, and news terminal data contracts. | `NEWS-*`, ticker news feed, related news panels. | `src/dashboard/news`, `src/dashboard/api`, `web/src/routes/newsRoute.tsx`. | `domain/news`, `application/news`. | Medium | Medium |
| Sentiment | Analytical | Own retail/news sentiment metrics and ranking inputs. | Retail sentiment status, sentiment chips, signal ranking. | `src/dashboard/ingestion_sentiment`, `src/dashboard/news`. | `domain/sentiment`, `application/sentiment`. | Medium | Medium |
| Business Strength | Analytical | Own scorecard categories, factor grades, evidence, and explainability. | `BS-*`, holding grades, scorecard panels. | `src/dashboard/services/business_strength`, `src/dashboard/api`. | `domain/scoring/business_strength`. | High | Medium |
| Simulations | Analytical | Own Monte Carlo, forecasting, scenario, optimization, and backtesting math. | Projection/forecast previews, future desktop-heavy workflows. | `src/dashboard/analytics`, `src/dashboard/api`. | `domain/simulations`, `application/simulations`. | Medium | Very large |
| Watchlists | Stateful Workflow | Own watchlist membership, quick monitoring, and mobile-friendly watch surfaces. | Watchlist controls, watchlist price checks. | Current support is partial through assets/watchlist-related queries. | `domain/watchlists`, `application/watchlists`. | Medium | Medium |
| Widget Configuration | Platform/Product | Own page feature flags, widget visibility, and layout configuration. | `LAYOUT-*`, feature menus, optional widgets. | `web/src/pageFeatureStore.ts`. | `contracts/widgets`, `application/preferences`, `web/src/platform/web`. | Medium | Small |
| Operations/Data Quality | System | Own ingestion status, readiness, freshness, job health, and operator controls. | `OPS-*`, worker cards, readiness tables, manual refresh controls. | `src/dashboard/api`, `src/dashboard/application/operations.py`, `src/dashboard/ingestion`, `web/src/routes/operationsRoute.tsx`. | `application/operations`, `contracts/operations`. | High | Medium |
| AI Insights | AI | Own generated explanations, summaries, Q&A, prompt versions, and evidence references. | AI summary placeholders/experiments, future ticker insight. | Experimental/placeholders only. | `src/dashboard/ai`, `contracts/insights`. | Low now | Large |
| Investor Intelligence | Analytical | Own deterministic observed investor profiles, evidence-backed profile dimensions, and future candidate/recommendation domain contracts. | Investor profile now; candidate and recommendation engines remain phased. | `src/dashboard/rules_and_data`. | `src/dashboard/rules_and_data`, future `application/investor_intelligence`. | High | Large |
| User Preferences | Product | Own durable preferences, feature availability, and per-user platform settings. | Feature menus, layout preferences, future settings. | `web/src/pageFeatureStore.ts`, API settings where present. | `application/preferences`, `contracts/preferences`. | Medium | Medium |

## Infrastructure Modules

| Module | Purpose | Current Code | Public Surface | Security Notes |
| --- | --- | --- | --- | --- |
| Database Access | Own DuckDB access, schema mapping, repository implementations. | `src/dashboard/db.py`, migrations/seeds. | Repository interfaces only. | May handle holdings, transactions, account links. |
| Provider Adapters | Own FMP, yfinance, news, broker, and future AI provider clients. | ingestion/news/brokers modules. | Provider-specific interfaces implemented behind application ports. | Provider keys must not leave backend/server config. |
| Background Jobs | Own scheduling and batch execution. | ingestion background worker/API startup hooks/tools. | Worker commands and status contracts. | Jobs may write persistence; no UI imports. |
| Caching | Own local cache and TTL behavior. | Current ad hoc cache/status logic. | Cache interfaces and freshness metadata. | Cache must preserve provenance. |
| Observability | Own logs, status payloads, health checks. | `/health`, operations/status routes, tools. | Health/status contracts. | Redact secrets and portfolio-sensitive data. |
| Configuration | Own env parsing and runtime settings. | `.env.example`, settings helpers. | Typed server configuration. | No backend secrets in web/mobile bundles. |
