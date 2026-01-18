"""/db/
sql query repository
"""


#               portfolio queries

UPSERT_PORTFOLIO = """
INSERT INTO portfolio (portfolio_id, name, base_ccy)
VALUES (?, ?, ?)
ON CONFLICT (portfolio_id) DO UPDATE SET
  name = name,
  base_ccy = base_ccy;
"""

GET_PORTFOLIO_BY_NAME = """
SELECT portfolio_id, name, base_ccy, created_at
FROM portfolio
WHERE name = ?;
"""

LIST_PORTFOLIOS = """
SELECT portfolio_id, name, base_ccy, created_at, updated_at
FROM portfolio
ORDER BY name;
"""

NEW_PORTFOLIO_ID = """
SELECT COALESCE(MAX(portfolio_id), 0)+1 
FROM portfolio
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
INSERT INTO transaction (
  portfolio_id, 
  time_stamp, 
  txn_type, 
  asset_id, 
  qty, 
  price, 
  ccy, 
  cash_amt, 
  fee_amt, 
  ext_ref
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
RETURNING txn_id;
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
    ext_ref
FROM txn
WHERE portfolio_id = ?
ORDER BY time_stamp, txn_id;
"""
