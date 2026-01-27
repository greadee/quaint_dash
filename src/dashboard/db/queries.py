"""/db/
sql query repository
"""


#               portfolio queries

UPSERT_PORTFOLIO_USER = """
INSERT INTO portfolio (portfolio_id, portfolio_name, base_ccy)
VALUES (?, ?, UPPER(?))
ON CONFLICT (portfolio_id) DO UPDATE SET
  portfolio_name = excluded.portfolio_name,
  base_ccy = excluded.base_ccy
"""

UPSERT_PORTFOLIO_IMPORT = """
INSERT INTO portfolio (portfolio_id, portfolio_name, created_at, updated_at)
VALUES (?, ?, ?, ?)
ON CONFLICT (portfolio_id) DO UPDATE SET
  portfolio_name = excluded.portfolio_name,
  updated_at = excluded.updated_at;
"""

GET_PORTFOLIO_BY_NAME = """
SELECT portfolio_id, portfolio_name, created_at, updated_at, base_ccy
FROM portfolio
WHERE portfolio_name = ?;
"""

GET_PORTFOLIO_BY_ID = """
SELECT portfolio_id, portfolio_name, created_at, updated_at, base_ccy
FROM portfolio
WHERE portfolio_id = ?;
"""

LIST_PORTFOLIOS = """
SELECT portfolio_id, portfolio_name, created_at, updated_at, base_ccy
FROM portfolio
ORDER BY portfolio_id;
"""

NEXT_PORTFOLIO_ID = """
SELECT COALESCE(MAX(portfolio_id), 0) + 1 AS next_id FROM portfolio
"""

CHECK_NEW_PORTFOLIO_ID = """
WITH m AS (
  SELECT COALESCE(MAX(portfolio_id), 0) + 1 AS next_id
  FROM portfolio
)
SELECT
  COALESCE(p.portfolio_id, m.next_id) AS portfolio_id,
  p.portfolio_id IS NULL              AS created
FROM m
LEFT JOIN portfolio p
  ON p.portfolio_name = ?;
"""

CHECK_PORTFOLIO_EXISTS = """
SELECT portfolio_id IS NULL 
FROM portfolio
WHERE portfolio_name = ?
"""

#               asset queries

UPSERT_ASSET = """
INSERT INTO asset (asset_id, asset_type, asset_subtype, ccy)
VALUES ( ?, ?, ?, ?)
ON CONFLICT(asset_id) DO UPDATE SET
  asset_type = asset_type,
  ccy = ccy;
"""

GET_ASSET = """
SELECT asset_id, asset_type, ccy
FROM asset
WHERE asset_id = ?;
"""

#               transaction queries

INSERT_TXN_BATCH = """
INSERT INTO txn (
  portfolio_id, 
  time_stamp, 
  txn_type, 
  asset_id, 
  qty, 
  price, 
  ccy, 
  cash_amt, 
  fee_amt, 
  batch_id
)
SELECT 
    p.portfolio_id,
    n.time_stamp, 
    n.txn_type, 
    n.asset_id, 
    n.qty, 
    n.price, 
    n.ccy, 
    n.cash_amt,
    n.fee_amt, 
    ? As batch_id
FROM norm_stg_txn n
JOIN portfolio p
  ON p.portfolio_name = n.portfolio_name;
  """

LIST_TXNS_FOR_PORTFOLIO = """
SELECT
    txn_id,
    portfolio_id,
    time_stamp,
    txn_type,
    asset_id,
    qty,
    price,
    ccy,
    cash_amt,
    fee_amt,
    batch_id
FROM txn
WHERE portfolio_id = ?
ORDER BY time_stamp, txn_id;
"""

# import batch queries

INSERT_IMPORT_BATCH = """
INSERT INTO import_batch (batch_type, import_time) 
VALUES (?, now()) 
RETURNING batch_id, import_time;
"""

#               validation queries

STAGE_TXN_CSV = """
DROP TABLE IF EXISTS stg_txn;
CREATE TEMP TABLE stg_txn AS
SELECT * FROM read_csv_auto(
  ?,
  delim=?,
  header=true,
  columns={
    'portfolio_name': 'VARCHAR',
    'time_stamp': 'VARCHAR',
    'txn_type': 'VARCHAR',
    'asset_id': 'VARCHAR',
    'qty': 'VARCHAR',
    'price': 'VARCHAR',
    'ccy': 'VARCHAR',
    'cash_amt': 'VARCHAR',
    'fee_amt': 'VARCHAR'
  }
);
"""

