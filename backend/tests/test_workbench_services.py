import httpx
from fastapi.testclient import TestClient
from app.main import app


def signed(client, name):
    r = client.post(
        "/api/auth/register", json={"username": name, "password": "test-password-123!"}
    )
    assert r.status_code == 201, r.text
    return {"X-Atlas-CSRF": r.json()["csrf_token"]}


def project(client, headers=None):
    r = client.post(
        "/api/projects",
        json={
            "title": "Research workspace",
            "research_question": "How does expectation work?",
            "domain": "image_anomaly_detection",
            "constraints": {"version": 1, "objective": "Understand methods"},
        },
        headers=headers or {},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_records_conflicts_project_search_export_and_isolation():
    with TestClient(app) as a, TestClient(app) as b:
        ha = signed(a, "records-owner")
        hb = signed(b, "records-other")
        pid = project(a, ha)
        body = {
            "id": "test-note",
            "title": "Bayes note",
            "body": "conditional probability",
            "project_id": pid,
        }
        r = a.post("/api/workbench/records", json=body, headers=ha)
        assert r.status_code == 200, r.text
        assert r.json()["version"] == 1
        assert (
            a.post("/api/workbench/records", json=body, headers=ha).status_code == 409
        )
        body["version"] = 1
        body["body"] = "updated probability"
        assert (
            a.post("/api/workbench/records", json=body, headers=ha).json()["version"]
            == 2
        )
        assert (
            a.get("/api/workbench/search", params={"q": "probability"}).json()["items"][
                0
            ]["kind"]
            == "笔记 / 草稿"
        )
        assert b.get("/api/workbench/records/test-note").status_code == 404
        assert b.get("/api/workbench/projects/" + pid).status_code == 404
        assert (
            b.post(
                "/api/workbench/records", json={**body, "id": "other"}, headers=hb
            ).status_code
            == 404
        )
        exported = a.get("/api/workbench/export").json()
        assert len(exported["workspace_records"]) == 1 and "provider" not in exported
        assert (
            a.get("/api/workbench/projects/" + pid).json()["records"][0]["body"]
            == "updated probability"
        )


def test_identifier_import_dedup_and_invalid_url(isolated_services):
    route = isolated_services.get(
        "https://api.crossref.org/works/10.1234%2Fexample"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {
                    "title": ["Test paper"],
                    "published": {"date-parts": [[2024]]},
                    "author": [],
                }
            },
        )
    )
    with TestClient(app) as c:
        pid = project(c)
        r = c.post(
            "/api/workbench/import",
            json={"value": "https://doi.org/10.1234/example", "project_id": pid},
        )
        assert r.status_code == 200, r.text
        assert not r.json()["duplicate"]
        assert c.post(
            "/api/workbench/import",
            json={"value": "10.1234/example", "project_id": pid},
        ).json()["duplicate"]
        assert route.call_count == 1
        assert len(c.get("/api/workbench/projects/" + pid).json()["papers"]) == 1
        assert (
            c.post(
                "/api/workbench/import", json={"value": "http://127.0.0.1/private"}
            ).status_code
            == 422
        )
        assert (
            c.post(
                "/api/workbench/import",
                json={"value": "10.1234/example", "project_id": "missing"},
            ).status_code
            == 404
        )


def test_recovery_revokes_sessions_and_is_single_use():
    with TestClient(app) as a, TestClient(app) as b, TestClient(app) as recovery:
        ha = signed(a, "recovery-person")
        b.post(
            "/api/auth/login",
            json={"username": "recovery-person", "password": "test-password-123!"},
        )
        assert len(a.get("/api/auth/sessions").json()["items"]) == 2
        assert a.post("/api/auth/sessions/revoke-others", headers=ha).status_code == 200
        assert b.get("/api/auth/session").json()["user"] is None
        issued = a.post(
            "/api/auth/recovery-code",
            json={"password": "test-password-123!"},
            headers=ha,
        )
        assert issued.status_code == 200, issued.text
        code = issued.json()["code"]
        req = {
            "username": "recovery-person",
            "code": code,
            "new_password": "recovered-password-123!",
        }
        assert (
            recovery.post(
                "/api/auth/recover", json={**req, "code": "wrong"}
            ).status_code
            == 401
        )
        assert recovery.post("/api/auth/recover", json=req).status_code == 200
        assert recovery.post("/api/auth/recover", json=req).status_code == 401
        assert a.get("/api/auth/session").json()["user"] is None
        assert (
            recovery.post(
                "/api/auth/login",
                json={"username": req["username"], "password": req["new_password"]},
            ).status_code
            == 200
        )


def test_project_preferences_apply_to_tutor_and_history(monkeypatch):
    from app import preferences

    captured = []

    def make_plan(question, source, profile, features, history):
        captured.append(features)
        return {
            "title": "Project lesson",
            "goal": "Learn",
            "steps": [{"question": "Why", "explanation": "Because"}],
            "terms": [],
            "quiz": [],
            "exercise": None,
            "prerequisites": [],
        }, "fixture"

    monkeypatch.setattr("app.api.tutoring.make_plan", make_plan)
    with TestClient(app) as c:
        pid = project(c)
        flags = preferences.Features().model_dump()
        flags["coding"] = False
        assert (
            c.post(
                "/api/workbench/projects/" + pid + "/preferences",
                json={"features": flags},
            ).status_code
            == 200
        )
        r = c.post(
            "/api/tutor/sessions",
            json={"question": "Explain this method", "project_id": pid},
        )
        assert r.status_code == 201, r.text
        assert not captured[-1]["coding"]
        assert (
            c.get("/api/workbench/projects/" + pid).json()["sessions"][0]["id"]
            == r.json()["id"]
        )


def test_recovery_guess_rate_limit():
    with TestClient(app) as c:
        req = {
            "username": "unknown",
            "code": "wrong",
            "new_password": "long-enough-password",
        }
        assert all(
            c.post("/api/auth/recover", json=req).status_code == 401 for _ in range(5)
        )
        assert c.post("/api/auth/recover", json=req).status_code == 429
