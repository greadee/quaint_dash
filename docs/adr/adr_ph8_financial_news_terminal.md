# ADR Ph8: Provider-Neutral Financial News Terminal

## Status

Accepted.

## Context

Quaint Dash needs financial news that can power a global terminal, asset feeds, portfolio feeds, watchlist feeds, alerts, search, clustering, and future AI summaries. Provider APIs differ in identifiers, categories, sentiment, article-body rights, pagination, and historical depth, so coupling UI or storage to one vendor would make later providers expensive to add.

## Decision

Implement a provider-neutral financial-news domain:

- Provider adapters implement `NewsProvider` and return `ProviderNewsArticle`.
- The domain stores normalized articles, provider attribution, raw payloads, asset links, categories, story clusters, ingestion state, user state, and alert rules.
- Entity resolution stores confidence and match method, and blocks ambiguous ticker-only matches unless corroborated.
- Classification, clustering, and ranking run in backend services, not React.
- Search uses bounded DuckDB text filtering first, with the service interface left open for a later dedicated search backend.
- The bundled development provider is deterministic `mock_news`; live adapters require explicit credentials and licensing review before registration.
- Full article bodies remain optional and must not be stored or displayed unless provider terms permit it.

## Consequences

The first production path is fully testable without network access and does not leak provider-specific payloads into the API. Adding live providers now requires an adapter, environment configuration, rate limiting, and provider-specific terms documentation, but no schema or frontend redesign.

Portfolio news ranking is auditable because it is computed in the service layer from article importance, asset confidence, and bounded position exposure. Future LLM summaries, portfolio impact explanations, and event extraction can attach to the normalized article, entity, category, and cluster records.

## Deferred

- Live paid provider adapters.
- WebSocket or SSE news streaming.
- Provider-specific correction webhooks.
- Dedicated full-text search service.
- Entity-level sentiment history.
- Email, push, SMS, Slack, Discord, and webhook alert delivery.
