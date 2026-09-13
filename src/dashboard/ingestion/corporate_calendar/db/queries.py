"""
SQL helpers for Domain B corporate calendar ingestion.
"""

NEXT_JOB_ID = """
SELECT nextval('seq_ingestion_job_id')
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

CLAIM_NEXT_PENDING_JOB = """
UPDATE ingestion_job
SET
    status = ?,
    attempt_count = attempt_count + 1,
    error_message = NULL,
    lease_owner = ?,
    leased_at = CURRENT_TIMESTAMP,
    lease_expires_at = CURRENT_TIMESTAMP + (? * INTERVAL '1 second'),
    terminal_reason = NULL,
    completed_at = NULL,
    updated_at = CURRENT_TIMESTAMP
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
SET
    status = ?,
    error_message = NULL,
    lease_owner = NULL,
    leased_at = NULL,
    lease_expires_at = NULL,
    completed_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = ?
"""

MARK_JOB_FAILED = """
UPDATE ingestion_job
SET
    status = ?,
    error_message = ?,
    lease_owner = NULL,
    leased_at = NULL,
    lease_expires_at = NULL,
    completed_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = ?
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

MARK_SYNC_RUNNING = """
UPDATE asset_sync_state
SET
    backfill_status = ?,
    backfill_start_date = ?,
    backfill_end_date = ?,
    last_attempted_at = CURRENT_TIMESTAMP,
    last_error = NULL,
    needs_repair = FALSE
WHERE asset_id = ?
  AND domain = ?
  AND dataset = ?
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

SELECT_TRACKED_STOCK_ASSET_IDS = """
SELECT asset_id
FROM asset
WHERE track = TRUE
  AND COALESCE(asset_type, 'stock') IN ('stock', 'adr')
ORDER BY asset_id
"""

UPSERT_EARNINGS_CALENDAR_EVENT = """
INSERT INTO earnings_calendar_event (
    asset_id,
    earnings_date,
    fiscal_year,
    fiscal_quarter,
    "time",
    eps_estimated,
    eps_actual,
    revenue_estimated,
    revenue_actual,
    source
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (asset_id, earnings_date)
DO UPDATE SET
    fiscal_year = COALESCE(excluded.fiscal_year, earnings_calendar_event.fiscal_year),
    fiscal_quarter = COALESCE(excluded.fiscal_quarter, earnings_calendar_event.fiscal_quarter),
    "time" = COALESCE(excluded."time", earnings_calendar_event."time"),
    eps_estimated = COALESCE(excluded.eps_estimated, earnings_calendar_event.eps_estimated),
    eps_actual = COALESCE(excluded.eps_actual, earnings_calendar_event.eps_actual),
    revenue_estimated = COALESCE(excluded.revenue_estimated, earnings_calendar_event.revenue_estimated),
    revenue_actual = COALESCE(excluded.revenue_actual, earnings_calendar_event.revenue_actual),
    source = excluded.source,
    as_of_ts = now()
"""

UPSERT_FINANCIAL_STATEMENT = """
INSERT INTO financial_statement (
    asset_id,
    statement_type,
    year,
    quarter,
    period_end_date,
    report_date,
    data_json,
    source
)
VALUES (?, ?, ?, ?, ?, ?, json(?), ?)
ON CONFLICT (asset_id, statement_type, year, quarter)
DO UPDATE SET
    period_end_date = excluded.period_end_date,
    report_date = excluded.report_date,
    data_json = excluded.data_json,
    source = excluded.source,
    ingested_at_utc = now()
"""

SELECT_DUE_EARNINGS_EVENTS = """
SELECT e.asset_id
FROM earnings_calendar_event e
LEFT JOIN ingestion_job j
  ON j.asset_id = e.asset_id
 AND j.domain = 'corporate'
 AND j.job_type = 'earnings_update'
 AND j.status IN ('pending', 'running')
WHERE e.earnings_date <= ?
  AND e.earnings_date >= ?
  AND j.job_id IS NULL
GROUP BY e.asset_id
ORDER BY MIN(e.earnings_date), e.asset_id
LIMIT ?
"""

SELECT_ASSETS_WITH_RECENT_EARNINGS_EVENTS = """
SELECT e.asset_id
FROM earnings_calendar_event e
JOIN asset a
  ON a.asset_id = e.asset_id
WHERE COALESCE(a.asset_type, 'stock') IN ('stock', 'adr')
  AND e.earnings_date >= ?
  AND e.earnings_date <= ?
GROUP BY e.asset_id
ORDER BY MIN(e.earnings_date), e.asset_id
LIMIT ?
"""
