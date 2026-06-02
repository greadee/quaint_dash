"""Official Reddit API provider placeholder."""

from __future__ import annotations

import os
from datetime import datetime

from dashboard.ingestion_sentiment.models import SocialPostInput


class RedditProvider:
    name = "reddit"

    def fetch_posts_for_ticker(
        self,
        ticker: str,
        since: datetime | None,
    ) -> list[SocialPostInput]:
        if not all(
            [
                os.getenv("REDDIT_CLIENT_ID"),
                os.getenv("REDDIT_CLIENT_SECRET"),
                os.getenv("REDDIT_USER_AGENT"),
            ]
        ):
            raise RuntimeError(
                "Reddit provider requires REDDIT_CLIENT_ID, "
                "REDDIT_CLIENT_SECRET, and REDDIT_USER_AGENT."
            )

        raise NotImplementedError(
            "Reddit API integration is not implemented yet; inject a provider in tests."
        )

