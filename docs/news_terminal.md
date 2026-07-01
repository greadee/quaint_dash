# Financial News Terminal

## Architecture

The news terminal uses a provider-neutral pipeline:

1. Provider adapters return `ProviderNewsArticle` records.
2. `normalize_provider_article` validates IDs, headlines, timestamps, URLs, language, sentiment, hashes, and raw payloads.
3. `NewsRepository` upserts normalized articles idempotently into DuckDB.
4. `EntityResolver` maps provider symbols and company aliases to internal assets with confidence and match method.
5. Deterministic classification assigns the controlled `news_category` taxonomy.
6. Story clustering groups same-event coverage by category, headline fingerprint, and resolved entities.
7. Ranking is computed in the service layer from importance, asset confidence, and portfolio exposure.
8. `NewsApiService` powers global, asset, portfolio, search, state, provider-health, and alert-rule APIs.
9. The React news terminal and asset/portfolio widgets render only normalized API responses.

The current bundled provider is `mock_news`, a deterministic fixture provider for development and tests. Live provider adapters should implement `NewsProvider` and be registered in the operational script or scheduler once credentials and licensing are available.

## Schema

The `financial_news.sql` migration adds:

- `news_provider`
- `news_article` normalized extensions
- `asset_entity_alias`
- `news_article_asset`
- `news_article_entity`
- `news_category`
- `news_article_category`
- `news_story_cluster`
- `news_story_cluster_article`
- `news_ingestion_state`
- `news_user_article_state`
- `news_alert_rule`
- `news_alert_rule_asset`
- `news_alert_rule_portfolio`
- `news_alert_delivery`

Raw provider payloads are retained in `news_article.raw_payload_json` for debugging and reprocessing. UI and API reads must not query raw payloads directly.

## Entity Resolution

Resolution is intentionally conservative:

- Provider-supplied symbols are preferred.
- Exchange-qualified and direct asset-symbol matches receive high confidence.
- `asset_entity_alias` supports company names, CDR/ADR aliases, and cross-listing aliases.
- Ticker-only fallback is blocked for common collision symbols including `AI`, `A`, `C`, `F`, `IT`, `ON`, `NOW`, `ALL`, `CAT`, and `FOR` unless provider symbols or aliases corroborate the match.

Each match stores `relevance_score`, `confidence_score`, `match_method`, `mention_type`, `is_primary_entity`, and `provider_assigned`.

## Classification And Ranking

The initial taxonomy is deterministic and includes earnings, guidance, analyst actions, M&A, regulatory, litigation, management changes, capital actions, macro, central bank, commodity, crypto, press releases, and general news.

Importance scoring combines provider importance, breaking status, category weight, sentiment severity, press-release penalty, correction/retraction penalty, and headline keywords. Portfolio ranking multiplies article importance by resolved-asset confidence and a bounded position-weight component so small holdings and repetitive press releases do not dominate the feed.

## API Endpoints

- `GET /api/v1/news`
- `GET /api/v1/news/latest`
- `GET /api/v1/news/breaking`
- `GET /api/v1/news/search`
- `GET /api/v1/news/articles/{article_id}`
- `POST /api/v1/news/articles/{article_id}/read`
- `POST /api/v1/news/articles/{article_id}/save`
- `DELETE /api/v1/news/articles/{article_id}/save`
- `GET /api/v1/news/providers`
- `GET /api/v1/news/health`
- `GET /api/v1/news/categories`
- `GET /api/v1/news/alerts`
- `POST /api/v1/news/alerts`
- `PATCH /api/v1/news/alerts/{alert_rule_id}`
- `DELETE /api/v1/news/alerts/{alert_rule_id}`
- `GET /api/v1/assets/{asset_id}/news`
- `GET /api/v1/portfolios/{portfolio_id}/news`

Responses include provider attribution, UTC timestamps, category mappings, asset mappings, cluster metadata, ranking score, and read/saved state.

## Operations

Credential-free local commands:

```powershell
.\.venv\Scripts\python.exe tools\news_ops.py refresh mock_news --limit 100
.\.venv\Scripts\python.exe tools\news_ops.py backfill-run mock_news --days 7 --limit 500
.\.venv\Scripts\python.exe tools\news_ops.py health
```

The script defaults to `data/persistent_db.db`; pass `--db` to target another DuckDB file.

## Configuration

Planned provider configuration keys:

- `NEWS_<PROVIDER>_ENABLED`
- `NEWS_<PROVIDER>_API_KEY`
- `NEWS_POLL_INTERVAL_SECONDS`
- `NEWS_MARKET_HOURS_INTERVAL_SECONDS`
- `NEWS_OFF_HOURS_INTERVAL_SECONDS`
- `NEWS_REQUEST_TIMEOUT_SECONDS`
- `NEWS_RETRY_COUNT`
- `NEWS_BATCH_SIZE`
- `NEWS_BACKFILL_DAYS`
- `NEWS_RAW_PAYLOAD_RETENTION_DAYS`
- `NEWS_MIN_RELEVANCE_SCORE`
- `NEWS_MIN_ALERT_IMPORTANCE`
- `NEWS_DEDUP_THRESHOLD`
- `NEWS_CLUSTER_THRESHOLD`
- `NEWS_DEFAULT_FEED_DENSITY`

No provider keys are required for `mock_news`.

## Licensing

The platform stores article metadata, summaries, URLs, provider attribution, and raw payloads when provider terms allow it. Full article bodies must only be stored when the provider license explicitly permits storage and display. The frontend links to original sources instead of scraping or reproducing copyrighted article bodies.

## Testing

Run the focused backend and frontend news tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\news\test_news_foundation.py tests\api\test_news_api.py
cd web
npm.cmd test -- --run src/routes/newsRoute.test.tsx src/App.test.tsx src/routes/assetRoute.test.tsx src/routes/portfolioRoute.test.tsx
npm.cmd run build
```
