"""SQL used by the sentiment ingestion repository."""

NEXT_NEWS_ARTICLE_ID = "SELECT nextval('seq_news_article_id')"
NEXT_SOCIAL_POST_ID = "SELECT nextval('seq_social_post_id')"
NEXT_SENTIMENT_OBSERVATION_ID = "SELECT nextval('seq_sentiment_observation_id')"
NEXT_JOB_ID = "SELECT nextval('seq_ingestion_job_id')"

SELECT_ASSET_REFS = """
SELECT asset_id, COALESCE(symbol, asset_id) AS ticker, name
FROM asset
WHERE track = TRUE
ORDER BY ticker
"""

UPSERT_NEWS_ARTICLE_BY_SOURCE_ITEM = """
INSERT INTO news_article (
    article_id,
    source_item_id,
    source_name,
    provider,
    title,
    summary,
    url,
    author,
    published_at,
    raw_payload_json,
    content_hash,
    updated_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
ON CONFLICT(provider, source_item_id)
DO UPDATE SET
    source_name = excluded.source_name,
    title = excluded.title,
    summary = excluded.summary,
    url = excluded.url,
    author = excluded.author,
    published_at = excluded.published_at,
    raw_payload_json = excluded.raw_payload_json,
    content_hash = excluded.content_hash,
    updated_at = now()
"""

UPSERT_NEWS_ARTICLE_BY_HASH = """
INSERT INTO news_article (
    article_id,
    source_item_id,
    source_name,
    provider,
    title,
    summary,
    url,
    author,
    published_at,
    raw_payload_json,
    content_hash,
    updated_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
ON CONFLICT(content_hash)
DO UPDATE SET
    source_name = excluded.source_name,
    title = excluded.title,
    summary = excluded.summary,
    url = excluded.url,
    author = excluded.author,
    published_at = excluded.published_at,
    raw_payload_json = excluded.raw_payload_json,
    updated_at = now()
"""

SELECT_NEWS_ARTICLE_ID_BY_SOURCE_ITEM = """
SELECT article_id
FROM news_article
WHERE provider = ? AND source_item_id = ?
"""

SELECT_NEWS_ARTICLE_ID_BY_HASH = """
SELECT article_id
FROM news_article
WHERE content_hash = ?
"""

UPSERT_NEWS_ARTICLE_MENTION = """
INSERT INTO news_article_asset_mention (
    article_id,
    asset_id,
    ticker,
    relevance_score,
    mention_reason
)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(article_id, asset_id)
DO UPDATE SET
    ticker = excluded.ticker,
    relevance_score = excluded.relevance_score,
    mention_reason = excluded.mention_reason
"""

UPSERT_SOCIAL_POST = """
INSERT INTO social_post (
    post_id,
    provider,
    source_post_id,
    source_name,
    author,
    title,
    body,
    url,
    published_at,
    score,
    comment_count,
    like_count,
    repost_count,
    reply_count,
    raw_payload_json,
    content_hash,
    updated_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
ON CONFLICT(provider, source_post_id)
DO UPDATE SET
    source_name = excluded.source_name,
    author = excluded.author,
    title = excluded.title,
    body = excluded.body,
    url = excluded.url,
    published_at = excluded.published_at,
    score = excluded.score,
    comment_count = excluded.comment_count,
    like_count = excluded.like_count,
    repost_count = excluded.repost_count,
    reply_count = excluded.reply_count,
    raw_payload_json = excluded.raw_payload_json,
    content_hash = excluded.content_hash,
    updated_at = now()
"""

SELECT_SOCIAL_POST_ID = """
SELECT post_id
FROM social_post
WHERE provider = ? AND source_post_id = ?
"""

UPSERT_SOCIAL_POST_MENTION = """
INSERT INTO social_post_asset_mention (
    post_id,
    asset_id,
    ticker,
    relevance_score,
    mention_reason
)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(post_id, asset_id)
DO UPDATE SET
    ticker = excluded.ticker,
    relevance_score = excluded.relevance_score,
    mention_reason = excluded.mention_reason
"""

SELECT_NEWS_FOR_TICKER = """
SELECT
    a.article_id,
    a.source_name,
    a.provider,
    a.title,
    a.summary,
    a.url,
    a.published_at,
    m.relevance_score
FROM news_article a
JOIN news_article_asset_mention m ON m.article_id = a.article_id
WHERE m.ticker = ?
ORDER BY COALESCE(a.published_at, a.fetched_at) DESC
LIMIT ?
"""

