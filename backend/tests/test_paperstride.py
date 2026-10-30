import json
from contextlib import closing
import httpx
from fastapi.testclient import TestClient
from app.main import app
from app.db.sqlite import connect, upsert_paper
from app.db.workspace import save_document
from app.models.paper import PaperDoc, ParsedPaper
from app.api.stride import setup
from app.diffusion_curriculum import LESSONS


def project(c):
    r = c.post(
        "/api/projects",
        json={
            "title": "Diffusion study",
            "research_question": "How can action diffusion work?",
            "domain": "robot_policy_learning",
            "constraints": {"version": 1, "objective": "Understand then test"},
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def paper(c, pid, uid="2303.04137"):
    with closing(connect()) as db:
        setup(db)
        upsert_paper(
            db,
            PaperDoc(
                uid=uid, arxiv_id=uid, title="Test action method", year=2023
            ).model_dump(),
        )
        save_document(
            db,
            uid,
            ParsedPaper(
                uid=uid,
                title="Test action method",
                abstract="",
                sections=[
                    {
                        "heading": "Method",
                        "text": "Our method predicts noise conditioned on observations.",
                        "page": 2,
                    }
                ],
            ),
        )
        db.commit()
    r = c.post(f"/api/workbench/projects/{pid}/papers", json={"paper_uid": uid})
    assert r.status_code == 200, r.text


def test_matrix_incremental_conflict_provenance_and_history():
    with TestClient(app) as c:
        pid = project(c)
        paper(c, pid)
        path = f"/api/workbench/projects/{pid}/matrix"
        first = c.post(path + "/extract").json()
        assert first["created"] == 6
        assert c.post(path + "/extract").json()["cache_hits"] == 6
        data = c.get(path).json()
        candidate = next(x for x in data["candidates"] if x["column_id"] == "method")
        assert candidate["data"]["page"] == 2
        body = {
            "paper_uid": "2303.04137",
            "column_id": "method",
            "version": 0,
            "content": "My correction",
            "candidate": candidate["fingerprint"],
        }
        r = c.post(path + "/cells", json=body)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["origin"] == "user_input"
        assert c.post(path + "/cells", json=body).status_code == 409
        c.post(path + "/extract")
        assert c.get(path).json()["cells"][0]["data"]["content"] == "My correction"
        columns = data["data"]
        columns[1]["rule"] = "changed rule"
        assert (
            c.post(
                path + "/columns", json={"version": 0, "columns": columns}
            ).status_code
            == 200
        )
        assert c.post(path + "/extract").json()["created"] == 1
        history = c.get(
            path + "/history", params={"paper_uid": "2303.04137", "column_id": "method"}
        ).json()["items"]
        assert len(history) == 1
        assert (
            c.post(
                path + "/columns", json={"version": 0, "columns": columns}
            ).status_code
            == 409
        )
        edited = c.post(
            path + "/cells",
            json={
                **body,
                "version": 1,
                "candidate": None,
                "content": "Second correction",
            },
        ).json()
        assert (
            edited["data"]["page"] == 2
            and edited["data"]["passage_id"] == candidate["data"]["passage_id"]
        )


def test_scene_dependencies_and_feature_gates():
    with TestClient(app) as c:
        pid = project(c)
        paper(c, pid)
        path = f"/api/workbench/projects/{pid}/scene"
        body = {"version": 0, "view": "reading", "paper": "2303.04137", "page": 2}
        assert c.post(path, json=body).status_code == 200
        assert c.get(path).json()["data"]["page"] == 2
        assert c.post(path, json=body).status_code == 409
        _dep = c.get("/api/stride/dependencies", params={"project_id": pid}).json()
        edges = [
            {"source": "dp-1", "target": "dp-2"},
            {"source": "dp-2", "target": "dp-1"},
        ]
        assert (
            c.post(
                "/api/stride/dependencies?project_id=" + pid,
                json={"version": 0, "edges": edges},
            ).status_code
            == 422
        )
        assert (
            c.post(
                "/api/stride/dependencies?project_id=" + pid,
                json={"version": 0, "edges": edges[:1]},
            ).status_code
            == 200
        )
        assert (
            len(
                c.get("/api/stride/dependencies/history?project_id=" + pid).json()[
                    "items"
                ]
            )
            == 1
        )
        flags = c.get("/api/workbench/projects/" + pid).json()["features"]
        flags.update(coding=False, quizzes=False, graph=False)
        c.post(
            "/api/workbench/projects/" + pid + "/preferences", json={"features": flags}
        )
        items = c.get("/api/stride/curriculum", params={"project_id": pid}).json()[
            "items"
        ]
        assert all(x["exercise"] is None and not x["quiz"] for x in items)
        assert c.get("/api/stride/dependencies?project_id=" + pid).status_code == 409
        assert (
            c.post(
                "/api/tutor/lessons/dp-1/quiz",
                json={"question_index": 0, "answer": 0, "project_id": pid},
            ).status_code
            == 409
        )


def test_curriculum_checked_examples_and_progress():
    for lesson in LESSONS:
        env = {}
        exec(lesson["exercise"]["solution"], env)
        exec(lesson["exercise"]["tests"], env)
    with TestClient(app) as c:
        pid = project(c)
        a = c.get(
            "/api/stride/curriculum", params={"project_id": pid, "persona": "robotics"}
        ).json()
        b = c.get(
            "/api/stride/curriculum",
            params={"project_id": pid, "persona": "generative"},
        ).json()
        assert a["items"][0]["id"] != b["items"][0]["id"] and len(a["items"]) == 5
        for i, q in enumerate(LESSONS[0]["quiz"]):
            r = c.post(
                "/api/tutor/lessons/dp-1/quiz",
                json={"question_index": i, "answer": q["answer"], "project_id": pid},
            )
            assert r.status_code == 200, r.text
        c.post(
            "/api/tutor/lessons/dp-1/practice",
            json={
                "exercise_id": LESSONS[0]["exercise"]["id"],
                "code": "pass",
                "passed": True,
                "project_id": pid,
            },
        )
        c.post(
            "/api/tutor/lessons/dp-1/quiz",
            json={"question_index": 0, "answer": 0, "project_id": pid},
        )
        checks = c.get("/api/stride/curriculum", params={"project_id": pid}).json()[
            "checks"
        ]
        assert checks[0]["state"] == "本轮通过" and checks[0]["checked"] == 2
        assert (
            c.get("/api/stride/curriculum").json()["checks"][0]["state"] == "尚未检查"
        )
        plan = c.get(f"/api/workbench/projects/{pid}/next-experiment")
        assert plan.status_code == 200, plan.text
        assert (
            "任务与环境版本" in plan.json()["markdown"]
            and "未知" in plan.json()["markdown"]
        )


def test_citation_direction_cache_and_failure(isolated_services):
    with TestClient(app) as c:
        pid = project(c)
        paper(c, pid)
        route = isolated_services.get(
            "https://api.semanticscholar.org/graph/v1/paper/arXiv:2303.04137/references"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "citedPaper": {
                                "paperId": "ref",
                                "title": "DDPM",
                                "externalIds": {"ArXiv": "2006.11239"},
                            }
                        }
                    ],
                    "next": 20,
                },
            )
        )
        params = {"seed": "2303.04137", "remote": True, "project_id": pid}
        r = c.get("/api/graph/explore", params=params)
        assert r.status_code == 200, r.text
        assert (
            r.json()["items"][0]["direction"] == "references" and r.json()["next"] == 20
        )
        assert c.get("/api/graph/explore", params=params).json()["cached"]
        assert route.call_count == 1
        isolated_services.get(
            "https://api.semanticscholar.org/graph/v1/paper/arXiv:2303.04137/citations"
        ).mock(return_value=httpx.Response(429))
        r = c.get("/api/graph/explore", params={**params, "direction": "citations"})
        assert r.status_code == 200 and "限流" in r.json()["notice"]


