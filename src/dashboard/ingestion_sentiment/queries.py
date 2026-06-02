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

