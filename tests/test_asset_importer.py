from dashboard.services.asset_importer import AssetImporter


class FakeManager:
    conn = None


def test_asset_importer_maps_direct_shares_outstanding():
    importer = AssetImporter(FakeManager(), api_key="test")

    fields = importer._map_profile_to_asset_fields(
        "AAPL",
        {
            "currency": "USD",
            "companyName": "Apple Inc.",
            "marketCap": 3_000_000_000_000,
            "sharesOutstanding": 15_000_000_000,
            "price": 200,
        },
    )

    assert fields["shares_outstanding"] == 15_000_000_000


def test_asset_importer_derives_shares_outstanding_from_market_cap_and_price():
    importer = AssetImporter(FakeManager(), api_key="test")

    fields = importer._map_profile_to_asset_fields(
        "MSFT",
        {
            "currency": "USD",
            "companyName": "Microsoft Corporation",
            "marketCap": 3_200_000_000_000,
            "price": 400,
        },
    )

    assert fields["shares_outstanding"] == 8_000_000_000
