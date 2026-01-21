"""/db/
sql query repository
"""


#               portfolio queries

UPSERT_PORTFOLIO = """
INSERT INTO portfolio (portfolio_id, portfolio_name, created_at, updated_at, base_ccy)
VALUES (?, ?, now(), now(), ?)
ON CONFLICT (portfolio_id) DO UPDATE SET
  portfolio_name = excluded.portfolio_name,
  base_ccy = excluded.base_ccy,
  updated_at = now();
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

INSERT_TXN = """
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
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
RETURNING txn_id;
"""

GET_NEXT_BATCH = """ 
WITH next_batch AS (
  SELECT COALESCE(MAX(batch_id), 0) + 1 AS batch_id
  FROM import_batch
  WHERE portfolio_id = ?
)
INSERT INTO import_batch (portfolio_id, batch_id, batch_type)
SELECT ?, next_batch.batch_id, ?
FROM next_batch
RETURNING batch_id;
"""

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
FROM norm_txn_csv n
JOIN portfolio p
  ON p.portfolio_name = n.portfolio_name
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

#               validation queries

STAGE_TXN_CSV = """
DROP TABLE IF EXISTS stg_txn_csv;
CREATE TEMP TABLE stg_txn_csv AS
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

NORMALIZE_TXN_CSV = """
DROP TABLE IF EXISTS norm_txn_csv;
CREATE TEMP TABLE norm_txn_csv AS
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
FROM stg_txn_csv;
"""

# Validation suite

CHECK_BAD_NAME = """
SELECT COUNT(*) 
FROM norm_txn_csv
WHERE portfolio_name IS NULL 
  OR portfolio_name = ''
"""

CHECK_BAD_TIMESTAMP = """
SELECT COUNT(*)
FROM norm_txn_csv
WHERE time_stamp IS NULL;
"""

CHECK_BAD_TYPE = """
SELECT COUNT(*)
FROM norm_txn_csv
WHERE txn_type IS NULL
  OR txn_type NOT IN ('contribution','withdrawal','dividend','interest','buy','sell');
"""

CHECK_BAD_ASSET = """
SELECT COUNT(*)
FROM norm_txn_csv
WHERE asset_id IS NULL
  AND txn_type IN ('buy', 'sell', 'dividend')
"""

CHECK_BAD_QTY = """
SELECT COUNT(*)
FROM norm_txn_csv
WHERE qty = -1;
"""

CHECK_BAD_PRICE= """
SELECT COUNT(*)
FROM norm_txn_csv
WHERE price = -1;
"""

CHECK_BAD_CCY = """
SELECT COUNT(*)
FROM norm_txn_csv
WHERE ccy IS NULL 
  OR length(ccy) <> 3;
"""

CHECK_BAD_CASH = """
SELECT COUNT(*)
FROM norm_txn_csv
WHERE cash_amt = -1;
"""

CHECK_BAD_FEE = """
SELECT COUNT(*)
FROM norm_txn_csv
WHERE fee_amt = -1;
"""

VALIDATE_TXN_SUITE = [
    CHECK_BAD_NAME,
    CHECK_BAD_TIMESTAMP,
    CHECK_BAD_TYPE,
    CHECK_BAD_ASSET,
    CHECK_BAD_QTY,
    CHECK_BAD_PRICE,
    CHECK_BAD_CCY,
    CHECK_BAD_CASH,
    CHECK_BAD_FEE]
