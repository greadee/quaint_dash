# Shared Domain Model Strategy

Shared models are business concepts. They must not be raw database rows, raw
provider payloads, or React component props.

| Model | Owner | Required Fields | Invariants | Serialization | Current Duplication | Migration |
| --- | --- | --- | --- | --- | --- | --- |
| `AssetId` | Asset Research | normalized symbol, exchange/region optional, internal id optional | One canonical identity per tradable/security. | string plus metadata object | Symbol/ticker/security terms vary. | Introduce in contracts first, map legacy fields. |
| `PortfolioId` | Portfolio | id, owner scope | Must not expose another user's portfolio. | string/int wrapper | Route params and DB ids used directly. | Wrap in use-case inputs. |
| `Position` | Holdings | asset id, quantity, cost basis optional, account optional | Quantity and asset id required; cost basis may be unavailable. | object | Holding/position names mixed. | Normalize in holdings contract. |
| `Transaction` | Transactions | id, portfolio/account, asset, type, quantity, amount, date | Signed quantity/amount rules by type. | object | Broker and local transaction shapes differ. | Anti-corruption adapter per broker. |
| `Money` | Shared Kernel | amount, currency | Currency required; no implicit conversion. | decimal string or number plus currency | Values often numeric without structured currency. | Add to contracts, keep display formatters separate. |
| `PricePoint` | Market Prices | asset id, timestamp/date, close, currency, adjustment | Timestamp and currency required. | object list | Quote/price naming mixed. | Market-data contract. |
| `DateRange` | Shared Kernel | start, end, inclusivity | start <= end. | ISO date strings | Route params and helpers. | Shared request model. |
| `ReturnSeries` | Performance Analytics | asset/portfolio id, points, calculation version | Ordered, comparable interval. | object list | Chart-ready arrays in API/UI. | Domain model plus chart adapter. |
| `MetricValue` | Shared Kernel | name, value, unit, period optional, provenance, freshness | Unknown values are explicit null/missing states, not zero. | object | API/UI metric rows vary. | Common metric contract. |
| `DataProvenance` | Shared Kernel | provider, dataset, retrieved_at, calculation_version optional | Provider/source attribution required for derived finance data. | object | Present in some APIs/statuses only. | Add to outputs by milestone. |
| `DataFreshness` | Shared Kernel | market_timestamp, calculated_at, state, stale_reason optional | Structured state, not display text. | object | Multiple ad hoc freshness fields. | Standardize in contracts. |
| `Benchmark` | Benchmarking | benchmark id, label, asset/proxy ids, universe/association | Stable id independent from display label. | object | Benchmark assets/proxies mixed. | Benchmarking contract. |
| `NewsItem` | News | id/url, title, source, published_at, symbols, sentiment optional | Source and timestamp required. | object | News feed/asset feed shapes overlap. | News contract. |
| `SimulationRequest` | Simulations | portfolio/asset refs, horizon, assumptions, seed optional | Assumptions explicit and auditable. | object | Forecast inputs are route/API-specific. | Introduce before desktop work. |
| `SimulationResult` | Simulations | scenarios, percentiles, assumptions, calculation version | Result references input request. | object | Future-heavy analytics. | Milestone E. |
| `AIInsight` | AI Insights | text, type, subject ids, evidence, model id, generated_at | Evidence refs required for investment commentary. | object | Experimental only. | Milestone F. |
| `WidgetId` | Widget Configuration | page id, widget key, platform support | Stable across route refactors. | string | Feature ids/page feature keys exist in web store. | Preserve keys, document ownership. |

## Transformation Rules

- Persistence row to domain model: infrastructure repository responsibility.
- Domain model to API DTO: API adapter responsibility.
- API DTO to web view model: web feature/presentation responsibility.
- Domain model to AI prompt input: AI orchestration responsibility with explicit
  evidence references.

