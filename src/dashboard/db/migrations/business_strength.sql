CREATE SEQUENCE IF NOT EXISTS seq_business_strength_methodology_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_business_strength_template_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_business_strength_analysis_run_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_business_strength_peer_group_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_business_strength_override_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_business_strength_future_research_input_id START 1;

CREATE TABLE IF NOT EXISTS business_strength_methodology (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_business_strength_methodology_id'),
    version TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS business_strength_template (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_business_strength_template_id'),
    methodology_id BIGINT NOT NULL,
    template_code TEXT NOT NULL,
    sector TEXT,
    industry TEXT,
    name TEXT NOT NULL,
    version INTEGER NOT NULL,
    configuration_json JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE(methodology_id, template_code, version)
);

CREATE TABLE IF NOT EXISTS asset_business_classification (
    asset_id TEXT NOT NULL,
    sector TEXT,
    industry TEXT,
    template_code TEXT NOT NULL,
    classification_source TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    effective_from DATE NOT NULL DEFAULT CURRENT_DATE,
    effective_to DATE,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY(asset_id, effective_from)
);

CREATE TABLE IF NOT EXISTS business_strength_analysis_run (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_business_strength_analysis_run_id'),
    asset_id TEXT NOT NULL,
    methodology_id BIGINT NOT NULL,
    template_id BIGINT NOT NULL,
    analysis_date DATE NOT NULL,
    source_data_as_of TIMESTAMP,
    overall_score DOUBLE PRECISION,
    classification TEXT NOT NULL,
    confidence_score DOUBLE PRECISION NOT NULL,
    completeness_score DOUBLE PRECISION NOT NULL,
    easy_hold_score DOUBLE PRECISION,
    status TEXT NOT NULL,
    failure_reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS business_strength_category_score (
    analysis_run_id BIGINT NOT NULL,
    category_code TEXT NOT NULL,
    raw_score DOUBLE PRECISION,
    adjusted_score DOUBLE PRECISION,
    category_weight DOUBLE PRECISION NOT NULL,
    confidence_score DOUBLE PRECISION NOT NULL,
    completeness_score DOUBLE PRECISION NOT NULL,
    explanation TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY(analysis_run_id, category_code)
);

CREATE TABLE IF NOT EXISTS business_strength_metric_result (
    analysis_run_id BIGINT NOT NULL,
    category_code TEXT NOT NULL,
    metric_code TEXT NOT NULL,
    raw_value DOUBLE PRECISION,
    normalized_value DOUBLE PRECISION,
    metric_score DOUBLE PRECISION,
    metric_weight DOUBLE PRECISION NOT NULL,
    contribution DOUBLE PRECISION,
    unit TEXT NOT NULL,
    direction TEXT NOT NULL,
    value_status TEXT NOT NULL,
    source TEXT NOT NULL,
    source_timestamp TIMESTAMP,
    peer_percentile DOUBLE PRECISION,
    historical_percentile DOUBLE PRECISION,
    confidence DOUBLE PRECISION NOT NULL,
    explanation TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY(analysis_run_id, category_code, metric_code)
);

CREATE TABLE IF NOT EXISTS business_strength_peer_group (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_business_strength_peer_group_id'),
    name TEXT NOT NULL,
    template_code TEXT NOT NULL,
    definition_json JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS business_strength_peer_member (
    peer_group_id BIGINT NOT NULL,
    asset_id TEXT NOT NULL,
    effective_from DATE NOT NULL DEFAULT CURRENT_DATE,
    effective_to DATE,
    PRIMARY KEY(peer_group_id, asset_id, effective_from)
);

CREATE TABLE IF NOT EXISTS business_strength_override (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_business_strength_override_id'),
    asset_id TEXT NOT NULL,
    analysis_run_id BIGINT,
    override_type TEXT NOT NULL,
    target_code TEXT NOT NULL,
    previous_value TEXT,
    override_value TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS business_strength_future_research_input (
    id BIGINT PRIMARY KEY DEFAULT nextval('seq_business_strength_future_research_input_id'),
    asset_id TEXT NOT NULL,
    analysis_run_id BIGINT,
    input_type TEXT NOT NULL,
    structured_payload JSON NOT NULL,
    source TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    review_status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_business_strength_latest
ON business_strength_analysis_run(asset_id, status, analysis_date, created_at);
