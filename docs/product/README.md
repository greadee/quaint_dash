# Product And Application Flow

Quaint Dash is a local-first portfolio workspace. The browser reads versioned FastAPI responses;
Python services and DuckDB remain authoritative for holdings, market data, analytics, readiness,
and broker state.

## Workspace Flow

1. **Overview** summarizes total value, portfolio and account coverage, recent movement, news, and
   operational items that need attention.
2. **Portfolios** moves from aggregate allocation into a selected portfolio, then into holdings,
   performance, risk, fundamentals, and optimization previews.
3. **Asset detail** opens from a holding or research result and combines stored price history,
   normalized news, fundamentals, and deterministic Business Strength.
4. **Signals and Compare** turn stored factors into inspectable evidence and side-by-side research.
5. **News, retail sentiment, and benchmarks** add market context without replacing financial
   calculations or becoming standalone recommendations.
6. **Brokers** links read-only accounts, maps them to portfolios, previews imports, reconciles
   records, and exposes sync history.
7. **Operations** shows ingestion workers, provider state, projection readiness, ranking readiness,
   and bounded repair controls.
8. **Settings and page controls** save visual preferences, widget visibility, ordering, and layout
   locally in the browser.

## Route Map

| Workspace | Route | Primary purpose |
| --- | --- | --- |
| Overview | `/` | Portfolio value, account coverage, movers, news, and next actions |
| Portfolios | `/portfolios` | Aggregate allocation, portfolio list, and fundamentals |
| Portfolio detail | `/portfolios/{id}` | Overview, holdings, performance, risk, optimization, fundamentals, activity |
| Asset research | `/assets/{asset_id}` | Price chart, news, fundamentals, Business Strength |
| Signals | `/signals` and `/signals/{id}` | Ranked evidence, lifecycle, confidence, priority, and user state |
| Compare | `/compare` | Multi-asset price, valuation, growth, quality, and balance-sheet comparison |
| News | `/news` | Normalized, attributed, filterable financial news |
| Retail sentiment | `/retail-sentiment` | Held-stock and popular-name social attention snapshots |
| Benchmarks | `/benchmarks` and `/benchmarks/{id}` | Normalized comparison, leadership, composition, risk, and freshness |
| Brokers | `/brokers` | Read-only account linking, sync, mapping, import, and reconciliation |
| Operations | `/operations` | Worker controls, ingestion queue, provider health, and readiness |
| Settings | `/settings` | Theme, density, feature color, and overview defaults |

## Portfolio Operations

The portfolio workflow supports transaction-ledger positions, broker-projected positions,
aggregate and per-portfolio allocation, asset-class/sector/country/industry/currency exposure,
holding grades, actual time-weighted performance, risk and drawdown metrics, valuation rollups,
forward projections, deterministic simulation bands, and constrained optimization previews.

Optimization is deliberately preview-only. Broker connections are read-only. Missing or stale
inputs remain visible as missing or unavailable rather than being coerced to zero.

## Read Next

- [Web application and metric semantics](web-app.md)
- [Page customization](page-customization.md)
- [Shared interface conventions](shared-ui.md)
- [Feature index](../features/README.md)
- [Operations and data health](../operations/README.md)
