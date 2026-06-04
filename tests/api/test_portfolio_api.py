from fastapi.testclient import TestClient

from dashboard.api.app import create_app
from dashboard.db.db_conn import DB


def test_portfolio_create_list_and_conflict(tmp_path):
    app = create_app(tmp_path / "api.db")

    with TestClient(app) as client:
        created = client.post("/api/v1/portfolios", json={"name": "Main", "base_ccy": "cad"})
        listed = client.get("/api/v1/portfolios")
        conflict = client.post("/api/v1/portfolios", json={"name": "Main"})

    assert created.status_code == 201
    assert created.json()["name"] == "Main"
    assert created.json()["base_ccy"] == "CAD"
    assert listed.json()[0]["portfolio_id"] == created.json()["portfolio_id"]
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "conflict"


def test_portfolio_overview_positions_and_transactions(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Main')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name)
        VALUES ('AAPL', 'AAPL', 'stock', 'USD', 'Apple Inc.')
        """
    )
    db.conn.execute("INSERT INTO import_batch(batch_id, batch_type) VALUES (1, 'manual-entry')")
    db.conn.execute(
        """
        INSERT INTO txn(
            txn_id, portfolio_id, time_stamp, txn_type, asset_id, qty, price, ccy, fee_amt, batch_id
        )
        VALUES (1, 1, '2026-01-02 10:00:00', 'buy', 'AAPL', 2, 100, 'USD', 1, 1)
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        VALUES ('AAPL', '2026-01-03', 125, 125, 'test')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        overview = client.get("/api/v1/portfolios/1/overview")
        positions = client.get("/api/v1/portfolios/1/positions")
        transactions = client.get("/api/v1/portfolios/1/transactions?limit=1")
        missing = client.get("/api/v1/portfolios/99/overview")

    assert overview.status_code == 200
    assert overview.json()["market_value"] == 250
    assert overview.json()["unrealized_gain"] == 50
    assert positions.json()[0]["weight"] == 1
    assert positions.json()[0]["name"] == "Apple Inc."
    assert transactions.json()["total"] == 1
    assert transactions.json()["items"][0]["transaction_type"] == "buy"
    assert missing.status_code == 404
