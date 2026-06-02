from __future__ import annotations

from dashboard.db.db_conn import DB, init_db


def table_columns(conn, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()}


def test_init_db_creates_sentiment_tables(tmp_path):
    db = DB(str(tmp_path / "sentiment_schema.db"))
    init_db(db)

    expected_tables = {
        "news_source",
        "news_article",
        "news_article_asset_mention",
        "social_source",
        "social_post",
        "social_post_asset_mention",
        "sentiment_observation",
        "ticker_sentiment_daily",
        "ticker_news_daily",
        "ticker_factor_snapshot",
        "ticker_quant_rating_snapshot",
        "sentiment_ingestion_state",
    }

    rows = db.conn.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'main'
        """
    ).fetchall()

    assert expected_tables.issubset({row[0] for row in rows})
    assert "asset_id" in table_columns(db.conn, "ticker_factor_snapshot")
    assert "overall_quant_rating" in table_columns(
        db.conn,
        "ticker_quant_rating_snapshot",
    )

