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
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name, sector, industry, country)
        VALUES ('AAPL', 'AAPL', 'stock', 'USD', 'Apple Inc.', 'Technology', 'Consumer Electronics', 'US')
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
    assert positions.json()[0]["sector"] == "Technology"
    assert positions.json()[0]["industry"] == "Consumer Electronics"
    assert positions.json()[0]["country"] == "US"
    assert transactions.json()["total"] == 1
    assert transactions.json()["items"][0]["transaction_type"] == "buy"
    assert missing.status_code == 404


def test_portfolio_positions_use_underlying_metadata_for_cdrs(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Main')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, asset_subtype, ccy, name, sector, industry, country)
        VALUES
            ('AMD', 'AMD', 'stock', NULL, 'USD', 'Advanced Micro Devices', 'Technology', 'Semiconductors', 'US'),
            ('AMD.TO', 'AMD.TO', 'etf', 'cdr', 'CAD', 'AMD Canadian Depositary Receipt', NULL, NULL, 'CA')
        """
    )
    db.conn.execute("INSERT INTO import_batch(batch_id, batch_type) VALUES (1, 'manual-entry')")
    db.conn.execute(
        """
        INSERT INTO txn(portfolio_id, time_stamp, txn_type, asset_id, qty, price, ccy, fee_amt, batch_id)
        VALUES (1, '2026-01-02 10:00:00', 'buy', 'AMD.TO', 3, 40, 'CAD', 0, 1)
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        positions = client.get("/api/v1/portfolios/1/positions")
        asset = client.get("/api/v1/assets/AMD.TO")

    assert positions.status_code == 200
    assert positions.json()[0]["sector"] == "Technology"
    assert positions.json()[0]["industry"] == "Semiconductors"
    assert positions.json()[0]["country"] == "US"
    assert asset.status_code == 200
    assert asset.json()["sector"] == "Technology"
    assert asset.json()["industry"] == "Semiconductors"
    assert asset.json()["country"] == "US"


def test_asset_detail_uses_known_cdr_classification_when_underlying_is_missing(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name)
        VALUES ('AMD.TO', 'AMD.TO', 'stock', 'CAD', 'Advanced Micro Devices, Inc. CDR')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        asset = client.get("/api/v1/assets/AMD.TO")

    assert asset.status_code == 200
    assert asset.json()["sector"] == "Technology"
    assert asset.json()["industry"] == "Semiconductors"
    assert asset.json()["country"] == "US"


def test_portfolio_position_delete_warns_for_broker_linked_holding(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Main')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES ('AAPL', 'AAPL', 'stock', 'USD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO broker_portfolio_position_map(
            provider,
            provider_account_id,
            provider_position_id,
            portfolio_id,
            asset_id,
            quantity,
            book_cost,
            currency
        )
        VALUES ('snaptrade', 'acct-1', 'pos-1', 1, 'AAPL', 2, 200, 'USD')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        positions = client.get("/api/v1/portfolios/1/positions")
        delete = client.delete("/api/v1/portfolios/1/positions/AAPL")
        after = client.get("/api/v1/portfolios/1/positions")

    assert positions.status_code == 200
    assert positions.json()[0]["broker_linked"] is True
    assert positions.json()[0]["broker_account_count"] == 1
    assert delete.status_code == 200
    assert delete.json()["result"]["broker_linked"] is True
    assert delete.json()["result"]["deleted_broker_mappings"] == 1
    assert after.json() == []


def test_portfolio_aggregate_and_delete(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute(
        """
        INSERT INTO portfolio(portfolio_id, portfolio_name)
        VALUES (1, 'Main'), (2, 'Sandbox')
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES ('AAPL', 'AAPL', 'stock', 'USD'), ('MSFT', 'MSFT', 'stock', 'USD')
        """
    )
    db.conn.execute("INSERT INTO import_batch(batch_id, batch_type) VALUES (1, 'manual-entry')")
    db.conn.execute(
        """
        INSERT INTO txn(
            portfolio_id, time_stamp, txn_type, asset_id, qty, price, ccy, fee_amt, batch_id
        )
        VALUES
            (1, '2026-01-02 10:00:00', 'buy', 'AAPL', 2, 100, 'USD', 0, 1),
            (2, '2026-01-02 10:00:00', 'buy', 'MSFT', 1, 300, 'USD', 0, 1)
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        aggregate = client.get("/api/v1/portfolios/aggregate/overview")
        delete = client.delete("/api/v1/portfolios/2")
        listed = client.get("/api/v1/portfolios")
        missing = client.get("/api/v1/portfolios/2/overview")

    assert aggregate.status_code == 200
    assert aggregate.json()["name"] == "All portfolios"
    assert aggregate.json()["book_cost"] == 500
    assert delete.status_code == 200
    assert [item["portfolio_id"] for item in listed.json()] == [1]
    assert missing.status_code == 404


def test_overview_updates_include_movers_and_news(tmp_path):
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
        INSERT INTO txn(portfolio_id, time_stamp, txn_type, asset_id, qty, price, ccy, fee_amt, batch_id)
        VALUES (1, '2026-01-02 10:00:00', 'buy', 'AAPL', 2, 100, 'USD', 0, 1)
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        VALUES
            ('AAPL', '2026-01-02', 100, 100, 'test'),
            ('AAPL', '2026-01-03', 125, 125, 'test')
        """
    )
    db.conn.execute(
        """
        INSERT INTO news_article(article_id, source_name, provider, title, url, published_at, content_hash)
        VALUES (1, 'Test Wire', 'test-news', 'Apple updates guidance', 'https://example.test/aapl', '2026-01-03 12:00:00', 'hash-aapl')
        """
    )
    db.conn.execute(
        """
        INSERT INTO news_article_asset_mention(article_id, asset_id, ticker)
        VALUES (1, 'AAPL', 'AAPL')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/overview/updates")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_market_value"] == 250
    assert payload["price_movers"][0]["symbol"] == "AAPL"
    assert payload["price_movers"][0]["change_percent"] == 0.25
    assert payload["news"][0]["title"] == "Apple updates guidance"
    assert payload["news"][0]["symbol"] == "AAPL"
