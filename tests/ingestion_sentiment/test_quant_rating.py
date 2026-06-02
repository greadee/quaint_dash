from __future__ import annotations

from datetime import date

from dashboard.db.db_conn import DB, init_db
from dashboard.ingestion_sentiment.models import FactorSnapshotInput
from dashboard.ingestion_sentiment.repo import SentimentIngestionRepository
from dashboard.ingestion_sentiment.scoring import QuantRatingScorer


def test_quant_rating_uses_factor_snapshot_labels(tmp_path):
    db = DB(str(tmp_path / "quant_rating.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES ('AMD', 'AMD', 'stock', 'USD')
        """
    )
    repo = SentimentIngestionRepository(db.conn)
    snapshot_date = date(2026, 1, 5)
    repo.upsert_factor_snapshot(
        FactorSnapshotInput(
            asset_id="AMD",
            ticker="AMD",
            snapshot_date=snapshot_date,
            growth_score=82,
            quality_score=78,
            momentum_score=88,
            overall_factor_score=81,
            factor_labels=["Growth", "Quality", "Momentum"],
            explanation="test snapshot",
        )
    )

    rating = QuantRatingScorer(repo).refresh_quant_rating(
        asset_id="AMD",
        ticker="AMD",
        snapshot_date=snapshot_date,
    )

    assert rating.overall_quant_rating == "Strong Buy"
    assert rating.factor_profile == "Compounder"
    assert rating.growth_rating == "A"
    assert db.conn.execute("SELECT COUNT(*) FROM ticker_quant_rating_snapshot").fetchone()[0] == 1

