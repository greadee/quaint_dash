# Phase 2 - Metric Ingestion

## ADR-012: Choice of Data Provider(s)

**Decision:** Use Finnhub for semi-real time ticker data and news, and FMP for ticker metadata, earnings, historical data, etc.

**Context:** Need to stay within API rate limits of free versions whilst supplying the most accurate information to the dashboard.

**Rationale:** 
- Finnhub supports websocket streaming 
- The data coming from Finnhub, and from FMP need to be scheduled differently
- Need to keep it to free tiers

## ADR-013: Finnhub: Websocket vs REST API

**Decision:** Implement ticker quotes from Finnhub through websocket streaming to for portfolio symbols only, watchlist symbols require us to evaluate the rate limit with portfolio.

**Context:** API: ~60 calls/min, Websocket: ~50 symbols subscribed; 10 less tickers tracked for streamed data is a worthy tradeoff.

**Rationale:** 
- Managing 50+ tickers concurrently is more in line with institutional portfolio management, and not retail use by one single user.
- Websocket streaming will be better for the semi-real time data, and news updates.
- Do not have to worry about exceeding call rate cap
- May have issues scaling the portfolio/watchlist within the free tier, but that would also be a problem for API calls.

## ADR-014: Ingestion Polling Rates

**Decision:** 
- Earnings calendar refreshed bi-weekly
- Daily close data pulled once per market day after close 
- (Core) index composition refreshed after open, lunch and close

**Context:** What data do we need, does it need to be updated regularly, and when?

**Rationale:**
- Need to keep an updated earnings calendar, (forward 14 days)
- Ingest closing data on days the market is open, instead of deriving closing data; to append to the collection of historical data daily
- Ingest only the main indicies (S&P 500, NAS 100, TSX 60, RUS 2000) intraday, less general indices can be queried

## ADR-015: Ingestion Scheduling Rates

**Decision:** Poll for bi-weekly earnings calendar/data on weekends or off-days to prevent exceeding the usage limits, poll for daily close data on tickers and indices a few minutes after close.

**Context:** We may exceed FMP's usage limits if we need to ingest earnings calendar/data, and also ingest daily close data on that day. 

**Rationale:** 
- The forward 14 day window on the earnings data ensures we are always up to date, as the earnings calendar is pretty concrete.
- Wait a few minutes after close in order to allow FMP to process the daily close data correctly.

## ADR-016: Market Hours Behaviour

**Decision:** 
- Schedule based off of ET time zone
- Convert back to local timezone for display
- Market calendar for determining open and closed days

**Context:** Job scheduling needs a clear definition of the time for market open, lunch and market close.

**Rationale:**
- Daily close data is only meaningful after the data provider has finalized the day's data
- Move as many API calls to after hours to preserve bandwitch for intraday
- Allows for timezone interchangeability for other dashboard users
- Start with a basic Mon-Fri open schedule, and adjust to a more accurate calendar source for handling of holidays and half-days

