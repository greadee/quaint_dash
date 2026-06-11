from fastapi.testclient import TestClient

from dashboard.api.app import API_VERSION, create_app, _run_startup_broker_sync_if_enabled


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


def test_unbuilt_web_application_reports_clear_status(tmp_path):
    app = create_app(tmp_path / "api.db", web_dist=tmp_path / "missing-dist")

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "web_not_built"


def test_development_origin_is_allowed(tmp_path):
    app = create_app(tmp_path / "api.db")

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/health",
            headers={"Origin": "http://127.0.0.1:5173"},
        )

    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_unknown_api_route_does_not_fall_through_to_web_application(tmp_path):
    app = create_app(tmp_path / "api.db")

    with TestClient(app) as client:
        response = client.get("/api/v1/not-real")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_api_startup_broker_sync_is_disabled_by_default(tmp_path, monkeypatch):
    calls = []
    monkeypatch.delenv("BROKER_SYNC_ON_STARTUP", raising=False)
    monkeypatch.delenv("BROKER_SYNC_ON_SERVER_STARTUP", raising=False)
    monkeypatch.setattr(
        "dashboard.api.app._run_startup_broker_sync",
        lambda db_path, max_users, min_age_hours: calls.append(
            (db_path, max_users, min_age_hours)
        ),
    )

    _run_startup_broker_sync_if_enabled(tmp_path / "api.db")

    assert calls == []


def test_api_startup_broker_sync_uses_server_env_flag(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("BROKER_SYNC_ON_SERVER_STARTUP", "true")
    monkeypatch.setenv("BROKER_SYNC_MAX_USERS", "2")
    monkeypatch.setenv("BROKER_SYNC_MIN_AGE_HOURS", "6")

    monkeypatch.setattr(
        "dashboard.api.app._run_startup_broker_sync",
        lambda db_path, max_users, min_age_hours: calls.append(
            (db_path, max_users, min_age_hours)
        )
        or type(
            "DueSync",
            (),
            {
                "users_synced": 0,
                "accounts_seen": 0,
                "positions_seen": 0,
                "transactions_seen": 0,
            },
        )(),
    )

    app = create_app(tmp_path / "api.db")

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert calls == [(tmp_path / "api.db", 2, 6)]


def test_built_web_application_serves_spa_routes(tmp_path):
    web_dist = tmp_path / "dist"
    web_dist.mkdir()
    (web_dist / "index.html").write_text("<h1>Quaint Dash</h1>", encoding="utf-8")
    app = create_app(tmp_path / "api.db", web_dist=web_dist)

    with TestClient(app) as client:
        response = client.get("/assets/AAPL")

    assert response.status_code == 200
    assert "Quaint Dash" in response.text
