"""Deterministic category classification for normalized news."""

from __future__ import annotations

from dashboard.news.models import NormalizedNewsArticle

CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("bankruptcy", ("bankruptcy", "chapter 11", "insolvency")),
    ("merger_acquisition", ("acquire", "acquisition", "merger", "takeover", "buyout")),
    ("guidance", ("guidance", "outlook", "forecast")),
    ("earnings", ("earnings", "revenue", "eps", "quarterly results", "results")),
    ("analyst_rating", ("upgrade", "downgrade", "price target", "initiates coverage")),
    ("regulatory", ("regulator", "regulatory", "sec", "antitrust", "probe", "investigation")),
    ("litigation", ("lawsuit", "litigation", "settlement", "court")),
    ("management_change", ("ceo", "cfo", "resigns", "appointed", "executive")),
    ("capital_raise", ("capital raise", "offering", "share sale")),
    ("buyback", ("buyback", "repurchase")),
    ("dividend", ("dividend",)),
    ("stock_split", ("stock split", "split shares")),
    ("product_launch", ("launches", "unveils", "product launch")),
    ("central_bank", ("federal reserve", "central bank", "rate decision")),
    ("economic_data", ("jobs report", "inflation", "cpi", "pce", "gdp")),
    ("cybersecurity", ("cyberattack", "data breach", "ransomware")),
    ("press_release", ("press release",)),
)


def classify_article(article: NormalizedNewsArticle) -> list[str]:
    categories = list(dict.fromkeys(article.categories))
    text = f"{article.headline} {article.summary or ''}".lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in text for keyword in keywords) and category not in categories:
            categories.append(category)
    if not categories:
        categories.append("general")
    return categories
