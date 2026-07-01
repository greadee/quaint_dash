"""Conservative article-to-asset resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass

from dashboard.news.models import AssetNewsMatch, NormalizedNewsArticle

AMBIGUOUS_TICKERS = {
    "A",
    "AI",
    "ALL",
    "ARE",
    "C",
    "CAN",
    "CAT",
    "F",
    "FOR",
    "GO",
    "IT",
    "NOW",
    "ON",
    "OR",
    "SO",
    "USA",
}


@dataclass(frozen=True, slots=True)
class AssetIdentity:
    asset_id: str
    ticker: str
    name: str | None = None
    exchange_code: str | None = None
    country: str | None = None
    aliases: tuple[str, ...] = ()


class EntityResolver:
    def __init__(self, conn) -> None:
        self.conn = conn

    def resolve(self, article: NormalizedNewsArticle) -> list[AssetNewsMatch]:
        identities = self._asset_identities()
        matches: dict[str, AssetNewsMatch] = {}
        provider_symbols = {symbol.upper().strip() for symbol in article.symbols}
        text = f"{article.headline} {article.summary or ''} {' '.join(article.entities)}"

        for asset in identities:
            ticker = asset.ticker.upper().strip()
            if not ticker:
                continue

            if ticker in provider_symbols or asset.asset_id.upper() in provider_symbols:
                matches[asset.asset_id] = AssetNewsMatch(
                    asset_id=asset.asset_id,
                    ticker=ticker,
                    relevance_score=0.96,
                    confidence_score=0.95,
                    match_method="provider_symbol",
                    mention_type="security",
                    is_primary_entity=not matches,
                    provider_assigned=True,
                )
                continue

            exchange_symbol = f"{ticker}.{(asset.exchange_code or '').upper()}".strip(".")
            if exchange_symbol in provider_symbols:
                matches[asset.asset_id] = AssetNewsMatch(
                    asset_id=asset.asset_id,
                    ticker=ticker,
                    relevance_score=0.94,
                    confidence_score=0.94,
                    match_method="provider_symbol",
                    mention_type="security",
                    is_primary_entity=not matches,
                    provider_assigned=True,
                )
                continue

            for alias in asset.aliases:
                if _contains_phrase(text, alias):
                    matches[asset.asset_id] = AssetNewsMatch(
                        asset_id=asset.asset_id,
                        ticker=ticker,
                        relevance_score=0.82,
                        confidence_score=0.82,
                        match_method="alias_match",
                        mention_type="company",
                        is_primary_entity=not matches,
                    )
                    break
            if asset.asset_id in matches:
                continue

            if asset.name and len(asset.name) >= 4 and _contains_phrase(text, asset.name):
                matches[asset.asset_id] = AssetNewsMatch(
                    asset_id=asset.asset_id,
                    ticker=ticker,
                    relevance_score=0.78,
                    confidence_score=0.78,
                    match_method="exact_company_name",
                    mention_type="company",
                    is_primary_entity=not matches,
                )
                continue

            if ticker not in AMBIGUOUS_TICKERS and _contains_ticker(text, ticker):
                matches[asset.asset_id] = AssetNewsMatch(
                    asset_id=asset.asset_id,
                    ticker=ticker,
                    relevance_score=0.55,
                    confidence_score=0.48,
                    match_method="ticker_match",
                    mention_type="ticker",
                    is_primary_entity=False,
                )

        return sorted(matches.values(), key=lambda item: (-item.confidence_score, item.ticker))

    def _asset_identities(self) -> list[AssetIdentity]:
        rows = self.conn.execute(
            """
            SELECT
                a.asset_id,
                COALESCE(a.symbol, a.asset_id) AS ticker,
                a.name,
                a.exchange_code,
                a.country,
                LIST(alias.alias) FILTER (WHERE alias.alias IS NOT NULL) AS aliases
            FROM asset a
            LEFT JOIN asset_entity_alias alias ON alias.asset_id = a.asset_id
            WHERE a.track = TRUE
            GROUP BY a.asset_id, a.symbol, a.name, a.exchange_code, a.country
            ORDER BY ticker
            """
        ).fetchall()
        return [
            AssetIdentity(
                asset_id=row[0],
                ticker=row[1],
                name=row[2],
                exchange_code=row[3],
                country=row[4],
                aliases=tuple(row[5] or ()),
            )
            for row in rows
        ]


def _contains_ticker(text: str, ticker: str) -> bool:
    pattern = re.compile(rf"(?<![A-Za-z0-9_])\$?{re.escape(ticker)}(?![A-Za-z0-9_])", re.IGNORECASE)
    return bool(pattern.search(text))


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized = phrase.strip()
    if not normalized:
        return False
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_]){re.escape(normalized)}(?![A-Za-z0-9_])",
        re.IGNORECASE,
    )
    return bool(pattern.search(text))
