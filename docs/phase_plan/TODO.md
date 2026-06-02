# Investment Dashboard To-Do List

## Phase 3 - Analytics
Design Decisions: [ADR's](../adr/adr_ph3.md)

### Completed:
- Calculation-first analytics module over stored data
    - Risk and return metrics
    - Relative benchmark metrics
    - Dividend discount model
    - Discounted cash flow model
    - Implied priced-in growth
    - Valuation depth metrics from stored statement JSON
    - ETF expense, distribution, tracking-error, exposure, holding, and overlap analytics
    - Forecast metrics with blended expected CAGR and simulation bands
    - AI-ready facts, explanations, anomaly flags, and snapshot comparisons
    - Portfolio weighted return series
- Data coverage and missing-input reporting
- Optional analytics snapshot storage
    - Disabled by default
    - Stores compact metric columns and JSON payloads when enabled
    - Refreshes daily
    - Refreshes same-day portfolio snapshots when portfolio state changes

### Tasks:
- Add CLI/dashboard commands for analytics reports
- Add user-facing configuration for enabling analytics storage
- Add migration/schema docs for analytics snapshot tables once the storage surface is promoted beyond service-level opt-in
- Add benchmark default selection per portfolio or asset geography

## Phase 2 - Metric Ingestion
Design Decisions: [ADR's](../adr/adr_ph2.md)
- Leave (Non-Core) index snapshot ingestion for later in the phase:
    - Need to figure out how index snapshots will be used in the dashboard before we can say whether or not it will fit the rate cap of our current data providers in free tier.

- Leave ingestion for watchlist tickers until later in the phase:
    - Websocket data is not a concern.
    - Need to figure out whether or not historical data ingestion should be automatic if we can expect that watchlist items are frequently added and removed.
   - WatchlistView and WatchlistManager

### Completed:
- Ingest metadata sync upon portfolio add (FMP)
    - CLI test cmd
    - Scheduler
- Ingest historical price history backfill (yfinance)
    - CLI test cmd
    - Scheduler
- Trading day calendar ingestion
- Corporate calendar ingestion
- Core index ingestion
    - non-core index ingestion
- Ingest ticker earnings data sync on calendar event finished (FMP)
    - Scheduler
- Stream ticker data (price, vol, mkt cap) for positions (Finnhub)
    - Open stream on dash open and is market day
- Ingestion of forward looking fundamentals


### Tasks: 
- Historical backfill for fundamentals
- Rate limiter and failsafes

