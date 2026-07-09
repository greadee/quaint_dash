from fastapi.testclient import TestClient

from dashboard.api.app import create_app
from dashboard.db.db_conn import DB


def _seed_signal_assets(db: DB) -> None:
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Core')")
    db.conn.execute("INSERT INTO import_batch(batch_id, batch_type) VALUES (1, 'manual-entry')")
    assets = [
        ("BUYME", "BUYME", "Buy Momentum"),
        ("SELLME", "SELLME", "Sell Momentum"),
    ]
    for asset_id, symbol, name in assets:
        db.conn.execute(
            "INSERT INTO asset(asset_id, symbol, asset_type, ccy, name, sector, industry) VALUES (?, ?, 'stock', 'USD', ?, 'Technology', 'Software')",
            [asset_id, symbol, name],
        )
        db.conn.execute(
            """
            INSERT INTO txn(portfolio_id, time_stamp, txn_type, asset_id, qty, price, ccy, fee_amt, batch_id)
            VALUES (1, '2026-01-02 10:00:00', 'buy', ?, 10, 100, 'USD', 0, 1)
            """,
            [asset_id],
        )
    for index in range(70):
        db.conn.execute(
            """
            INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
            VALUES
                ('BUYME', DATE '2026-01-01' + CAST(? AS INTEGER), ?, ?, 'test'),
                ('SELLME', DATE '2026-01-01' + CAST(? AS INTEGER), ?, ?, 'test')
            """,
            [index, 100 + index, 100 + index, index, 170 - index, 170 - index],
        )


def test_signals_summary_exposes_distinct_strength_confidence_and_priority(tmp_path):
    db_path = tmp_path / "signals.db"
    app = create_app(db_path)
    db = DB(db_path)
    _seed_signal_assets(db)
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/signals?direction=negative&min_confidence=0.7&sort=priority")

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_version"] == "signals.rankings.v1"
    assert payload["total"] > 0
    item = payload["items"][0]
    assert item["signal_id"].startswith("ranking.")
    assert item["direction"] == "negative"
    assert item["strength"] >= 0
    assert item["confidence"] >= 0.7
    assert item["confidence"] < 1
    assert item["portfolio_priority"] >= 0
    assert item["supporting_evidence"]
    assert item["affected_portfolios"][0]["portfolio_name"] == "Core"
    assert item["historical_efficacy"]["sample_size"] == 0


def test_signals_summary_excludes_etfs_and_etf_like_assets(tmp_path):
    db_path = tmp_path / "signals.db"
    app = create_app(db_path)
    db = DB(db_path)
    _seed_signal_assets(db)
    for asset_id, symbol, asset_type, asset_subtype, name in [
        ("VTI", "VTI", "etf", None, "Vanguard Total Stock Market ETF"),
        ("MISETF", "MISETF", "stock", "index_etf", "Misclassified Growth ETF"),
    ]:
        db.conn.execute(
            """
            INSERT INTO asset(asset_id, symbol, asset_type, asset_subtype, ccy, name, track)
            VALUES (?, ?, ?, ?, 'USD', ?, TRUE)
            """,
            [asset_id, symbol, asset_type, asset_subtype, name],
        )
        for index in range(70):
            db.conn.execute(
                """
                INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
                VALUES (?, DATE '2026-01-01' + CAST(? AS INTEGER), ?, ?, 'test')
                """,
                [asset_id, index, 100 + index, 100 + index],
            )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/signals?limit=100")

    assert response.status_code == 200
    tickers = {item["ticker"] for item in response.json()["items"]}
    assert "VTI" not in tickers
    assert "MISETF" not in tickers


def test_signal_detail_user_state_alert_and_idempotent_persistence(tmp_path):
    db_path = tmp_path / "signals.db"
    app = create_app(db_path)
    db = DB(db_path)
    _seed_signal_assets(db)
    db.conn.close()

    with TestClient(app) as client:
        first = client.get("/api/v1/signals?limit=1")
        second = client.get("/api/v1/signals?limit=1")
        signal_id = first.json()["items"][0]["signal_id"]
        detail = client.get(f"/api/v1/signals/{signal_id}")
        state = client.put(f"/api/v1/signals/{signal_id}/user-state", json={"reviewed": True, "note": "checked"})
        alert = client.post(f"/api/v1/signals/{signal_id}/alerts", json={"condition": "status_active"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["total"] == second.json()["total"]
    assert detail.status_code == 200
    assert detail.json()["lifecycle"]
    assert detail.json()["strength_history"]
    assert state.status_code == 200
    assert state.json()["reviewed_at"] is not None
    assert state.json()["note"] == "checked"
    assert alert.status_code == 200
    assert alert.json()["signal_id"] == signal_id


def test_signal_efficacy_uses_prior_snapshots_without_lookahead(tmp_path):
    db_path = tmp_path / "signals.db"
    app = create_app(db_path)
    db = DB(db_path)
    _seed_signal_assets(db)
    for index, snapshot_date in enumerate(["2026-01-05", "2026-01-12", "2026-01-19", "2026-01-26"]):
        db.conn.execute(
            """
            INSERT INTO stock_ranking_snapshot(
                asset_id, factor, snapshot_date, universe, score, action,
                confidence, data_status, latest_data_date, components_json,
                missing_inputs_json
            )
            VALUES ('BUYME', 'share_price_momentum', ?, 'tracked', ?, 'Buy', 1, 'complete', ?, '[]', '[]')
            """,
            [snapshot_date, 18 + index, snapshot_date],
        )
    db.conn.close()

    with TestClient(app) as client:
        response = client.get("/api/v1/signals?category=momentum&q=BUYME&limit=1")

    assert response.status_code == 200
    item = response.json()["items"][0]
    efficacy = item["historical_efficacy"]
    assert efficacy["label"] == "Backtested from stored point-in-time snapshots"
    assert efficacy["sample_size"] >= 3
    assert efficacy["prior_occurrences"] == 4
    assert efficacy["median_forward_return"] is not None
    assert efficacy["hit_rate"] is not None
    assert efficacy["warning"] is None
