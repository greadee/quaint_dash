# Naming Conventions

Do not rename broad code in Phase 1.5. Use this standard for new boundaries and
future migrations.

## Canonical Terms

| Current Terms | Canonical Future Term | Meaning |
| --- | --- | --- |
| asset, ticker, security | Asset | Tradable or investable subject identified by symbol/exchange/internal id. |
| quote, price | Price | Market value at a timestamp; quote is latest price payload. |
| holding, position | Position | Portfolio-owned quantity of an asset; holding may be UI label. |
| portfolio performance, return analytics | Performance Analytics | Deterministic return and drawdown calculations. |
| metric, ratio | MetricValue | Named numeric or qualitative value with unit, period, provenance. |
| provider, source | Provider | External integration; source is article/data origin when displayed. |
| insight, analysis | Insight | Generated or derived explanatory output; deterministic analytics remain metrics. |
| feature, widget | Feature and Widget | Feature is capability; widget is presentation unit. |

## Naming Rules

- Use cases: verb-object, such as `GetAssetOverview` or `CalculatePortfolioRisk`.
- Commands: imperative write intent, such as `RunIngestionJob`.
- Queries: read intent, such as `GetTickerNews`.
- Repositories: entity plus `Repository`, such as `PriceRepository`.
- Provider adapters: provider plus capability, such as `FmpFundamentalsProvider`.
- DTOs/contracts: capability plus `Request` or `Response` where transport-specific.
- Domain entities: noun, such as `Portfolio`, `Position`, `Benchmark`.
- Value objects: noun phrase, such as `Money`, `DateRange`, `DataFreshness`.
- Widgets: page/capability key, such as `portfolio.performance.cagrCard`.
- Feature IDs: stable uppercase domain prefix plus number, preserving Phase 1 ids.
- Tests: mirror module and behavior, such as `test_calculate_business_strength_handles_missing_inputs`.

