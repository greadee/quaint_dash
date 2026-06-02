from __future__ import annotations

from datetime import datetime

from dashboard.db.db_conn import DB, init_db
from dashboard.ingestion_sentiment.models import SocialPostInput
from dashboard.ingestion_sentiment.repo import SentimentIngestionRepository


def test_social_posts_are_upserted_idempotently(tmp_path):
    db = DB(str(tmp_path / "social_repo.db"))
    init_db(db)
    repo = SentimentIngestionRepository(db.conn)

    post = SocialPostInput(
        provider="reddit",
        source_post_id="post-1",
        source_name="reddit",
        author="test-user",
        title="AMD earnings thread",
        body="Bullish on $AMD",
        published_at=datetime(2026, 1, 2, 12, 0),
        score=10,
        comment_count=2,
    )

    first_id = repo.upsert_social_post(post)
    second_id = repo.upsert_social_post(
        SocialPostInput(
            provider="reddit",
            source_post_id="post-1",
            source_name="reddit",
            author="test-user",
            title="AMD earnings thread",
            body="Bullish on $AMD after guidance",
            published_at=datetime(2026, 1, 2, 12, 0),
            score=25,
            comment_count=5,
        )
    )

    rows = db.conn.execute("SELECT post_id, body, score, comment_count FROM social_post").fetchall()

    assert first_id == second_id
    assert rows == [(first_id, "Bullish on $AMD after guidance", 25, 5)]

