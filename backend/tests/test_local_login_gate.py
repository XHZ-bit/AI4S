from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def test_local_login_required_enforces_api_and_account_scope(monkeypatch):
    monkeypatch.setenv("REQUIRE_LOGIN", "true")
    get_settings.cache_clear()
    with TestClient(app) as client:
        assert client.get("/api/auth/session").json()["require_login"] is True
        assert client.get("/api/projects").status_code == 401
        assert client.get("/health").status_code == 200
        registered = client.post("/api/auth/register", json={"username": "login_test_user", "password": "test-password-123"})
        assert registered.status_code == 201
        assert registered.json()["user"]["username"] == "login_test_user"
        assert client.get("/api/projects").status_code == 200
    get_settings.cache_clear()
