# Quaint Dash

Quaint Dash is a local-first investment intelligence workspace for managing portfolios, validating
the data behind them, and researching the assets that drive their results. It combines a React
application with a FastAPI service and DuckDB so portfolio records, analytics, market data, and
operational state remain inspectable on the user's machine.

The project is built around one constraint: the interface may explain and visualize financial
facts, but it does not invent them. Returns, risk, valuation, rankings, readiness, and portfolio
weights come from stored data and deterministic Python services, with missing inputs reported
explicitly.

## Application Workflow

| Workspace | What it supports |
| --- | --- |
| **Overview** | Total market value, portfolio and broker coverage, movers, recent news, and actions that need attention |
| **Portfolios** | Aggregate allocation, individual portfolio analysis, holdings, activity, exposures, performance, risk, fundamentals, and optimization previews |
| **Asset Research** | Price history, holding context, activity, news, fundamentals, valuation analytics, and Business Strength evidence |
| **Signals** | Ranked factor evidence with separate strength, confidence, portfolio priority, lifecycle, and user-review state |
| **Compare** | Side-by-side price, growth, valuation, quality, profitability, and balance-sheet evidence |
| **Benchmarks** | Core, sector, industry, and theme index performance, composition, exposures, relative metrics, and freshness |
| **News and Sentiment** | Normalized financial news plus held-stock and popular-name retail-attention snapshots |
| **Brokers** | Read-only account linking, portfolio mapping, import previews, reconciliation, synchronization, and sync history |
| **Operations** | Ingestion queues, worker controls, provider state, retry history, and valuation, projection, and ranking readiness |

## Portfolio Operations And Analytics

Quaint Dash treats transactions as the durable portfolio ledger. Positions are derived from that
ledger or projected from mapped broker accounts, which keeps manual records, imports, and
reconciliation traceable.

The portfolio workspace includes:

- aggregate and per-portfolio market value, allocation, and holdings;
- asset-class, sector, country, industry, and currency exposure views;
- transaction activity and broker-to-ledger provenance;
- transaction-aware time-weighted performance and money-weighted investor return;
- CAGR, volatility, Sharpe, Sortino, drawdown, alpha, beta, correlation, and excess-return metrics;
- valuation rollups, including multiples, margin of safety, dividend yield, expected CAGR, and
  holding-level contribution;
- DCF and dividend-discount evidence, implied growth, quality, profitability, leverage, and
  statement-derived fundamentals;
- deterministic forward projections and simulation bands;
- constrained target-allocation previews that never create a trade or overwrite a position; and
- holding grades and Business Strength scorecards with methodology, evidence, freshness, and
  missing-input detail.

Unavailable or stale inputs stay visible as unavailable or stale. They are not silently displayed
as zero, and hypothetical current-weight backtests remain separate from actual ledger performance.

## Research And Monitoring

Asset pages connect portfolio context to stored price history, fundamentals, news, and auditable
Business Strength scoring. Compare and benchmark workspaces make relative evidence inspectable
without turning a factor score into a recommendation.

Signals distinguish magnitude from confidence and portfolio relevance. News is normalized,
attributed, classified, and filterable. Retail sentiment is an optional research input with
provider health and freshness surfaced through Operations. Deterministic investor-profile and
outside-holding candidate components exist as internal backend foundations; they do not expose a
recommendation, suitability, LLM, or trading workflow.

## Data And Operations

Market history, corporate calendars, fundamentals, live prices, benchmark data, financial news,
and social sentiment use provider-neutral ingestion services backed by persisted jobs. Work is
bounded by symbol caps, date ranges, rate limits, retry rules, and per-run call budgets.

Background workers are safe-off by default. The Operations workspace can start or tick bounded
workers, inspect pending/running/failed jobs, retry failures, and verify whether portfolios have
the data required for valuation, projections, risk, and rankings. Provider entitlement failures
remain explicit and sensitive values are redacted before errors are persisted.

Broker support is read-only. Quaint Dash uses SnapTrade's connection portal, stores encrypted local
user secrets, and requires explicit account-to-portfolio mapping before transactions can be
imported into the local ledger.

## Engineering Approach

- **Backend-owned truth:** Python services calculate financial metrics; React formats API DTOs.
- **Local-first storage:** DuckDB stores portfolio, provider, analytics, broker, and operational
  evidence.
- **Versioned API:** FastAPI exposes the same application services to the browser and future
  clients.
- **Deterministic core:** scoring, rules, eligibility, and calculations do not depend on an LLM.
- **Explicit provenance:** source, freshness, missing-input, and failure context travel with the
  data where the domain supports them.
- **Read-only financial connections:** no trade execution or automatic target-weight application.
- **Verification:** Ruff, pytest, ESLint, TypeScript, Vitest, Vite builds, API health checks, and
  full data-health scans cover the backend and browser workflows.

## Technology

- Python, FastAPI, Pydantic, DuckDB, pandas, NumPy, SciPy, and Uvicorn
- React, TypeScript, Vite, React Query, Recharts, Vitest, and Playwright
- Provider adapters for Yahoo Finance, Financial Modeling Prep, Finnhub, Reddit, X, SnapTrade, and
  financial-news sources, enabled only when configured

## Quick Start

The repository includes Windows-friendly workflow commands:

```cmd
git clone https://github.com/greadee/quaint_dash.git
cd quaint_dash
scripts\qd.cmd setup
scripts\qd.cmd launch
```

For a manual setup:

```cmd
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip==26.2.1
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
cd web
npm.cmd ci
```

Copy `.env.example` to `.env` only when provider or broker integrations are needed. Local databases,
credentials, logs, raw provider payloads, and broker exports must remain outside Git.

## Current Boundaries

Quaint Dash is currently a single-user localhost application. DuckDB remains the application
database, dated FX ingestion is not yet complete, background work requires explicit configuration,
and authentication, hosted deployment, native clients, LLM features, and trading are deferred.

## Documentation

Start with the [documentation index](docs/README.md), which opens progressively from product
behavior into feature, operations, development, and architecture detail.

- [Product and application flow](docs/product/README.md)
- [Web application and metric semantics](docs/product/web-app.md)
- [Feature index](docs/features/README.md)
- [Operations and data health](docs/operations/README.md)
- [Contributor onboarding](docs/development/onboarding.md)
- [Testing and verification](docs/development/testing.md)
- [Architecture index](docs/architecture/README.md)
- [Current database schema](docs/architecture/database/current_schema.md)
- [CLI reference](docs/reference/README.md)
- [Architecture decisions](docs/architecture/decisions/index.md)
- [Historical reports and diagrams](docs/archive/README.md)

## Project Context

Quaint Dash is developed by Connor Proulx as a practical portfolio-management tool and an ongoing
software-engineering project. It demonstrates full-stack product development, financial-domain
modeling, provider integration, data provenance, deterministic analytics, operational tooling,
architecture documentation, and CI-backed testing.

## License

MIT
