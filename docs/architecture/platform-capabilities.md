# Platform Capability Matrix

Platform plans are based on Phase 1 feature inventory and current code. They are
not implementation commitments for apps that do not exist yet.

| Capability | Shared Core | Web | Desktop | Mobile | Server/Worker/AI | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Portfolio overview | Yes | Full | Full | Compact | API/server | Mobile shows summary cards and essential charts. |
| Holdings/exposure | Yes | Full | Full | Compact | API/server | Detailed drilldowns web/desktop first. |
| Transaction import | Partial | Full | Full | Read-only/none | Server | Write workflow stays server-authorized. |
| Broker sync | Partial | Full admin | Full admin | Not planned | Server/worker | Sensitive provider/account data. |
| Asset identity | Yes | Full | Full | Full | API/server | Good early shared capability. |
| Price checks | Yes | Full | Full | Full | API/server | Mobile preferred for quick checks. |
| Historical charts | Yes data, platform charting | Full | Full/advanced | Simple | API/server | Chart UI is platform-specific. |
| Fundamentals | Yes | Full | Full | Essential | API/server | Mobile compact metric set. |
| Valuation | Yes | Full | Full | Essential | API/server | Shared deterministic calculations. |
| Business-strength scoring | Yes | Full | Full | Compact | API/server | Evidence/audit needed on all platforms. |
| News terminal | Yes | Full | Full | Summary feed | API/server | Desktop/web can support advanced filtering. |
| Sentiment | Yes | Full | Full | Summary | API/server | Provider coverage and confidence required. |
| Compare workspace | Yes | Full | Preferred | Limited | API/server | Desktop preferred for large grids/workspaces. |
| Benchmarking | Yes | Full | Full | Limited | API/server | Compact benchmark deltas on mobile. |
| Risk analytics | Yes | Full | Preferred | Summary | API/server | Heavy analytics desktop preferred. |
| Monte Carlo/simulations | Yes | Preview | Preferred | Not planned/summary | Server/desktop | Long-running compute requires job/result model. |
| Operations/admin | Partial | Full | Admin optional | Not planned | Server/worker | Write controls web/admin only. |
| Widget configuration | Yes config | Full | Full | Limited | API/local cache | Platform capability filters required. |
| Alerts/watchlists | Yes | Full | Full | Preferred | Server/notification | Alerts are future until rules exist. |
| AI summaries | AI contract shared | Display | Preferred | Short display | AI service/worker | Requires consent/evidence boundary. |

## Consumption Modes

- Web consumes shared capabilities through HTTP API and browser-local UI state.
- Desktop may consume HTTP API, local service adapters, and future local compute
  for heavy simulations and exports.
- Mobile consumes compact HTTP/read-model payloads and notification payloads.
- Workers consume application commands and infrastructure repositories.
- AI consumes deterministic application queries and evidence references.

