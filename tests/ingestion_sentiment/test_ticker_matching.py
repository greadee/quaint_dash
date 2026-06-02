from __future__ import annotations

from dashboard.ingestion_sentiment.models import AssetRef
from dashboard.ingestion_sentiment.ticker_matching import find_ticker_mentions


def test_matches_cashtags_and_plain_tickers():
    assets = [
        AssetRef(asset_id="AMD", ticker="AMD", name="Advanced Micro Devices"),
        AssetRef(asset_id="NVDA", ticker="NVDA", name="NVIDIA Corporation"),
    ]

    mentions = find_ticker_mentions("$AMD and NVDA are moving together.", assets)

    assert [(m.ticker, m.mention_reason) for m in mentions] == [
        ("AMD", "cashtag"),
        ("NVDA", "ticker"),
    ]


def test_ambiguous_ticker_requires_cashtag_or_company_name():
    assets = [
        AssetRef(asset_id="NOW", ticker="NOW", name="ServiceNow Inc."),
        AssetRef(asset_id="ON", ticker="ON", name="ON Semiconductor"),
    ]

    plain_mentions = find_ticker_mentions("Buy it now while the trend is on.", assets)
    tagged_mentions = find_ticker_mentions("$NOW has strong enterprise demand.", assets)
    name_mentions = find_ticker_mentions("ServiceNow Inc. raised guidance.", assets)

    assert plain_mentions == []
    assert [(m.ticker, m.mention_reason) for m in tagged_mentions] == [("NOW", "cashtag")]
    assert [(m.ticker, m.mention_reason) for m in name_mentions] == [
        ("NOW", "company_name")
    ]


def test_one_item_can_map_to_multiple_tickers():
    assets = [
        AssetRef(asset_id="AMD", ticker="AMD", name="Advanced Micro Devices"),
        AssetRef(asset_id="ASML", ticker="ASML", name="ASML Holding"),
    ]

    mentions = find_ticker_mentions("ASML demand helps AMD accelerator supply.", assets)

    assert {m.ticker for m in mentions} == {"AMD", "ASML"}