def test_matrix_account_isolation():
    with TestClient(app) as a, TestClient(app) as b:

        def login(c, name):
            r = c.post(
                "/api/auth/register",
                json={"username": name, "password": "test-password-123!"},
            )
            c.headers["X-Atlas-CSRF"] = r.json()["csrf_token"]

        login(a, "stride-owner")
        pid = project(a)
        login(b, "stride-other")
        assert b.get(f"/api/workbench/projects/{pid}/matrix").status_code == 404
        assert (
            b.post(
                f"/api/workbench/projects/{pid}/scene",
                json={"version": 0, "view": "overview"},
            ).status_code
            == 404
        )


def test_legacy_contract_still_accepted():
    from app.models.research import ComparisonResult

    assert "research-v1.1" in str(
        ComparisonResult.model_fields["contract_version"].annotation
    )


def test_model_candidates_require_quotes_and_do_not_replay(
    isolated_services, monkeypatch
):
    from app.config import get_settings

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    get_settings.cache_clear()
    with TestClient(app) as c:
        pid = project(c)
        paper(c, pid)
        with closing(connect()) as db:
            passage = db.execute("SELECT id,text FROM passages LIMIT 1").fetchone()
        url = get_settings().llm_api_base + "/chat/completions"
        route = isolated_services.post(url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "content": "预测噪声",
                                        "quote": passage["text"],
                                        "passage_id": passage["id"],
                                        "finding": "reported",
                                    }
                                )
                            }
                        }
                    ]
                },
            )
        )
        path = f"/api/workbench/projects/{pid}/matrix/interpret"
        body = {"paper_uid": "2303.04137", "column_id": "method"}
        first = c.post(path, json=body)
        assert first.status_code == 200, first.text
        assert first.json()["data"]["origin"] == "model_suggestion"
        assert c.post(path, json=body).json()["cached"] and route.call_count == 1
        route.mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "content": "unsupported",
                                        "quote": "invented quotation",
                                        "passage_id": passage["id"],
                                    }
                                )
                            }
                        }
                    ]
                },
            )
        )
        body["column_id"] = "results"
        assert c.post(path, json=body).status_code == 502
        assert c.post(path, json=body).status_code == 409
        assert route.call_count == 2


