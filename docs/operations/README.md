# Operations And Data Health

The Operations workspace is the control plane for local data. It exposes bounded worker controls
and readiness state without hiding provider failures or manufacturing missing values.

## What Operations Covers

- routine ingestion scheduling and queue processing;
- current-price refresh for tracked holdings;
- valuation and projection readiness;
- stock-ranking readiness and refresh controls;
- retail-sentiment provider status and queued work;
- provider health, retry state, dead-letter history, and explicit limitations.

Worker cards distinguish the pending count recorded after their last cycle from the current
pending queue. Full queue counts and oldest backlog age are refreshed from the read-only queue
status endpoint every 30 seconds, independently of whether a worker is enabled. Current failures
and the latest historical failure remain distinct; successful work in one phase cannot erase
another phase's error.

The app defaults provider-heavy background work to off unless environment settings enable it.
Manual actions are bounded by job, asset, date-range, and provider-call limits.

## Operational Guides

- [Runtime diagnostics and recovery](runtime-recovery.md)
- [Web runtime and full data-health workflow](../product/web-app.md#full-data-health-workflow)
- [Environment and worker configuration](../development/environment.md)
- [Testing and live verification](../development/testing.md)
- [Data safety and sensitive information](data-safety.md)
- [News provider operations](../features/news.md#operations)
- [Retail sentiment ingestion](../features/retail-sentiment.md)

DuckDB, normalized ingestion tables, and the API payloads are authoritative. A stale worker card or
cached page should be checked against the corresponding API response before data is changed.
