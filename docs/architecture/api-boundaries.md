# API Boundary Strategy

The target API is capability-oriented. It should avoid one endpoint per widget
and avoid page-sized payloads that cannot serve mobile or AI consumers.

## Current API Categories

| Category | Current State | Target Treatment |
| --- | --- | --- |
| Health/status | `/health`, Operations/status endpoints | Keep, add structured contracts and admin/read separation. |
| Portfolio | Portfolio summary/detail endpoints | Keep compatibility, introduce `GetPortfolioSummary` facade. |
| Assets | Asset overview/search/detail endpoints | Keep compatibility, split identity, prices, fundamentals only when contracts are stable. |
| Compare | Compare workspace endpoints | Keep, move orchestration behind Comparisons application service. |
| News | News terminal/ticker endpoints | Keep, normalize NewsItem and pagination contracts. |
| Brokers | Broker profile/import/sync endpoints | Keep web/admin, separate transaction command contracts. |
| Ingestion/jobs | Operations and worker controls | Keep admin-only, route through Operations/Data Quality application commands. |
| Signals/rankings | Signal and readiness endpoints | Keep, align with Performance/Risk/Sentiment owners. |

## Proposed Application Queries And Commands

| Name | Consumers | Request | Response | Freshness | Notes |
| --- | --- | --- | --- | --- | --- |
| `GET /api/v2/portfolios/{id}/summary` | web, mobile, desktop, AI | date range, benchmark optional | `PortfolioSummary` | required | Can coexist with current routes. |
| `GET /api/v2/assets/{id}/overview` | web, mobile, desktop, AI | metric sets, compact flag | `AssetOverview` | required | Avoid giant page payload by optional sections. |
| `GET /api/v2/assets/{id}/prices` | charts, analytics | range, interval, adjusted flag | `PricePoint[]` | required | Supports mobile compact charts. |
| `GET /api/v2/assets/{id}/fundamentals` | asset/compare/AI | metric set, period | `MetricValue[]` | required | No provider raw fields. |
| `GET /api/v2/news` | news/asset/mobile/AI | symbols, range, filters, page | `NewsItemPage` | required | Pagination mandatory. |
| `POST /api/v2/comparisons` | web/desktop | subjects, metric sets | `ComparisonResult` | required | Desktop may request larger payload. |
| `GET /api/v2/operations/status` | web/admin | sections optional | `OperationsStatus` | required | Read-only status can be separate from commands. |
| `POST /api/v2/operations/jobs` | web/admin/worker | job command, idempotency key | accepted/result | required | Operator authorization. |
| `POST /api/v2/ai/insights/ticker` | AI service/web/desktop | subject and evidence refs | `AIInsight` | required | Future only, consent needed. |

## Current APIs Needing Attention

- Page-shaped asset and portfolio payloads should remain for compatibility, then
  be backed by capability facades.
- Provider-specific fields must stay internal or be wrapped in provenance.
- Operations write endpoints need explicit idempotency and authorization docs as
  they mature.
- Mobile payloads should avoid large compare/news/history responses by default.
- AI consumers need evidence references, not display-ready prose alone.

