from contextlib import closing
from fastapi.testclient import TestClient
from app.main import app
from app.db.sqlite import connect, upsert_paper
from app.models.paper import PaperDoc


def draft(stage="exploring"):
    return {
        "title": "从兴趣开始",
        "research_question": "",
        "domain": "custom",
        "custom_domain": "数字人文与人机交互",
        "stage": stage,
        "constraints": {"version": 1, "objective": ""},
    }


def test_open_ended_project_keeps_unknowns_and_can_be_refined():
    with TestClient(app) as c:
        r = c.post("/api/projects", json=draft())
        assert r.status_code == 201, r.text
        p = r.json()
        assert (
            p["custom_domain"] == "数字人文与人机交互"
            and p["research_question"] == ""
            and p["constraints"]["objective"] == ""
        )
        assert c.get("/api/projects/" + p["id"]).json()["stage"] == "exploring"
        path = "/api/projects/" + p["id"]
        assert (
            c.patch(
                path, json={"expected_version": 1, "stage": "validating"}
            ).status_code
            == 422
        )
        update = {
            "expected_version": 1,
            "stage": "framing",
            "research_question": "哪些场景值得进一步了解？",
            "domain": "custom",
            "custom_domain": "跨学科探索",
        }
        r = c.patch(path, json=update)
        assert r.status_code == 200, r.text
        assert (
            r.json()["stage"] == "framing" and r.json()["custom_domain"] == "跨学科探索"
        )
        assert c.patch(path, json=update).status_code == 409
        plan = c.get("/api/workbench/projects/" + p["id"] + "/next-experiment").json()
        assert (
            "探索记录" in plan["markdown"]
            and "浏览器合成数据实验" not in plan["markdown"]
        )
        assert c.post("/api/projects", json=draft("validating")).status_code == 422


def test_topic_directions_are_grounded_in_local_input_and_never_call_models(
    monkeypatch,
):
    def fail(*a, **k):
        raise AssertionError("unexpected model call")

    monkeypatch.setattr("app.api.tutoring.make_plan", fail)
    with TestClient(app) as c:
        with closing(connect()) as db:
            upsert_paper(
                db,
                PaperDoc(
                    uid="topic-human",
                    title="Human collaboration in robotics",
                    abstract="How people collaborate with robots.",
                    year=2025,
                ).model_dump(),
            )
            db.commit()
        r = c.post(
            "/api/workbench/topic-exploration",
            json={
                "interests": "collaboration",
                "background": "Python",
                "resources": "每周两小时",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert (
            len(body["directions"]) == 3 and body["papers"][0]["uid"] == "topic-human"
        )
        assert all("collaboration" in x["question"] for x in body["directions"])
        assert "每周两小时" in body["directions"][2]["needed"]
        chinese = c.post(
            "/api/workbench/topic-exploration", json={"interests": "我想了解人机协作"}
        ).json()
        assert chinese["papers"][0]["uid"] == "topic-human"
        assert (
            c.post(
                "/api/workbench/topic-exploration",
                json={"interests": "unrelated-keyword"},
            ).json()["papers"]
            == []
        )
        assert (
            c.post(
                "/api/workbench/topic-exploration", json={"project_id": "other-project"}
            ).status_code
            == 404
        )


def test_topic_library_and_project_are_account_isolated():
    with TestClient(app) as a, TestClient(app) as b:

        def login(client, name):
            r = client.post(
                "/api/auth/register",
                json={"username": name, "password": "test-password-123!"},
            )
            client.headers["X-Atlas-CSRF"] = r.json()["csrf_token"]

        login(a, "topic-owner")
        p = a.post("/api/projects", json=draft()).json()
        login(b, "topic-other")
        assert (
            b.post(
                "/api/workbench/topic-exploration", json={"project_id": p["id"]}
            ).status_code
            == 404
        )


def test_dependency_edit_preserves_existing_provenance_but_does_not_trust_new_labels():
    with TestClient(app) as c:
        before = c.get("/api/stride/dependencies").json()
        original = before["data"][0]
        new = {"source": "dp-5", "target": "vectors", "origin": "teaching_suggestion"}
        # Pick a separate existing base edge so the new pair has no return path.
        r = c.post(
            "/api/stride/dependencies",
            json={"version": before["version"], "edges": [original, new]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"][0]["origin"] == original["origin"]
        assert r.json()["data"][1]["origin"] == "user_input"
