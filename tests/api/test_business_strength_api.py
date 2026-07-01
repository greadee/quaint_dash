from fastapi.testclient import TestClient

from dashboard.api.app import create_app
from tests.services.test_business_strength import seed_business_strength_fixture


def test_business_strength_asset_and_compare_endpoints(tmp_path):
    db_path = tmp_path / "api_business_strength.db"
    app = create_app(db_path=db_path, web_dist=tmp_path / "missing-dist")
    from dashboard.db.db_conn import DB, init_db

    db = DB(db_path)
    init_db(db)
    seed_business_strength_fixture(db.conn)
    db.conn.close()

    with TestClient(app) as client:
        asset = client.get("/api/v1/assets/NVDA/business-strength")
        assert asset.status_code == 200
        payload = asset.json()
        assert payload["template_code"] == "semiconductor_designer"
        assert payload["category_scores"]
        assert payload["future_research_enabled"] is False

        catalog_alias = client.get("/api/v1/assets/WCN/business-strength")
        assert catalog_alias.status_code == 200
        assert catalog_alias.json()["asset_id"] == "WCN.TO"
        assert catalog_alias.json()["template_code"] == "waste_management"

        compare = client.post("/api/v1/compare/business-strength", json={"symbols": ["NVDA", "TSM"]})
        assert compare.status_code == 200
        comparison = compare.json()
        assert comparison["mixed_templates"] is True
        assert len(comparison["assets"]) == 2
        assert comparison["warning"].startswith("Category scores are comparable")
