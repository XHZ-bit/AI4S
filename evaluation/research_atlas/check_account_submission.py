"""Isolated account HTTP smoke check; never starts services or sends mail/model calls."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
profile = (ROOT / ".tmp" / "aic-account-smoke" / uuid4().hex).resolve()
if not profile.is_relative_to((ROOT / ".tmp" / "aic-account-smoke").resolve()):
    raise RuntimeError("Unsafe account smoke directory")
profile.mkdir(parents=True)
os.environ.update(DATA_DIR=str(profile), ATLAS_ENV_FILE=str(profile / "no-env"), ACCESS_MODE="local",
                  DASHSCOPE_API_KEY="", KNOWLEDGE_MODEL_ENABLED="false", RESEARCH_MODEL_ENABLED="false",
                  OFFLINE_MODE="true", SMTP_HOST="", AUTH_PUBLIC_URL="", GROBID_BASE_URL="http://127.0.0.1:1")
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


def run():
    report = {"scope": "fresh isolated local profile, no lifespan/model/mail", "profile": str(profile), "checks": {}}
    alice, bob = TestClient(app), TestClient(app)
    secret = "synthetic account smoke passphrase"
    for client, name in ((alice, "alice"), (bob, "bob")):
        result = client.post("/api/auth/register", json={"username": name, "password": secret})
        assert result.status_code == 201, result.text
        assert result.json()["user"]["username"] == name
        client.headers["X-Atlas-CSRF"] = result.json()["csrf_token"]
        assert client.get("/api/auth/session").json()["user"]["username"] == name
    report["checks"]["real_registration_and_session"] = True
    project_body = {"title": "Synthetic private project", "research_question": "Check account boundaries",
                    "domain": "custom", "constraints": {"version": 1, "objective": "Account smoke"}}
    saved_header = alice.headers.pop("X-Atlas-CSRF")
    assert alice.post("/api/projects", json=project_body).status_code == 403
    alice.headers["X-Atlas-CSRF"] = saved_header
    project = alice.post("/api/projects", json=project_body)
    assert project.status_code == 201, project.text
    pid = project.json()["id"]
    assert bob.get("/api/projects/" + pid).status_code == 404
    assert alice.get("/api/projects/" + pid).status_code == 200
    report["checks"]["csrf_and_private_project"] = True
    assert alice.post("/api/auth/logout").status_code == 200
    assert alice.get("/api/auth/session").json()["user"] is None
    assert alice.get("/api/projects/" + pid).status_code == 404
    result = alice.post("/api/auth/login", json={"username": "alice", "password": secret})
    assert result.status_code == 200
    alice.headers["X-Atlas-CSRF"] = result.json()["csrf_token"]
    assert alice.get("/api/projects/" + pid).status_code == 200
    report["checks"]["logout_and_real_password_login"] = True
    assert "HttpOnly" in result.headers["set-cookie"] and "SameSite=strict" in result.headers["set-cookie"]
    report["checks"]["session_cookie_flags"] = True
    alice.close()
    bob.close()
    output = ROOT / ".tmp" / "aic-account-smoke-result.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    run()
