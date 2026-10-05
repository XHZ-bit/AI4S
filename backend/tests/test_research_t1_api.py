from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import projects as project_api
from app.db import projects as store
from app.db.sqlite import connect
from app.models.research import GraphNode, GraphQueryResult


def payload():
    return {
        "title": "验证课题",
        "research_question": "哪个候选值得验证？",
        "domain": "image_anomaly_detection",
        "constraints": {"version": 1, "objective": "验证候选路线"},
    }


def make_client(tmp_path, monkeypatch):
    path = str(tmp_path / "api.sqlite3")

    def connection():
        conn = connect(path)
        store.init_research_schema(conn)
        return conn

    monkeypatch.setattr(project_api, "_connect", connection)
    app = FastAPI()
    app.include_router(project_api.router)
    return TestClient(app), connection


def test_project_crud_and_structured_conflict(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    created = client.post("/api/projects", json=payload())
    assert created.status_code == 201
    project = created.json()
    assert (
        client.patch(
            f"/api/projects/{project['id']}",
            json={"expected_version": 1, "title": "新标题"},
        ).status_code
        == 200
    )
    conflict = client.patch(
        f"/api/projects/{project['id']}", json={"expected_version": 1, "title": "覆盖"}
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "version_conflict"
    assert conflict.json()["detail"]["current_version"] == 2


def test_extraction_returns_durable_task_with_test_dispatcher(tmp_path, monkeypatch):
    client, connection = make_client(tmp_path, monkeypatch)
    dispatched = []
    monkeypatch.setattr(project_api, "_task_dispatcher", lambda: dispatched.append)
    project = client.post("/api/projects", json=payload()).json()
    with connection() as conn:
        conn.execute(
            "INSERT INTO papers(uid,title,abstract) VALUES(?,?,?)",
            ("paper-1", "Paper", ""),
        )
        conn.execute(
            "INSERT INTO documents(id,paper_uid,content_hash,coverage) VALUES(?,?,?,?)",
            ("doc-1", "paper-1", "hash", "fulltext"),
        )
        conn.commit()
    linked = client.post(
        f"/api/projects/{project['id']}/papers",
        json={"expected_project_version": 1, "paper_uid": "paper-1", "role": "primary"},
    ).json()
    response = client.post(
        f"/api/projects/{project['id']}/papers/{linked['id']}/extractions",
        json={"expected_project_version": 2, "document_id": "doc-1"},
    )
    assert response.status_code == 202
    task = response.json()
    assert task["status"] == "queued" and dispatched == [task["id"]]
    again = client.post(
        f"/api/projects/{project['id']}/papers/{linked['id']}/extractions",
        json={"expected_project_version": 2, "document_id": "doc-1"},
    )
    assert again.json()["id"] == task["id"]
    assert dispatched == [task["id"]]


def test_unavailable_dispatcher_fails_without_fake_success(tmp_path, monkeypatch):
    client, connection = make_client(tmp_path, monkeypatch)

    def unavailable_dispatcher():
        raise project_api.service.CapabilityUnavailable(
            "task_dispatch", "synthetic dispatcher unavailable"
        )

    monkeypatch.setattr(project_api, "_task_dispatcher", unavailable_dispatcher)
    project = client.post("/api/projects", json=payload()).json()
    with connection() as conn:
        conn.execute(
            "INSERT INTO papers(uid,title,abstract) VALUES(?,?,?)",
            ("paper-1", "Paper", ""),
        )
        conn.execute(
            "INSERT INTO documents(id,paper_uid,content_hash,coverage) VALUES(?,?,?,?)",
            ("doc-1", "paper-1", "hash", "fulltext"),
        )
        conn.commit()
    linked = client.post(
        f"/api/projects/{project['id']}/papers",
        json={"expected_project_version": 1, "paper_uid": "paper-1", "role": "primary"},
    ).json()
    response = client.post(
        f"/api/projects/{project['id']}/papers/{linked['id']}/extractions",
        json={"expected_project_version": 2, "document_id": "doc-1"},
    )
    assert response.status_code == 501
    assert response.json()["detail"]["code"] == "not_implemented"
    with connection() as conn:
        assert (
            conn.execute("SELECT COUNT(*) n FROM research_async_tasks").fetchone()["n"]
            == 0
        )


def test_graph_http_forwards_typed_filters_and_returns_service_result(
    tmp_path, monkeypatch
):
    client, _ = make_client(tmp_path, monkeypatch)
    seen = []

    def query_graph(_conn, query):
        seen.append(query)
        return GraphQueryResult(
            project_id=query.project_id,
            snapshot_id=query.snapshot_id,
            nodes=[GraphNode(id=query.node_ids[0], kind=query.kinds[0], label="命中")],
        )

    monkeypatch.setattr(project_api.service, "query_graph", query_graph)
    response = client.get(
        "/api/projects/project-1/graph",
        params=[
            ("snapshot_id", "snapshot-3"),
            ("node_ids", "method-9"),
            ("kinds", "method"),
            ("limit", "9"),
        ],
    )
    assert response.status_code == 200
    assert response.json()["nodes"][0]["id"] == "method-9"
    assert seen[0].snapshot_id == "snapshot-3" and seen[0].limit == 9
    assert (
        client.get(
            "/api/projects/project-1/graph",
            params={"snapshot_id": "snapshot-3", "limit": 0},
        ).status_code
        == 422
    )
