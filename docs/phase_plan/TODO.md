# Investment Dashboard To-Do List

## Phase 2 - Metric Ingestion
Design Decisions: [ADR's](../adr/adr_ph2.md)
- Leave (Non-Core) index snapshot ingestion for later in the phase:
    - Need to figure out how index snapshots will be used in the dashboard before we can say whether or not it will fit the rate cap of our current data providers in free tier.

- Leave ingestion for watchlist tickers until later in the phase:
    - Websocket data is not a concern.
    - Need to figure out whether or not historical data ingestion should be automatic if we can expect that watchlist items are frequently added and removed.
   - WatchlistView and WatchlistManager
### Tasks: 
- Initialize asset tables on transaction import 
- Ingest metadata sync upon watchlist, portfolio add (FMP)
    - Scheduler
- Ingest biweekly earnings calendar update (FMP)
    - Scheduler
- Ingest core index composition 3x intraday (FMP)
    - Scheduler
- Ingest ticker earnings data sync on calendar event finished (FMP)
    - Scheduler
- Ingest ticker historical backfill up to 10 years (Finnhub)
    - Scheduler
- Stream ticker data (price, vol, mkt cap) for positions (Finnhub)
    - Open stream on dash open and is market day
- Rate limiter and failsafes
- Replace Mon-Fri market calendar to handle holidays and half-days
- TBD: non-core index ingestion
- TBD: items in watchlist ingestion

