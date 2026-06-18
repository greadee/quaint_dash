from fastapi.testclient import TestClient

from dashboard.api.app import create_app
from dashboard.db.db_conn import DB


def test_portfolio_create_list_and_conflict(tmp_path):
    app = create_app(tmp_path / "api.db")

    with TestClient(app) as client:
        created = client.post("/api/v1/portfolios", json={"name": "Main", "base_ccy": "cad"})
        conflict = client.post("/api/v1/portfolios", json={"name": "Main"})
        renamed = client.patch(
            f"/api/v1/portfolios/{created.json()['portfolio_id']}",
            json={"name": "Core"},
        )
        listed = client.get("/api/v1/portfolios")

    assert created.status_code == 201
    assert created.json()["name"] == "Main"
    assert created.json()["base_ccy"] == "CAD"
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "conflict"
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Core"
    assert listed.json()[0]["portfolio_id"] == created.json()["portfolio_id"]
    assert listed.json()[0]["name"] == "Core"


def test_portfolio_rename_conflicts_with_existing_name(tmp_path):
    app = create_app(tmp_path / "api.db")

    with TestClient(app) as client:
        client.post("/api/v1/portfolios", json={"name": "Main"})
        second = client.post("/api/v1/portfolios", json={"name": "Sandbox"})
        conflict = client.patch(
            f"/api/v1/portfolios/{second.json()['portfolio_id']}",
            json={"name": "Main"},
        )

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "conflict"


