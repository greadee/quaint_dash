CREATE TABLE IF NOT EXISTS candidate_run (
    run_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    schema_version TEXT NOT NULL,
    methodology_version TEXT NOT NULL,
    reason_codes_version TEXT NOT NULL,
    evidence_schema_version TEXT NOT NULL,
    investor_profile_id TEXT NOT NULL,
    investor_profile_schema_version TEXT NOT NULL,
    investor_profile_methodology_version TEXT NOT NULL,
    input_snapshot_hash TEXT NOT NULL,
    output_hash TEXT NOT NULL,
    run_status TEXT NOT NULL,
    blocking_conditions_json JSON NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    runtime_ms BIGINT,
    request_id TEXT
);

CREATE TABLE IF NOT EXISTS candidate_source_watermark (
    run_id TEXT NOT NULL,
    source_domain TEXT NOT NULL,
    source_schema_version TEXT NOT NULL,
    as_of TIMESTAMPTZ,
    coverage_state TEXT NOT NULL,
    PRIMARY KEY(run_id, source_domain)
);

CREATE TABLE IF NOT EXISTS candidate_review (
    review_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    methodology_version TEXT NOT NULL,
    reason_codes_version TEXT NOT NULL,
    fit_score DECIMAL(18, 8),
    diversification_score DECIMAL(18, 8),
    redundancy_score DECIMAL(18, 8),
    data_as_of TIMESTAMPTZ NOT NULL,
    methodology_as_of TIMESTAMPTZ NOT NULL,
    eligibility_state TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_json JSON NOT NULL,
    UNIQUE(run_id, candidate_id)
);

CREATE TABLE IF NOT EXISTS candidate_review_reason (
    review_id TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    PRIMARY KEY(review_id, reason_code)
);

CREATE TABLE IF NOT EXISTS candidate_source_match (
    review_id TEXT NOT NULL,
    source_family TEXT NOT NULL,
    source_methodology_version TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    nomination_strength DECIMAL(18, 8),
    evidence_ids_json JSON NOT NULL,
    PRIMARY KEY(review_id, source_family, reason_code, source_methodology_version)
);

CREATE TABLE IF NOT EXISTS candidate_evidence (
    run_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    evidence_schema_version TEXT NOT NULL,
    source_domain TEXT NOT NULL,
    source_schema_version TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    payload_hash TEXT NOT NULL,
    freshness_state TEXT NOT NULL,
    PRIMARY KEY(run_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS candidate_missing_metric (
    review_id TEXT NOT NULL,
    metric_code TEXT NOT NULL,
    criticality TEXT NOT NULL,
    expected_source TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    guardrail_effect TEXT NOT NULL,
    PRIMARY KEY(review_id, metric_code)
);

CREATE TABLE IF NOT EXISTS candidate_warning (
    review_id TEXT NOT NULL,
    warning_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    blocking BOOLEAN NOT NULL,
    evidence_ids_json JSON NOT NULL,
    PRIMARY KEY(review_id, warning_code)
);

CREATE INDEX IF NOT EXISTS idx_candidate_run_portfolio_history
ON candidate_run(portfolio_id, as_of, run_id);

CREATE INDEX IF NOT EXISTS idx_candidate_review_run_state
ON candidate_review(run_id, eligibility_state, candidate_id);

CREATE INDEX IF NOT EXISTS idx_candidate_evidence_source
ON candidate_evidence(run_id, source_domain, source_record_id);
