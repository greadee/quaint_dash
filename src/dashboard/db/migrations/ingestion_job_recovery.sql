-- Durable ingestion claim and recovery metadata.

ALTER TABLE ingestion_job ADD COLUMN IF NOT EXISTS work_key TEXT;
ALTER TABLE ingestion_job ADD COLUMN IF NOT EXISTS lease_owner TEXT;
ALTER TABLE ingestion_job ADD COLUMN IF NOT EXISTS leased_at TIMESTAMP;
ALTER TABLE ingestion_job ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMP;
ALTER TABLE ingestion_job ADD COLUMN IF NOT EXISTS max_attempts INTEGER DEFAULT 3;
ALTER TABLE ingestion_job ADD COLUMN IF NOT EXISTS terminal_reason TEXT;
ALTER TABLE ingestion_job ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;
ALTER TABLE ingestion_job ADD COLUMN IF NOT EXISTS superseded_by_job_id BIGINT;

UPDATE ingestion_job
SET max_attempts = 3
WHERE max_attempts IS NULL OR max_attempts < 1;
