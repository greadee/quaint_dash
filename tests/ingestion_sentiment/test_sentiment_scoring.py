from __future__ import annotations

from dashboard.ingestion_sentiment.models import NewsArticleInput, SocialPostInput
from dashboard.ingestion_sentiment.scoring import RulesBasedSentimentScorer


def test_rules_based_article_scoring_is_deterministic():
    scorer = RulesBasedSentimentScorer()
    article = NewsArticleInput(
        source_name="Fake News",
        provider="fake-news",
        title="AMD beats estimates and raises guidance",
        summary="Strong growth supports upside.",
    )

    first = scorer.score_article(article, "AMD")
    second = scorer.score_article(article, "AMD")

    assert first.sentiment_label == "bullish"
    assert first.sentiment_score == second.sentiment_score
    assert first.confidence == second.confidence
    assert "bullish_keywords=" in (first.explanation or "")


def test_engagement_changes_weight_not_raw_sentiment():
    scorer = RulesBasedSentimentScorer()
    quiet = SocialPostInput(
        provider="reddit",
        source_post_id="quiet",
        source_name="reddit",
        body="AMD looks bullish after a strong quarter.",
        score=1,
    )
    busy = SocialPostInput(
        provider="reddit",
        source_post_id="busy",
        source_name="reddit",
        body="AMD looks bullish after a strong quarter.",
        score=200,
        comment_count=50,
    )

    quiet_score = scorer.score_post(quiet, "AMD")
    busy_score = scorer.score_post(busy, "AMD")

    assert quiet_score.sentiment_score == busy_score.sentiment_score
    assert busy_score.engagement_weight > quiet_score.engagement_weight

