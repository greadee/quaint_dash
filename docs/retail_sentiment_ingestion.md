# Retail Sentiment Ingestion

Retail sentiment uses the existing sentiment ingestion pipeline:

1. Provider adapters fetch social posts.
2. Posts are normalized into `SocialPostInput`.
3. `SentimentIngestionRepository` upserts `social_post` rows and asset mentions.
4. `RulesBasedSentimentScorer` writes deterministic `sentiment_observation` rows.
5. `DailySentimentAggregator` writes `ticker_sentiment_daily` retail scores.
6. Ranking, factor cards, and readiness checks read stored backend data only.

In plain terms: the app reads social posts, matches them to ticker symbols, scores the tone, and stores a daily ticker-level snapshot. The web app then shows that snapshot as a social attention signal. It does not turn Reddit or X chatter into a standalone investment recommendation.

## Providers

The bundled live social providers are:

- `reddit`: OAuth client-credentials search against configured subreddits.
- `x`: X API recent search using cashtag-first queries.

Both providers are optional. If credentials are missing, provider jobs fail with a clear error instead of fabricating observations.

## Configuration

Set these values in a local `.env` file when live ingestion is intended:

```powershell
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=quaint_dash:v1.0.0 (by /u/your-user)
REDDIT_SUBREDDITS=stocks,investing,wallstreetbets,SecurityAnalysis
REDDIT_POST_LIMIT=25
REDDIT_REQUEST_TIMEOUT_SECONDS=10

X_BEARER_TOKEN=
X_POST_LIMIT=25
X_REQUEST_TIMEOUT_SECONDS=10
X_INCLUDE_PLAIN_TICKER=false
```

`X_INCLUDE_PLAIN_TICKER=false` is the conservative default. Cashtags avoid many ticker-word collisions; plain ticker search can be enabled later for curated universes.

## Commands

Queue provider jobs for all tracked assets:

```powershell
.\.venv\Scripts\python.exe -m dashboard sentiment-refresh all --source reddit
.\.venv\Scripts\python.exe -m dashboard sentiment-refresh all --source x
.\.venv\Scripts\python.exe -m dashboard sentiment-run --max-jobs 10
```

Refresh one ticker immediately:

```powershell
.\.venv\Scripts\python.exe -m dashboard sentiment-refresh AMD --source reddit
.\.venv\Scripts\python.exe -m dashboard sentiment-refresh AMD --source x
```

Review stored output:

```powershell
.\.venv\Scripts\python.exe -m dashboard social-list AMD --limit 10
.\.venv\Scripts\python.exe -m dashboard sentiment-summary AMD
```

## Provider Rules

- Use official APIs only.
- Store provider IDs, URLs, timestamps, engagement metrics, and provider attribution.
- Keep raw payloads for debugging only when provider terms permit it.
- Do not scrape full pages or infer unavailable values.
- Treat missing provider credentials, rate limits, and entitlement failures as operational gaps.

## App Surfaces

Retail sentiment is visible in three places:

- `/retail-sentiment`: the main review page for held stocks and high-activity popular names.
- `/signals`: an optional `Include retail add-on` filter can include retail-derived signals.
- `/operations`: the ingestion card shows provider configuration, queued jobs, stored snapshots, and recent mapped posts.

For buy/sell ratings, the aggregate ranking excludes retail sentiment by default. When the user enables retail sentiment, it is added as a small social-attention modifier, not as an equal-weight institutional or analyst signal. The current aggregate model weights the primary evidence around price momentum, news sentiment, earnings momentum, and institutional buying; retail sentiment is a 10% optional add-on when available.

## Verification

Focused backend proof:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ingestion_sentiment -q
```

For web-facing or readiness-affecting work, also run the repo data-health workflow from `AGENTS.md`.
