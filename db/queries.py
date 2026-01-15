
#               portfolio queries

CREATE_PORTFOLIO = """
INSERT INTO portfolio (portfolio_id, base_ccy, created_at, updated_at)
VALUES (?, ?, NOW(), NOW())
RETURNING portfolio_id, base_ccy, created_at, updated_at;
"""

GET_PORTFOLIO = """
SELECT portfolio_id, base_ccy, created_at, updated_at
FROM portfolio
WHERE portfolio_id = ?;
"""

LIST_PORTFOLIOS = """
SELECT portfolio_id, base_ccy, created_at, updated_at
FROM portfolio
ORDER BY portfolio_id;
"""

#               asset queries

UPSERT_ASSET = """
INSERT INTO asset (asset_id, asset_type, ccy)
VALUES ( ?, ?, ?)
ON CONFLICT(asset_id) DO UPDATE SET
  asset_type = excluded.asset_type,
  ccy = excluded.ccy
RETURNING asset_id, asset_type, ccy;
"""

GET_ASSET = """
SELECT asset_id, asset_type, ccy
FROM asset
WHERE asset_id = ?;
"""

#               transaction queries

INSERT_TXN = """
INSERT INTO transaction (
  txn_id, portfolio_id, ts, type, asset_id, quantity, price,
  cash_amount, fees, ccy, note
)
VALUES (
  nextval('seq_txn_id'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
)
RETURNING txn_id;
"""

MAX_TXN_ID = """
SELECT COALESCE(MAX(id), 0)
FROM transaction
WHERE portfolio_id = ?;
"""

#               view queries

GET_POSITIONS_CURRENT = """
SELECT 
  v.asset_id, 
  v.quantity, 
  a.asset_id, 
  a.asset_type,
  a.ccy
FROM positionQty_view v
JOIN asset a ON a.asset_id = v.asset_id
WHERE v.portfolio_id = ?
ORDER BY a.asset_id;
"""

GET_CASH_CURRENT = """
SELECT
  v.asset_id,
  v.cash_balance,
  a.symbol,
  a.ccy
FROM v_cash_balance_current v
JOIN asset a ON a.asset_id = v.asset_id
WHERE v.portfolio_id = ?
ORDER BY a.symbol;
"""

GET_DAILY_FLOWS = """
SELECT day, contributions, withdrawals, income, expenses
FROM v_portfolio_net_flows
WHERE portfolio_id = ?
  AND (? IS NULL OR day >= ?)
  AND (? IS NULL OR day <= ?)
ORDER BY day;
"""