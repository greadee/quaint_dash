"""
constants for corporate calendar ingestion
"""

DOMAIN_CORPORATE = "corporate"

JOB_TYPE_REFRESH = "refresh"
JOB_TYPE_CALENDAR_REFRESH = "calendar_refresh"
JOB_TYPE_EARNINGS_UPDATE = "earnings_update"
JOB_TYPE_EARNINGS_BACKUP = "earnings_backup"
JOB_TYPE_BACKFILL = "backfill"

DATASET_EARNINGS_CALENDAR = "earnings_calendar"
DATASET_EARNINGS_ACTUALS = "earnings_actuals"
DATASET_FINANCIAL_STATEMENTS = "financial_statements"

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

BACKFILL_NOT_STARTED = "not_started"
BACKFILL_RUNNING = "running"
BACKFILL_DONE = "done"
BACKFILL_FAILED = "failed"

PRIORITY_EARNINGS_UPDATE = 110
PRIORITY_CALENDAR_REFRESH = 70
PRIORITY_CORPORATE_BACKFILL = 60
