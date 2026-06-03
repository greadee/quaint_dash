# Investment Dashboard Project
Author: Connor Proulx

Terminal-based portfolio management dashboard built in Python. The system allows users to create and manage portfolios, track transactions, view actively held positions.

Project emphasizes seperation of concerns, function dependant layered structure, documentation through UML class diagrams, ADR's, development through CI-backed testing and phase planning.

I am building this project to help consolidate, and manage my own personal finances, as well as familiarize myself with software engineering practices as I am actively learning in CMPUT 301: Software Engineering at the University of Alberta (W2026).
<br>


## Setup 
Open up Command Prompt on Windows, or Terminal on Mac/Linux and:
#### Grab your own local copy:
```
git clone https://github.com/greadee/quaint-dash.git 
cd quaint-dash
```
#### Standalone Environment
```
python -m venv .venv
.venv\Scripts\activate
```
#### Build dependencies:
```
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```
#### (Dev) Linting and testing:
```
ruff check 
pytest
```
<br>


## Usage 

#### Run:
```
dashboard           # or python -m dashboard
```
#### Dashboard Commands: [Dashboard Commands](docs/usage/cmds/dashboard_cmds.md)
#### Portfolio Commands: [Portfolio Commands](docs/usage/cmds/portfolio_cmds.md)
#### Broker Commands: [Broker Commands](docs/usage/cmds/broker_cmds.md)
<br>

## Records 
### Phase 0: Project and CLI setup
    - Github Actions
    - basic CLI setup and smoke test

#### Architectural Decision Records: [Main Decisions](docs/adr/adr_ph0.md)
--- 
<br>

### Phase 1: Data Modelling and CLI refinement

    - DB schema, queries
    - Domain models and storage layer
    - Normalized and validated transaction import for csv and manual entry
    - Refactor CLI into robust Unix-style terminal.
    - CLI cmds for displaying Portfolio, Position, Transaction data. 
    - CLI Formatters for displaying CLI cmds

#### Architectural Decision Records: [Main Decisions](docs/adr/adr_ph1.md)
--- 
<br>

### Phase 2: Metric Ingestion

```
- Portfolio and watchlist ticker universe tables for ingestion scope
- Price-history ingestion for daily OHLCV, dividends, and splits through queued backfill jobs
- Corporate calendar and fundamentals ingestion for earnings events and financial statements
- Fundamentals subscriptions, recurring refreshes, and historical backfills
- Trading calendar ingestion for market-aware scheduling
- Live price ingestion with Finnhub regular-session streaming and FMP extended-hours polling
- Benchmark index ingestion for core, sector, industry, and theme benchmarks
- Unified ingestion job listing, scheduling, and processing commands
- Shared provider rate limiters, per-run call budgets, symbol caps, and failure recording
```

#### Architectural Decision Records: [Main Decisions](docs/adr/adr_ph2.md)
---
<br>

### Phase 3: Analytics

```
- Calculation-first analytics over existing portfolio, price, dividend, benchmark, and financial statement data
- Risk and return metrics including CAGR, volatility, Sharpe, Sortino, max drawdown, alpha, beta, correlation, and excess CAGR
- Intrinsic value models including dividend discount, discounted cash flow, margin of safety, expected CAGR, and implied priced-in growth
- Valuation depth from stored statement JSON, including growth, margin, leverage, profitability, payout, multiple, and DCF scenario metrics
- ETF analytics including expense ratio, distribution yield, tracking error, top holdings, exposures, and direct-holding overlap
- Forecast analytics including valuation mean reversion, dividend growth projection, blended expected CAGR, and deterministic simulation bands
- Portfolio analytics with weighted synthetic return series from current positions
- Portfolio valuation posture with weighted valuation multiples, margin of safety, dividend yield, expected CAGR, and holding-level return contributions
- Explicit missing-input reporting when dividends, fundamentals, benchmarks, or positions are unavailable
- Default benchmark selection from stored ETF profile, benchmark metadata, or asset/portfolio geography and currency
- Optional analytics snapshot storage for future AI-layer context, disabled by default
- Dashboard CLI commands for analytics reports, JSON output, storage status, storage toggle, and storage refresh
- Daily snapshot refresh behavior with same-day portfolio-change refreshes when storage is enabled
- AI-ready report context with structured facts, explanations, anomaly flags, and snapshot fact comparisons
- Stable analytics report payload schema: `phase3.analytics.v1`
```

#### Architectural Decision Records: [Main Decisions](docs/adr/adr_ph3.md)
---
<br>

### Phase 4: Broker Sync

```
- Read-only broker account linking through SnapTrade
- Hosted connection portal URLs; broker credentials are never collected by this app
- SnapTrade user registration with encrypted local user-secret storage
- Signed direct SnapTrade REST client for register, portal, connections, accounts, positions, and activities
- Provider-neutral broker sync domain models and repository tables
- Broker sync run tracking for account, position, and transaction refreshes
- Manual broker-account-to-portfolio mapping
- Idempotent import of mapped broker transactions into the local transaction ledger
- Broker-to-ledger provenance through broker_portfolio_txn_map
- Dashboard CLI commands for broker registration, portal creation, sync, account listing, mapping, and import
```

#### Architectural Decision Records: [Main Decisions](docs/adr/adr_ph4.md)
---
<br>

## Diagrams


### UML Class Diagrams:
<br>

App Architecture: 

![App Architecture](docs/classes/to-display/app_ph2.svg)
- [Phase 2 Ingestion Architecture](docs/classes/to-display/ingestion_ph2.svg)
- [Phase 1 Display Formatters](docs/classes/to-display/formatters_ph1.svg)

### Database E-R:
<br>

- [Phase 2 ER overview](docs/erd/to-display/erd_ph2.svg)
- [Core portfolio and ticker universe ER](docs/erd/to-display/erd_ph2_core.svg)
- [Ingestion and fundamentals ER](docs/erd/to-display/erd_ph2_ingestion.svg)
- [Live price and trading calendar ER](docs/erd/to-display/erd_ph2_live_calendar.svg)
- [Benchmark index ER](docs/erd/to-display/erd_ph2_benchmarks.svg)

## License: 
![License](https://img.shields.io/badge/license-MIT-blue.svg)