SELECT_SOCIAL_FOR_TICKER = """
SELECT
    p.post_id,
    p.provider,
    p.source_name,
    p.title,
    p.body,
    p.url,
    p.published_at,
    p.score,
    p.comment_count,
    m.relevance_score
FROM social_post p
JOIN social_post_asset_mention m ON m.post_id = p.post_id
WHERE m.ticker = ?
ORDER BY COALESCE(p.published_at, p.fetched_at) DESC
LIMIT ?
"""

INSERT_SENTIMENT_OBSERVATION = """
INSERT INTO sentiment_observation (
    observation_id,
    asset_id,
    ticker,
    item_type,
    item_id,
    provider,
    sentiment_label,
    sentiment_score,
    confidence,
    relevance_score,
    source_weight,
    engagement_weight,
    explanation,
    observed_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

SELECT_SENTIMENT_OBSERVATIONS_FOR_DATE = """
SELECT
    asset_id,
    ticker,
    item_type,
    item_id,
    provider,
    sentiment_label,
    sentiment_score,
    confidence,
    relevance_score,
    source_weight,
    engagement_weight,
    observed_at
FROM sentiment_observation
WHERE asset_id = ?
  AND CAST(observed_at AS DATE) = ?
"""

UPSERT_TICKER_SENTIMENT_DAILY = """
INSERT INTO ticker_sentiment_daily (
    asset_id,
    ticker,
    date,
    retail_sentiment_score,
    news_sentiment_score,
    analyst_sentiment_score,
    blended_sentiment_score,
    reddit_post_count,
    x_post_count,
    article_count,
    bullish_count,
    neutral_count,
    bearish_count,
    sentiment_momentum_1d,
    sentiment_momentum_7d,
    sentiment_momentum_30d,
    unusual_volume_flag,
    updated_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
ON CONFLICT(asset_id, date)
DO UPDATE SET
    ticker = excluded.ticker,
    retail_sentiment_score = excluded.retail_sentiment_score,
    news_sentiment_score = excluded.news_sentiment_score,
    analyst_sentiment_score = excluded.analyst_sentiment_score,
    blended_sentiment_score = excluded.blended_sentiment_score,
    reddit_post_count = excluded.reddit_post_count,
    x_post_count = excluded.x_post_count,
    article_count = excluded.article_count,
    bullish_count = excluded.bullish_count,
    neutral_count = excluded.neutral_count,
    bearish_count = excluded.bearish_count,
    sentiment_momentum_1d = excluded.sentiment_momentum_1d,
    sentiment_momentum_7d = excluded.sentiment_momentum_7d,
    sentiment_momentum_30d = excluded.sentiment_momentum_30d,
    unusual_volume_flag = excluded.unusual_volume_flag,
    updated_at = now()
"""

SELECT_DAILY_BLENDED_SCORE = """
SELECT blended_sentiment_score
FROM ticker_sentiment_daily
WHERE asset_id = ? AND date = ?
"""

SELECT_RECENT_AVG_ITEM_COUNT = """
SELECT AVG(reddit_post_count + x_post_count + article_count)
FROM ticker_sentiment_daily
WHERE asset_id = ?
  AND date < ?
  AND date >= ? - INTERVAL 30 DAY
"""

INSERT_SENTIMENT_JOB = """
INSERT INTO ingestion_job (
    job_id,
    asset_id,
    domain,
    job_type,
    dataset,
    status,
    priority,
    requested_start_date,
    requested_end_date
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

CLAIM_NEXT_PENDING_SENTIMENT_JOB = """
UPDATE ingestion_job
SET
    status = ?,
    attempt_count = attempt_count + 1,
    updated_at = now(),
    error_message = NULL,
    lease_owner = ?,
    leased_at = CURRENT_TIMESTAMP,
    lease_expires_at = CURRENT_TIMESTAMP + (? * INTERVAL '1 second'),
    terminal_reason = NULL,
    completed_at = NULL
WHERE job_id = (
    SELECT candidate.job_id
    FROM ingestion_job candidate
    WHERE candidate.domain = ?
      AND candidate.status = ?
      AND COALESCE(candidate.attempt_count, 0) < COALESCE(
          candidate.max_attempts,
          ?
      )
    ORDER BY candidate.priority DESC, candidate.created_at ASC
    LIMIT 1
)
  AND status = ?
RETURNING
    job_id,
    asset_id,
    domain,
    job_type,
    dataset,
    status,
    priority,
    requested_start_date,
    requested_end_date,
    attempt_count,
    error_message
"""

MARK_JOB_DONE = """
UPDATE ingestion_job
SET status = ?,
    updated_at = now(),
    error_message = NULL,
    lease_owner = NULL,
    leased_at = NULL,
    lease_expires_at = NULL,
    completed_at = CURRENT_TIMESTAMP
WHERE job_id = ?
"""

MARK_JOB_FAILED = """
UPDATE ingestion_job
SET status = ?,
    error_message = ?,
    updated_at = now(),
    lease_owner = NULL,
    leased_at = NULL,
    lease_expires_at = NULL,
    completed_at = CURRENT_TIMESTAMP
WHERE job_id = ?
"""

SELECT_PRICE_HISTORY_FOR_FACTOR = """
SELECT date, close, adj_close
FROM asset_quote_daily
WHERE asset_id = ?
  AND date <= ?
  AND date >= ? - INTERVAL 400 DAY
ORDER BY date
"""

SELECT_ASSET_FACTOR_METADATA = """
SELECT market_beta, sector, industry
FROM asset
WHERE asset_id = ?
"""

SELECT_DIVIDENDS_FOR_FACTOR = """
SELECT ex_date, dividend_per_share
FROM dividend_event
WHERE asset_id = ?
  AND ex_date <= ?
  AND ex_date >= ? - INTERVAL 400 DAY
ORDER BY ex_date
"""

UPSERT_FACTOR_SNAPSHOT = """
INSERT INTO ticker_factor_snapshot (
    asset_id,
    ticker,
    snapshot_date,
    growth_score,
    value_score,
    quality_score,
    momentum_score,
    defensive_score,
    dividend_score,
    volatility_score,
    revision_score,
    overall_factor_score,
    factor_labels_json,
    explanation,
    updated_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
ON CONFLICT(asset_id, snapshot_date)
DO UPDATE SET
    ticker = excluded.ticker,
    growth_score = excluded.growth_score,
    value_score = excluded.value_score,
    quality_score = excluded.quality_score,
    momentum_score = excluded.momentum_score,
    defensive_score = excluded.defensive_score,
    dividend_score = excluded.dividend_score,
    volatility_score = excluded.volatility_score,
    revision_score = excluded.revision_score,
    overall_factor_score = excluded.overall_factor_score,
    factor_labels_json = excluded.factor_labels_json,
    explanation = excluded.explanation,
    updated_at = now()
"""

SELECT_FACTOR_SNAPSHOT = """
SELECT
    asset_id,
    ticker,
    snapshot_date,
    growth_score,
    value_score,
    quality_score,
    momentum_score,
    defensive_score,
    dividend_score,
    volatility_score,
    revision_score,
    overall_factor_score,
    factor_labels_json,
    explanation
FROM ticker_factor_snapshot
WHERE asset_id = ? AND snapshot_date = ?
"""

UPSERT_QUANT_RATING_SNAPSHOT = """
INSERT INTO ticker_quant_rating_snapshot (
    asset_id,
    ticker,
    snapshot_date,
    overall_quant_score,
    overall_quant_rating,
    growth_rating,
    value_rating,
    quality_rating,
    momentum_rating,
    defensive_rating,
    dividend_rating,
    volatility_rating,
    factor_profile,
    explanation,
    updated_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
ON CONFLICT(asset_id, snapshot_date)
DO UPDATE SET
    ticker = excluded.ticker,
    overall_quant_score = excluded.overall_quant_score,
    overall_quant_rating = excluded.overall_quant_rating,
    growth_rating = excluded.growth_rating,
    value_rating = excluded.value_rating,
    quality_rating = excluded.quality_rating,
    momentum_rating = excluded.momentum_rating,
    defensive_rating = excluded.defensive_rating,
    dividend_rating = excluded.dividend_rating,
    volatility_rating = excluded.volatility_rating,
    factor_profile = excluded.factor_profile,
    explanation = excluded.explanation,
    updated_at = now()
"""