def test_mapped_broker_portfolio_summary_uses_broker_positions_only(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'TFSA')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES
            ('MU.TO', 'MU.TO', 'stock', 'CAD'),
            ('OLD.TO', 'OLD.TO', 'stock', 'CAD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO broker_account(
            provider,
            provider_account_id,
            provider_connection_id,
            account_name,
            account_type,
            currency,
            portfolio_id,
            raw_json
        )
        VALUES ('snaptrade', 'acct-1', 'conn-1', 'TFSA', 'tfsa', 'CAD', 1, '{}')
        """
    )
    db.conn.execute("INSERT INTO import_batch(batch_id, batch_type) VALUES (1, 'manual-entry')")
    db.conn.execute(
        """
        INSERT INTO txn(
            txn_id, portfolio_id, time_stamp, txn_type, asset_id, qty, price, ccy, fee_amt, batch_id
        )
        VALUES
            (1, 1, '2026-01-02 10:00:00', 'buy', 'OLD.TO', 10, 50, 'CAD', 0, 1),
            (2, 1, '2026-01-03 10:00:00', 'buy', 'MU.TO', 85, 25, 'CAD', 0, 1)
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
        VALUES ('snaptrade', 'acct-1', 'pos-mu', 1, 'MU.TO', 85, 464.10, 'CAD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO broker_position_snapshot(
            provider,
            provider_account_id,
            provider_position_id,
            as_of_date,
            asset_id,
            symbol,
            quantity,
            market_value,
            currency
        )
        VALUES ('snaptrade', 'acct-1', 'pos-mu', '2026-01-03', 'MU.TO', 'MU.TO', 85, 1200, 'CAD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        VALUES ('MU.TO', '2026-01-04', 50, 50, 'test')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        portfolios = client.get("/api/v1/portfolios")
        positions = client.get("/api/v1/portfolios/1/positions")

    assert portfolios.status_code == 200
    summary = portfolios.json()[0]
    assert summary["position_count"] == 1
    assert summary["market_value"] == 1200
    assert summary["book_cost"] == 464.1
    assert round(summary["unrealized_gain"] / summary["book_cost"], 4) == 1.5856

    assert positions.status_code == 200
    payload = positions.json()
    assert [item["asset_id"] for item in payload] == ["MU.TO"]
    assert payload[0]["market_value"] == 1200
    assert payload[0]["latest_price"] == 1200 / 85
    assert payload[0]["broker_linked"] is True


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
        INSERT INTO position(portfolio_id, asset_id, qty, book_cost, created_at, updated_at)
        VALUES (1, 'AAPL', 2, 200, now(), now())
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        SELECT
            'AAPL',
            DATE '2025-01-01' + CAST(i AS INTEGER),
            100 + i * 0.05 + CASE WHEN i % 2 = 0 THEN 0.10 ELSE -0.10 END,
            100 + i * 0.05 + CASE WHEN i % 2 = 0 THEN 0.10 ELSE -0.10 END,
            'test'
        FROM range(0, 366) AS prices(i)
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        overview = client.get("/api/v1/portfolios/1/overview")
        positions = client.get("/api/v1/portfolios/1/positions")
        transactions = client.get("/api/v1/portfolios/1/transactions?limit=1")
        missing = client.get("/api/v1/portfolios/99/overview")

    assert overview.status_code == 200
    assert round(overview.json()["market_value"], 2) == 236.30
    assert round(overview.json()["unrealized_gain"], 2) == 36.30
    assert overview.json()["projected_value"] is not None
    assert overview.json()["projected_horizon_years"] == 5
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
    assert asset.json()["is_cdr"] is True
    assert asset.json()["underlying_asset_id"] == "AMD"


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
        underlying = client.get("/api/v1/assets/AMD")

    assert asset.status_code == 200
    assert asset.json()["sector"] == "Technology"
    assert asset.json()["industry"] == "Semiconductors"
    assert asset.json()["country"] == "US"
    assert asset.json()["is_cdr"] is True
    assert asset.json()["underlying_asset_id"] == "AMD"
    assert underlying.status_code == 200
    assert underlying.json()["symbol"] == "AMD"
    assert underlying.json()["is_cdr"] is False


def test_portfolio_positions_classify_known_cdr_tickers_without_cdr_name(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Main')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name)
        VALUES ('GOOG.TO', 'GOOG.TO', 'stock', 'CAD', 'Alphabet Inc.')
        """
    )
    db.conn.execute("INSERT INTO import_batch(batch_id, batch_type) VALUES (1, 'broker-ingest')")
    db.conn.execute(
        """
        INSERT INTO txn(portfolio_id, time_stamp, txn_type, asset_id, qty, price, ccy, fee_amt, batch_id)
        VALUES (1, '2026-01-02 10:00:00', 'buy', 'GOOG.TO', 2, 50, 'CAD', 0, 1)
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        positions = client.get("/api/v1/portfolios/1/positions")

    assert positions.status_code == 200
    assert positions.json()[0]["sector"] == "Communication Services"
    assert positions.json()[0]["industry"] == "Internet Content & Information"
    assert positions.json()[0]["country"] == "US"


def test_portfolio_positions_classify_cdr_ticker_aliases(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Main')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name)
        VALUES (
            'NOWS.TO',
            'NOWS.TO',
            'stock',
            'CAD',
            'ServiceNow Inc Canadian Depository Receipt (CAD Hedged)'
        )
        """
    )
    db.conn.execute("INSERT INTO import_batch(batch_id, batch_type) VALUES (1, 'broker-ingest')")
    db.conn.execute(
        """
        INSERT INTO txn(portfolio_id, time_stamp, txn_type, asset_id, qty, price, ccy, fee_amt, batch_id)
        VALUES (1, '2026-01-02 10:00:00', 'buy', 'NOWS.TO', 2, 50, 'CAD', 0, 1)
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        positions = client.get("/api/v1/portfolios/1/positions")

    assert positions.status_code == 200
    assert positions.json()[0]["sector"] == "Technology"
    assert positions.json()[0]["industry"] == "Software - Application"
    assert positions.json()[0]["country"] == "US"


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


def test_portfolio_position_delete_allows_zero_broker_holding_cleanup(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Main')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES ('OLD', 'OLD', 'stock', 'USD')
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
        VALUES ('snaptrade', 'acct-1', 'pos-old', 1, 'OLD', 0, 0, 'USD')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        delete = client.delete("/api/v1/portfolios/1/positions/OLD")

    db = DB(db_path)
    remaining = db.conn.execute(
        "SELECT COUNT(*) FROM broker_portfolio_position_map WHERE portfolio_id = 1 AND asset_id = 'OLD'"
    ).fetchone()[0]
    db.conn.close()

    assert delete.status_code == 200
    assert delete.json()["result"]["deleted_broker_mappings"] == 1
    assert remaining == 0


def test_asset_holdings_include_portfolio_context_and_returns(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Main')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name)
        VALUES ('MU.TO', 'MU.TO', 'stock', 'CAD', 'Micron CDR')
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
        VALUES ('snaptrade', 'acct-1', 'pos-mu', 1, 'MU.TO', 85, 464.10, 'CAD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO broker_position_snapshot(
            provider,
            provider_account_id,
            provider_position_id,
            as_of_date,
            asset_id,
            symbol,
            quantity,
            market_value,
            currency
        )
        VALUES ('snaptrade', 'acct-1', 'pos-mu', '2026-01-03', 'MU.TO', 'MU.TO', 85, 595, 'CAD')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        holdings = client.get("/api/v1/assets/MU.TO/holdings")
        delete = client.delete("/api/v1/portfolios/1/positions/MU.TO")
        after = client.get("/api/v1/assets/MU.TO/holdings")

    assert holdings.status_code == 200
    payload = holdings.json()
    assert payload[0]["portfolio_id"] == 1
    assert payload[0]["portfolio_name"] == "Main"
    assert payload[0]["quantity"] == 85
    assert payload[0]["book_cost"] == 464.1
    assert payload[0]["latest_price"] == 7
    assert payload[0]["market_value"] == 595
    assert round(payload[0]["total_return_percent"], 4) == 0.2821
    assert payload[0]["broker_linked"] is True
    assert delete.status_code == 200
    assert after.json() == []


def test_asset_activity_lists_broker_and_local_activity(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Main')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name)
        VALUES ('MU.TO', 'MU.TO', 'stock', 'CAD', 'Micron CDR')
        """
    )
    db.conn.execute(
        """
        INSERT INTO broker_account(
            provider,
            provider_account_id,
            provider_connection_id,
            account_name,
            account_type,
            currency,
            balance,
            portfolio_id,
            raw_json
        )
        VALUES ('snaptrade', 'acct-1', 'conn-1', 'TFSA', 'registered', 'CAD', 0, 1, '{}')
        """
    )
    db.conn.execute(
        """
        INSERT INTO broker_transaction(
            provider,
            provider_transaction_id,
            provider_account_id,
            trade_date,
            txn_type,
            asset_id,
            symbol,
            quantity,
            price,
            amount,
            currency,
            raw_json
        )
        VALUES
            ('snaptrade', 'buy-mu', 'acct-1', '2026-01-02', 'BUY', 'MU.TO', 'MU.TO', 85, 5.46, -464.10, 'CAD', '{}'),
            ('snaptrade', 'div-mu', 'acct-1', '2026-01-03', 'DIVIDEND', 'MU.TO', 'MU.TO', NULL, NULL, 12.50, 'CAD', '{}')
        """
    )
    db.conn.execute("INSERT INTO import_batch(batch_id, batch_type) VALUES (1, 'manual-entry')")
    db.conn.execute(
        """
        INSERT INTO txn(
            portfolio_id, time_stamp, txn_type, asset_id, qty, price, ccy, fee_amt, batch_id
        )
        VALUES (1, '2026-01-04 10:00:00', 'sell', 'MU.TO', -5, 40, 'CAD', 0, 1)
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/assets/MU.TO/activity")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert [item["transaction_type"] for item in payload["items"]] == ["sell", "DIVIDEND", "BUY"]
    assert payload["items"][0]["source"] == "local"
    assert payload["items"][1]["source"] == "broker"
    assert payload["items"][1]["cash_amount"] == 12.5
    assert payload["items"][2]["portfolio_name"] == "Main"


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


def test_overview_updates_returns_all_price_movers(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Main')")
    db.conn.execute("INSERT INTO import_batch(batch_id, batch_type) VALUES (1, 'manual-entry')")
    for index in range(9):
        asset_id = f"T{index}"
        db.conn.execute(
            "INSERT INTO asset(asset_id, symbol, asset_type, ccy, name) VALUES (?, ?, 'stock', 'USD', ?)",
            [asset_id, asset_id, f"Ticker {index}"],
        )
        db.conn.execute(
            """
            INSERT INTO txn(portfolio_id, time_stamp, txn_type, asset_id, qty, price, ccy, fee_amt, batch_id)
            VALUES (1, '2026-01-02 10:00:00', 'buy', ?, 1, 100, 'USD', 0, 1)
            """,
            [asset_id],
        )
        db.conn.execute(
            """
            INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
            VALUES
                (?, '2026-01-02', 100, 100, 'test'),
                (?, '2026-01-03', ?, ?, 'test')
            """,
            [asset_id, asset_id, 101 + index, 101 + index],
        )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/overview/updates")

    assert response.status_code == 200
    assert response.json()["mover_count"] == 9
    assert len(response.json()["price_movers"]) == 9


def test_stock_rankings_rank_buy_and_sell_signals_from_stored_metrics(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Main')")
    db.conn.execute("INSERT INTO import_batch(batch_id, batch_type) VALUES (1, 'manual-entry')")
    assets = [
        ("BUYME", "BUYME", "Buy Momentum"),
        ("SELLME", "SELLME", "Sell Momentum"),
        ("FLAT", "FLAT", "Flat Holding"),
    ]
    for asset_id, symbol, name in assets:
        db.conn.execute(
            "INSERT INTO asset(asset_id, symbol, asset_type, ccy, name) VALUES (?, ?, 'stock', 'USD', ?)",
            [asset_id, symbol, name],
        )
        db.conn.execute(
            """
            INSERT INTO txn(portfolio_id, time_stamp, txn_type, asset_id, qty, price, ccy, fee_amt, batch_id)
            VALUES (1, '2026-01-02 10:00:00', 'buy', ?, 1, 100, 'USD', 0, 1)
            """,
            [asset_id],
        )
    price_paths = {
        "BUYME": [100 + index for index in range(70)],
        "SELLME": [170 - index for index in range(70)],
        "FLAT": [100 for _index in range(70)],
    }
    for asset_id, closes in price_paths.items():
        for index, close in enumerate(closes):
            db.conn.execute(
                """
                INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
                VALUES (?, DATE '2026-01-01' + CAST(? AS INTEGER), ?, ?, 'test')
                """,
                [asset_id, index, close, close],
            )
    db.conn.execute(
        """
        INSERT INTO stock_catalog(asset_id, symbol, exchange_code, ccy, name)
        VALUES ('AAAACAT', 'AAAACAT', 'NYSE', 'USD', 'Catalog Only')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/rankings/stocks?factor=share_price_momentum&universe=tracked&direction=buy"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["factor"] == "share_price_momentum"
    assert payload["universe"] == "tracked"
    assert "stored daily close momentum" in payload["methodology"]
    by_symbol = {item["symbol"]: item for item in payload["items"]}
    assert list(by_symbol)[0] == "BUYME"
    assert by_symbol["BUYME"]["action"] in {"Buy", "Strong Buy"}
    assert by_symbol["SELLME"]["action"] in {"Sell", "Strong Sell"}
    assert by_symbol["BUYME"]["is_held"] is True
    assert by_symbol["BUYME"]["confidence"] == 1
    assert by_symbol["BUYME"]["data_status"] == "complete"
    assert [component["name"] for component in by_symbol["BUYME"]["components"]] == [
        "Price trend",
        "Risk",
    ]
    assert by_symbol["BUYME"]["components"][0]["available"] is True
    assert by_symbol["BUYME"]["components"][1]["available"] is True

    with TestClient(app) as client:
        sell_response = client.get(
            "/api/v1/rankings/stocks?factor=share_price_momentum&universe=tracked&direction=sell"
        )

    assert sell_response.status_code == 200
    assert sell_response.json()["items"][0]["symbol"] == "SELLME"

    with TestClient(app) as client:
        all_response = client.get(
            "/api/v1/rankings/stocks?factor=aggregate&universe=all&direction=buy&limit=100"
        )

    all_payload = all_response.json()
    assert all_response.status_code == 200
    catalog_row = next(item for item in all_payload["items"] if item["symbol"] == "AAAACAT")
    assert catalog_row["is_tracked"] is False
    assert catalog_row["data_status"] == "missing"
    assert any(
        "Needs at least 22 stored daily closes for price momentum." in item
        for item in catalog_row["missing_inputs"]
    )


def test_portfolio_positions_normalize_object_like_currency_code(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Main')")
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name)
        VALUES ('CADHOLD', 'CADHOLD', 'stock', '{''CODE'': ''CAD'', ''NAME'': ''CANADIAN DOLLAR''}', 'CAD Holding')
        """
    )
    db.conn.execute("INSERT INTO import_batch(batch_id, batch_type) VALUES (1, 'manual-entry')")
    db.conn.execute(
        """
        INSERT INTO txn(portfolio_id, time_stamp, txn_type, asset_id, qty, price, ccy, fee_amt, batch_id)
        VALUES (1, '2026-01-02 10:00:00', 'buy', 'CADHOLD', 1, 100, 'CAD', 0, 1)
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/portfolios/1/positions")

    assert response.status_code == 200
    assert response.json()[0]["currency"] == "CAD"
