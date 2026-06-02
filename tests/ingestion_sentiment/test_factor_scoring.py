from __future__ import annotations

from datetime import date, timedelta

from dashboard.db.db_conn import DB, init_db
from dashboard.ingestion_sentiment.repo import SentimentIngestionRepository
from dashboard.ingestion_sentiment.scoring import FactorScorer


def test_factor_scores_handle_missing_data_without_crashing(tmp_path):
    db = DB(str(tmp_path / "factor_missing.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES ('AMD', 'AMD', 'stock', 'USD')
        """
    )
    repo = SentimentIngestionRepository(db.conn)

    snapshot = FactorScorer(repo).refresh_factor_snapshot(
        asset_id="AMD",
        ticker="AMD",
        snapshot_date=date(2026, 1, 5),
    )

    assert snapshot.overall_factor_score is None
    assert "momentum missing" in (snapshot.explanation or "")
    assert db.conn.execute("SELECT COUNT(*) FROM ticker_factor_snapshot").fetchone()[0] == 1


def test_factor_scoring_assigns_momentum_label_from_price_history(tmp_path):
    db = DB(str(tmp_path / "factor_momentum.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, market_beta)
        VALUES ('AMD', 'AMD', 'stock', 'USD', 1.1)
        """
    )
    start = date(2025, 1, 1)
    for i in range(260):
        price = 100 + i
        db.conn.execute(
            """
            INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
            VALUES ('AMD', ?, ?, ?, 'test')
            """,
            [start + timedelta(days=i), price, price],
        )
    repo = SentimentIngestionRepository(db.conn)

    snapshot = FactorScorer(repo).refresh_factor_snapshot(
        asset_id="AMD",
        ticker="AMD",
        snapshot_date=start + timedelta(days=259),
    )

    assert snapshot.momentum_score is not None
    assert snapshot.momentum_score >= 70
    assert "Momentum" in snapshot.factor_labels

