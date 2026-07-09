NEXT_JOB_ID = """
SELECT nextval('seq_ingestion_job_id')
"""

NEXT_SAFE_JOB_ID = """
SELECT GREATEST(nextval('seq_ingestion_job_id'), COALESCE(MAX(job_id), 0) + 1)
FROM ingestion_job
"""

INSERT_JOB = """
INSERT INTO ingestion_job (
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
    error_message,
    created_at,
    updated_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
"""

SELECT_NEXT_PENDING_JOB = """
SELECT
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
FROM ingestion_job
WHERE domain = ?
  AND status = ?
  AND COALESCE(attempt_count, 0) = 0
  AND NOT EXISTS (
      SELECT 1
      FROM ingestion_job newer
      WHERE newer.asset_id = ingestion_job.asset_id
        AND newer.domain = ingestion_job.domain
        AND newer.dataset = ingestion_job.dataset
        AND newer.status = 'done'
        AND newer.job_id > ingestion_job.job_id
  )
  AND NOT EXISTS (
      SELECT 1
      FROM asset_sync_state sync
      WHERE sync.asset_id = ingestion_job.asset_id
        AND sync.domain = ingestion_job.domain
        AND sync.dataset = ingestion_job.dataset
        AND (
            sync.backfill_status = 'done'
            OR sync.last_successful_at IS NOT NULL
            OR sync.last_successful_date IS NOT NULL
        )
        AND COALESCE(sync.last_successful_at, sync.last_attempted_at, TIMESTAMP '1970-01-01') >= ingestion_job.updated_at
  )
ORDER BY priority DESC, created_at ASC
LIMIT 1
"""

MARK_JOB_RUNNING = """
UPDATE ingestion_job
SET
    status = ?,
    attempt_count = attempt_count + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = ?
"""

MARK_JOB_DONE = """
UPDATE ingestion_job
SET
    status = ?,
    error_message = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = ?
"""

MARK_JOB_FAILED = """
UPDATE ingestion_job
SET
    status = ?,
    error_message = ?,
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = ?
"""

UPSERT_SYNC_STATE = """
INSERT INTO asset_sync_state (
    asset_id,
    domain,
    dataset,
    backfill_status,
    backfill_start_date,
    backfill_end_date,
    last_successful_date,
    last_attempted_at,
    last_successful_at,
    last_error,
    needs_repair
)
VALUES (?, ?, ?, ?, ?, ?, ?, now(), now(), ?, ?)
ON CONFLICT (asset_id, domain, dataset)
DO UPDATE SET
    backfill_status = excluded.backfill_status,
    backfill_start_date = excluded.backfill_start_date,
    backfill_end_date = excluded.backfill_end_date,
    last_successful_date = excluded.last_successful_date,
    last_attempted_at = now(),
    last_successful_at = now(),
    last_error = excluded.last_error,
    needs_repair = excluded.needs_repair
"""

UPDATE_SYNC_STATE_FAILED = """
UPDATE asset_sync_state
SET
    backfill_status = ?,
    last_attempted_at = now(),
    last_error = ?,
    needs_repair = TRUE
WHERE asset_id = ?
  AND domain = ?
  AND dataset = ?
"""

ENSURE_SYNC_STATE = """
INSERT INTO asset_sync_state (
    asset_id,
    domain,
    dataset,
    backfill_status,
    backfill_start_date,
    backfill_end_date,
    last_successful_date,
    last_attempted_at,
    last_successful_at,
    last_error,
    needs_repair
)
VALUES (?, ?, ?, 'not_started', NULL, NULL, NULL, NULL, NULL, NULL, FALSE)
ON CONFLICT (asset_id, domain, dataset)
DO NOTHING
"""

LATEST_PRICE_DATE = """
SELECT MAX("date")
FROM asset_quote_daily
WHERE asset_id = ?
"""

LATEST_DIVIDEND_DATE = """
SELECT MAX(ex_date)
FROM dividend_event
WHERE asset_id = ?
"""

LATEST_SPLIT_DATE = """
SELECT MAX(ex_date)
FROM split_event
WHERE asset_id = ?
"""

UPSERT_PRICE_DAILY = """
INSERT INTO asset_quote_daily (
    asset_id,
    "date",
    "open",
    "high",
    "low",
    "close",
    adj_close,
    volume,
    ing_source,
    ing_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, now())
ON CONFLICT (asset_id, "date")
DO UPDATE SET
    "open" = excluded."open",
    "high" = excluded."high",
    "low" = excluded."low",
    "close" = excluded."close",
    adj_close = excluded.adj_close,
    volume = excluded.volume,
    ing_source = excluded.ing_source,
    ing_at = now()
"""

UPSERT_DIVIDEND_EVENT = """
INSERT INTO dividend_event (
    asset_id,
    ex_date,
    payment_date,
    record_date,
    declaration_date,
    dividend_per_share,
    currency,
    source,
    as_of_ts
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, now())
ON CONFLICT (asset_id, ex_date)
DO UPDATE SET
    payment_date = excluded.payment_date,
    record_date = excluded.record_date,
    declaration_date = excluded.declaration_date,
    dividend_per_share = excluded.dividend_per_share,
    currency = excluded.currency,
    source = excluded.source,
    as_of_ts = now()
"""

UPSERT_SPLIT_EVENT = """
INSERT INTO split_event (
    asset_id,
    ex_date,
    split_from,
    split_to,
    source,
    as_of_ts
)
VALUES (?, ?, ?, ?, ?, now())
ON CONFLICT (asset_id, ex_date)
DO UPDATE SET
    split_from = excluded.split_from,
    split_to = excluded.split_to,
    source = excluded.source,
    as_of_ts = now()
"""

SELECT_ALL_ASSET_IDS = """
SELECT asset_id
FROM asset
ORDER BY asset_id
"""
