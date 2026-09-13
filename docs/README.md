# Quaint Dash Documentation

The documentation is arranged from product behavior to implementation detail. Start with the
application flow, follow a feature into its domain guide, and open architecture or reference
material only when you need the deeper contract.

## 1. Understand The Product

- [Product and application flow](product/README.md): what each workspace does and how the screens
  connect.
- [Web application guide](product/web-app.md): local runtime, routes, API ownership, and metric
  semantics.
- [Page customization](product/page-customization.md): configurable tabs, widgets, and saved
  layouts.
- [Shared interface conventions](product/shared-ui.md): reusable loading, error, table, and
  formatting behavior.

## 2. Explore Feature Behavior

- [Feature index](features/README.md): current user-facing features and deterministic backend
  foundations.
- [Business Strength](features/business-strength.md)
- [Financial news](features/news.md)
- [Retail sentiment](features/retail-sentiment.md)
- [Investor profile](features/investor-profile.md)
- [Outside-holding candidate engine](features/candidate-engine.md)

## 3. Run And Maintain The App

- [Operations index](operations/README.md): readiness, ingestion, provider limits, and data safety.
- [Data safety](operations/data-safety.md)
- [Development index](development/README.md): setup, onboarding, tests, and contributor workflow.
- [CLI reference](reference/README.md)

## 4. Go Deeper

- [Architecture index](architecture/README.md): current system first, then boundaries, data, and
  future migration material.
- [Current architecture overview](architecture/overview.md)
- [Codebase map](architecture/codebase-map.md)
- [Current schema](architecture/database/current_schema.md)
- [Architecture decisions](architecture/decisions/index.md)
- [Historical reports and generated diagrams](archive/README.md)

The repository [README](../README.md) is the product-facing introduction and quick-start guide.
This index is the complete documentation map.
