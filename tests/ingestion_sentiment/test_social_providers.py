from __future__ import annotations

from datetime import datetime

from dashboard.ingestion_sentiment.providers.reddit_provider import RedditProvider
from dashboard.ingestion_sentiment.providers.x_provider import XProvider


class FakeJsonClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request_json(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError("No fake response queued")
        return self.responses.pop(0)


def test_reddit_provider_fetches_and_normalizes_posts():
    client = FakeJsonClient(
        [
            {"access_token": "token-1"},
            {
                "data": {
                    "children": [
                        {
                            "data": {
                                "name": "t3_post1",
                                "subreddit": "stocks",
                                "title": "$AMD earnings thread",
                                "selftext": "Bullish and strong after guidance.",
                                "author": "investor_1",
                                "permalink": "/r/stocks/comments/post1/amd/",
                                "created_utc": 1767614400,
                                "score": 42,
                                "num_comments": 7,
                            }
                        },
                        {
                            "data": {
                                "name": "t3_old",
                                "subreddit": "stocks",
                                "title": "$AMD old thread",
                                "created_utc": 1767520000,
                            }
                        },
                    ]
                }
            },
        ]
    )
    provider = RedditProvider(
        client_id="client",
        client_secret="secret",
        user_agent="quaint-test",
        subreddits=["stocks"],
        post_limit=10,
        http_client=client,
    )

    posts = provider.fetch_posts_for_ticker("AMD", since=datetime(2026, 1, 5, 11, 0))

    assert len(posts) == 1
    assert posts[0].provider == "reddit"
    assert posts[0].source_post_id == "t3_post1"
    assert posts[0].source_name == "r/stocks"
    assert posts[0].url == "https://www.reddit.com/r/stocks/comments/post1/amd/"
    assert posts[0].score == 42
    assert posts[0].comment_count == 7
    assert client.calls[1][2]["params"]["q"] == '("AMD" OR $AMD)'
    assert client.calls[1][2]["params"]["restrict_sr"] == "1"


def test_x_provider_fetches_recent_search_and_normalizes_posts():
    client = FakeJsonClient(
        [
            {
                "data": [
                    {
                        "id": "12345",
                        "author_id": "678",
                        "text": "$AMD looks bullish",
                        "created_at": "2026-01-05T12:00:00.000Z",
                        "public_metrics": {
                            "like_count": 9,
                            "retweet_count": 2,
                            "reply_count": 1,
                        },
                    },
                    {
                        "id": "old",
                        "text": "$AMD old",
                        "created_at": "2026-01-05T10:00:00.000Z",
                    },
                ]
            }
        ]
    )
    provider = XProvider(
        bearer_token="token",
        post_limit=10,
        include_plain_ticker=False,
        http_client=client,
    )

    posts = provider.fetch_posts_for_ticker("AMD", since=datetime(2026, 1, 5, 11, 0))

    assert len(posts) == 1
    assert posts[0].provider == "x"
    assert posts[0].source_post_id == "12345"
    assert posts[0].author == "678"
    assert posts[0].like_count == 9
    assert posts[0].repost_count == 2
    assert posts[0].reply_count == 1
    assert posts[0].url == "https://x.com/i/web/status/12345"
    assert client.calls[0][2]["params"]["query"] == "($AMD) lang:en -is:retweet"
    assert client.calls[0][2]["params"]["max_results"] == 10