def test_immediate_pdf_before_parsing(tmp_path):
    import pymupdf
    from app.tenancy import data_dir

    with TestClient(app) as c:
        _pid = project(c)
        with closing(connect()) as db:
            upsert_paper(
                db,
                PaperDoc(
                    uid="pending-test", title="Pending PDF", year=2023
                ).model_dump(),
            )
            db.commit()
        folder = data_dir() / "pdfs"
        folder.mkdir(parents=True, exist_ok=True)
        doc = pymupdf.open()
        doc.new_page()
        doc.save(folder / "pending-test.pdf")
        doc.close()
        resources = c.get(
            "/api/resources", params={"scope": "paper", "id": "pending-test"}
        ).json()["items"]
        pdf = next(x for x in resources if x["kind"] == "pdf")
        assert pdf["document_id"] is None
        assert c.get(pdf["url"]).content.startswith(b"%PDF")


def test_additive_migration_is_repeatable_and_preserves_data():
    with closing(connect()) as db:
        upsert_paper(
            db, PaperDoc(uid="legacy", title="Existing", year=2020).model_dump()
        )
        db.commit()
        setup(db)
        setup(db)
        assert (
            db.execute('SELECT title FROM papers WHERE uid="legacy"').fetchone()[0]
            == "Existing"
        )
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_exploration_stays_within_project_sources():
    with TestClient(app) as c:
        one = project(c)
        two = project(c)
        paper(c, one, "2303.04137")
        paper(c, two, "2006.11239")
        nodes = c.get("/api/graph/nodes", params={"project_id": one}).json()["items"]
        assert any(n["paper_uid"] == "2303.04137" for n in nodes)
        assert all(
            n["paper_uid"] != "2006.11239" and n["project_id"] == one for n in nodes
        )
        assert (
            c.get(
                "/api/graph/explore", params={"project_id": one, "seed": "2006.11239"}
            ).status_code
            == 404
        )
        assert not c.get(
            "/api/graph/neighbors/2006.11239", params={"project_id": one}
        ).json()["nodes"]
