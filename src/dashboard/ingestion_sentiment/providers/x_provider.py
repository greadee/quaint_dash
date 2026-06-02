"""Official X API provider placeholder."""

from __future__ import annotations

import os
from datetime import datetime

from dashboard.ingestion_sentiment.models import SocialPostInput


class XProvider:
    name = "x"

    def fetch_posts_for_ticker(
        self,
        ticker: str,
        since: datetime | None,
    ) -> list[SocialPostInput]:
        if not os.getenv("X_BEARER_TOKEN"):
            raise RuntimeError("X provider requires X_BEARER_TOKEN.")

        raise NotImplementedError(
            "X recent-search integration is not implemented yet; inject a provider in tests."
        )

