from fastapi.testclient import TestClient

from dashboard.api.app import API_VERSION, create_app


def test_health_reports_api_and_database_status(tmp_path):
    app = create_app(tmp_path / "api.db")

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "api_version": API_VERSION,
        "database": "connected",
    }


def test_openapi_document_is_available(tmp_path):
    app = create_app(tmp_path / "api.db")

    with TestClient(app) as client:
        response = client.get("/api/openapi.json")

    assert response.status_code == 200
    assert "/api/v1/health" in response.json()["paths"]
