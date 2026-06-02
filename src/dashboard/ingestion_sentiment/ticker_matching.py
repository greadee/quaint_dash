"""Conservative ticker matching for sentiment items."""

from __future__ import annotations

import re
from collections.abc import Iterable

from dashboard.ingestion_sentiment.models import AssetRef, TickerMention


AMBIGUOUS_TICKERS = {
    "ALL",
    "ARE",
    "CAN",
    "FOR",
    "GO",
    "IT",
    "NOW",
    "ON",
    "OR",
    "SO",
    "USA",
}


def find_ticker_mentions(
    text: str,
    assets: Iterable[AssetRef],
    ambiguous_tickers: set[str] | None = None,
) -> list[TickerMention]:
    blocked = ambiguous_tickers if ambiguous_tickers is not None else AMBIGUOUS_TICKERS
    haystack = text or ""
    mentions: dict[str, TickerMention] = {}

    for asset in assets:
        ticker = asset.ticker.upper().strip()
        if not ticker:
            continue

        cashtag_pattern = re.compile(rf"(?<![A-Za-z0-9_])\${re.escape(ticker)}\b", re.IGNORECASE)
        ticker_pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(ticker)}(?![A-Za-z0-9_])", re.IGNORECASE)

        if cashtag_pattern.search(haystack):
            mentions[asset.asset_id] = TickerMention(
                asset_id=asset.asset_id,
                ticker=ticker,
                relevance_score=1.0,
                mention_reason="cashtag",
            )
            continue

        if ticker not in blocked and ticker_pattern.search(haystack):
            mentions[asset.asset_id] = TickerMention(
                asset_id=asset.asset_id,
                ticker=ticker,
                relevance_score=0.85,
                mention_reason="ticker",
            )
            continue

        if asset.name:
            name = asset.name.strip()
            if len(name) >= 4 and _contains_phrase(haystack, name):
                mentions[asset.asset_id] = TickerMention(
                    asset_id=asset.asset_id,
                    ticker=ticker,
                    relevance_score=0.75,
                    mention_reason="company_name",
                )

    return sorted(mentions.values(), key=lambda item: item.ticker)


def _contains_phrase(text: str, phrase: str) -> bool:
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_]){re.escape(phrase)}(?![A-Za-z0-9_])",
        re.IGNORECASE,
    )
    return bool(pattern.search(text))

