BEGIN TRANSACTION;

CREATE SEQUENCE IF NOT EXISTS seq_financial_news_provider_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_news_category_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_news_story_cluster_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_asset_entity_alias_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_news_alert_rule_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_news_alert_delivery_id START 1;

CREATE TABLE IF NOT EXISTS news_provider (
    provider_id BIGINT PRIMARY KEY DEFAULT nextval('seq_financial_news_provider_id'),
    provider_code TEXT NOT NULL UNIQUE,
    provider_name TEXT NOT NULL,
    provider_type TEXT NOT NULL DEFAULT 'api',
    base_url TEXT,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    priority INTEGER NOT NULL DEFAULT 100,
    default_language TEXT NOT NULL DEFAULT 'en',
    supports_streaming BOOLEAN NOT NULL DEFAULT FALSE,
    supports_symbol_news BOOLEAN NOT NULL DEFAULT FALSE,
    supports_full_text BOOLEAN NOT NULL DEFAULT FALSE,
    supports_latest_news BOOLEAN NOT NULL DEFAULT TRUE,
    supports_summaries BOOLEAN NOT NULL DEFAULT FALSE,
    supports_images BOOLEAN NOT NULL DEFAULT FALSE,
    supports_sentiment BOOLEAN NOT NULL DEFAULT FALSE,
    supports_categories BOOLEAN NOT NULL DEFAULT FALSE,
    supports_languages BOOLEAN NOT NULL DEFAULT FALSE,
    supports_regions BOOLEAN NOT NULL DEFAULT FALSE,
    supports_company_entities BOOLEAN NOT NULL DEFAULT FALSE,
    supports_press_releases BOOLEAN NOT NULL DEFAULT FALSE,
    supports_provider_updates BOOLEAN NOT NULL DEFAULT FALSE,
    supports_article_corrections BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS asset_entity_alias (
    alias_id BIGINT PRIMARY KEY DEFAULT nextval('seq_asset_entity_alias_id'),
    asset_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    country TEXT,
    exchange_code TEXT,
    valid_from DATE,
    valid_to DATE,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.75,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE(asset_id, alias, alias_type),
    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

ALTER TABLE news_article ADD COLUMN IF NOT EXISTS provider_id BIGINT;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS provider_article_id TEXT;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS canonical_story_id TEXT;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS headline TEXT;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS subheadline TEXT;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS article_body TEXT;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS canonical_url TEXT;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS image_url TEXT;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS language TEXT;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS provider_updated_at TIMESTAMP;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS first_ingested_at TIMESTAMP;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS last_ingested_at TIMESTAMP;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS headline_hash TEXT;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS story_fingerprint TEXT;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS importance_score DOUBLE PRECISION;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS sentiment_score DOUBLE PRECISION;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS sentiment_label TEXT;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS is_breaking BOOLEAN;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS is_press_release BOOLEAN;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS is_correction BOOLEAN;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS is_retracted BOOLEAN;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS is_paywalled BOOLEAN;
ALTER TABLE news_article ADD COLUMN IF NOT EXISTS is_active BOOLEAN;

UPDATE news_article
SET
    provider_article_id = COALESCE(provider_article_id, source_item_id),
    headline = COALESCE(headline, title),
    canonical_url = COALESCE(canonical_url, url),
    first_ingested_at = COALESCE(first_ingested_at, fetched_at, created_at),
    last_ingested_at = COALESCE(last_ingested_at, fetched_at, updated_at),
    language = COALESCE(language, 'en'),
    is_breaking = COALESCE(is_breaking, FALSE),
    is_press_release = COALESCE(is_press_release, FALSE),
    is_correction = COALESCE(is_correction, FALSE),
    is_retracted = COALESCE(is_retracted, FALSE),
    is_paywalled = COALESCE(is_paywalled, FALSE),
    is_active = COALESCE(is_active, TRUE)
WHERE headline IS NULL
   OR canonical_url IS NULL
   OR first_ingested_at IS NULL
   OR last_ingested_at IS NULL
   OR language IS NULL
   OR is_breaking IS NULL
   OR is_press_release IS NULL
   OR is_correction IS NULL
   OR is_retracted IS NULL
   OR is_paywalled IS NULL
   OR is_active IS NULL;

CREATE INDEX IF NOT EXISTS idx_news_article_provider_article
ON news_article(provider_id, provider_article_id);

CREATE INDEX IF NOT EXISTS idx_news_article_canonical_url
ON news_article(canonical_url);

CREATE INDEX IF NOT EXISTS idx_news_article_story_fingerprint
ON news_article(story_fingerprint);

CREATE TABLE IF NOT EXISTS news_article_asset (
    article_id BIGINT NOT NULL,
    asset_id TEXT NOT NULL,
    relevance_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    confidence_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    match_method TEXT NOT NULL,
    mention_type TEXT NOT NULL DEFAULT 'unknown',
    is_primary_entity BOOLEAN NOT NULL DEFAULT FALSE,
    provider_assigned BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY(article_id, asset_id),
    FOREIGN KEY(article_id) REFERENCES news_article(article_id),
    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

CREATE TABLE IF NOT EXISTS news_article_entity (
    article_id BIGINT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    relevance_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    confidence_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY(article_id, entity_type, entity_key),
    FOREIGN KEY(article_id) REFERENCES news_article(article_id)
);

CREATE TABLE IF NOT EXISTS news_category (
    category_id BIGINT PRIMARY KEY DEFAULT nextval('seq_news_category_id'),
    category_code TEXT NOT NULL UNIQUE,
    category_name TEXT NOT NULL,
    default_importance_weight DOUBLE PRECISION NOT NULL DEFAULT 0.35,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS news_article_category (
    article_id BIGINT NOT NULL,
    category_id BIGINT NOT NULL,
    confidence_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    classification_source TEXT NOT NULL DEFAULT 'deterministic',
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY(article_id, category_id),
    FOREIGN KEY(article_id) REFERENCES news_article(article_id),
    FOREIGN KEY(category_id) REFERENCES news_category(category_id)
);

CREATE TABLE IF NOT EXISTS news_story_cluster (
    cluster_id BIGINT PRIMARY KEY DEFAULT nextval('seq_news_story_cluster_id'),
    cluster_key TEXT NOT NULL UNIQUE,
    primary_article_id BIGINT,
    cluster_headline TEXT NOT NULL,
    cluster_summary TEXT,
    first_published_at TIMESTAMP,
    last_updated_at TIMESTAMP,
    article_count BIGINT NOT NULL DEFAULT 0,
    importance_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    FOREIGN KEY(primary_article_id) REFERENCES news_article(article_id)
);

CREATE TABLE IF NOT EXISTS news_story_cluster_article (
    cluster_id BIGINT NOT NULL,
    article_id BIGINT NOT NULL,
    similarity_score DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY(cluster_id, article_id),
    FOREIGN KEY(article_id) REFERENCES news_article(article_id)
);

CREATE TABLE IF NOT EXISTS news_ingestion_state (
    provider_id BIGINT NOT NULL,
    feed_type TEXT NOT NULL,
    cursor TEXT,
    last_provider_timestamp TIMESTAMP,
    last_attempted_at TIMESTAMP,
    last_succeeded_at TIMESTAMP,
    last_error_at TIMESTAMP,
    last_error_message TEXT,
    sync_status TEXT NOT NULL DEFAULT 'pending',
    articles_received BIGINT NOT NULL DEFAULT 0,
    articles_inserted BIGINT NOT NULL DEFAULT 0,
    articles_updated BIGINT NOT NULL DEFAULT 0,
    articles_rejected BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY(provider_id, feed_type),
    FOREIGN KEY(provider_id) REFERENCES news_provider(provider_id)
);

CREATE TABLE IF NOT EXISTS news_user_article_state (
    user_id TEXT NOT NULL,
    article_id BIGINT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    read_at TIMESTAMP,
    is_saved BOOLEAN NOT NULL DEFAULT FALSE,
    saved_at TIMESTAMP,
    is_hidden BOOLEAN NOT NULL DEFAULT FALSE,
    hidden_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY(user_id, article_id),
    FOREIGN KEY(article_id) REFERENCES news_article(article_id)
);

CREATE TABLE IF NOT EXISTS news_alert_rule (
    alert_rule_id BIGINT PRIMARY KEY DEFAULT nextval('seq_news_alert_rule_id'),
    user_id TEXT NOT NULL DEFAULT 'local',
    rule_name TEXT NOT NULL,
    target_scope TEXT NOT NULL,
    keyword_query TEXT,
    min_importance DOUBLE PRECISION,
    sentiment_threshold DOUBLE PRECISION,
    breaking_only BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    delivery_channel TEXT NOT NULL DEFAULT 'in_app',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS news_alert_rule_asset (
    alert_rule_id BIGINT NOT NULL,
    asset_id TEXT NOT NULL,
    PRIMARY KEY(alert_rule_id, asset_id),
    FOREIGN KEY(alert_rule_id) REFERENCES news_alert_rule(alert_rule_id),
    FOREIGN KEY(asset_id) REFERENCES asset(asset_id)
);

CREATE TABLE IF NOT EXISTS news_alert_rule_portfolio (
    alert_rule_id BIGINT NOT NULL,
    portfolio_id BIGINT NOT NULL,
    PRIMARY KEY(alert_rule_id, portfolio_id),
    FOREIGN KEY(alert_rule_id) REFERENCES news_alert_rule(alert_rule_id),
    FOREIGN KEY(portfolio_id) REFERENCES portfolio(portfolio_id)
);

CREATE TABLE IF NOT EXISTS news_alert_delivery (
    delivery_id BIGINT PRIMARY KEY DEFAULT nextval('seq_news_alert_delivery_id'),
    alert_rule_id BIGINT NOT NULL,
    article_id BIGINT,
    cluster_id BIGINT,
    delivery_channel TEXT NOT NULL DEFAULT 'in_app',
    delivery_status TEXT NOT NULL DEFAULT 'pending',
    delivered_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE(alert_rule_id, article_id, cluster_id, delivery_channel),
    FOREIGN KEY(alert_rule_id) REFERENCES news_alert_rule(alert_rule_id),
    FOREIGN KEY(article_id) REFERENCES news_article(article_id),
    FOREIGN KEY(cluster_id) REFERENCES news_story_cluster(cluster_id)
);

INSERT INTO news_category(category_code, category_name, default_importance_weight)
VALUES
    ('earnings', 'Earnings', 0.75),
    ('earnings_upcoming', 'Upcoming earnings', 0.65),
    ('earnings_reported', 'Reported earnings', 0.85),
    ('earnings_transcript', 'Earnings transcript', 0.55),
    ('guidance', 'Guidance', 0.8),
    ('analyst_rating', 'Analyst rating', 0.5),
    ('merger_acquisition', 'Merger and acquisition', 0.9),
    ('partnership', 'Partnership', 0.45),
    ('product_launch', 'Product launch', 0.45),
    ('regulatory', 'Regulatory', 0.8),
    ('litigation', 'Litigation', 0.75),
    ('management_change', 'Management change', 0.65),
    ('capital_raise', 'Capital raise', 0.7),
    ('debt', 'Debt', 0.55),
    ('buyback', 'Buyback', 0.65),
    ('dividend', 'Dividend', 0.55),
    ('stock_split', 'Stock split', 0.45),
    ('insider_activity', 'Insider activity', 0.45),
    ('institutional_activity', 'Institutional activity', 0.45),
    ('contract_award', 'Contract award', 0.5),
    ('government_policy', 'Government policy', 0.65),
    ('central_bank', 'Central bank', 0.75),
    ('economic_data', 'Economic data', 0.65),
    ('macro', 'Macro', 0.55),
    ('geopolitics', 'Geopolitics', 0.65),
    ('commodity', 'Commodity', 0.5),
    ('currency', 'Currency', 0.45),
    ('crypto', 'Crypto', 0.45),
    ('technology', 'Technology', 0.4),
    ('operations', 'Operations', 0.45),
    ('supply_chain', 'Supply chain', 0.55),
    ('cybersecurity', 'Cybersecurity', 0.65),
    ('bankruptcy', 'Bankruptcy', 0.95),
    ('restructuring', 'Restructuring', 0.75),
    ('press_release', 'Press release', 0.25),
    ('regulatory_filing', 'Regulatory filing', 0.8),
    ('social_post', 'Social post', 0.15),
    ('general', 'General', 0.3)
ON CONFLICT(category_code) DO UPDATE SET
    category_name = excluded.category_name,
    default_importance_weight = excluded.default_importance_weight,
    updated_at = now();

CREATE INDEX IF NOT EXISTS idx_news_article_asset_asset_time
ON news_article_asset(asset_id, relevance_score, confidence_score);

CREATE INDEX IF NOT EXISTS idx_news_article_category_category
ON news_article_category(category_id, article_id);

CREATE INDEX IF NOT EXISTS idx_news_user_article_state_user
ON news_user_article_state(user_id, is_read, is_saved);

COMMIT;