STAGE_TXN_MANUAL = """
DROP TABLE IF EXISTS stg_txn;
CREATE TEMP TABLE stg_txn (
    portfolio_name TEXT,
    time_stamp TEXT,
    txn_type TEXT,
    asset_id TEXT,
    qty TEXT,
    price TEXT,
    ccy TEXT,
    cash_amt TEXT,
    fee_amt TEXT
);
INSERT INTO stg_txn VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

NORMALIZE_TXN = """
DROP TABLE IF EXISTS norm_stg_txn;
CREATE TEMP TABLE norm_stg_txn AS
SELECT 
  TRIM(portfolio_name) AS portfolio_name,

  try_cast(TRIM(time_stamp) AS TIMESTAMP) AS time_stamp,

  LOWER(TRIM(txn_type)) AS txn_type,
  
  NULLIF(UPPER(TRIM(asset_id)), '') AS asset_id,

  CASE
    WHEN NULLIF(TRIM(qty), '') IS NULL THEN NULL             
    WHEN try_cast(TRIM(qty) AS DOUBLE) IS NULL THEN -1
    ELSE CAST(TRIM(qty) AS DOUBLE)
  END AS qty,

  CASE
    WHEN NULLIF(TRIM(price), '') IS NULL THEN NULL             
    WHEN try_cast(TRIM(price) AS DOUBLE) IS NULL THEN -1
    ELSE CAST(TRIM(price) AS DOUBLE)
  END AS price,

  UPPER(TRIM(ccy)) AS ccy,

  CASE
    WHEN NULLIF(TRIM(cash_amt), '') IS NULL THEN NULL
    WHEN try_cast(TRIM(cash_amt) AS DOUBLE) IS NULL THEN -1
    ELSE CAST(TRIM(cash_amt) AS DOUBLE)
  END AS cash_amt,

  CASE
    WHEN NULLIF(TRIM(fee_amt), '') IS NULL THEN NULL
    WHEN try_cast(TRIM(fee_amt) AS DOUBLE) IS NULL THEN -1
    ELSE CAST(TRIM(fee_amt) AS DOUBLE)
  END AS fee_amt
FROM stg_txn;
"""

# Validation suite

VALIDATE_STAGED_NAME = """
SELECT COUNT(*) 
FROM norm_stg_txn
WHERE portfolio_name IS NULL 
  OR portfolio_name = ''
"""

VALIDATE_STAGED_TIMESTAMP = """
SELECT COUNT(*)
FROM norm_stg_txn
WHERE time_stamp IS NULL;
"""

VALIDATE_STAGED_TYPE = """
SELECT COUNT(*)
FROM norm_stg_txn
WHERE txn_type IS NULL
  OR txn_type NOT IN ('contribution','withdrawal','dividend','interest','buy','sell');
"""

VALIDATE_STAGED_ASSET = """
SELECT COUNT(*)
FROM norm_stg_txn
WHERE asset_id IS NULL
  AND txn_type IN ('buy', 'sell', 'dividend')
"""

VALIDATE_STAGED_QTY = """
SELECT COUNT(*)
FROM norm_stg_txn
WHERE qty = -1;
"""

VALIDATE_STAGED_PRICE= """
SELECT COUNT(*)
FROM norm_stg_txn
WHERE price = -1;
"""

VALIDATE_STAGED_CCY = """
SELECT COUNT(*)
FROM norm_stg_txn
WHERE ccy IS NULL 
  OR length(ccy) <> 3;
"""

VALIDATE_STAGED_CASH = """
SELECT COUNT(*)
FROM norm_stg_txn
WHERE cash_amt = -1;
"""

VALIDATE_STAGED_FEE = """
SELECT COUNT(*)
FROM norm_stg_txn
WHERE fee_amt = -1;
"""

VALIDATE_TXN_SUITE = [
    VALIDATE_STAGED_NAME,
    VALIDATE_STAGED_TIMESTAMP,
    VALIDATE_STAGED_TYPE,
    VALIDATE_STAGED_ASSET,
    VALIDATE_STAGED_QTY,
    VALIDATE_STAGED_PRICE,
    VALIDATE_STAGED_CCY,
    VALIDATE_STAGED_CASH,
    VALIDATE_STAGED_FEE]
