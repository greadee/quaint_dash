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
    assert item["portfolio_priority"] >= 0
    assert item["supporting_evidence"]
    assert item["affected_portfolios"][0]["portfolio_name"] == "Core"
    assert item["historical_efficacy"]["sample_size"] == 0


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
